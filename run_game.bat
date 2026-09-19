@echo off
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found. Please install Python first.
    pause
    exit /b 1
)

python -c "import pygame" >nul 2>nul
if errorlevel 1 (
    echo Pygame was not found.
    echo Please run: python -m pip install -r requirements.txt
    pause
    exit /b 1
)

python ArrowEscapeGame.py

if errorlevel 1 (
    echo.
    echo The game exited with an error.
    pause
)
