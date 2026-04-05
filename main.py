import os
import sys
import argparse
import warnings
import re
import logging
from datetime import datetime
import sqlite3
import traceback

from config import APP_VERSION, MEDIA_FOLDER_PATH, EXCLUDE_LIST, DB_PATH, cancel_event

from scanner import VideoScanner
from title_parser import MovieParser
from fetcher import TMDBFetcher
from ai_parser import GeminiParser
from database import LocalMovieDB
from sheets import GoogleSheetSync

warnings.simplefilter(action='ignore', category=FutureWarning)
warnings.simplefilter(action='ignore', category=UserWarning)

os.makedirs("logs", exist_ok=True)
log_filename = os.path.join("logs", f"movielist_{datetime.now().strftime('%Y-%m-%d')}.log")
logging.basicConfig(
    filename=log_filename,
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(module)s: %(message)s",
    encoding="utf-8"
)


# --- ГЛОБАЛЬНИЙ ПЕРЕХОПЛЮВАЧ КРАХІВ ---
def handle_unhandled_exception(exc_type, exc_value, exc_traceback):
    # Ігноруємо натискання Ctrl+C (зупинка користувачем)
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    # Записуємо критичний крах у лог-файл
    logging.critical("КРИТИЧНИЙ ЗБІЙ ПРОГРАМИ (Необроблена помилка):", exc_info=(exc_type, exc_value, exc_traceback))


# Підміняємо стандартний обробник помилок на наш
sys.excepthook = handle_unhandled_exception

def has_cyrillic(text: str) -> bool:
    return bool(re.search('[а-яА-ЯіїєґІЇЄҐ]', text))


# --- ОТРИМАННЯ СТАТИСТИКИ ДЛЯ ЛОНЧЕРА ---
def get_db_stats() -> dict:
    """Повертає загальну кількість фільмів та кількість нерозпізнаних."""
    stats = {"total": 0, "unrecognized": 0, "last_scan": "Ніколи"}

    if not os.path.exists(DB_PATH):
        return stats

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM movies")
        stats["total"] = cursor.fetchone()[0]

        # Вважаємо "нерозпізнаним", якщо немає ні української, ні англійської назви
        cursor.execute(
            "SELECT COUNT(*) FROM movies WHERE (title_ua IS NULL OR title_ua = '') AND (title_en IS NULL OR title_en = '')")
        stats["unrecognized"] = cursor.fetchone()[0]

        # Беремо час створення або останньої зміни файлу БД
        mtime = os.path.getmtime(DB_PATH)
        stats["last_scan"] = datetime.fromtimestamp(mtime).strftime("%d.%m.%Y %H:%M")

        conn.close()
    except Exception as e:
        logging.error(f"Помилка отримання статистики: {e}")

    return stats

# --- ДОПОМІЖНІ ФУНКЦІЇ ДЛЯ SCAN ---

def _prepare_new_files(db_local, scanner) -> list[str]:
    """Сканує директорію, чистить БД від видалених файлів та повертає список нових."""
    print(f"📁 Сканування директорії: {MEDIA_FOLDER_PATH}...")
    actual_disk_files = [f.name for f in scanner.scan()]

    db_local.remove_missing_files(actual_disk_files)
    db_local.clean_orphan_posters()

    existing_in_db = db_local.get_all_filenames()
    new_files = [f for f in actual_disk_files if f not in existing_in_db]

    if not new_files:
        logging.info("Нових файлів не знайдено.")
        print("🤷‍♂️ Нових файлів не знайдено. Локальна база актуальна.")
        return []

    logging.info(f"Знайдено {len(new_files)} нових файлів для обробки.")
    print(f"\n🔍 Знайдено {len(new_files)} нових файлів для обробки.")
    return new_files


def _needs_ai_processing(movie_info: dict, filename: str) -> bool:
    """Перевіряє, чи потрібне залучення ШІ для отриманої інформації."""
    if not movie_info or not movie_info.get("overview"):
        return True

    found_year = movie_info.get("release_date", "")
    official_title = movie_info.get("official_title", "")

    if found_year and found_year.isdigit() and int(found_year) < 2005 and str(found_year) not in filename:
        print("👴 Надто старий фільм. До ШІ.", end=" ")
        return True

    if not has_cyrillic(official_title):
        print("🇺🇦 Немає UA-назви. До ШІ.", end=" ")
        return True

    return False


