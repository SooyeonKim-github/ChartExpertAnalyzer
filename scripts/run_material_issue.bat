@echo off
setlocal EnableExtensions
chcp 65001 >nul

set "ROOT=%~dp0..\"
cd /d "%ROOT%"

set "PYTHON_EXE="
set "PYTHON_PREFIX="
if exist "%ROOT%MaterialAnalyzer\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT%MaterialAnalyzer\.venv\Scripts\python.exe"
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
    echo [WARN] Python was not found for MaterialAnalyzer.
    exit /b 1
)

"%PYTHON_EXE%" %PYTHON_PREFIX% -c "import pandas, requests, bs4, pykrx, FinanceDataReader" >nul 2>nul
if errorlevel 1 (
    echo [INFO] Installing MaterialAnalyzer requirements...
    "%PYTHON_EXE%" %PYTHON_PREFIX% -m pip install -r "%ROOT%MaterialAnalyzer\requirements.txt"
    if errorlevel 1 exit /b 1
)

echo ============================================
echo   MaterialAnalyzer - Independent Issue Run
echo ============================================
echo Pipeline: News -^> Cluster -^> Event -^> Novelty -^> Score -^> TickerLink
echo.

"%PYTHON_EXE%" %PYTHON_PREFIX% -m MaterialAnalyzer.news.main_collect
if errorlevel 1 exit /b 1
"%PYTHON_EXE%" %PYTHON_PREFIX% -m MaterialAnalyzer.news.run_article_cluster
if errorlevel 1 exit /b 1
"%PYTHON_EXE%" %PYTHON_PREFIX% -m MaterialAnalyzer.news.run_event_extractor
if errorlevel 1 exit /b 1
"%PYTHON_EXE%" %PYTHON_PREFIX% -m MaterialAnalyzer.news.run_novelty_analyzer
if errorlevel 1 exit /b 1
"%PYTHON_EXE%" %PYTHON_PREFIX% -m MaterialAnalyzer.news.run_material_scorer
if errorlevel 1 exit /b 1
"%PYTHON_EXE%" %PYTHON_PREFIX% -m MaterialAnalyzer.news.run_ticker_linker
if errorlevel 1 exit /b 1

"%PYTHON_EXE%" %PYTHON_PREFIX% "%ROOT%scripts\export_material_today_issue.py"
if errorlevel 1 exit /b 1

echo [DONE] Material issue pipeline completed.
exit /b 0
