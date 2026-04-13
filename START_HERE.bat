@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo ==========================================
echo IonIn Fixture - One Click Start
echo ==========================================
echo.

set "PY_EXE="
if exist ".venv\Scripts\python.exe" (
  set "PY_EXE=.venv\Scripts\python.exe"
  echo Using existing virtual environment.
) else (
  echo No local virtual environment found. Creating .venv ...
  where py >nul 2>nul
  if %errorlevel%==0 (
    py -3 -m venv .venv
  ) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
      python -m venv .venv
    ) else (
      echo ERROR: Python not found.
      echo Install Python 3, then run this file again.
      pause
      exit /b 1
    )
  )
  if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Failed to create .venv
    pause
    exit /b 1
  )
  set "PY_EXE=.venv\Scripts\python.exe"
)

echo.
echo Installing/updating dependencies...
"%PY_EXE%" -m pip install --upgrade pip >nul
"%PY_EXE%" -m pip install -r requirements.txt
if errorlevel 1 (
  echo ERROR: Dependency installation failed.
  pause
  exit /b 1
)

echo.
echo Starting IonIn Easy Menu...
echo (No command typing needed; use arrow keys or numbers)
echo.
"%PY_EXE%" ionin_ops_cli.py
set "RC=%errorlevel%"

echo.
echo IonIn session ended. Exit code: %RC%
echo.
pause
exit /b %RC%
