import os
from dotenv import load_dotenv

load_dotenv()

APP_VERSION = "1.2.5"

MEDIA_FOLDER_PATH = os.getenv("MEDIA_FOLDER_PATH", "")
EXCLUDE_FOLDERS_RAW = os.getenv("EXCLUDE_FOLDERS", "")
EXCLUDE_LIST = [item.strip() for item in EXCLUDE_FOLDERS_RAW.split(",") if item.strip()]

TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")