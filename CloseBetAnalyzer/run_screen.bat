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

set "TOP_N=100"
set "SORT_BY=trading_value"

echo ============================================
echo   CloseBetAnalyzer V1
echo ============================================
echo Candidate selection : completed daily data
echo Buy-day decision     : manual price guide only
echo Universe TOP N       : %TOP_N%
echo Sort by              : %SORT_BY%
echo ============================================
echo.

"%PYTHON_EXE%" "%HERE%main.py" --top-n %TOP_N% --sort-by %SORT_BY%
if errorlevel 1 (
    echo.
    echo [FAILED] CloseBetAnalyzer screening failed.
    pause
    exit /b 1
)

echo.
echo [DONE] CloseBetAnalyzer screening completed.
pause
