import os
from pathlib import Path

import openai

for require in ['yt-dlp', 'ffmpeg']:
    assert any(os.path.exists(os.path.join(p, require))
               for p in os.environ['PATH'].split(os.pathsep)), \
        'You are missing the required dependency: ' + require

MAX_STARS = 2
# (if applicable)
# don't forget to adjust the easter egg values in results.jinja2

# maximum number of concurrent connections per userscript user
MAX_USERSCRIPT_SLOTS = 3

RANK_FILE_CONVERT_EXT = {'.png'}
RANK_FILE_EXT = '.webp'

TTV_TOKEN = os.environ['TTV_TOKEN']
TTV_USERNAME = os.environ['TTV_USERNAME']
TTV_CHANNEL = os.environ['TTV_CHANNEL']

VOTE_WHITELIST = set(u.strip() for u in os.getenv('VOTE_WHITELIST', '').lower().split(','))
NO_MONITOR = os.getenv('NO_MONITOR') == '1'
NO_DOWNLOAD = os.getenv('NO_DOWNLOAD') == '1'
NO_AUTO_FINISH = os.getenv('NO_AUTO_FINISH') == '1'
DUMMY_VOTES = int(os.getenv('DUMMY_VOTES', '0'))

DATA_DIR = Path('data')
DATA_DIR.mkdir(exist_ok=True)

CLIPS_PATH = DATA_DIR / Path('clips.txt')
BLACKLIST_PATH = DATA_DIR / Path('blacklist.txt')

SUMMARY_MIN_VOTES = int(os.getenv('SUMMARY_MIN_VOTES', '5'))
SUMMARY_PATH = DATA_DIR / Path('summary.json')

# ensure proper file permissions
for file in [CLIPS_PATH, BLACKLIST_PATH, SUMMARY_PATH]:
    with open(file, 'a+') as f:
        pass

CACHE_DIR = DATA_DIR / Path('cache')
CACHE_DIR.mkdir(exist_ok=True)

RANKS_DIR = DATA_DIR / Path('ranks')
RANKS_DIR.mkdir(exist_ok=True)

DOWNLOAD_DIR = DATA_DIR / Path('download')
DOWNLOAD_DIR.mkdir(exist_ok=True)

BOARDS_DIR = DATA_DIR / Path('boards')
BOARDS_DIR.mkdir(exist_ok=True)

# ensure proper directory permissions
for dir in [CACHE_DIR, DOWNLOAD_DIR, BOARDS_DIR]:
    assert os.access(dir, os.W_OK | os.X_OK), f'Permission denied: {dir}'

OPENAI_KEY = os.getenv('OPENAI_KEY', None)

if OPENAI_KEY:
    openai.api_key = OPENAI_KEY

N_TOP_USERS = 5


UI_CONFIG = {
    'APP_NAME': 'Teodle',
    'APP_TITLE': 'Teodle',
    'HEAD_PREFIX': 'teo',
    'STREAMER_NAME': 'Teo',
    'STREAMER_ICON': 'teo.png',
    'STREAMER_GOOD_ICON': 'teo-gold.png',  # optional
    'STREAMER_BAD_ICON': 'laugh.png',  # optional
    'FIRST_PLACE_ICON': 'jam.gif',
    'MVP_ICON': 'chad.webp',
}

# override UI_CONFIG with environment variables
for key, default in UI_CONFIG.items():
    if (val := os.getenv(key, None)) is not None:
        UI_CONFIG[key] = val
