@echo off
REM ============================================
REM Commit and push changes to GitHub with date/time message
REM ============================================

REM Stage all changes
git add .

REM Use system date and time as commit message
set msg=%date% %time%

git commit -m "%msg%"

REM Push to main branch
git push origin main

REM Pause so you can see any error messages
pause

