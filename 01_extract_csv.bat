@echo off
echo ===========================================
echo Step 1: Extract CSV Data from Database
echo ===========================================
echo.

cd /d "%~dp0"

echo Running gencsv/main.py...
echo.
python gencsv/main.py

echo.
echo ===========================================
echo CSV extraction complete!
echo Output: gencsv\output\
echo ===========================================
pause
