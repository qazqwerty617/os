@echo off
title MEXC Pump Monitor - Genius Edition
echo.
echo ========================================
echo   MEXC PUMP MONITOR - ONE COMMAND
echo ========================================
echo.
if exist .env (
    for /f "tokens=1,* delims==" %%a in (.env) do (
        if not "%%a"=="" if not "%%a:~0,1%"=="#" set "%%a=%%b"
    )
    echo .env loaded
) else (
    echo Warning: .env not found - copy .env.example to .env
)
echo.
echo Starting...
python main.py
pause
