@echo off
setlocal
cd /d "%~dp0\..\.."

echo ============================================================================
echo MaterialAnalyzer - MaterialScorer V1.1
echo Deterministic 100 Point Material Score + Routine Governance Guard
echo ============================================================================
echo.
echo [1/2] MaterialScorer smoke test
python -m MaterialAnalyzer.news.material_scorer_smoke_test
if errorlevel 1 (
  echo.
  echo [ERROR] MaterialScorer smoke test failed.
  if not "%NEWS_COLLECTOR_NO_PAUSE%"=="1" pause
  exit /b 1
)

echo.
echo [2/2] Incremental material scoring
python -m MaterialAnalyzer.news.run_material_scorer %*
set RC=%ERRORLEVEL%

echo.
if not "%RC%"=="0" (
  echo [ERROR] MaterialScorer exited with code %RC%.
) else (
  echo [DONE] MaterialScorer finished.
  echo Report: MaterialAnalyzer\data\material_score_report.csv
)

echo.
if not "%NEWS_COLLECTOR_NO_PAUSE%"=="1" pause
exit /b %RC%
