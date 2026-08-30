@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 > nul
cd /d "%~dp0"

echo ============================================
echo   Chart Expert Analyzer - Run All Screens
echo ============================================
echo.

rem Child run_screen.bat files must not pause or ask interactive questions.
set "NO_PAUSE=1"

set /a TOTAL=0
for /d %%D in ("%~dp0*") do (
    if exist "%%~fD\run_screen.bat" set /a TOTAL+=1
)

if !TOTAL! EQU 0 (
    echo [ERROR] No analyzer run_screen.bat files were found.
    set "NO_PAUSE="
    pause
    exit /b 1
)

echo [INFO] Found !TOTAL! analyzer screen scripts.
echo.

set /a CURRENT=0
for /d %%D in ("%~dp0*") do (
    if exist "%%~fD\run_screen.bat" (
        set /a CURRENT+=1
        echo ============================================
        echo [!CURRENT!/!TOTAL!] Running %%~nxD\run_screen.bat ...
        echo ============================================
        call "%%~fD\run_screen.bat"
        if errorlevel 1 (
            echo.
            echo [ERROR] %%~nxD screening failed.
            goto RUN_FAILED
        )
        echo.
        echo [OK] %%~nxD screening finished.
        echo.
    )
)

echo ============================================
echo [POST] Aggregating confirmed candidates ...
echo ============================================

set "AGG_PYTHON="
set "AGG_PREFIX="

if exist "%~dp0KJBChartAnalyzer\.venv\Scripts\python.exe" (
    set "AGG_PYTHON=%~dp0KJBChartAnalyzer\.venv\Scripts\python.exe"
) else if exist "%~dp0SwingChartProbabilityAnalyzer\.venv\Scripts\python.exe" (
    set "AGG_PYTHON=%~dp0SwingChartProbabilityAnalyzer\.venv\Scripts\python.exe"
) else if exist "%~dp0MAChartAnalyzer\.venv\Scripts\python.exe" (
    set "AGG_PYTHON=%~dp0MAChartAnalyzer\.venv\Scripts\python.exe"
) else (
    where py >nul 2>nul
    if not errorlevel 1 (
        set "AGG_PYTHON=py"
        set "AGG_PREFIX=-3"
    ) else (
        where python >nul 2>nul
        if not errorlevel 1 set "AGG_PYTHON=python"
    )
)

if not defined AGG_PYTHON (
    echo [ERROR] Python was not found for confirmed candidate aggregation.
    goto RUN_FAILED
)

"!AGG_PYTHON!" !AGG_PREFIX! "%~dp0scripts\aggregate_confirmed_candidates.py"
if errorlevel 1 (
    echo [ERROR] Confirmed candidate aggregation failed.
    goto RUN_FAILED
)

set "NO_PAUSE="

echo.
echo ============================================
echo [DONE] All analyzer screenings finished.
echo ============================================
echo [Confirmed Summary]
echo   results\confirmed_candidates.csv
echo.
echo [KJB Agent]
echo   KJBChartAnalyzer\output\agent\candidates.json
echo   KJBChartAnalyzer\output\agent\candidates.md
echo   KJBChartAnalyzer\output\confirmed_charts\
echo.
echo [Siyoon Agent]
echo   SwingChartProbabilityAnalyzer\results\YYYYMMDD\agent\candidates.json
echo   SwingChartProbabilityAnalyzer\results\YYYYMMDD\agent\candidates.md
echo   STRONG_CONFIRMED is ranked first in candidates/charts.
echo.
echo [MA Analyzer]
echo   MAChartAnalyzer\results\YYYYMMDD\scan_results.csv
echo   MAChartAnalyzer\results\YYYYMMDD\candidates.csv
echo   MAChartAnalyzer\results\YYYYMMDD\ma_candidates.xlsx
echo ============================================
pause
exit /b 0

:RUN_FAILED
set "NO_PAUSE="
echo.
echo ============================================
echo [FAILED] Run All Screens stopped because one analyzer failed.
echo ============================================
pause
exit /b 1
