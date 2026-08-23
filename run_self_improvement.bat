@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found in PATH.
    pause
    exit /b 1
)

if "%~1"=="" (
    echo [Self-Improvement] Round-robin review + safe apply mode
    python scripts\run_self_improvement.py --apply
) else (
    echo [Self-Improvement] Custom mode: %*
    python scripts\run_self_improvement.py %*
)

set ERR=%ERRORLEVEL%
if not "%ERR%"=="0" (
    echo [ERROR] Self-improvement loop failed. ExitCode=%ERR%
    pause
    exit /b %ERR%
)

echo.
echo [DONE] Self-improvement review completed.
echo Reports: reports\self-improvement\
pause
endlocal
