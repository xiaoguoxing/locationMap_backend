@echo off
echo ===========================================
echo Step 3: Starting Dashboard Server
echo ===========================================
echo.

cd /d "%~dp0dashboard"

echo Starting Flask server on http://localhost:5000
echo.
echo Press Ctrl+C to stop the server
echo ===========================================
echo.

python app.py
