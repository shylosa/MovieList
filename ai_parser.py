import os
import json
import warnings
import logging
from typing import Dict, Any, List
from google import genai
from google.genai import types


class GeminiParser:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("❌ API Key не знайдено!")
        self.client = genai.Client(api_key=api_key)
        self.model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-3-flash-preview")

    def clean_filenames_bulk(self, filenames: List[str]) -> List[Dict[str, Any]]:
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

        try:
            print(f"   🧠 Пакетне розпізнавання (пріоритет: новинки) для {len(filenames)} файлів...")
            logging.info(f"Відправка запиту до Gemini для {len(filenames)} файлів.")

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
            logging.error(f"Помилка парсингу ШІ: {e}")
            print(f"⚠️ Помилка ШІ: {e}")
            return []