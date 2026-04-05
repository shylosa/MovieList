import pytest
from pathlib import Path
from scanner import VideoScanner


def test_scan_invalid_path() -> None:
    """Перевіряє, чи викидається помилка, якщо шлях не існує або це не директорія."""
    scanner = VideoScanner("non_existent_path_123")
    with pytest.raises(ValueError, match="Директорія не знайдена"):
        list(scanner.scan())


def test_scan_flat_files(tmp_path: Path) -> None:
    """Перевіряє розпізнавання відеофайлів у корені папки."""
    # Створюємо відеофайли
    (tmp_path / "movie1.mkv").write_text("fake data")
    (tmp_path / "movie2.MP4").write_text("fake data")  # Перевірка на регістр

    # Створюємо невідео
    (tmp_path / "info.txt").write_text("fake data")
    (tmp_path / "poster.jpg").write_text("fake data")

    scanner = VideoScanner(str(tmp_path))
    results = list(scanner.scan())

    # Маємо отримати 2 файли
    assert len(results) == 2
    filenames = {f.name for f in results}
    assert "movie1.mkv" in filenames
    assert "movie2.MP4" in filenames
    assert "info.txt" not in filenames


def test_scan_folders_with_video(tmp_path: Path) -> None:
    """
    Перевіряє логіку сканування папок:
    папка має бути видана (yielded), якщо всередині є відео.
    """
    # Папка з відео
    movie_dir = tmp_path / "Inception"
    movie_dir.mkdir()
    (movie_dir / "inception_rip.mkv").write_text("fake")

    # Папка без відео (тільки картинки)
    empty_dir = tmp_path / "Photos"
    empty_dir.mkdir()
    (empty_dir / "vacation.jpg").write_text("fake")

    scanner = VideoScanner(str(tmp_path))
    results = list(scanner.scan())

    # Має бути знайдено тільки папку Inception
    assert len(results) == 1
    assert results[0].name == "Inception"
    assert results[0].is_dir()


def test_scan_exclude_folders(tmp_path: Path) -> None:
    """Перевіряє, чи ігноруються папки зі списку виключень."""
    # Папка, яку треба проігнорувати
    recycle_bin = tmp_path / "$RECYCLE.BIN"
    recycle_bin.mkdir()
    (recycle_bin / "deleted_movie.mkv").write_text("fake")

    # Звичайна папка
    normal_dir = tmp_path / "Movies"
    normal_dir.mkdir()
    (normal_dir / "matrix.mkv").write_text("fake")

    scanner = VideoScanner(str(tmp_path), exclude_folders=["$RECYCLE.BIN"])
    results = list(scanner.scan())

    # Маємо побачити тільки Movies
    assert len(results) == 1
    assert results[0].name == "Movies"


def test_scan_deep_nested_video(tmp_path: Path) -> None:
    """Перевіряє, чи знайдеться папка, якщо відео лежить глибоко всередині."""
    # Структура: Root / Series / Season 1 / ep1.mkv
    series_dir = tmp_path / "The Boys"
    series_dir.mkdir()
    season_dir = series_dir / "Season 01"
    season_dir.mkdir()
    (season_dir / "s01e01.mkv").write_text("fake")

    scanner = VideoScanner(str(tmp_path))
    results = list(scanner.scan())

    # Має видати папку "The Boys"
    assert len(results) == 1
    assert results[0].name == "The Boys"


def test_permission_error_handling(tmp_path: Path, mocker: pytest.LogCaptureFixture) -> None:
    """Перевіряє захист від PermissionError (наприклад, системні папки)."""
    system_dir = tmp_path / "SystemFolder"
    system_dir.mkdir()

    # Використовуємо мок, щоб імітувати помилку доступу при спробі зайти в папку
    from pathlib import Path as PathLib
    # Ми мокаємо rglob саме для нашого об'єкта папки
    import scanner
    # Тут ми трохи схитруємо: змусимо any() викинути помилку всередині циклу
    mocker.patch("scanner.Path.rglob", side_effect=PermissionError("Access denied"))

    scanner_obj = VideoScanner(str(tmp_path))

    # Програма не має впасти, вона просто проігнорує цю папку
    results = list(scanner_obj.scan())
    assert results == []