@echo off
setlocal enabledelayedexpansion

echo ========================================================
echo   GitHub LinkedIn AI Publisher - Setup Script
echo ========================================================
echo.

:: 1. Check for Python
py -3.11 --version >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON_CMD=py -3.11
    goto :python_found
)

python --version >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON_CMD=python
    goto :python_found
)

echo [ERROR] Python 3.11 or compatible Python installation not found.
echo Please install Python 3.11 (64-bit) and ensure it is added to your PATH.
exit /b 1

:python_found
echo [INFO] Using Python: %PYTHON_CMD%
%PYTHON_CMD% --version

:: 2. Create Virtual Environment
if not exist ".venv" (
    echo [INFO] Creating Python virtual environment in .venv ...
    %PYTHON_CMD% -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        exit /b 1
    )
    echo [SUCCESS] Virtual environment created.
) else (
    echo [INFO] Existing virtual environment found in .venv.
)

:: 3. Install Dependencies
echo [INFO] Upgrading pip and installing required packages...
call .venv\Scripts\python.exe -m pip install --upgrade pip
call .venv\Scripts\pip.exe install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies.
    exit /b 1
)

:: Install prebuilt llama-cpp-python wheel for local GGUF models
echo [INFO] Installing prebuilt llama-cpp-python binary for local GGUF models...
call .venv\Scripts\pip.exe install llama-cpp-python --prefer-binary --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu


:: 4. Install Playwright Chromium Browser
echo [INFO] Installing Playwright Chromium browser for demo inspection...
call .venv\Scripts\playwright.exe install chromium
if %errorlevel% neq 0 (
    echo [WARNING] Playwright browser installation encountered a warning. Demo inspection may require manual browser download.
)

:: 5. Create local data directories
if not exist "data" mkdir data
if not exist "data\screenshots" mkdir data\screenshots

echo.
echo ========================================================
echo   Setup Complete!
echo ========================================================
echo Next steps:
echo   1. Run 'run.bat' to start the application and open the dashboard.
echo   2. Run 'test.bat' to execute the automated test suite.
echo ========================================================
echo.
