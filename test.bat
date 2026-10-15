@echo off
setlocal

echo ========================================================
echo   GitHub LinkedIn AI Publisher - Running Test Suite
echo ========================================================
echo.

if not exist ".venv\Scripts\pytest.exe" (
    echo [ERROR] pytest not found in virtual environment. Please run setup.bat first.
    exit /b 1
)

call .venv\Scripts\pytest.exe -v --tb=short
if %errorlevel% equ 0 (
    echo.
    echo [SUCCESS] All tests passed!
) else (
    echo.
    echo [FAILURE] Some tests failed. Please inspect the output above.
)
exit /b %errorlevel%
