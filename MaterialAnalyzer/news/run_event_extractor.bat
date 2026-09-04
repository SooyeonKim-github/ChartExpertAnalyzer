@echo off
setlocal
cd /d "%~dp0\..\.."

echo ============================================================================
echo MaterialAnalyzer - EventExtractor V1.1
echo Title First + Material Filter + Meaningful Numbers
echo ============================================================================
echo.
echo [1/2] EventExtractor smoke test
python -m MaterialAnalyzer.news.event_smoke_test
if errorlevel 1 (
  echo.
  echo [ERROR] EventExtractor smoke test failed.
  if not "%NEWS_COLLECTOR_NO_PAUSE%"=="1" pause
  exit /b 1
)

echo.
echo [2/2] Incremental event extraction
python -m MaterialAnalyzer.news.run_event_extractor
set RC=%ERRORLEVEL%

echo.
if not "%RC%"=="0" (
  echo [ERROR] EventExtractor exited with code %RC%.
) else (
  echo [DONE] EventExtractor finished.
  echo Report: MaterialAnalyzer\data\event_report.csv
)

echo.
if not "%NEWS_COLLECTOR_NO_PAUSE%"=="1" pause
exit /b %RC%
