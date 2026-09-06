@echo off
setlocal
cd /d "%~dp0\..\.."

echo ============================================================================
echo MaterialAnalyzer - TickerLinker V1
echo Direct / Exact Company / Evidence / Theme Linking
echo ============================================================================
echo.
echo [1/2] TickerLinker smoke test
python -m MaterialAnalyzer.news.ticker_linker_smoke_test
if errorlevel 1 (
  echo.
  echo [ERROR] TickerLinker smoke test failed.
  if not "%NEWS_COLLECTOR_NO_PAUSE%"=="1" pause
  exit /b 1
)

echo.
echo [2/2] Incremental ticker linking
python -m MaterialAnalyzer.news.run_ticker_linker %*
set RC=%ERRORLEVEL%

echo.
if not "%RC%"=="0" (
  echo [ERROR] TickerLinker exited with code %RC%.
) else (
  echo [DONE] TickerLinker finished.
  echo Report    : MaterialAnalyzer\data\ticker_link_report.csv
  echo Unresolved: MaterialAnalyzer\data\ticker_link_unresolved.csv
)

echo.
if not "%NEWS_COLLECTOR_NO_PAUSE%"=="1" pause
exit /b %RC%