def _phase1_classic_search(new_files: list[str], parser, fetcher, db_local) -> list[str]:
    """Виконує пошук через TMDB і повертає список файлів, яким потрібен ШІ."""
    print("\n[ФАЗА 1: Класичний пошук]")
    ai_queue = []

    for filename in new_files:
        if cancel_event.is_set():
            print("\n🛑 Процес сканування зупинено користувачем!")
            break  # Виходимо з циклу
        parsed = parser.parse_filename(filename)
        title, year = parsed.get('title'), parsed.get('year')

        if not title:
            ai_queue.append(filename)
            continue

        print(f"[{filename}] 🔍 TMDB...", end=" ")
        movie_info = fetcher.search_movie(title, year, original_filename=filename)

        if _needs_ai_processing(movie_info, filename):
            print("📝 Відкладено для ШІ.")
            ai_queue.append(filename)
        else:
            print("✅ Знайдено!")
            db_local.save_movie(filename, movie_info)
            logging.info(f"Успішно додано з TMDB: {filename}")

    return ai_queue


def _save_hybrid_merge(filename: str, movie_info: dict, ai_data: dict, db_local):
    """Зливає дані TMDB з даними ШІ та зберігає у БД."""
    merged_info = movie_info.copy()

    if not has_cyrillic(merged_info.get("official_title", "")) and ai_data.get("title_ua"):
        merged_info["official_title"] = ai_data.get("title_ua")

    if not merged_info.get("overview"): merged_info["overview"] = ai_data.get("plot", "")
    if not merged_info.get("cast"): merged_info["cast"] = ai_data.get("cast", "")
    if not merged_info.get("genres"): merged_info["genres"] = ai_data.get("genres", "")

    print("✅ Гібрид збережено!")
    db_local.save_movie(filename, merged_info)
    logging.info(f"Гібридне збереження: {filename} -> {merged_info.get('official_title')}")


def _save_ai_fallback(filename: str, ai_data: dict, clean_title: str, clean_year: str, db_local):
    """Зберігає суто дані від ШІ, якщо TMDB не дав результату."""
    print("⚠️ TMDB не знайшов. 100% даних ШІ.")
    fallback_info = {
        "official_title": ai_data.get("title_ua", clean_title),
        "original_title": ai_data.get("title_en", ""),
        "release_date": clean_year,
        "genres": ai_data.get("genres", ""),
        "overview": ai_data.get("plot", ""),
        "cast": ai_data.get("cast", ""),
        "poster_url": "",
        "local_poster_path": ""
    }
    db_local.save_movie(filename, fallback_info)
    logging.warning(f"Збережено тільки за даними ШІ: {filename}")


def _phase2_and_3_ai_processing(ai_queue: list[str], ai, fetcher, db_local):
    """Виконує запит до ШІ та гібридне злиття результатів."""
    print(f"\n[ФАЗА 2: Глибокий аналіз {len(ai_queue)} складних назв через ШІ]")
    ai_results = ai.clean_filenames_bulk(ai_queue)

    print("\n[ФАЗА 3: Гібридне злиття даних (TMDB + ШІ)]")
    for filename in ai_queue:
        ai_data = next((item for item in ai_results if item.get("original_file") == filename), None)

        if not ai_data or not ai_data.get("clean_title"):
            print(f"[{filename}] ❌ Пропущено. Кешуємо пустим.")
            db_local.save_movie(filename, {}, raw_fallback=filename)
            logging.error(f"ШІ не розпізнав файл: {filename}")
            continue

        clean_title = ai_data.get("clean_title")
        clean_year = str(ai_data.get("year", "")) if ai_data.get("year") else ""

        print(f"[{filename}] ✨ ШІ: '{clean_title}'. TMDB...", end=" ")
        movie_info = fetcher.search_movie(clean_title, clean_year, original_filename=filename)

        if movie_info:
            _save_hybrid_merge(filename, movie_info, ai_data, db_local)
        else:
            _save_ai_fallback(filename, ai_data, clean_title, clean_year, db_local)

# --- ОСНОВНА ФУНКЦІЯ ---

def run_scan():
    """Головний метод запуску сканування медіатеки."""
    logging.info(f"=== Запуск сканування ({APP_VERSION}) ===")
    print(f"🚀 Ініціалізація MovieList {APP_VERSION}...")

    db_local = LocalMovieDB()
    scanner = VideoScanner(MEDIA_FOLDER_PATH, exclude_folders=EXCLUDE_LIST)
    parser = MovieParser()

    try:
        fetcher = TMDBFetcher()
        ai = GeminiParser()
    except Exception as e:
        logging.critical(f"Помилка ініціалізації API: {e}")
        print(f"❌ Помилка ініціалізації API: {e}")
        return

    new_files = _prepare_new_files(db_local, scanner)

    if not new_files:
        return

    ai_queue = _phase1_classic_search(new_files, parser, fetcher, db_local)

    if ai_queue:
        _phase2_and_3_ai_processing(ai_queue, ai, fetcher, db_local)

    print("\n✅ Локальне сканування завершено!")

    # --- Сповіщення про нерозпізнані файли ---
    stats = get_db_stats()
    unrecognized = stats.get("unrecognized", 0)
    if unrecognized > 0:
        print("\n" + "⚠️" * 20)
        print(f"⚠️ УВАГА: У базі є {unrecognized} нерозпізнаних файлів!")
        print("💡 Перейдіть у вкладку 'Редактор' для їх швидкого виправлення.")
        print("⚠️" * 20)

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


