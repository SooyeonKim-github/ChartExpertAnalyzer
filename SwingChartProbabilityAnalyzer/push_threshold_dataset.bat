@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
    echo [INFO] Creating virtual environment...
    py -3 -m venv .venv 2>nul
    if errorlevel 1 python -m venv .venv
)

rem Refuse to mix unrelated staged work into the threshold-data commit.
git diff --cached --quiet
if errorlevel 1 (
    echo [ERROR] There are already staged changes in this repository.
    echo         Commit or unstage them before running this script.
    pause
    exit /b 1
)

rem GitHub rejects any blob above 100 MB. Abort early if current HEAD already
rem contains a large local-only result commit that would be pushed in history.
.venv\Scripts\python.exe -c "import subprocess,sys; out=subprocess.check_output(['git','ls-tree','-r','-l','HEAD'], text=True, errors='replace'); bad=[]; [bad.append((int(p[3]),p[4])) for line in out.splitlines() if len((p:=line.split(None,4)))==5 and p[3].isdigit() and int(p[3])>95*1024*1024]; [print(f'[LARGE IN HEAD] {s/1024/1024:.1f} MB  {n}') for s,n in bad]; sys.exit(1 if bad else 0)"
if errorlevel 1 (
    echo.
    echo [ERROR] Current HEAD already contains files larger than 95 MB.
    echo         If the last commit is the failed long-range result commit, run:
    echo         git reset --soft HEAD~1
    echo         git reset
    echo         Then run this script again.
    pause
    exit /b 1
)

echo.
set /p RANGE_NAME=Range folder name under results ^(example: range_20210101_20260901^): 
if "%RANGE_NAME%"=="" (
    echo [ERROR] Range folder name is required.
    pause
    exit /b 1
)

set "TARGET_DIR=results\%RANGE_NAME%\threshold_input"
if not exist "%TARGET_DIR%\manifest.csv" (
    echo [ERROR] %TARGET_DIR%\manifest.csv not found.
    echo         Run run_export_threshold_dataset.bat first.
    pause
    exit /b 1
)

rem Ensure every generated shard is comfortably below GitHub's 100 MB limit.
.venv\Scripts\python.exe -c "import sys; from pathlib import Path; p=Path(sys.argv[1]); bad=[f for f in p.glob('*') if f.is_file() and f.stat().st_size>95*1024*1024]; [print(f'[TOO LARGE] {f.stat().st_size/1024/1024:.1f} MB  {f}') for f in bad]; sys.exit(1 if bad else 0)" "%TARGET_DIR%"
if errorlevel 1 (
    echo [ERROR] At least one threshold dataset file is too large for GitHub.
    echo         Re-export with a smaller --rows-per-file value.
    pause
    exit /b 1
)

echo [INFO] Staging threshold_input only...
git add -f -- "%TARGET_DIR%"
if errorlevel 1 goto :error

git diff --cached --quiet
if not errorlevel 1 (
    echo [INFO] Nothing new to commit in %TARGET_DIR%.
    pause
    exit /b 0
)

git commit -m "Add Swing threshold dataset %RANGE_NAME%"
if errorlevel 1 goto :error

set "BRANCH_SUFFIX=%RANGE_NAME:range_=%"
set "DATA_BRANCH=swing-threshold-data-%BRANCH_SUFFIX%"
echo.
echo [INFO] Pushing to dedicated branch: %DATA_BRANCH%
git push origin HEAD:%DATA_BRANCH%
if errorlevel 1 goto :error

echo.
echo ============================================
echo  Threshold dataset push complete
 echo ============================================
echo Branch: %DATA_BRANCH%
echo Only files under %TARGET_DIR% were staged by this script.
pause
exit /b 0

:error
echo.
echo [ERROR] Threshold dataset commit/push failed.
pause
exit /b 1
