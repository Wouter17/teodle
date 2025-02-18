import os
import re
from asyncio import create_task, sleep
from datetime import datetime
from functools import cache

import timeago
from fastapi import FastAPI, Form, WebSocket
from fastapi.responses import JSONResponse
from starlette import status
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

import twitch_userscript
from ai import complete
from blacklist import Blacklist
from config import (BLACKLIST_PATH, CLIPS_PATH, DOWNLOAD_DIR, NO_AUTO_FINISH,
                    RANKS_DIR, UI_CONFIG)
from config_generator import generate_config
from downloader import Downloader
from events import TYPE_TOTAL_VOTES, Subscription, toggle_subscriptions
from summary import get_summary, update_summary
from twitch_monitor import TwitchMonitor
from vote import Vote, VoteState
from ws_route import WSLoopTaskRoute, WSRoute

app = FastAPI()
app.include_router(twitch_userscript.router)
app.mount('/static', StaticFiles(directory='static'), name='static')
app.mount('/ranks', StaticFiles(directory=RANKS_DIR), name='ranks')
app.mount('/download', StaticFiles(directory=DOWNLOAD_DIR), name='download')

tmpl = Jinja2Templates(directory='templates')


vote: Vote

twitch_monitor = TwitchMonitor()
downloader = Downloader()


def set_vote(vote_: Vote) -> None:
    global vote
    vote = vote_
    twitch_monitor.load(vote)
    downloader.load(vote)


set_vote(Vote(CLIPS_PATH))


@app.on_event('startup')
async def startup() -> None:
    create_task(downloader.loop())
    create_task(twitch_monitor.loop())


def default_context(request: Request) -> dict:
    return {
        'request': request,
        'css_mtime': int(os.stat('static/css/style.css').st_mtime),
        'vote': vote
    } | UI_CONFIG


def clips_mtime() -> str:
    return timeago.format(datetime.fromtimestamp(CLIPS_PATH.stat().st_mtime),
                          datetime.now())


@cache
def get_template_filename(name: str) -> str:
    streamer_filename = f'{name}.{UI_CONFIG["STREAMER_NAME"].lower()}.jinja2'

    if os.path.exists(f'templates/{streamer_filename}'):
        return streamer_filename

    generic_filename = f'{name}.jinja2'
    return generic_filename


@app.get('/')
async def index(request: Request):
    ctx = default_context(request)

    if vote.state == VoteState.IDLE:
        return tmpl.TemplateResponse(get_template_filename('idle'), ctx | {
            'config_mtime': clips_mtime(),
            'downloader': downloader
        })

    elif vote.state == VoteState.VOTING:
        return tmpl.TemplateResponse(get_template_filename('voting'), ctx)

    elif vote.state == VoteState.RESULTS:
        return tmpl.TemplateResponse(get_template_filename('results'), ctx | {
            'summary': get_summary() if not vote.has_next_clip else None
        })

    raise Exception('Not implemented vote state')


INDEX_REDIRECT = RedirectResponse('/', status_code=status.HTTP_302_FOUND)


@app.post('/cast_vote')
async def cast_vote(clip_idx: int = Form(), rank: str = Form()):
    # ensure the client state
    if vote.clip_idx == clip_idx and vote.state in {VoteState.VOTING}:
        vote.cast_streamer_vote(rank)
        await vote.end_clip()

        if not vote.has_next_clip:
            update_summary(vote)

    return INDEX_REDIRECT


@app.post('/next_clip')
async def next_clip(clip_idx: int = Form(), testing: bool = Form(False)):
    global vote

    # ensure the client state
    if vote.clip_idx == clip_idx and vote.state in {VoteState.IDLE, VoteState.RESULTS}:
        if vote.has_next_clip:

            # start of the game
            if vote.clip_idx == -1:
                toggle_subscriptions(enabled=not testing)

            async with twitch_monitor.lock:
                if not twitch_monitor.run_loop.is_set():
                    await twitch_monitor.connect()

            vote.begin_next_clip()

        else:
            async with twitch_monitor.lock:
                await twitch_monitor.disconnect()

            set_vote(Vote(CLIPS_PATH))

    return INDEX_REDIRECT


@app.get('/congratulate')
async def congratulate() -> JSONResponse:
    # ensure the client state
    if not vote.has_next_clip and vote.state == VoteState.RESULTS:
        system = \
            "You write an insanely creative congratulations for the given username - it's a reward for winning the game. " \
            "The congratulations message must rhyme. " \
            "You must always incorporate the username in an insanely creative way. " \
            "You write about 3-4 sentences and use a newline separator. " \
            "Your message ends with a simple complementary ASCII art."

        content = await complete(system, vote.result.top_users[0][1].username, temperature=0.8, max_tokens=512)

        return JSONResponse({
            'content': content
        })

    raise HTTPException(500, 'Bad state')


@app.get('/config')
async def get_config(request: Request):
    if vote.state != VoteState.IDLE:
        return INDEX_REDIRECT

    with open(CLIPS_PATH) as f:
        config = f.read()

    with open(BLACKLIST_PATH) as f:
        blacklist = f.read()

    return tmpl.TemplateResponse('config.jinja2', default_context(request) | {
        'config': config,
        'blacklist': blacklist,
    })


@app.post('/config')
async def post_config(config: str = Form(), blacklist: str = Form(default='')):
    global vote

    if vote.state != VoteState.IDLE:
        raise HTTPException(500, 'Invalid state: voting in progress')

    config = config.strip()
    blacklist = blacklist.strip()

    try:
        # parse the configs to ensure they are valid
        new_blacklist = Blacklist(blacklist)
        new_vote = Vote(config, blacklist=new_blacklist)

        assert len(new_vote.clips), 'No clips found'
    except Exception as e:
        raise HTTPException(500, str(e))

    for path, content in [(CLIPS_PATH, config), (BLACKLIST_PATH, blacklist)]:
        with open(path, 'r+') as f:
            current = f.read().strip()

            # only update the file if the content has changed
            if current.replace('\r', '') != content.replace('\r', ''):
                print(f'[INFO] Saving config: {path}')
                f.seek(0)
                f.write(content)
                f.truncate()

    set_vote(new_vote)

    return INDEX_REDIRECT


@app.post('/generate')
async def generate(input: str = Form()) -> JSONResponse:
    if vote.state != VoteState.IDLE:
        return JSONResponse({}, status_code=400)

    response = {
        'body': await generate_config(input),
    }

    return JSONResponse(response)


@app.websocket('/ws')
class WS(WSLoopTaskRoute):
    async def on_connect(self) -> None:
        await self.start()

    async def loop(self) -> None:
        with Subscription(TYPE_TOTAL_VOTES) as s_total:
            while self.connected:
                total: int = await s_total.wait()
                await self.ws.send_json({'total': total})
                await sleep(0.2)


@app.websocket('/ws/finish')
class WSFinish(WSRoute):
    def __init__(self, ws: WebSocket):
        super().__init__(ws)
        self.clip_idx = vote.clip_idx
        self.reject = vote.has_next_clip

    async def on_connect(self) -> None:
        print('[WSFinish] Connection established')

    async def on_disconnect(self) -> None:
        if NO_AUTO_FINISH:
            return

        print('[WSFinish] Finishing the game')
        await next_clip(self.clip_idx)