# --- ДОПОМІЖНІ ФУНКЦІЇ ДЛЯ РЕДАКТОРА (fix_recognition) ---

def _extract_tmdb_id(hint: str) -> str | None:
    """Аналізує підказку і намагається витягнути з неї TMDB ID."""
    if not hint:
        return None

    match_url = re.search(r'movie/(\d+)', hint)
    if match_url:
        return match_url.group(1)

    if hint.isdigit() and len(hint) > 4:
        return hint

    return None


def _process_with_ai_fallback(filename: str, hint: str, ai, fetcher) -> dict | None:
    """Запитує дані у ШІ, шукає в TMDB та зливає результати."""
    ai_query = f"{filename} (Підказка: {hint})" if hint else filename
    ai_results = ai.clean_filenames_bulk([ai_query])

    if not ai_results:
        print("❌ ШІ повернув порожній результат.")
        return None

    ai_data = ai_results[0]
    clean_title = ai_data.get("clean_title", "")
    clean_year = str(ai_data.get("year", "")) if ai_data.get("year") else ""

    print(f"✨ ШІ відповів: '{clean_title}' ({clean_year}). Шукаємо в TMDB...")
    movie_data = fetcher.search_movie(clean_title, clean_year, original_filename=filename)

    # Якщо TMDB знайшов фільм — робимо гібридне злиття
    if movie_data:
        if not has_cyrillic(movie_data.get("official_title", "")) and ai_data.get("title_ua"):
            movie_data["official_title"] = ai_data.get("title_ua")
        if not movie_data.get("overview"): movie_data["overview"] = ai_data.get("plot", "")
        if not movie_data.get("cast"): movie_data["cast"] = ai_data.get("cast", "")
        if not movie_data.get("genres"): movie_data["genres"] = ai_data.get("genres", "")
        return movie_data

    # Якщо TMDB нічого не знайшов — повертаємо 100% даних від ШІ
    print("⚠️ TMDB не знайшов збігу. Використовуємо 100% даних ШІ.")
    return {
        "official_title": ai_data.get("title_ua", clean_title),
        "original_title": ai_data.get("title_en", ""),
        "release_date": clean_year,
        "genres": ai_data.get("genres", ""),
        "overview": ai_data.get("plot", ""),
        "cast": ai_data.get("cast", ""),
        "poster_url": "",
        "local_poster_path": ""
    }


def _process_single_fix_item(item: dict, db_local, ai, fetcher):
    """Обробляє один запис (один фільм) із загального списку на виправлення."""
    filename = item["filename"]
    hint = item["hint"]

    print(f"\n🔄 Обробляємо: {filename}")
    if hint:
        print(f"💡 Підказка: {hint}")

    tmdb_id = _extract_tmdb_id(hint)

    # Запитуємо або напряму по ID, або через ШІ
    if tmdb_id:
        print(f"🎯 Запит точно по TMDB ID: {tmdb_id}")
        movie_data = fetcher.get_movie_by_id(tmdb_id, original_filename=filename)
    else:
        movie_data = _process_with_ai_fallback(filename, hint, ai, fetcher)

    # Збереження результату
    if movie_data:
        db_local.save_movie(filename, movie_data)
        print(f"✅ Оновлено: {movie_data.get('official_title', 'Без назви')}")
    else:
        print(f"❌ Не вдалося знайти нові дані для {filename}")


# --- ОСНОВНА ФУНКЦІЯ ---

def fix_recognition(data_list):
    """Головна точка входу для масового виправлення файлів."""
    print("\n" + "=" * 40)
    print("🛠️ ПОЧАТОК ПРОЦЕСУ ВИПРАВЛЕННЯ")
    print("=" * 40)

    try:
        db_local = LocalMovieDB()
        ai = GeminiParser()
        fetcher = TMDBFetcher()

        for item in data_list:
            if cancel_event.is_set():
                print("\n🛑 Процес виправлення зупинено користувачем!")
                break
            _process_single_fix_item(item, db_local, ai, fetcher)

        print("\n" + "=" * 40)
        print("🎉 Процес виправлення завершено!")
        print("=" * 40)

    except Exception:
        print("\n❌ СТАЛАСЯ КРИТИЧНА ПОМИЛКА:")
        traceback.print_exc()


def main():
    parser = argparse.ArgumentParser(description=f"MovieList {APP_VERSION}")
    parser.add_argument("command", choices=["scan", "sync"], help="Команда для виконання")
    args = parser.parse_args()

    if args.command == "scan":
        run_scan()
    elif args.command == "sync":
        run_sync()


if __name__ == "__main__":
    main()