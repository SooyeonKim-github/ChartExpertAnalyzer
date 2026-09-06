@echo off
setlocal
cd /d "%~dp0\..\.."

echo ============================================================================
echo MaterialAnalyzer - KRX TickerMaster Builder
echo KOSPI + KOSDAQ exact company/ticker master
echo ============================================================================
echo.
python -m MaterialAnalyzer.news.build_ticker_master %*
set RC=%ERRORLEVEL%
echo.
if not "%RC%"=="0" (
  echo [ERROR] TickerMaster build failed with code %RC%.
) else (
  echo [DONE] TickerMaster build finished.
  echo File: MaterialAnalyzer\data\reference\ticker_master.csv
)
echo.
if not "%NEWS_COLLECTOR_NO_PAUSE%"=="1" pause
exit /b %RC%
