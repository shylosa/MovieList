import pytest
from typing import Any, Generator
from pytest_mock import MockerFixture

# Імпортуємо наш парсер ШІ
from ai_parser import GeminiParser


@pytest.fixture(autouse=True)
def mock_env_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Ця фікстура автоматично запускається перед кожним тестом (autouse=True).
    Вона підміняє API-ключ, щоб клас GeminiParser не викидав ValueError при ініціалізації
    у середовищі, де немає файлу .env.
    """
    monkeypatch.setattr("ai_parser.GEMINI_API_KEY", "fake_test_key_123")


def test_extract_list_from_json() -> None:
    """Перевіряємо, чи правильно парситься сирий JSON-текст."""
    parser = GeminiParser()
    valid_json = """
    [
        {
            "original_file": "Matrix.mkv", 
            "clean_title": "The Matrix", 
            "title_ua": "Матриця", 
            "title_en": "The Matrix", 
            "year": 1999, 
            "plot": "Опис", 
            "genres": "Фантастика", 
            "cast": "Кіану Рівз"
        }
    ]
    """
    result: list[dict[str, Any]] = parser._extract_list_from_json(valid_json)

    assert len(result) == 1
    assert result[0]["clean_title"] == "The Matrix"
    assert result[0]["year"] == 1999


def test_clean_filenames_bulk_success(mocker: MockerFixture) -> None:
    """Сценарій 1: Основна модель відповідає з першої спроби."""
    parser = GeminiParser()

    # Підготовлена "успішна" відповідь
    fake_response = [{"original_file": "movie.mkv", "clean_title": "Movie"}]

    # Змушуємо метод _make_api_request завжди повертати fake_response,
    # замість того, щоб реально стукати в Google.
    mock_request = mocker.patch.object(parser, '_make_api_request', return_value=fake_response)

    result: list[dict[str, Any]] = parser.clean_filenames_bulk(["movie.mkv"])

    assert result == fake_response
    # Перевіряємо, що запит був лише один
    assert mock_request.call_count == 1
    # Перевіряємо, що запит пішов саме до ОСНОВНОЇ моделі
    assert mock_request.call_args[0][1] == parser.primary_model


def test_clean_filenames_bulk_fallback(mocker: MockerFixture) -> None:
    """
    Сценарій 2: Основна модель 'лежить', вмикається резервна.
    Тут ми використовуємо 'side_effect' - список результатів для кожного наступного виклику.
    """
    parser = GeminiParser()
    fake_response = [{"original_file": "movie.mkv", "clean_title": "Movie"}]

    # Виклик 1 (спроба 1 основної): None (помилка)
    # Виклик 2 (спроба 2 основної): None (помилка)
    # Виклик 3 (резервна модель): fake_response (успіх!)
    mock_request = mocker.patch.object(
        parser,
        '_make_api_request',
        side_effect=[None, None, fake_response]
    )

    # Відключаємо time.sleep, щоб тест не чекав 2 секунди між спробами
    mocker.patch('time.sleep', return_value=None)

    # Запускаємо з max_retries=2
    result: list[dict[str, Any]] = parser.clean_filenames_bulk(["movie.mkv"], max_retries=2)

    assert result == fake_response
    # Перевіряємо, що було рівно 3 запити
    assert mock_request.call_count == 3

    # Перевіряємо, що останній запит (виклик №3) пішов саме до РЕЗЕРВНОЇ моделі
    last_call_model_name = mock_request.call_args_list[-1][0][1]
    assert last_call_model_name == parser.fallback_model


def test_clean_filenames_bulk_total_failure(mocker: MockerFixture) -> None:
    """Сценарій 3: Жодна модель не відповіла."""
    parser = GeminiParser()

    # Завжди повертаємо None (імітація повного падіння API)
    mock_request = mocker.patch.object(parser, '_make_api_request', return_value=None)
    mocker.patch('time.sleep', return_value=None)

    result: list[dict[str, Any]] = parser.clean_filenames_bulk(["movie.mkv"], max_retries=2)

    # Якщо все впало, має повернутися порожній список
    assert result == []
    # 2 спроби основної + 1 спроба резервної = 3 виклики
    assert mock_request.call_count == 3