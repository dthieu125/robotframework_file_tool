@echo off
chcp 65001 >nul
title Robot Framework Web Tool

echo.
echo ================================================
echo   Robot Framework Web Tool – Start-up
echo ================================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Cannot find Python. Please install Python 3.9+
    pause
    exit /b 1
)

:: Create venv if not exists
if not exist "venv" (
    echo [INFO] Create virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Cannot create venv
        pause
        exit /b 1
    )
)

:: Activate venv
call venv\Scripts\activate.bat

:: Install/upgrade dependencies
echo [INFO] Check and install dependencies...
pip install -q --index-url https://pypi.org/simple/ -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Install dependencies failed
    pause
    exit /b 1
)

:: Create required dirs
if not exist "uploads" mkdir uploads
if not exist "results" mkdir results

echo.
echo [OK] Everything is ready!
echo.

:: Get local IP
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4"') do (
    set LOCAL_IP=%%a
    goto :found_ip
)
:found_ip
set LOCAL_IP=%LOCAL_IP: =%

echo ================================================
echo   Access tool at:
echo     Local  : http://localhost:5000
echo     Mang   : http://%LOCAL_IP%:5000
echo ================================================
echo.
echo Press Ctrl+C to stop server
echo.

:: Open browser after 2 seconds
start /b cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:5000"

:: Start server
python app.py

pause
