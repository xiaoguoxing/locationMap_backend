@echo off
setlocal
cd /d "%~dp0"

set "PYTHON=%~dp0.venv312\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo [ERROR] Python 3.12 virtual environment not found: .venv312
    echo Run: py -3.12 -m venv .venv312
    echo Then: .venv312\Scripts\python.exe -m pip install -r requirements.txt
    exit /b 1
)

if "%~1"=="" (
    echo Extracting the latest 30 days with 7-day rolling windows...
    "%PYTHON%" "%~dp0gencsv\date_range_runner.py" --days 30 --range-days 7
) else (
    echo Extracting CSV data with arguments: %*
    "%PYTHON%" "%~dp0gencsv\date_range_runner.py" %*
)

set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" echo [ERROR] CSV extraction failed with exit code %EXIT_CODE%.
exit /b %EXIT_CODE%