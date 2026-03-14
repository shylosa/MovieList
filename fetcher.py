import os
import requests
from typing import Dict, Any, Optional


class TMDBFetcher:
    def __init__(self):
        self.api_key = os.getenv("TMDB_API_KEY")
        if not self.api_key:
            raise ValueError("❌ TMDB_API_KEY не знайдено у .env!")

        self.base_url = "https://api.themoviedb.org/3"
        self.image_base_url = "https://image.tmdb.org/t/p/w500"
        self.posters_dir = "posters"
        os.makedirs(self.posters_dir, exist_ok=True)

    def _download_poster(self, poster_url: str, filename: str) -> str:
        if not poster_url:
            return ""
        base_name = os.path.splitext(filename)[0]
        safe_name = f"{base_name}.jpg"
        local_path = os.path.join(self.posters_dir, safe_name)
        if os.path.exists(local_path):
            return local_path
        try:
            response = requests.get(poster_url, stream=True, timeout=10)
            if response.status_code == 200:
                with open(local_path, 'wb') as f:
                    for chunk in response.iter_content(1024):
                        f.write(chunk)
                return local_path
        except Exception as e:
            print(f"\n⚠️ Помилка завантаження постера: {e}")
        return ""

    def search_movie(self, title: str, year: Optional[str] = None, original_filename: str = "") -> Dict[str, Any]:
        # Використовуємо мульти-пошук (фільми + серіали)
        url = f"{self.base_url}/search/multi"
        params = {"api_key": self.api_key, "query": title, "language": "uk-UA"}

        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            for item in data.get("results", []):
                media_type = item.get("media_type")
                # Беремо перший знайдений фільм або серіал (ігноруємо акторів)
                if media_type in ["movie", "tv"]:
                    item_id = item["id"]

                    # Запит до деталей (окремо для фільму і серіалу)
                    details_url = f"{self.base_url}/{media_type}/{item_id}"
                    details_params = {"api_key": self.api_key, "language": "uk-UA", "append_to_response": "credits"}
                    details_response = requests.get(details_url, params=details_params, timeout=10)
                    details_response.raise_for_status()
                    details = details_response.json()

                    # Правильні ключі для серіалів та фільмів
                    title_key = "title" if media_type == "movie" else "name"
                    orig_title_key = "original_title" if media_type == "movie" else "original_name"
                    date_key = "release_date" if media_type == "movie" else "first_air_date"

                    genres = ", ".join([g["name"] for g in details.get("genres", [])])
                    overview_text = details.get("overview", "").strip() or "Опис відсутній"
                    cast_list = details.get("credits", {}).get("cast", [])[:5]
                    cast_str = ", ".join([actor["name"] for actor in cast_list]) if cast_list else "Дані відсутні"

                    poster_path = details.get("poster_path")
                    poster_url = f"{self.image_base_url}{poster_path}" if poster_path else ""
                    local_poster_path = self._download_poster(poster_url, original_filename) if poster_url else ""

                    return {
                        "official_title": details.get(title_key, ""),
                        "original_title": details.get(orig_title_key, ""),
                        "release_date": details.get(date_key, "")[:4] if details.get(date_key) else "",
                        "genres": genres if genres else "Не вказано",
                        "cast": cast_str,
                        "overview": overview_text,
                        "poster_url": poster_url,
                        "local_poster_path": local_poster_path
                    }
        except Exception as e:
            print(f"\n⚠️ Помилка доступу до TMDB: {e}")
        return {}