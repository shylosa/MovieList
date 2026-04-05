import os
import pytest
from typing import Generator
from pathlib import Path  # <--- ДОДАЙ ЦЕЙ ІМПОРТ

from database import LocalMovieDB

@pytest.fixture
def temp_posters_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str: # <--- ЗМІНИ ТИП ТУТ
    """
    Фікстура: створює тимчасову папку для постерів і підміняє POSTERS_DIR у модулі database.
    Це гарантує, що тести ніколи не видалять реальні картинки користувача.
    """
    temp_dir = str(tmp_path / "test_posters")
    monkeypatch.setattr("database.POSTERS_DIR", temp_dir)
    return temp_dir


@pytest.fixture
def db(temp_posters_dir: str) -> Generator[LocalMovieDB, None, None]:
    """
    Фікстура: ініціалізує базу даних в оперативній пам'яті (:memory:).
    Кожен тест отримуватиме абсолютно нову, чисту базу.
    """
    database = LocalMovieDB(db_path=":memory:")
    yield database
    # Після завершення тесту закриваємо з'єднання
    database.conn.close()


def test_save_and_get_all_filenames(db: LocalMovieDB) -> None:
    """Перевіряє збереження фільму та коректність отримання списку файлів."""
    data = {
        "official_title": "Матриця",
        "original_title": "The Matrix",
        "release_date": "1999",
        "genres": "Sci-Fi",
        "cast": "Keanu Reeves",
        "overview": "Культовий фільм.",
        "poster_url": "http://img.com/1.jpg",
        "local_poster_path": "posters/1.jpg"
    }

    db.save_movie("matrix.mkv", data)

    # Перевіряємо, чи файл з'явився у списку
    files = db.get_all_filenames()
    assert files == {"matrix.mkv"}

    # Перевіряємо мапінг полів при збереженні
    export = db.get_all_movies_for_export()
    assert len(export) == 1
    row = export[0]
    assert row[0] == "matrix.mkv"  # filename
    assert row[1] == "Матриця"  # title_ua (з official_title)
    assert row[2] == "The Matrix"  # title_en (з original_title)
    assert row[3] == "1999"  # year (з release_date)


def test_save_movie_fallback(db: LocalMovieDB) -> None:
    """Перевіряє, чи правильно працює raw_fallback (запис пустушки)."""
    db.save_movie("unknown.mkv", {}, raw_fallback="unknown.mkv")

    export = db.get_all_movies_for_export()
    row = export[0]

    assert row[0] == "unknown.mkv"
    assert row[1] == "unknown.mkv"  # fallback має потрапити у title_ua
    assert row[2] == ""  # інші поля мають бути порожніми


def test_remove_missing_files(db: LocalMovieDB) -> None:
    """Перевіряє видалення 'зомбі-записів' з бази."""
    # Додаємо три файли
    db.save_movie("keep1.mkv", {})
    db.save_movie("keep2.mkv", {})
    db.save_movie("delete.mkv", {})

    assert len(db.get_all_filenames()) == 3

    # Імітуємо, що на диску залишилося тільки два файли (і з'явився якийсь новий)
    db.remove_missing_files(["keep1.mkv", "keep2.mkv", "new.mkv"])

    # Перевіряємо: 'delete.mkv' має зникнути
    files = db.get_all_filenames()
    assert files == {"keep1.mkv", "keep2.mkv"}


def test_clean_orphan_posters(db: LocalMovieDB, temp_posters_dir: str) -> None:
    """Перевіряє логіку очищення хвостів (загублених постерів)."""
    # 1. Постер, який явно прописаний у БД
    db_poster_path = os.path.join(temp_posters_dir, "db_poster.jpg")
    with open(db_poster_path, "w") as f:
        f.write("image data")
    db.save_movie("movie1.mkv", {"local_poster_path": db_poster_path})

    # 2. Постер, який співпадає за назвою з файлом (valid_manual_posters)
    manual_poster_path = os.path.join(temp_posters_dir, "movie2.jpg")
    with open(manual_poster_path, "w") as f:
        f.write("image data")
    db.save_movie("movie2.mkv", {})

    # 3. 'Покинутий' постер (orphan)
    orphan_poster_path = os.path.join(temp_posters_dir, "orphan.jpg")
    with open(orphan_poster_path, "w") as f:
        f.write("image data")

    # Запускаємо очищення
    db.clean_orphan_posters()

    # Перевірки: легальні постери залишилися, а сирота зник
    assert os.path.exists(db_poster_path) is True
    assert os.path.exists(manual_poster_path) is True
    assert os.path.exists(orphan_poster_path) is False