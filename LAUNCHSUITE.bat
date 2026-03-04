@echo off

IF NOT EXIST ".venv\Scripts\pythonw.exe" (
    echo First time setup - this may take a few minutes...
    python -m venv .venv
    IF ERRORLEVEL 1 (
        echo ERROR: Python not found. Please install Python 3.10+ and try again.
        pause
        exit /b 1
    )
    call .venv\Scripts\activate.bat
    pip install -r requirements.txt
    IF ERRORLEVEL 1 (
        echo ERROR: Failed to install requirements.
        pause
        exit /b 1
    )
    echo Setup complete.
)

start "" .venv\Scripts\pythonw.exe main.py