import os
import time
import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError
from typing import List
from gspread.utils import ValueInputOption

class SheetConnectionError(Exception):
    """Кастомний клас помилки для роботи з Google Sheets."""
    pass

class GoogleSheetSync:
    def __init__(self):
        self.credentials_file = 'credentials.json'
        self.sheet_url = os.getenv("GOOGLE_SHEET_URL")
        self.worksheet_name = os.getenv("GOOGLE_SHEET_WORKSHEET_NAME", "base")

        if not self.sheet_url:
            raise ValueError("❌ GOOGLE_SHEET_URL не знайдено у .env файлі!")

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        try:
            creds = Credentials.from_service_account_file(self.credentials_file, scopes=scopes)
            self.client = gspread.authorize(creds)
            self.sheet = self.client.open_by_url(self.sheet_url).worksheet(self.worksheet_name)
        except Exception as e:
            # Викидаємо кастомну помилку
            raise SheetConnectionError(f"❌ Помилка підключення до Google Sheets: {e}")

    def _col_letter(self, n: int) -> str:
        """
        Конвертує номер колонки (1-based) у літеру Excel/Sheets.
        Наприклад: 1→A, 26→Z, 27→AA
        """
        result = ""
        while n:
            n, rem = divmod(n - 1, 26)
            result = chr(65 + rem) + result
        return result

    def _retry(self, func, attempts: int = 3, delay: float = 5.0):
        """Обгортка для безпечного виконання запитів до API Гугла."""
        for attempt in range(attempts):
            try:
                return func()
            except APIError as e:
                if attempt == attempts - 1:
                    raise # Якщо це остання спроба, прокидаємо помилку далі
                print(f"⚠️ API Гугла перевантажено, повторна спроба через {delay} сек... ({e})")
                time.sleep(delay)

    def full_sync(self, all_data: List[List[str]]):
        HEADERS = [["File Path", "Title (UA)", "Title (EN)", "Year", "Genre", "Cast", "Plot", "Poster URL"]]

        print(f"🧹 Очищення вкладки '{self.worksheet_name}'...")
        # Використовуємо _retry для очищення
        self._retry(self.sheet.clear)

        if not all_data:
            print("⚠️ Даних для запису немає.")
            return

        # Генератор списку: швидший і компактніший запис
        formatted_data = [
            [
                row[0], row[1], row[2], row[3], row[4], row[5], row[6],
                row[7] if len(row) > 7 and row[7] else ""
            ]
            for row in all_data
        ]

        data_to_write = HEADERS + formatted_data

        print(f"📦 Відправка {len(formatted_data)} записів у хмару...")

        # Використовуємо надійний метод обчислення колонки
        end_col = self._col_letter(len(HEADERS[0]))
        end_row = len(data_to_write)
        cell_range = f"A1:{end_col}{end_row}"

        # Використовуємо _retry для оновлення (через лямбду, щоб передати аргументи)
        self._retry(
            lambda: self.sheet.update(
                range_name=cell_range,
                values=data_to_write,
                value_input_option=ValueInputOption.raw
            )
        )
        print("✅ Хмарна таблиця успішно оновлена!")