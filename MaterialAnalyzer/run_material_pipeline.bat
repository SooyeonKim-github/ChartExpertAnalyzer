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

if "%TARGET_DATE%"=="" (
    "%PYTHON_EXE%" -m MaterialAnalyzer.main
    if errorlevel 1 goto :fail
    "%PYTHON_EXE%" -m MaterialAnalyzer.analyze_schedule
) else (
    "%PYTHON_EXE%" -m MaterialAnalyzer.main --date %TARGET_DATE%
    if errorlevel 1 goto :fail
    "%PYTHON_EXE%" -m MaterialAnalyzer.analyze_schedule --date %TARGET_DATE%
)
if errorlevel 1 goto :fail

popd
echo.
echo [DONE] Material collection + schedule analysis completed.
pause
exit /b 0

:fail
set "EXIT_CODE=%ERRORLEVEL%"
popd
echo.
echo [FAILED] Material pipeline failed.
pause
exit /b %EXIT_CODE%
