@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  py -3 -m venv .venv
  if errorlevel 1 (echo Install Python 3.11+ and enable the py launcher.& pause & exit /b 1)
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (echo Dependency install failed.& pause & exit /b 1)
if not exist ".env" (
  copy .env.example .env >nul
  echo.
  echo IMPORTANT: Edit .env and set SEC_USER_AGENT to your real contact email.
  notepad .env
)
".venv\Scripts\python.exe" -m streamlit run app.py
pause
