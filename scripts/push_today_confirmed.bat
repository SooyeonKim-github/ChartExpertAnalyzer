@echo off
setlocal EnableExtensions

set "ROOT=%~dp0..\"
cd /d "%ROOT%"

set "TODAY_CONFIRMED_FILE="
for /f "delims=" %%F in ('dir /b /a-d /o-d "results\today_confirmed_*.csv" 2^>nul') do if not defined TODAY_CONFIRMED_FILE set "TODAY_CONFIRMED_FILE=%%F"

if not defined TODAY_CONFIRMED_FILE (
    echo [WARN] No today_confirmed_YYYYMMDD.csv file found. Git push skipped.
    exit /b 0
)

where git >nul 2>nul
if errorlevel 1 (
    echo [WARN] Git was not found. %TODAY_CONFIRMED_FILE% remains local.
    exit /b 0
)

git rev-parse --is-inside-work-tree >nul 2>nul
if errorlevel 1 (
    echo [WARN] Current directory is not a Git repository. %TODAY_CONFIRMED_FILE% remains local.
    exit /b 0
)

git status --porcelain -- "results/%TODAY_CONFIRMED_FILE%" | findstr /r "." >nul
if errorlevel 1 (
    echo [INFO] %TODAY_CONFIRMED_FILE% has no Git changes. Push skipped.
    exit /b 0
)

echo [INFO] Adding %TODAY_CONFIRMED_FILE% to Git...
git add -- "results/%TODAY_CONFIRMED_FILE%"
if errorlevel 1 (
    echo [WARN] git add failed. %TODAY_CONFIRMED_FILE% remains local.
    exit /b 0
)

REM Commit only the generated daily file so unrelated staged changes are not included.
git commit -m "Update %TODAY_CONFIRMED_FILE%" -- "results/%TODAY_CONFIRMED_FILE%"
if errorlevel 1 (
    echo [WARN] git commit failed. Check Git status manually.
    exit /b 0
)

echo [INFO] Pushing %TODAY_CONFIRMED_FILE%...
git push
if errorlevel 1 (
    echo [WARN] git push failed. The commit remains local and can be pushed later.
    exit /b 0
)

echo [DONE] Pushed results/%TODAY_CONFIRMED_FILE%
exit /b 0
