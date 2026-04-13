@echo off
setlocal
cd /d "%~dp0"

echo.
echo ==========================================
echo IonIn Fixture - Automatic Calibration Run
echo ==========================================
echo This will:
echo   1) run startup workflow checks
echo   2) if checks pass, run full mode chain
echo.
echo Press Ctrl+C now to cancel.
timeout /t 5 >nul

set "PY_EXE="
if exist ".venv\Scripts\python.exe" (
  set "PY_EXE=.venv\Scripts\python.exe"
) else (
  where py >nul 2>nul
  if %errorlevel%==0 (
    py -3 -m venv .venv
  ) else (
    python -m venv .venv
  )
  set "PY_EXE=.venv\Scripts\python.exe"
)

"%PY_EXE%" -m pip install --upgrade pip >nul
"%PY_EXE%" -m pip install -r requirements.txt
if errorlevel 1 (
  echo ERROR: Dependency setup failed.
  pause
  exit /b 1
)

echo.
echo Running workflow gate...
"%PY_EXE%" ionin_ops_cli.py workflow
if errorlevel 1 (
  echo.
  echo Workflow failed. Calibration chain NOT started.
  echo Fix hardware/config and rerun.
  pause
  exit /b 2
)

echo.
echo Workflow passed. Starting automatic mode chain...
"%PY_EXE%" ionin_ops_cli.py run-chain
set "RC=%errorlevel%"

echo.
echo Automatic run finished. Exit code: %RC%
pause
exit /b %RC%
