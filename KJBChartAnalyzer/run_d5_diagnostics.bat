@echo off
setlocal
cd /d "%~dp0"

echo ==============================================================
echo KJB D+5 Diagnostics + OverextensionPenalty
echo ==============================================================
echo.

python d5_diagnostics.py %*

if errorlevel 1 (
    echo.
    echo [ERROR] D+5 diagnostics failed.
    pause
    exit /b 1
)

echo.
echo [DONE] KJB D+5 diagnostics completed.
pause
