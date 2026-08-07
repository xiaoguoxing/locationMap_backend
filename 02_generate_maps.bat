@echo off
echo ===========================================
echo Step 2: Generate All Maps
echo ===========================================
echo.

cd /d "%~dp0"

echo [1/2] Running maps/location_mapper.py...
echo       (Generates district + detailed maps)
echo.
python maps/location_mapper.py

echo.
echo [2/2] Running maps/multi_param_mapper.py...
echo       (Generates multi-parameter combined maps)
echo.
python maps/multi_param_mapper.py

echo.
echo ===========================================
echo Map generation complete!
echo Output directories:
echo   - maps\output\district\
echo   - maps\output\detailed\
echo   - maps\output\district_all_param\
echo ===========================================
pause
