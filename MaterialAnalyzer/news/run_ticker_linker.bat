@echo off
setlocal
cd /d "%~dp0\..\.."

echo ============================================================================
echo MaterialAnalyzer - TickerLinker V1.2
echo Robust TickerMaster / Exact Company / Material Theme Linking
echo ============================================================================
echo.
echo [0/3] Refresh KOSPI/KOSDAQ ticker master if stale
python -m MaterialAnalyzer.news.build_ticker_master --if-stale-days 7 --best-effort

echo.
echo [1/3] TickerLinker smoke test
python -m MaterialAnalyzer.news.ticker_linker_smoke_test
if errorlevel 1 (
  echo.
  echo [ERROR] TickerLinker smoke test failed.
  if not "%NEWS_COLLECTOR_NO_PAUSE%"=="1" pause
  exit /b 1
)

echo.
echo [2/3] Incremental ticker linking
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
