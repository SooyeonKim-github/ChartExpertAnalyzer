@echo off
setlocal
cd /d "%~dp0\.."

echo ==============================================================================
echo MaterialAnalyzer - HistoricalMaterialRangeCollector V1.2
echo Fast DART Bulk / Point-in-Time / Resume / Material Prefilter / Derived Rebuild
echo ==============================================================================
echo.
echo [1/2] Smoke test
python -m MaterialAnalyzer.history_smoke_test
if errorlevel 1 (
  echo.
  echo [ERROR] Historical range smoke test failed.
  pause
  exit /b 1
)

echo.
echo [2/2] Historical range pipeline
python -m MaterialAnalyzer.run_material_range %*
set RC=%ERRORLEVEL%

echo.
if not "%RC%"=="0" (
  echo [ERROR] Historical material range exited with code %RC%.
) else (
  echo [DONE] Historical material range finished.
  echo DB       : MaterialAnalyzer\data\history\material_history.db
  echo History  : MaterialAnalyzer\data\history\material_history.csv
  echo Backtest : MaterialAnalyzer\data\history\material_history_backtest.csv
  echo Coverage : MaterialAnalyzer\data\history\historical_source_coverage.csv
  echo.
  echo Modes:
  echo   --collect-only  : resume/collect raw history only
  echo   --derive-only   : reuse raw history and rebuild derived layers only
  echo.
  echo Next:
  echo   MaterialAnalyzer\run_material_backtest.bat
)

echo.
pause
exit /b %RC%
