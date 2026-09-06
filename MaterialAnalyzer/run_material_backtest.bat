@echo off
setlocal
cd /d "%~dp0\.."

echo ==============================================================================
echo MaterialAnalyzer - MaterialBacktester V1
echo D+1 / D+5 / D+10 / D+20 / D+40 / D+60
echo ==============================================================================
echo.
echo [1/2] Smoke test
python -m MaterialAnalyzer.material_backtest_smoke_test
if errorlevel 1 (
  echo.
  echo [ERROR] MaterialBacktester smoke test failed.
  pause
  exit /b 1
)

echo.
echo [2/2] Historical material backtest
python -m MaterialAnalyzer.run_material_backtest %*
set RC=%ERRORLEVEL%

echo.
if not "%RC%"=="0" (
  echo [ERROR] MaterialBacktester exited with code %RC%.
) else (
  echo [DONE] MaterialBacktester finished.
  echo Results : MaterialAnalyzer\data\history\backtest\material_backtest_results.csv
  echo Summary : MaterialAnalyzer\data\history\backtest\material_backtest_summary.csv
  echo Errors  : MaterialAnalyzer\data\history\backtest\material_backtest_errors.csv
)

echo.
pause
exit /b %RC%
