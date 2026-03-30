import logging
import re
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class TMDBFetcher:
    IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
    DEFAULT_TIMEOUT = (5, 15)  # Константа для таймаутів

    def __init__(self, api_key: str | None = None, posters_dir: str | Path | None = None):
        # Гнучка передача залежностей. Якщо нічого не передати, беремо з config.py
        from config import TMDB_API_KEY, POSTERS_DIR

        self.api_key = api_key or TMDB_API_KEY
        if not self.api_key:
            raise ValueError("Не знайдено TMDB_API_KEY")

        self.base_url = "https://api.themoviedb.org/3"
        self.posters_dir = Path(posters_dir or POSTERS_DIR)

        # Створюємо директорію один раз при старті, використовуючи сучасний pathlib
        self.posters_dir.mkdir(parents=True, exist_ok=True)

        self.session = requests.Session()

        # Налаштування ретраїв: 3 спроби, пауза: 1с, 2с, 4с.
        retries = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )

        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def search_movie(self, title: str, year: str = "", original_filename: str = "") -> dict[str, Any]:
        url = f"{self.base_url}/search/multi"
        params = {
            "api_key": self.api_key,
            "query": title,
            "language": "uk-UA"
        }

        if year:
            params["year"] = year

        try:
            response = self.session.get(url, params=params, timeout=self.DEFAULT_TIMEOUT)
            response.raise_for_status()

            data = response.json()
            if not data.get("results"):
                return {}

            # Беремо перший найкращий збіг
            best_match = data["results"][0]
            tmdb_id = best_match.get("id")
            media_type = best_match.get("media_type", "movie")

            # Додатковий запит за деталями (актори, жанри)
            details_url = f"{self.base_url}/{media_type}/{tmdb_id}"
            details_params = {
                "api_key": self.api_key,
                "language": "uk-UA",
                "append_to_response": "credits"
            }

            details_response = self.session.get(details_url, params=details_params, timeout=self.DEFAULT_TIMEOUT)
            details_response.raise_for_status()
            details_data = details_response.json()

            # Отримуємо "чистий" відформатований словник
            result = self._format_result(details_data, media_type, original_filename)

            # Робимо завантаження окремо, якщо є постер
            if result.get("poster_url"):
                result["local_poster_path"] = self._download_poster(result["poster_url"], original_filename)

            return result

        except requests.exceptions.RequestException as e:
            logging.error(f"Помилка мережі при зверненні до TMDB для '{title}': {e}")
            print(f"⚠️ Мережева помилка (TMDB): {e}")
            return {}

    def get_movie_by_id(self, tmdb_id: str, original_filename: str = "") -> dict[str, Any]:
        """Отримує детальну інформацію про фільм за його TMDB ID."""
        url = f"{self.base_url}/movie/{tmdb_id}"
        params = {
            "api_key": self.api_key,
            "language": "uk-UA",
            "append_to_response": "credits"
        }

        try:
            response = self.session.get(url, params=params, timeout=self.DEFAULT_TIMEOUT)
            response.raise_for_status()

            result = self._format_result(response.json(), "movie", original_filename)

            if result.get("poster_url"):
                result["local_poster_path"] = self._download_poster(result["poster_url"], original_filename)

            return result
        except requests.exceptions.RequestException as e:
            logging.error(f"Помилка завантаження по ID {tmdb_id}: {e}")
            return {}

    def _format_result(self, data: dict[str, Any], media_type: str, original_filename: str) -> dict[str, Any]:
        official_title = data.get("title") if media_type == "movie" else data.get("name")
        original_title = data.get("original_title") if media_type == "movie" else data.get("original_name")

        date_str = data.get("release_date") if media_type == "movie" else data.get("first_air_date")
        year = date_str[:4] if date_str and len(date_str) >= 4 else ""

        genres_list = data.get("genres", [])
        genres = ", ".join([g.get("name", "") for g in genres_list])

        cast_list = data.get("credits", {}).get("cast", [])
        cast = ", ".join([c.get("name", "") for c in cast_list[:5]])

        overview = data.get("overview", "")

        poster_path = data.get("poster_path")
        poster_url = f"{self.IMAGE_BASE_URL}{poster_path}" if poster_path else ""

        return {
            "official_title": official_title or original_filename,
            "original_title": original_title or "",
            "release_date": year,
            "genres": genres,
            "overview": overview,
            "cast": cast,
            "poster_url": poster_url,
            "local_poster_path": ""
        }

    def _download_poster(self, url: str, filename: str) -> str:
        clean_name = Path(filename).stem
        safe_name = re.sub(r'[\\/*?:"<>|.]', "", clean_name).strip()

        # Виправлено: беремо оригінальне ім'я з URL постера, щоб кешування працювало завжди
        if not safe_name:
            safe_name = Path(url).stem

        # Уніфікована робота зі шляхами
        local_path = self.posters_dir / f"{safe_name}.jpg"

        # Якщо постер вже є на диску - не качаємо його повторно
        if local_path.exists():
            return str(local_path)

        try:
            # stream=True гарантує, що ми не заб'ємо пам'ять при завантаженні купи файлів
            response = self.session.get(url, timeout=self.DEFAULT_TIMEOUT, stream=True)
            response.raise_for_status()
            
            with open(local_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    
            return str(local_path)
        except Exception as e:
            logging.error(f"Не вдалося завантажити постер {url}: {e}")
            return ""