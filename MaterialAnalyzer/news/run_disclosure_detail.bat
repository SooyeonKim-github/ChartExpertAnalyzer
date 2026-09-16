@echo off
setlocal
chcp 65001 >nul

set "HERE=%~dp0"
set "ROOT=%HERE%..\.."
set "PYTHON_EXE="

if exist "%ROOT%\KJBChartAnalyzer\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT%\KJBChartAnalyzer\.venv\Scripts\python.exe"
) else if exist "%ROOT%\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT%\.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

pushd "%ROOT%"
"%PYTHON_EXE%" -m MaterialAnalyzer.news.run_disclosure_detail %*
set "EXIT_CODE=%ERRORLEVEL%"
popd

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [FAILED] DisclosureDetailEnricher failed.
    exit /b %EXIT_CODE%
)

echo.
echo [DONE] DisclosureDetailEnricher completed.
exit /b 0
