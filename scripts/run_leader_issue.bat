@echo off
setlocal EnableExtensions
chcp 65001 >nul

set "ROOT=%~dp0..\"
cd /d "%ROOT%"

set "LEADER_TOP_N=%~1"
if "%LEADER_TOP_N%"=="" set "LEADER_TOP_N=100"

set "PYTHON_EXE="
if exist "%ROOT%LeaderStockAnalyzer\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT%LeaderStockAnalyzer\.venv\Scripts\python.exe"
) else if exist "%ROOT%KJBChartAnalyzer\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT%KJBChartAnalyzer\.venv\Scripts\python.exe"
) else (
    where py >nul 2>nul
    if not errorlevel 1 set "PYTHON_EXE=py -3"
    if not defined PYTHON_EXE set "PYTHON_EXE=python"
)

echo ============================================
echo   LeaderStockAnalyzer - Independent Issue Run
echo ============================================
echo TOP N : %LEADER_TOP_N%
echo.

pushd "%ROOT%LeaderStockAnalyzer"
%PYTHON_EXE% main.py --top-n %LEADER_TOP_N%
set "RC=%ERRORLEVEL%"
popd
if not "%RC%"=="0" (
    echo [WARN] LeaderStockAnalyzer failed with code %RC%.
    exit /b %RC%
)

%PYTHON_EXE% "%ROOT%scripts\export_leader_today_issue.py"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" exit /b %RC%

echo [DONE] Leader issue pipeline completed.
exit /b 0
