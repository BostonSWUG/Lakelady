@echo off
title Lakelady - Agile PLM Automation
cd /d "%~dp0"

REM Check if Python is available
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH.
    echo Please install Python 3.10+ from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

REM Install dependencies if needed (first run)
if not exist ".deps_installed" (
    echo Installing dependencies - first run only...
    python -m pip install -r requirements.txt --quiet
    if %errorlevel% neq 0 (
        echo ERROR: Failed to install dependencies.
        pause
        exit /b 1
    )
    type nul > .deps_installed
    echo Dependencies installed successfully.
)

REM Launch Lakelady
echo Starting Lakelady...
echo.
echo The app will open in your browser at http://localhost:8501
echo Close this window to stop Lakelady.
echo.
timeout /t 2 /nobreak >nul
start "" http://localhost:8501
python -m streamlit run app.py --server.headless true --browser.gatherUsageStats false
echo.
echo Lakelady has stopped.
pause
