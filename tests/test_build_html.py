import os
import sqlite3
import pytest
from pathlib import Path

# Імпортуємо функції та класи з нашого генератора
import build_html
from build_html import Movie, _resolve_poster, _render_card, generate_html


@pytest.fixture
def mock_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """
    Фікстура створює повністю ізольоване середовище для тестів:
    тимчасову БД, тимчасову папку постерів та тимчасовий HTML-файл.
    """
    db_path = tmp_path / "test_movies.db"
    html_path = tmp_path / "test_index.html"
    posters_dir = tmp_path / "posters"
    posters_dir.mkdir()

    # Створюємо фейкову БД і таблицю
    with sqlite3.connect(db_path) as conn:
        conn.execute('''
            CREATE TABLE movies (
                filename TEXT PRIMARY KEY, title_ua TEXT, title_en TEXT,
                year TEXT, genres TEXT, "cast" TEXT, plot TEXT, local_poster_path TEXT
            )
        ''')
        # Додаємо один тестовий фільм
        conn.execute('''
            INSERT INTO movies VALUES (
                'test_movie.mkv', 'Тестовий Фільм', 'Test Movie', 
                '2024', 'Екшн', 'Актор 1', 'Опис', NULL
            )
        ''')

    # Підміняємо константи у модулі build_html
    monkeypatch.setattr(build_html, "DB_PATH", str(db_path))
    monkeypatch.setattr(build_html, "HTML_PATH", str(html_path))
    monkeypatch.setattr(build_html, "POSTERS_DIR", str(posters_dir))
    monkeypatch.setattr(build_html, "APP_VERSION", "vTest.0")

    return {
        "db": str(db_path),
        "html": str(html_path),
        "posters": str(posters_dir)
    }


def test_resolve_poster_fallback(mock_env: dict[str, str]) -> None:
    """Перевіряє, чи видається стандартна заглушка, якщо файлу немає на диску."""
    movie = Movie("unknown.mkv", "Без постера", None, None, None, None, None, None)

    poster = _resolve_poster(movie)
    assert poster == build_html._POSTER_PLACEHOLDER


def test_resolve_poster_exists(mock_env: dict[str, str]) -> None:
    """Перевіряє, чи знаходить функція реальний постер у папці."""
    # Створюємо фейковий файл постера у тимчасовій папці
    poster_file = os.path.join(mock_env["posters"], "avatar.jpg")
    Path(poster_file).write_text("fake image")

    movie = Movie("avatar.mkv", "Аватар", None, None, None, None, None, None)

    poster = _resolve_poster(movie)
    assert poster == poster_file


def test_render_card_xss_protection() -> None:
    """
    КРИТИЧНО ВАЖЛИВИЙ ТЕСТ: Перевіряє, чи екрануються небезпечні HTML-теги,
    щоб уникнути XSS ін'єкцій у веб-інтерфейсі.
    """
    malicious_movie = Movie(
        filename="hack.mkv",
        title_ua="<script>alert('XSS')</script>",  # Спроба атаки
        title_en=None, year=None, genres=None, cast=None, plot=None, local_poster_path=None
    )

    card_html = _render_card(malicious_movie)

    # Тег <script> має бути перетворений на безпечні &lt;script&gt;
    assert "<script>" not in card_html
    assert "&lt;script&gt;alert(&#x27;XSS&#x27;)&lt;/script&gt;" in card_html


def test_generate_html_full_cycle(mock_env: dict[str, str]) -> None:
    """Перевіряє повний цикл генерації HTML-файлу на основі даних з БД."""
    html_file = Path(mock_env["html"])

    # Файлу ще не має бути
    assert not html_file.exists()

    # Запускаємо генерацію
    generate_html()

    # Файл має з'явитися
    assert html_file.exists()

    content = html_file.read_text(encoding="utf-8")

    # Перевіряємо, чи потрапили дані з нашої фейкової БД (див. фікстуру mock_env) у HTML
    assert "Тестовий Фільм" in content
    assert "Test Movie" in content
    assert "2024" in content
    assert "vTest.0" in content  # Наш фейковий APP_VERSION