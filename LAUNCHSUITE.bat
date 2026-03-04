@echo off

IF NOT EXIST ".venv\Scripts\pythonw.exe" (
    echo First time setup - this may take a few minutes...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install -r requirements.txt
    echo Setup complete.
)

start "" .venv\Scripts\pythonw.exe main.py