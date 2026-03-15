import os
import requests
import logging
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from config import TMDB_API_KEY  # Беремо ключ з конфігу


class TMDBFetcher:
    def __init__(self):
        self.api_key = TMDB_API_KEY
        if not self.api_key:
            raise ValueError("Не знайдено TMDB_API_KEY")

        self.base_url = "https://api.themoviedb.org/3"

        # --- МАГІЯ НАДІЙНОСТІ: Налаштовуємо сесію з авто-повторами ---
        self.session = requests.Session()

        # Налаштування: 3 спроби, пауза збільшується: 1с, 2с, 4с.
        # Спрацьовує при помилках: 429 (Забагато запитів), 500, 502, 503, 504 (Впав сервер)
        retries = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )

        # Чіпляємо адаптер до нашої HTTP сесії
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
            # Замість requests.get тепер використовуємо нашу "броньовану" сесію
            # Timeout (5, 15): 5 сек на з'єднання, 15 сек на отримання відповіді
            response = self.session.get(url, params=params, timeout=(5, 15))
            response.raise_for_status()  # Кидає виняток, якщо статус 4xx (наприклад 401 Unauthorized)

            data = response.json()
            if not data.get("results"):
                return {}

            # ... далі твій стандартний код розбору результатів TMDB ...
            # (Я залишаю цю частину без змін, просто скопіюй свій старий блок обробки data)

            best_match = data["results"][0]
            tmdb_id = best_match.get("id")
            media_type = best_match.get("media_type", "movie")

            # Додатковий запит за деталями (теж використовуємо self.session!)
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

        # Обробляємо будь-які мережеві помилки (якщо всі 3 спроби провалилися)
        except requests.exceptions.RequestException as e:
            logging.error(f"Помилка мережі при зверненні до TMDB для '{title}': {e}")
            print(f"⚠️ Мережева помилка (TMDB): {e}")
            return {}

    def _format_result(self, data: dict, media_type: str, original_filename: str) -> dict:
        # ... твій код форматування ... (без змін)
        pass