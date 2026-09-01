@echo off
setlocal EnableExtensions
chcp 65001 > nul
cd /d "%~dp0"

set "TOP_N=%~1"
if "%TOP_N%"=="" set "TOP_N=100"

set "PYTHON_EXE="
set "PYTHON_PREFIX="
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    where py >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_EXE=py"
        set "PYTHON_PREFIX=-3"
    ) else (
        set "PYTHON_EXE=python"
    )
)

"%PYTHON_EXE%" %PYTHON_PREFIX% main.py scan --top-n %TOP_N% --sort-by trading_value
set "ERR=%ERRORLEVEL%"
if not "%NO_PAUSE%"=="1" pause
exit /b %ERR%
