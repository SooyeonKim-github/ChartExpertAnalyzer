@echo off
setlocal EnableExtensions
chcp 65001 >nul

set "ROOT=%~dp0..\"
cd /d "%ROOT%"

set "LEADER_TOP_N=%~1"
if "%LEADER_TOP_N%"=="" set "LEADER_TOP_N=100"

set "PYTHON_EXE="
set "PYTHON_PREFIX="
if exist "%ROOT%LeaderStockAnalyzer\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT%LeaderStockAnalyzer\.venv\Scripts\python.exe"
) else if exist "%ROOT%KJBChartAnalyzer\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT%KJBChartAnalyzer\.venv\Scripts\python.exe"
) else (
    where py >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_EXE=py"
        set "PYTHON_PREFIX=-3"
    ) else (
        where python >nul 2>nul
        if not errorlevel 1 set "PYTHON_EXE=python"
    )
)

if "%PYTHON_EXE%"=="" (
    echo [WARN] Python was not found for LeaderStockAnalyzer.
    exit /b 1
)

"%PYTHON_EXE%" %PYTHON_PREFIX% -c "import pandas, numpy, yaml, openpyxl, pykrx" >nul 2>nul
if errorlevel 1 (
    echo [WARN] LeaderStockAnalyzer dependencies are missing.
    exit /b 1
)

echo ============================================
echo   LeaderStockAnalyzer - Independent Issue Run
echo ============================================
echo TOP N : %LEADER_TOP_N%
echo.

pushd "%ROOT%LeaderStockAnalyzer"
"%PYTHON_EXE%" %PYTHON_PREFIX% main.py --top-n %LEADER_TOP_N%
set "RC=%ERRORLEVEL%"
popd
if not "%RC%"=="0" (
    echo [WARN] LeaderStockAnalyzer failed with code %RC%.
    exit /b %RC%
)

"%PYTHON_EXE%" %PYTHON_PREFIX% "%ROOT%scripts\export_leader_today_issue.py"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" exit /b %RC%

echo [DONE] Leader issue pipeline completed.
exit /b 0
