@echo off
setlocal
chcp 65001 >nul

set "HERE=%~dp0"
set "ROOT=%HERE%.."
set "PYTHON_EXE="

if exist "%ROOT%\KJBChartAnalyzer\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT%\KJBChartAnalyzer\.venv\Scripts\python.exe"
) else if exist "%ROOT%\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT%\.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

set "TARGET_DATE="
set /p TARGET_DATE=Target date YYYYMMDD (Enter=today): 

set "LOOKAHEAD=21"
set /p LOOKAHEAD=Schedule lookahead days (Enter=21): 
if "%LOOKAHEAD%"=="" set "LOOKAHEAD=21"

pushd "%ROOT%"

echo.
echo ============================================
echo   MaterialAnalyzer - ScheduleCollector
echo ============================================
echo Input     : Naver news + Policy Briefing
echo Extraction: explicit future date/time only
echo Lookahead : %LOOKAHEAD% days
echo ============================================
echo.

if "%TARGET_DATE%"=="" (
    "%PYTHON_EXE%" -m MaterialAnalyzer.main --sources naver,policy,schedule --schedule-lookahead %LOOKAHEAD%
) else (
    "%PYTHON_EXE%" -m MaterialAnalyzer.main --date %TARGET_DATE% --sources naver,policy,schedule --schedule-lookahead %LOOKAHEAD%
)

set "EXIT_CODE=%ERRORLEVEL%"
popd

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [FAILED] Schedule collection failed.
    pause
    exit /b %EXIT_CODE%
)

echo.
echo [DONE] Schedule collection completed.
pause
