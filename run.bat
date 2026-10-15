@echo off
setlocal

echo ========================================================
echo   GitHub LinkedIn AI Publisher - Starting Application
echo ========================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found. Please run setup.bat first.
    pause
    exit /b 1
)

:: Create data directory if not exists
if not exist "data" mkdir data
if not exist "data\screenshots" mkdir data\screenshots

echo [INFO] Binding to localhost (127.0.0.1:8000)...
echo [INFO] Press Ctrl+C in this window to stop the server.
echo.

:: Launch browser after a short delay
start "" http://127.0.0.1:8000

:: Start Uvicorn bound strictly to 127.0.0.1
call .venv\Scripts\python.exe -m uvicorn src.publisher.main:app --host 127.0.0.1 --port 8000 --log-level info

echo.
echo Application stopped.
