@echo off
echo ===========================================
echo Location Map - Full Pipeline
echo ===========================================
echo.
echo This batch file will:
echo   1. Extract CSV data from database
echo   2. Generate all maps (district, detailed, multi-param)
echo   3. Start the dashboard server
echo.
pause

cd /d "%~dp0"

echo.
echo ===========================================
echo Step 1/3: Extract CSV from Database
echo ===========================================
echo.
python gencsv/main.py
if errorlevel 1 (
    echo.
    echo [ERROR] CSV extraction failed!
    pause
    exit /b 1
)

echo.
echo ===========================================
echo Step 2/3: Generate All Maps
echo ===========================================
echo.

echo [A] Running location_mapper.py (district + detailed maps)...
python maps/location_mapper.py

echo.
echo [B] Running multi_param_mapper.py (combined maps)...
python maps/multi_param_mapper.py

echo.
echo ===========================================
echo Step 3/3: Starting Dashboard
echo ===========================================
echo.
echo Output locations:
echo   - maps\output\district\
echo   - maps\output\detailed\
echo   - maps\output\district_all_param\
echo.
echo Dashboard will be at: http://localhost:5000
echo.
echo Press Ctrl+C to stop the server when done
echo ===========================================
echo.

cd dashboard
python app.py
