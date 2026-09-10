@echo off
setlocal EnableExtensions

set "ROOT=%~dp0..\"
cd /d "%ROOT%"

where git >nul 2>nul
if errorlevel 1 (
    echo [WARN] Git was not found. Daily result push skipped.
    exit /b 0
)

git rev-parse --is-inside-work-tree >nul 2>nul
if errorlevel 1 (
    echo [WARN] Current directory is not a Git repository. Daily result push skipped.
    exit /b 0
)

set "FILES="
set "LATEST_CONFIRMED="
set "LATEST_LEADER="
set "LATEST_MATERIAL="

for /f "delims=" %%F in ('dir /b /a-d /o-d "results\today_confirmed_*.csv" 2^>nul') do if not defined LATEST_CONFIRMED set "LATEST_CONFIRMED=results\%%F"
for /f "delims=" %%F in ('dir /b /a-d /o-d "results\leader\today_issue_*.csv" 2^>nul') do if not defined LATEST_LEADER set "LATEST_LEADER=results\leader\%%F"
for /f "delims=" %%F in ('dir /b /a-d /o-d "results\material\today_issue_*.csv" 2^>nul') do if not defined LATEST_MATERIAL set "LATEST_MATERIAL=results\material\%%F"

call :ADD_IF_CHANGED "%LATEST_CONFIRMED%"
call :ADD_IF_CHANGED "%LATEST_LEADER%"
call :ADD_IF_CHANGED "%LATEST_MATERIAL%"

if not defined FILES (
    echo [INFO] No daily result changes to commit.
    exit /b 0
)

echo [INFO] Committing daily result files only...
git commit -m "Update daily screening results" -- %FILES%
if errorlevel 1 (
    echo [WARN] git commit failed. Check Git status manually.
    exit /b 0
)

echo [INFO] Pushing daily screening results...
git push
if errorlevel 1 (
    echo [WARN] git push failed. The commit remains local and can be pushed later.
    exit /b 0
)

echo [DONE] Daily screening results pushed.
exit /b 0

:ADD_IF_CHANGED
set "TARGET=%~1"
if "%TARGET%"=="" exit /b 0
if not exist "%TARGET%" exit /b 0
git status --porcelain -- "%TARGET%" | findstr /r "." >nul
if errorlevel 1 exit /b 0
git add -- "%TARGET%"
if errorlevel 1 exit /b 0
set FILES=%FILES% "%TARGET%"
exit /b 0
