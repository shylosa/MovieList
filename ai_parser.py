import os
import json
import time
import logging
from typing import Any

from google import genai
from google.genai import types

from config import GEMINI_API_KEY, GEMINI_MODEL_NAME, GEMINI_FALLBACK_MODEL, cancel_event


class GeminiParser:
    def __init__(self) -> None:  # НОВЕ: додано типізацію повернення
        if not GEMINI_API_KEY:
            raise ValueError("❌ API Key не знайдено в config.py!")
        self.client = genai.Client(api_key=GEMINI_API_KEY)

        # НОВЕ: зберігаємо обидві моделі
        self.primary_model: str = GEMINI_MODEL_NAME
        self.fallback_model: str = GEMINI_FALLBACK_MODEL

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

    # НОВЕ: додано аргумент model_name для гнучкого вибору моделі
    def _make_api_request(self, prompt: str, model_name: str) -> list[dict[str, Any]] | None:
        """Виконує один запит до API та обробляє сиру відповідь."""
        try:
            response = self.client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=self._get_response_schema(),
                    temperature=0.2
                )
            )
            return self._extract_list_from_json(response.text)

        except Exception as e:
            error_msg = str(e)
            # НОВЕ: додано назву моделі у вивід помилок, щоб розуміти, хто саме впав
            if "503" in error_msg or "UNAVAILABLE" in error_msg:
                print(f"❌ Сервери {model_name} зараз перевантажені (Помилка 503).")
            elif "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                print(f"❌ Вичерпано ліміт запитів до {model_name} (Помилка 429).")
            elif "400" in error_msg:
                print(f"❌ Неправильний формат запиту до {model_name} (Помилка 400).")
            else:
                print(f"❌ Невідома помилка ШІ ({model_name}): {error_msg.split('.')[0]}")

            logging.warning(f"Детальний збій Gemini ({model_name}): {repr(e)}")
            return None

    # НОВЕ: зменшив стандартну кількість спроб до 2, оскільки тепер є ще резервна модель
    def clean_filenames_bulk(self, filenames: list[str], max_retries: int = 2) -> list[dict[str, Any]]:
        """Керує логікою повторних спроб (Retry logic) із можливістю зупинки та резервною моделлю."""
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

        CRITICAL RULE FOR "year": 
        The year in your output MUST be within +/- 1 year of the year mentioned in the original filename. (e.g., if the file says 2026, acceptable answers are 2025, 2026, or 2027). 
        NEVER change the year by 2 or more years to fit a known movie. If no exact match is found within the +/- 1 year range, keep the year exactly as it appears in the filename and translate the title literally.

        List of files:
        {filenames_str}
        """

        print(f"   🧠 Пакетне розпізнавання для {len(filenames)} файлів (Основна: {self.primary_model})...")

        # --- СПРОБА 1: ОСНОВНА МОДЕЛЬ ---
        for attempt in range(max_retries):
            if cancel_event.is_set():
                print("🛑 Запит до ШІ перервано користувачем.")
                return []

            # НОВЕ: передаємо основну модель
            result = self._make_api_request(prompt, self.primary_model)

            if result is not None:
                return result

            if attempt < max_retries - 1:
                sleep_time = 2 ** attempt
                print(
                    f"⏳ Повторна спроба {attempt + 2}/{max_retries} через {sleep_time} сек (Натисніть 'Зупинити' для скасування)...")

                for _ in range(int(sleep_time * 2)):
                    if cancel_event.is_set():
                        print("🛑 Очікування перервано.")
                        return []
                    time.sleep(0.5)

        # --- СПРОБА 2: РЕЗЕРВНА МОДЕЛЬ ---
        # НОВЕ: Логіка перемикання на запасний варіант
        print(f"🔄 Основна модель не відповідає. Спроба через резервну: {self.fallback_model}...")
        result = self._make_api_request(prompt, self.fallback_model)

        if result is not None:
            print("✅ Резервна модель успішно впоралася!")
            return result

        # --- ФІНАЛ: ЯКЩО НІЧОГО НЕ ДОПОМОГЛО ---
        # НОВЕ: Виводимо зрозумілу інструкцію замість простого пропускання
        print("\n" + "!" * 50)
        print("⛔ КРИТИЧНО: Жодна з моделей ШІ не змогла відповісти.")
        print("🤖 Порада: Натисніть кнопку 'Моделі ШІ' в меню зліва,")
        print("   щоб перевірити доступні сервіси Google вручну.")
        print("!" * 50 + "\n")

        return []