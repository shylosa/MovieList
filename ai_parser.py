import os
import json
import time
import logging
from typing import Any

from google import genai
from google.genai import types

from config import GEMINI_API_KEY


class GeminiParser:
    def __init__(self):
        if not GEMINI_API_KEY:
            raise ValueError("❌ API Key не знайдено в config.py!")
        self.client = genai.Client(api_key=GEMINI_API_KEY)
        self.model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-3-flash-preview")

    @staticmethod
    def _get_response_schema() -> dict[str, Any]:
        """Повертає жорстку JSON-схему для гарантованої структури відповіді."""
        return {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "original_file": {"type": "STRING", "description": "exact original filename"},
                    "clean_title": {"type": "STRING", "description": "pure original title for TMDB search"},
                    "title_ua": {"type": "STRING", "description": "Ukrainian title"},
                    "title_en": {"type": "STRING", "description": "Original English title"},
                    "year": {"type": "INTEGER", "nullable": True},
                    "plot": {"type": "STRING", "description": "2-3 sentences in Ukrainian"},
                    "genres": {"type": "STRING", "description": "Ukrainian, comma separated"},
                    "cast": {"type": "STRING", "description": "names of 3-5 main actors in Ukrainian"}
                },
                "required": ["original_file", "clean_title", "title_ua", "title_en", "plot", "genres", "cast"]
            }
        }

    @staticmethod
    def _extract_list_from_json(text_response: str) -> list[dict[str, Any]]:
        """Парсить текст у JSON та надійно витягує список об'єктів."""
        try:
            data = json.loads(text_response)
        except json.JSONDecodeError as e:
            logging.error(f"Помилка декодування JSON: {e}")
            return []

        if isinstance(data, list):
            return data

        if isinstance(data, dict):
            for val in data.values():
                if isinstance(val, list):
                    return val

        return []

    def _make_api_request(self, prompt: str) -> list[dict[str, Any]] | None:
        """Виконує один запит до API та обробляє сиру відповідь."""
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=self._get_response_schema(),
                    temperature=0.2  # Низька температура для більшої стабільності парсингу
                )
            )

            text_response = response.text
            logging.debug(f"=== СИРА ВІДПОВІДЬ GEMINI ===\n{text_response}\n=============================")

            return self._extract_list_from_json(text_response)

        except Exception as e:
            logging.warning(f"Помилка парсингу ШІ під час запиту: {e}")
            return None

    def clean_filenames_bulk(self, filenames: list[str], max_retries: int = 3) -> list[dict[str, Any]]:
        """
        Головний метод: керує логікою повторних спроб (Retry logic).
        Когнітивна складність знижена з 18 до ~5.
        """
        if not filenames:
            return []

        filenames_str = "\n".join(f'- {f}' for f in filenames)
        prompt = f"""
        ACT AS A MOVIE/TV DATABASE EXPERT. Process these filenames. Return a JSON LIST of objects.

        CRITICAL RULES:
        1. TOP PRIORITY: The user prefers MODERN (2010+) US/Hollywood/Western cinema and TV shows.
        2. If a title is ambiguous (e.g., "The Rookie", "Женщины"), ALWAYS assume the modern remake or modern TV series, NOT the old 1990s or Soviet versions.
        3. Identify TV shows clearly (if you see S01, S04, Season, WEB-DLRip for a show, treat it as a TV series).
        4. Translate transliterated words logically.

        List of files:
        {filenames_str}
        """

        print(f"   🧠 Пакетне розпізнавання (пріоритет: новинки) для {len(filenames)} файлів...")
        logging.info(f"Відправка запиту до Gemini для {len(filenames)} файлів.")

        for attempt in range(max_retries):
            result = self._make_api_request(prompt)

            # Якщо отримали валідний результат (навіть порожній список), повертаємо його
            if result is not None:
                return result

            # Логіка очікування між спробами (Exponential Backoff)
            if attempt < max_retries - 1:
                sleep_time = 2 ** attempt
                print(f"⏳ Збій мережі/API (Gemini). Повторна спроба через {sleep_time} сек...")
                time.sleep(sleep_time)
            else:
                logging.error(f"Усі {max_retries} спроби доступу до Gemini вичерпано.")
                print(f"❌ Помилка ШІ після {max_retries} спроб.")

        return []