@echo off
setlocal
cd /d "%~dp0\..\.."

echo ============================================================================
echo MaterialAnalyzer - NoveltyAnalyzer V1
echo Rule Based Event Family / Delta Analysis
echo ============================================================================
echo.
echo [1/2] NoveltyAnalyzer smoke test
python -m MaterialAnalyzer.news.novelty_smoke_test
if errorlevel 1 (
  echo.
  echo [ERROR] NoveltyAnalyzer smoke test failed.
  if not "%NEWS_COLLECTOR_NO_PAUSE%"=="1" pause
  exit /b 1
)

echo.
echo [2/2] Novelty analysis
python -m MaterialAnalyzer.news.run_novelty_analyzer %*
set RC=%ERRORLEVEL%

echo.
if not "%RC%"=="0" (
  echo [ERROR] NoveltyAnalyzer exited with code %RC%.
) else (
  echo [DONE] NoveltyAnalyzer finished.
  echo Report: MaterialAnalyzer\data\novelty_report.csv
)

echo.
if not "%NEWS_COLLECTOR_NO_PAUSE%"=="1" pause
exit /b %RC%
