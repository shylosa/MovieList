import os
import argparse
import warnings
import re
import logging
from datetime import datetime
from dotenv import load_dotenv

from scanner import VideoScanner
from title_parser import MovieParser
from fetcher import TMDBFetcher
from ai_parser import GeminiParser
from database import LocalMovieDB
from sheets import GoogleSheetSync

# Глушимо попередження
warnings.simplefilter(action='ignore', category=FutureWarning)
warnings.simplefilter(action='ignore', category=UserWarning)

load_dotenv()


# --- Читаємо версію ---
def get_version():
    try:
        with open("version.txt", "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "1.0.0"


APP_VERSION = get_version()

# --- Налаштування Логування ---
os.makedirs("logs", exist_ok=True)
log_filename = os.path.join("logs", f"movielist_{datetime.now().strftime('%Y-%m-%d')}.log")
logging.basicConfig(
    filename=log_filename,
    level=logging.DEBUG,  # Пишемо в лог абсолютно все (навіть те, що не виводимо на екран)
    format="%(asctime)s [%(levelname)s] %(module)s: %(message)s",
    encoding="utf-8"
)


def has_cyrillic(text: str) -> bool:
    return bool(re.search('[а-яА-ЯіїєґІЇЄҐ]', text))


def run_scan():
    logging.info(f"=== Запуск сканування (v{APP_VERSION}) ===")
    folder_path = os.getenv("MEDIA_FOLDER_PATH")
    exclude_raw = os.getenv("EXCLUDE_FOLDERS", "")
    exclude_list = [item.strip() for item in exclude_raw.split(",") if item.strip()]

    print(f"🚀 Ініціалізація MovieList v{APP_VERSION}...")
    db_local = LocalMovieDB()
    scanner = VideoScanner(folder_path, exclude_folders=exclude_list)
    parser = MovieParser()

    try:
        fetcher = TMDBFetcher()
        ai = GeminiParser()
    except Exception as e:
        logging.critical(f"Помилка ініціалізації API: {e}")
        print(f"❌ Помилка ініціалізації API: {e}")
        return

    print(f"📁 Сканування директорії: {folder_path}...")
    actual_disk_files = [f.name for f in scanner.scan()]

    # 1. Видаляємо з бази записи про фільми, яких вже немає на диску
    db_local.remove_missing_files(actual_disk_files)

    # 2. ОДРАЗУ прибираємо їхні старі постери та будь-яке інше сміття
    db_local.clean_orphan_posters()

    existing_in_db = db_local.get_all_filenames()
    new_files = [f for f in actual_disk_files if f not in existing_in_db]

    if not new_files:
        logging.info("Нових файлів не знайдено.")
        print("🤷‍♂️ Нових файлів не знайдено. Локальна база актуальна.")
        return

    logging.info(f"Знайдено {len(new_files)} нових файлів для обробки.")
    print(f"\n🔍 Знайдено {len(new_files)} нових файлів для обробки.")
    ai_queue = []

    # --- ФАЗА 1: Швидкий пошук у TMDB ---
    print("\n[ФАЗА 1: Класичний пошук]")
    for filename in new_files:
        parsed = parser.parse_filename(filename)
        title, year = parsed.get('title'), parsed.get('year')

        if not title:
            ai_queue.append(filename)
            continue

        print(f"[{filename}] 🔍 TMDB...", end=" ")
        movie_info = fetcher.search_movie(title, year, original_filename=filename)

        if movie_info and movie_info.get("overview") != "Опис відсутній":
            found_year = movie_info.get("release_date", "")
            official_title = movie_info.get("official_title", "")

            if found_year and found_year.isdigit() and int(found_year) < 2005 and str(found_year) not in filename:
                print(f"👴 Надто старий фільм. До ШІ.")
                ai_queue.append(filename)
            elif not has_cyrillic(official_title):
                print("🇺🇦 Немає UA-назви. До ШІ.")
                ai_queue.append(filename)
            else:
                print("✅ Знайдено!")
                db_local.save_movie(filename, movie_info)
                logging.info(f"Успішно додано з TMDB: {filename}")
        else:
            print("📝 Відкладено для ШІ.")
            ai_queue.append(filename)

    # --- ФАЗА 2 та 3: Очищення через ШІ та гібридний пошук ---
    if ai_queue:
        print(f"\n[ФАЗА 2: Глибокий аналіз {len(ai_queue)} складних назв через ШІ]")
        ai_results = ai.clean_filenames_bulk(ai_queue)

        print("\n[ФАЗА 3: Гібридне злиття даних (TMDB + ШІ)]")
        for filename in ai_queue:
            ai_data = next((item for item in ai_results if item.get("original_file") == filename), None)

            if ai_data and ai_data.get("clean_title"):
                clean_title = ai_data.get("clean_title")
                clean_year = str(ai_data.get("year", "")) if ai_data.get("year") else ""

                print(f"[{filename}] ✨ ШІ: '{clean_title}'. TMDB...", end=" ")
                movie_info = fetcher.search_movie(clean_title, clean_year, original_filename=filename)

                if movie_info:
                    merged_info = movie_info.copy()
                    if not has_cyrillic(merged_info.get("official_title", "")) and ai_data.get("title_ua"):
                        merged_info["official_title"] = ai_data.get("title_ua")
                    if not merged_info.get("overview") or merged_info.get("overview") == "Опис відсутній":
                        merged_info["overview"] = ai_data.get("plot", "Опис відсутній")
                    if not merged_info.get("cast") or merged_info.get("cast") == "Дані відсутні" or merged_info.get(
                            "cast") == "":
                        merged_info["cast"] = ai_data.get("cast", "Дані відсутні")
                    if not merged_info.get("genres") or merged_info.get("genres") == "":
                        merged_info["genres"] = ai_data.get("genres", "Не вказано")

                    print("✅ Гібрид збережено!")
                    db_local.save_movie(filename, merged_info)
                    logging.info(f"Гібридне збереження: {filename} -> {merged_info.get('official_title')}")
                else:
                    print("⚠️ TMDB не знайшов. 100% даних ШІ.")
                    fallback_info = {
                        "official_title": ai_data.get("title_ua", clean_title),
                        "original_title": ai_data.get("title_en", ""),
                        "release_date": clean_year,
                        "genres": ai_data.get("genres", "Не вказано"),
                        "overview": ai_data.get("plot", "Опис відсутній"),
                        "cast": ai_data.get("cast", "Дані відсутні"),
                        "poster_url": "",
                        "local_poster_path": ""
                    }
                    db_local.save_movie(filename, fallback_info)
                    logging.warning(f"Збережено тільки за даними ШІ: {filename}")
            else:
                print(f"[{filename}] ❌ Пропущено. Кешуємо пустим.")
                db_local.save_movie(filename, {}, raw_fallback=filename)
                logging.error(f"ШІ не розпізнав файл: {filename}")

    print("\n✅ Локальне сканування завершено!")
    logging.info("=== Сканування завершено ===")


def run_sync():
    print("🚀 Підготовка до синхронізації з хмарою...")
    db_local = LocalMovieDB()
    all_movies = db_local.get_all_movies_for_export()

    if not all_movies:
        print("⚠️ Локальна база порожня. Нічого відправляти.")
        return

    try:
        sheets_sync = GoogleSheetSync()
        sheets_sync.full_sync(all_movies)
        logging.info("Синхронізація з Google Sheets пройшла успішно.")
    except Exception as e:
        print(f"❌ Помилка синхронізації: {e}")
        logging.error(f"Помилка Google Sheets: {e}")


def main():
    parser = argparse.ArgumentParser(description=f"MovieList v{APP_VERSION}")
    parser.add_argument("command", choices=["scan", "sync"], help="Команда для виконання")
    args = parser.parse_args()

    if args.command == "scan":
        run_scan()
    elif args.command == "sync":
        run_sync()


if __name__ == "__main__":
    main()