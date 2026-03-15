import os
from dotenv import load_dotenv

# Завантажуємо .env файл лише один раз для всього проєкту
load_dotenv()

def get_version():
    try:
        with open("version.txt", "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "1.0.0"

APP_VERSION = get_version()

# Шляхи та папки
MEDIA_FOLDER_PATH = os.getenv("MEDIA_FOLDER_PATH", "")
EXCLUDE_FOLDERS_RAW = os.getenv("EXCLUDE_FOLDERS", "")
EXCLUDE_LIST = [item.strip() for item in EXCLUDE_FOLDERS_RAW.split(",") if item.strip()]

# API ключі (тепер інші модулі можуть брати їх звідси, а не смикати os.getenv)
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")