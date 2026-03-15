import sqlite3
import os
from typing import List, Dict, Any, Set


class LocalMovieDB:
    def __init__(self, db_name="movies.db"):
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        self._create_table()

        # Автоматично створюємо папку для постерів
        os.makedirs("posters", exist_ok=True)

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

    def get_all_filenames(self) -> Set[str]:
        self.cursor.execute("SELECT filename FROM movies")
        return {row[0] for row in self.cursor.fetchall()}

    def get_all_movies_for_export(self) -> List[List[str]]:
        self.cursor.execute("SELECT * FROM movies")
        return [list(row) for row in self.cursor.fetchall()]

    def save_movie(self, filename: str, data: Dict[str, Any], raw_fallback: str = ""):
        self.cursor.execute('''
            INSERT OR REPLACE INTO movies 
            (filename, title_ua, title_en, year, genres, cast, plot, poster_url, local_poster_path)
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

    def remove_missing_files(self, actual_disk_files: List[str]):
        db_files = self.get_all_filenames()
        zombies = db_files - set(actual_files for actual_files in actual_disk_files)

        if zombies:
            print(f"🗑️ Видаляємо {len(zombies)} неіснуючих файлів з локальної БД...")
            self.cursor.executemany(
                "DELETE FROM movies WHERE filename = ?",
                [(z,) for z in zombies]
            )
            self.conn.commit()
            print("✅ Локальну базу очищено.")

    def clean_orphan_posters(self):
        print("🧹 Перевірка та очищення старих постерів...")

        # Отримуємо всі дійсні шляхи до постерів з БД (завантажені автоматично)
        self.cursor.execute("SELECT local_poster_path FROM movies WHERE local_poster_path IS NOT NULL")
        valid_db_posters = {os.path.normpath(row[0]) for row in self.cursor.fetchall() if row[0]}

        # Захищаємо "ручні" постери (які ти міг додати сам під назву файлу)
        self.cursor.execute("SELECT filename FROM movies")
        valid_manual_posters = {
            os.path.normpath(os.path.join("posters", f"{os.path.splitext(row[0])[0]}.jpg"))
            for row in self.cursor.fetchall()
        }

        # Об'єднуємо всі легальні постери в один набір
        all_valid = valid_db_posters.union(valid_manual_posters)

        posters_dir = "posters"
        if not os.path.exists(posters_dir):
            return

        deleted_count = 0
        # Проходимося по всіх файлах у папці posters
        for file in os.listdir(posters_dir):
            file_path = os.path.normpath(os.path.join(posters_dir, file))
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