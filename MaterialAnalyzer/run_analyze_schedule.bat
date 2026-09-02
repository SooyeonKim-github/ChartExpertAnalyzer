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
set /p TARGET_DATE=Scan date YYYYMMDD (Enter=today): 

pushd "%ROOT%"

echo.
echo ============================================
echo   MaterialAnalyzer - Schedule Analysis
echo ============================================
echo Importance + Theme + Stock mapping
echo ============================================
echo.

if "%TARGET_DATE%"=="" (
    "%PYTHON_EXE%" -m MaterialAnalyzer.analyze_schedule
) else (
    "%PYTHON_EXE%" -m MaterialAnalyzer.analyze_schedule --date %TARGET_DATE%
)

set "EXIT_CODE=%ERRORLEVEL%"
popd

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [FAILED] Schedule analysis failed.
    pause
    exit /b %EXIT_CODE%
)

echo.
echo [DONE] Schedule analysis completed.
pause
