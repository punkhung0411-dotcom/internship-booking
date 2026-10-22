@echo off
REM ============================================================
REM  setup.bat  -  ติดตั้งระบบ (ทําครั้งเดียว)
REM ============================================================
cd /d "%~dp0"

set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not exist "%PY%" set "PY=python"

echo [1/3] Creating virtual environment (.venv) ...
if not exist ".venv\Scripts\python.exe" (
    "%PY%" -m venv .venv
    if errorlevel 1 goto fail
)

echo [2/3] Upgrading pip ...
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet

echo [3/3] Installing requirements (Flask, waitress) ...
".venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet
if errorlevel 1 goto fail

echo.
echo ============================================================
echo  Setup completed successfully.
echo  Next step: double-click  run.bat  to start the system.
echo ============================================================
pause
exit /b 0

:fail
echo.
echo *** Setup failed. Please check the messages above. ***
pause
exit /b 1
