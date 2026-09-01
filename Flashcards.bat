@echo off
rem Double-click to study. First run builds .venv and installs edge-tts (~10 s).
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo First run: creating .venv and installing edge-tts...
  python -m venv .venv || goto :err
  .venv\Scripts\python.exe -m pip install --quiet --upgrade pip
  .venv\Scripts\python.exe -m pip install --quiet edge-tts || goto :err
  echo Done.
)

echo Starting on http://127.0.0.1:8765/  -- close this window to stop.
.venv\Scripts\python.exe server.py
goto :eof

:err
echo.
echo Setup failed. Check that Python 3.9+ is installed and on PATH.
pause
