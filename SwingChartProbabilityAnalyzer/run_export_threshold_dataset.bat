@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
    echo [INFO] Creating virtual environment...
    py -3 -m venv .venv 2>nul
    if errorlevel 1 python -m venv .venv
)

.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo.
echo ============================================
echo  Swing Threshold Dataset Export
echo ============================================
echo Example:
echo   range_20210101_20260901
echo   results\range_20210101_20260901
echo   results\range_20210101_20260901\range_all_results.csv
echo.
set /p RANGE_INPUT=Range folder/file ^(Enter=latest modified range^): 

if "%RANGE_INPUT%"=="" (
    .venv\Scripts\python.exe export_threshold_dataset.py
) else (
    .venv\Scripts\python.exe export_threshold_dataset.py --range-file "%RANGE_INPUT%"
)
if errorlevel 1 goto :error

echo.
echo [DONE] Threshold-only CSV shards were created under the range folder's threshold_input directory.
echo [NEXT] Run push_threshold_dataset.bat to commit/push only those small files.
pause
exit /b 0

:error
echo.
echo [ERROR] Threshold dataset export failed.
pause
exit /b 1
