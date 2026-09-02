@echo off
setlocal EnableExtensions
chcp 65001 > nul

set "HERE=%~dp0"
set "ROOT=%HERE%.."

set "PYTHON_EXE="
set "PYTHON_PREFIX="
if exist "%ROOT%\KJBChartAnalyzer\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT%\KJBChartAnalyzer\.venv\Scripts\python.exe"
) else if exist "%ROOT%\SwingChartProbabilityAnalyzer\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT%\SwingChartProbabilityAnalyzer\.venv\Scripts\python.exe"
) else if exist "%ROOT%\MAChartAnalyzer\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT%\MAChartAnalyzer\.venv\Scripts\python.exe"
) else (
    where py >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_EXE=py"
        set "PYTHON_PREFIX=-3"
    ) else (
        set "PYTHON_EXE=python"
    )
)

if "%PYTHON_EXE%"=="" exit /b 1

echo ============================================
echo   Dynamic PositionManager - Daily Plans
echo ============================================
echo CONFIRMED signals are re-evaluated using only known daily closes.
echo READY_BUY is executed on the following trading-day open.
echo ============================================
"%PYTHON_EXE%" %PYTHON_PREFIX% "%HERE%main.py" screen
if errorlevel 1 (
    echo [FAILED] PositionManager screen failed.
    pause
    exit /b 1
)
pause
exit /b 0
