from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
STATIC_DIR = BASE_DIR / 'app' / 'static'
TEMPLATES_DIR = BASE_DIR / 'app' / 'templates'
FILES_ROOT = STATIC_DIR / 'files'
LOGS_DIR = BASE_DIR / 'logs'
