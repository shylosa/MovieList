@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ===================================================
echo   🚀 Збірка MovieList у виконуваний файл (.exe)
echo ===================================================
echo.

echo [1/3] Очищення старих файлів...
rmdir /S /Q build 2>nul
rmdir /S /Q dist 2>nul
del /Q MovieList.spec 2>nul
del /Q version.txt 2>nul

echo [2/3] Запуск PyInstaller...
pyinstaller --noconfirm --onefile --windowed --icon="logo.ico" --name "MovieList" --collect-data babelfish --collect-data guessit --collect-submodules babelfish --collect-submodules guessit launcher.pyw

echo.
echo [3/3] Готово!
echo ===================================================
pause