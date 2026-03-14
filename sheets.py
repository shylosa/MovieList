import os
import gspread
from google.oauth2.service_account import Credentials
from typing import List


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
            raise ConnectionError(f"❌ Помилка підключення до Google Sheets: {e}")

    def full_sync(self, all_data: List[List[str]]):
        # Остання колонка тепер просто "Poster URL"
        HEADERS = [["File Path", "Title (UA)", "Title (EN)", "Year", "Genre", "Cast", "Plot", "Poster URL"]]

        print(f"🧹 Очищення вкладки '{self.worksheet_name}'...")
        self.sheet.clear()

        if not all_data:
            print("⚠️ Даних для запису немає.")
            return

        formatted_data = []
        for row in all_data:
            # Беремо URL як звичайний текст, ніяких формул!
            poster_url = row[7] if len(row) > 7 and row[7] else ""

            formatted_data.append([
                row[0], row[1], row[2], row[3], row[4], row[5], row[6], poster_url
            ])

        data_to_write = HEADERS + formatted_data

        print(f"📦 Відправка {len(formatted_data)} записів у хмару...")

        end_col = chr(ord('A') + len(HEADERS[0]) - 1)
        end_row = len(data_to_write)
        cell_range = f"A1:{end_col}{end_row}"

        # Відправляємо як RAW текст
        self.sheet.update(range_name=cell_range, values=data_to_write, value_input_option='RAW')
        print("✅ Хмарна таблиця успішно оновлена!")