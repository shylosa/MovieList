import sqlite3
import os
from typing import Any

# Імпортуємо централізовані налаштування
from config import DB_PATH, POSTERS_DIR


class LocalMovieDB:
    def __init__(self, db_path=DB_PATH):
        # Включаємо check_same_thread=False для безпечної роботи в багатопотоковому GUI
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self._create_table()

        # Автоматично створюємо папку для постерів з конфігу
        os.makedirs(POSTERS_DIR, exist_ok=True)

    def __del__(self):
        """Гарантує закриття з'єднання з БД при завершенні роботи з класом."""
        try:
            self.conn.close()
        except Exception:
            pass

    def _create_table(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS movies (
                filename TEXT PRIMARY KEY,
                title_ua TEXT,
                title_en TEXT,
                year TEXT,
                genres TEXT,
                cast TEXT,
                plot TEXT,
                poster_url TEXT,
                local_poster_path TEXT
            )
        ''')
        self.conn.commit()

    def get_all_filenames(self) -> set[str]:
        self.cursor.execute("SELECT filename FROM movies")
        return {row[0] for row in self.cursor.fetchall()}

    def get_all_movies_for_export(self) -> list[list[Any]]:
        self.cursor.execute("SELECT * FROM movies")
        return [list(row) for row in self.cursor.fetchall()]

    def save_movie(self, filename: str, data: dict[str, Any], raw_fallback: str = ""):
        self.cursor.execute('''
            INSERT OR REPLACE INTO movies 
            (filename, title_ua, title_en, year, genres, "cast", plot, poster_url, local_poster_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            filename,
            data.get("official_title", raw_fallback),
            data.get("original_title", ""),
            data.get("release_date", ""),
            data.get("genres", ""),
            data.get("cast", ""),
            data.get("overview", ""),
            data.get("poster_url", ""),
            data.get("local_poster_path", "")
        ))
        self.conn.commit()

    def remove_missing_files(self, actual_disk_files: list[str]):
        db_files = self.get_all_filenames()
        zombies = db_files - set(actual_disk_files)

        if zombies:
            print(f"🗑️ Видаляємо {len(zombies)} неіснуючих файлів з локальної БД...")
            # Використовуємо генератор для економії пам'яті
            self.cursor.executemany(
                "DELETE FROM movies WHERE filename = ?",
                ((z,) for z in zombies)
            )
            self.conn.commit()
            print("✅ Локальну базу очищено.")

    def clean_orphan_posters(self):
        print("🧹 Перевірка та очищення старих постерів...")

        # 🟡 Надійність: Використовуємо abspath для точного порівняння шляхів
        self.cursor.execute("SELECT local_poster_path FROM movies WHERE local_poster_path IS NOT NULL AND local_poster_path != ''")
        valid_db_posters = {os.path.abspath(row[0]) for row in self.cursor.fetchall() if row[0]}

        self.cursor.execute("SELECT filename FROM movies")
        valid_manual_posters = {
            os.path.abspath(os.path.join(POSTERS_DIR, f"{os.path.splitext(row[0])[0]}.jpg"))
            for row in self.cursor.fetchall()
        }

        all_valid = valid_db_posters.union(valid_manual_posters)

        if not os.path.exists(POSTERS_DIR):
            return

        deleted_count = 0
        for file in os.listdir(POSTERS_DIR):
            file_path = os.path.abspath(os.path.join(POSTERS_DIR, file))
            if os.path.isfile(file_path) and file_path not in all_valid:
                try:
                    os.remove(file_path)
                    deleted_count += 1
                except Exception as e:
                    print(f"⚠️ Не вдалося видалити {file}: {e}")

        if deleted_count > 0:
            print(f"✅ Видалено {deleted_count} неактуальних постерів (хвостів).")
        else:
            print("✨ Папка з постерами в ідеальному стані (хвостів немає).")