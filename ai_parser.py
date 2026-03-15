import os
import json
import time
import warnings
import logging
from typing import Dict, Any, List
from google import genai
from google.genai import types

from config import GEMINI_API_KEY  # Беремо ключ з нашого єдиного конфігу


class GeminiParser:
    def __init__(self):
        if not GEMINI_API_KEY:
            raise ValueError("❌ API Key не знайдено в config.py!")
        self.client = genai.Client(api_key=GEMINI_API_KEY)
        self.model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-3-flash-preview")

    def clean_filenames_bulk(self, filenames: List[str], max_retries: int = 3) -> List[Dict[str, Any]]:
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

        Each object MUST have these EXACT keys:
        - "original_file": (string, the exact filename)
        - "clean_title": (string, pure original title for TMDB search)
        - "title_ua": (string, Ukrainian title)
        - "title_en": (string, Original English title)
        - "year": (integer or null)
        - "plot": (string, 2-3 sentences in Ukrainian)
        - "genres": (string, Ukrainian)
        - "cast": (string, names of 3-5 main actors in Ukrainian)

        List of files:
        {filenames_str}
        """

        print(f"   🧠 Пакетне розпізнавання (пріоритет: новинки) для {len(filenames)} файлів...")
        logging.info(f"Відправка запиту до Gemini для {len(filenames)} файлів.")

        # --- МАГІЯ НАДІЙНОСТІ: Цикл повторень з паузою (Exponential Backoff) ---
        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json")
                )

                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    text_response = response.text

                # Записуємо сиру відповідь ШІ у лог (це врятує, якщо щось зламається)
                logging.debug(f"=== СИРА ВІДПОВІДЬ GEMINI ===\n{text_response}\n=============================")

                data = json.loads(text_response)
                return data if isinstance(data, list) else list(data.values())

            except Exception as e:
                logging.warning(f"Помилка парсингу ШІ (спроба {attempt + 1}): {e}")

                # Якщо це ще не остання спроба — чекаємо і пробуємо знову
                if attempt < max_retries - 1:
                    sleep_time = 2 ** attempt  # Пауза зростає: 1 сек, 2 сек...
                    print(f"⏳ Збій мережі/API (Gemini). Повторна спроба через {sleep_time} сек...")
                    time.sleep(sleep_time)
                else:
                    # Якщо всі 3 спроби вичерпано
                    logging.error(f"Усі {max_retries} спроби доступу до Gemini вичерпано. Останній збій: {e}")
                    print(f"❌ Помилка ШІ після {max_retries} спроб: {e}")
                    return []

        return []