@echo off
setlocal EnableExtensions
chcp 65001 > nul
cd /d "%~dp0"

set "TICKER=%~1"
set "PROVIDER=%~2"

if "%TICKER%"=="" set "TICKER=005930"
if "%PROVIDER%"=="" set "PROVIDER=pykrx"

set "PYTHON_EXE="
set "PYTHON_PREFIX="

if exist "%CD%\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
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
    echo [ERROR] Python was not found.
    echo Install Python or create .venv in this project folder.
    pause
    exit /b 1
)


set "PROVIDER_ARG="
set "ANALYZE_TICKER=%TICKER%"

if /I not "%PROVIDER%"=="default" (
    set "PROVIDER_ARG=--provider %PROVIDER%"
) else (
    echo %TICKER% | findstr /C:"." >nul
    if errorlevel 1 set "ANALYZE_TICKER=%TICKER%.KS"
)

echo [INFO] Single stock analysis
echo [INFO] Ticker   : %ANALYZE_TICKER%
echo [INFO] Provider : %PROVIDER%
echo.

"%PYTHON_EXE%" %PYTHON_PREFIX% app.py analyze ^
    %PROVIDER_ARG% ^
    --ticker "%ANALYZE_TICKER%" ^
    --market ^KS11 ^
    --period 5y ^
    --out "output\%ANALYZE_TICKER%.json" ^
    --chart "output\%ANALYZE_TICKER%.png" ^
    --report "output\%ANALYZE_TICKER%.html"

if errorlevel 1 (
    echo.
    echo [ERROR] Analysis failed.
    pause
    exit /b 1
)

echo.
echo [DONE] Analysis finished.
echo [DONE] output\%ANALYZE_TICKER%.json
echo [DONE] output\%ANALYZE_TICKER%.png
echo [DONE] output\%ANALYZE_TICKER%.html
pause
exit /b 0
