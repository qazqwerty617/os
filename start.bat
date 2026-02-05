@echo off
title MEXC Pump Monitor - Genius Edition
echo.
echo ========================================
echo   MEXC PUMP MONITOR - STARTING...
echo ========================================
echo.
echo Loading .env...
for /f "tokens=1,* delims==" %%a in (.env) do (
    if not "%%a"=="" if not "%%a:~0,1%"=="#" set "%%a=%%b"
)
echo.
echo Starting system...
python main.py --mode both --risk moderate
pause
