import pytest
from typing import Any
from pytest_mock import MockerFixture

from title_parser import MovieParser


def test_parse_standard_movie() -> None:
    """Перевіряє класичне розпізнавання фільму з роком."""
    filename = "The.Matrix.1999.1080p.mkv"
    result: dict[str, Any] = MovieParser.parse_filename(filename)

    assert result["original_filename"] == filename
    assert result["title"] == "The Matrix"
    assert result["year"] == "1999"
    assert result["type"] == "movie"


def test_parse_movie_without_year() -> None:
    """Перевіряє поведінку, якщо рік у назві відсутній."""
    filename = "Inception.WEB-DL.mkv"
    result: dict[str, Any] = MovieParser.parse_filename(filename)

    assert result["original_filename"] == filename
    assert result["title"] == "Inception"
    assert result["year"] == ""  # Має бути порожній рядок, а не None
    assert result["type"] == "movie"


def test_parse_tv_show_episode() -> None:
    """Перевіряє, чи правильно визначається тип для серіалів."""
    filename = "Breaking.Bad.S01E05.720p.mkv"
    result: dict[str, Any] = MovieParser.parse_filename(filename)

    assert result["title"] == "Breaking Bad"
    assert result["type"] == "episode"


def test_year_as_list_protection(mocker: MockerFixture) -> None:
    """
    Штучно імітуємо ситуацію (мокаємо), коли guessit повертає список років,
    щоб перевірити, чи спрацює твій захисний механізм.
    """
    # Змушуємо guessit повернути нестандартні дані
    mocked_guess = {
        'title': 'Tricky Movie',
        'year': [2026, 2027],  # Умисно передаємо список
        'type': 'movie'
    }
    mocker.patch('title_parser.guessit', return_value=mocked_guess)

    filename = "Tricky.Movie.2026.2027.mkv"
    result: dict[str, Any] = MovieParser.parse_filename(filename)

    # Наша логіка має взяти перший елемент списку і перетворити на рядок
    assert result["year"] == "2026"
    assert result["title"] == "Tricky Movie"