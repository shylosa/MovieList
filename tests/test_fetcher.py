import pytest
from pathlib import Path
from typing import Any
import requests
from pytest_mock import MockerFixture

from fetcher import TMDBFetcher


@pytest.fixture
def fetcher(tmp_path: Path) -> TMDBFetcher:
    """
    Створюємо екземпляр fetcher із фейковим API-ключем та тимчасовою папкою для постерів.
    Так ми ізолюємо тести від реального конфігу та файлової системи.
    """
    return TMDBFetcher(api_key="fake_test_key", posters_dir=tmp_path)


def test_init_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Перевіряємо, чи клас викидає помилку, якщо ключа немає ні в аргументах, ні в config.py."""
    # Змушуємо імпорт з config повернути None
    monkeypatch.setattr("config.TMDB_API_KEY", None)

    with pytest.raises(ValueError, match="Не знайдено TMDB_API_KEY"):
        TMDBFetcher(api_key=None)


def test_format_result_movie(fetcher: TMDBFetcher) -> None:
    """Перевіряємо логіку парсингу JSON (фільм)."""
    data = {
        "title": "Матриця",
        "original_title": "The Matrix",
        "release_date": "1999-03-30",
        "genres": [{"name": "Фантастика"}, {"name": "Бойовик"}],
        "overview": "Культовий фільм.",
        "credits": {"cast": [{"name": "Keanu Reeves"}, {"name": "Laurence Fishburne"}]},
        "poster_path": "/matrix.jpg"
    }

    result = fetcher._format_result(data, media_type="movie", original_filename="matrix.mkv")

    assert result["official_title"] == "Матриця"
    assert result["release_date"] == "1999"
    assert result["genres"] == "Фантастика, Бойовик"
    assert "Keanu Reeves" in result["cast"]
    assert result["poster_url"] == "https://image.tmdb.org/t/p/w500/matrix.jpg"


def test_format_result_tv_show(fetcher: TMDBFetcher) -> None:
    """Перевіряємо логіку парсингу JSON (серіал). У серіалів інші ключі в TMDB."""
    data = {
        "name": "Пуститися берега",
        "original_name": "Breaking Bad",
        "first_air_date": "2008-01-20",
    }

    result = fetcher._format_result(data, media_type="tv", original_filename="bb.mkv")

    assert result["official_title"] == "Пуститися берега"
    assert result["release_date"] == "2008"


def test_search_movie_success(fetcher: TMDBFetcher, mocker: MockerFixture) -> None:
    """
    Перевіряємо успішний пошук фільму.
    Тут функція робить ДВА мережеві запити, тому ми використовуємо side_effect.
    """
    # 1. Відповідь для /search/multi (знайшли фільм)
    search_mock = mocker.MagicMock()
    search_mock.json.return_value = {"results": [{"id": 123, "media_type": "movie"}]}

    # 2. Відповідь для /movie/123 (деталі)
    details_mock = mocker.MagicMock()
    details_mock.json.return_value = {
        "title": "Знайдений Фільм",
        "poster_path": "/test.jpg"
    }

    # Мокаємо requests.Session.get, щоб він повертав наші підготовлені відповіді
    mock_get = mocker.patch.object(fetcher.session, 'get', side_effect=[search_mock, details_mock])

    # Мокаємо завантаження постера (ми перевіримо його в окремому тесті)
    mocker.patch.object(fetcher, '_download_poster', return_value="C:/fake/path.jpg")

    result = fetcher.search_movie("Test Title")

    assert result["official_title"] == "Знайдений Фільм"
    assert result["local_poster_path"] == "C:/fake/path.jpg"
    assert mock_get.call_count == 2


def test_search_movie_not_found(fetcher: TMDBFetcher, mocker: MockerFixture) -> None:
    """Сценарій: TMDB повернув порожній список результатів."""
    search_mock = mocker.MagicMock()
    search_mock.json.return_value = {"results": []}

    mocker.patch.object(fetcher.session, 'get', return_value=search_mock)

    result = fetcher.search_movie("Unknown Title")
    assert result == {}


def test_search_movie_network_error(fetcher: TMDBFetcher, mocker: MockerFixture) -> None:
    """Сценарій: відпав інтернет (RequestException). Має повернутися порожній словник, а не впасти програма."""
    mocker.patch.object(fetcher.session, 'get', side_effect=requests.exceptions.ConnectionError("No internet"))

    result = fetcher.search_movie("Matrix")
    assert result == {}


def test_download_poster_new_and_cached(fetcher: TMDBFetcher, mocker: MockerFixture) -> None:
    """
    Перевіряємо:
    1. Завантаження та збереження нового постера.
    2. Механізм кешування (повторне скачування ігнорується, якщо файл є).
    """
    # Імітуємо стрім (iter_content), який повертає байти картинки
    mock_response = mocker.MagicMock()
    mock_response.iter_content.return_value = [b"fake ", b"image ", b"data"]

    mock_get = mocker.patch.object(fetcher.session, 'get', return_value=mock_response)

    # 1. Перше завантаження
    poster_path_str = fetcher._download_poster("http://tmdb.org/img.jpg", "Matrix.mkv")
    poster_path = Path(poster_path_str)

    assert poster_path.exists()
    assert poster_path.read_text() == "fake image data"
    assert mock_get.call_count == 1

    # 2. Друге завантаження того ж файлу
    poster_path_str_2 = fetcher._download_poster("http://tmdb.org/img.jpg", "Matrix.mkv")

    # Шлях має бути той самий
    assert poster_path_str_2 == poster_path_str
    # Кількість викликів requests.get МАЄ ЗАЛИШИТИСЯ 1 (бо спрацював кеш)
    assert mock_get.call_count == 1