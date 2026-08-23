@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found in PATH.
    pause
    exit /b 1
)

set "NEED_CODEX=1"
if /I "%~1"=="--dry-run" set "NEED_CODEX=0"

if "%NEED_CODEX%"=="1" (
    where codex >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] Codex CLI was not found in PATH.
        echo Install/sign in to Codex CLI first, or run with --dry-run.
        pause
        exit /b 1
    )
)

if "%~1"=="" (
    echo [Self-Improvement] Codex round-robin review + safe apply mode
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
echo [DONE] Codex self-improvement review completed.
echo Reports: reports\self-improvement\
pause
endlocal
