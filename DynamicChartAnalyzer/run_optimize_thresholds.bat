@echo off
setlocal
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
    echo [INFO] Creating virtual environment...
    py -3 -m venv .venv 2>nul
    if errorlevel 1 python -m venv .venv
)

.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo.
echo [Dynamic V2.3 Stage-aware Threshold Optimizer]
echo Stage1, Stage2, Stage3 will be optimized separately.
set /p RANGE_FILE=Range CSV path ^(Enter=latest^): 

for %%S in (1 2 3) do (
    echo.
    echo ============================================================
    echo [INFO] Optimizing Stage %%S
    echo ============================================================
    if "%RANGE_FILE%"=="" (
        .venv\Scripts\python.exe run_threshold_optimizer.py --stage %%S
    ) else (
        .venv\Scripts\python.exe run_threshold_optimizer.py --stage %%S --range-file "%RANGE_FILE%"
    )
    if errorlevel 1 goto :error
)

echo.
echo ============================================================
echo [DONE] Stage1 / Stage2 / Stage3 optimization completed.
echo Check results\range_*\optimizer\stage1~stage3 folders.
echo ============================================================
pause
exit /b 0

:error
echo.
echo [ERROR] Dynamic threshold optimization failed.
pause
exit /b 1
