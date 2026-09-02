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

pushd "%ROOT%"

echo.
echo ============================================
echo   MaterialAnalyzer V1 - Collector
echo ============================================
echo News   : Naver Search API
echo Policy : Korea Policy Briefing
echo Filing : OpenDART
echo ============================================
echo.

if "%TARGET_DATE%"=="" (
    "%PYTHON_EXE%" -m MaterialAnalyzer.main
) else (
    "%PYTHON_EXE%" -m MaterialAnalyzer.main --date %TARGET_DATE%
)

set "EXIT_CODE=%ERRORLEVEL%"
popd

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [FAILED] Material collection failed.
    pause
    exit /b %EXIT_CODE%
)

echo.
echo [DONE] Material collection completed.
pause
