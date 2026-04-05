import pytest
import gspread
from gspread.exceptions import APIError
from gspread.utils import ValueInputOption
from pytest_mock import MockerFixture

# Імпортуємо наш клас та кастомну помилку
from sheets import GoogleSheetSync, SheetConnectionError


@pytest.fixture
def mock_sheets_env(monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture):
    """
    Фікстура для повної ізоляції Google Sheets.
    Підміняє змінні оточення та блокує реальну авторизацію.
    """
    monkeypatch.setenv("GOOGLE_SHEET_URL", "https://docs.google.com/spreadsheets/d/test")
    monkeypatch.setenv("GOOGLE_SHEET_WORKSHEET_NAME", "test_ws")

    # Мокаємо Credentials та gspread.authorize, щоб не шукати реальний файл credentials.json
    mocker.patch("google.oauth2.service_account.Credentials.from_service_account_file")
    mock_authorize = mocker.patch("gspread.authorize")

    # Створюємо ієрархію моків для gspread: client -> spreadsheet -> worksheet
    mock_client = mock_authorize.return_value
    mock_spreadsheet = mock_client.open_by_url.return_value
    mock_worksheet = mock_spreadsheet.worksheet.return_value

    return mock_worksheet


def test_col_letter_logic():
    """Тестуємо алгоритм перетворення номера колонки в літери (Excel style)."""
    sync = mocker_init_sync()  # Допоміжна функція нижче
    assert sync._col_letter(1) == "A"
    assert sync._col_letter(26) == "Z"
    assert sync._col_letter(27) == "AA"
    assert sync._col_letter(52) == "AZ"


def mocker_init_sync():
    """Створює екземпляр класу без реального підключення (використовується для тестів логіки)."""
    with pytest.MonkeyPatch().context() as mp:
        mp.setenv("GOOGLE_SHEET_URL", "http://test")
        import gspread
        from pytest_mock import mocker
        # Тут ми просто обходимо __init__ для простих тестів
        class Dummy: pass

        obj = Dummy()
        obj.__class__ = GoogleSheetSync
        obj.worksheet_name = "test"
        return obj


def test_init_missing_url(monkeypatch: pytest.MonkeyPatch):
    """Перевірка викидання ValueError, якщо URL таблиці не задано."""
    monkeypatch.delenv("GOOGLE_SHEET_URL", raising=False)
    with pytest.raises(ValueError, match="GOOGLE_SHEET_URL не знайдено"):
        GoogleSheetSync()


def test_retry_mechanism_success_after_failure(mocker: MockerFixture):
    """
    Тестуємо логіку ретраїв:
    перший раз API повертає APIError, другий раз — успіх.
    """
    sync = mocker_init_sync()
    mock_func = mocker.Mock()

    # 1. Створюємо "муляж" відповіді від сервера, яку очікує gspread.APIError
    mock_response = mocker.Mock()
    mock_response.json.return_value = {"error": {"code": 500, "message": "Server error"}}
    mock_response.text = '{"error": "Server error"}'

    # 2. Тепер створюємо саму помилку APIError, передаючи їй цей муляж
    fake_api_error = APIError(mock_response)

    # 3. Налаштовуємо side_effect: спочатку помилка, потім успіх
    mock_func.side_effect = [fake_api_error, "Success"]

    # Мокаємо sleep, щоб не чекати реально
    mocker.patch("time.sleep")

    result = sync._retry(mock_func, attempts=2)

    assert result == "Success"
    assert mock_func.call_count == 2


def test_full_sync_data_formatting(mock_sheets_env, mocker: MockerFixture):
    """
    Перевіряємо, чи правильно формуються дані для відправки:
    Headers + перепаковані рядки з БД.
    """
    # Створюємо екземпляр (він підхопить моки з фікстури mock_sheets_env)
    sync = GoogleSheetSync()

    # Дані у форматі, який приходить з LocalMovieDB.get_all_movies_for_export()
    # (id, title_ua, title_en, year, genres, cast, plot, poster_url, local_path)
    test_data = [
        ["path/1.mkv", "Матриця", "The Matrix", "1999", "Sci-Fi", "Keanu", "Plot...", "http://img.jpg", "local/1.jpg"]
    ]

    sync.full_sync(test_data)

    # Перевіряємо виклик методу update
    # Очікуємо: 8 колонок (A:H)
    mock_sheets_env.update.assert_called_once()
    args, kwargs = mock_sheets_env.update.call_args

    range_name = kwargs.get('range_name')
    values = kwargs.get('values')

    assert range_name == "A1:H2"  # Заголовки (1) + 1 фільм = 2 рядки. A-H = 8 колонок.
    assert values[0][0] == "File Path"  # Перевірка заголовка
    assert values[1][1] == "Матриця"  # Перевірка даних
    assert values[1][7] == "http://img.jpg"  # Перевірка URL постера (8-й елемент)