import os
import requests
import logging
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from config import TMDB_API_KEY


class TMDBFetcher:
    def __init__(self):
        self.api_key = TMDB_API_KEY
        if not self.api_key:
            raise ValueError("Не знайдено TMDB_API_KEY")

        self.base_url = "https://api.themoviedb.org/3"

        # --- МАГІЯ НАДІЙНОСТІ: Налаштовуємо сесію з авто-повторами ---
        self.session = requests.Session()

        # Налаштування: 3 спроби, пауза: 1с, 2с, 4с.
        retries = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )

        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def search_movie(self, title: str, year: str = "", original_filename: str = "") -> dict:
        url = f"{self.base_url}/search/multi"
        params = {
            "api_key": self.api_key,
            "query": title,
            "language": "uk-UA"
        }

        try:
            response = self.session.get(url, params=params, timeout=(5, 15))
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

            details_response = self.session.get(details_url, params=details_params, timeout=(5, 15))
            details_response.raise_for_status()
            details_data = details_response.json()

            return self._format_result(details_data, media_type, original_filename)

        except requests.exceptions.RequestException as e:
            logging.error(f"Помилка мережі при зверненні до TMDB для '{title}': {e}")
            print(f"⚠️ Мережева помилка (TMDB): {e}")
            return {}

    def _format_result(self, data: dict, media_type: str, original_filename: str) -> dict:
        # Витягуємо назви (для фільмів і серіалів ключі відрізняються)
        official_title = data.get("title") if media_type == "movie" else data.get("name")
        original_title = data.get("original_title") if media_type == "movie" else data.get("original_name")

        # Витягуємо рік
        date_str = data.get("release_date") if media_type == "movie" else data.get("first_air_date")
        year = date_str[:4] if date_str and len(date_str) >= 4 else ""

        # Витягуємо жанри
        genres_list = data.get("genres", [])
        genres = ", ".join([g.get("name", "") for g in genres_list])

        # Витягуємо акторів (беремо перших 5)
        cast_list = data.get("credits", {}).get("cast", [])
        cast = ", ".join([c.get("name", "") for c in cast_list[:5]])

        # Опис
        overview = data.get("overview", "")

        # Завантажуємо постер
        poster_url = ""
        local_poster_path = ""
        poster_path = data.get("poster_path")

        if poster_path:
            poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
            local_poster_path = self._download_poster(poster_url, original_filename)

        return {
            "official_title": official_title or original_filename,
            "original_title": original_title or "",
            "release_date": year,
            "genres": genres,
            "overview": overview,
            "cast": cast,
            "poster_url": poster_url,
            "local_poster_path": local_poster_path
        }

    def _download_poster(self, url: str, filename: str) -> str:
        os.makedirs("posters", exist_ok=True)
        safe_name = os.path.splitext(filename)[0]
        local_path = os.path.join("posters", f"{safe_name}.jpg")

        # Якщо постер вже є на диску - не качаємо його повторно
        if os.path.exists(local_path):
            return local_path

        try:
            response = self.session.get(url, timeout=(5, 15))
            response.raise_for_status()
            with open(local_path, "wb") as f:
                f.write(response.content)
            return local_path
        except Exception as e:
            logging.error(f"Не вдалося завантажити постер {url}: {e}")
            return ""