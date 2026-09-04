@echo off
setlocal
cd /d "%~dp0\..\.."

echo ============================================================================
echo MaterialAnalyzer - ArticleCluster V1 (Rule Based Only)
echo Semantic Similarity / Embedding: DISABLED
echo ============================================================================
echo.
echo [1/2] Cluster smoke test
python -m MaterialAnalyzer.news.cluster_smoke_test
if errorlevel 1 (
  echo.
  echo [ERROR] Cluster smoke test failed.
  if not "%NEWS_COLLECTOR_NO_PAUSE%"=="1" pause
  exit /b 1
)

echo.
echo [2/2] Incremental article clustering
python -m MaterialAnalyzer.news.run_article_cluster
set RC=%ERRORLEVEL%

echo.
if not "%RC%"=="0" (
  echo [ERROR] ArticleCluster exited with code %RC%.
) else (
  echo [DONE] ArticleCluster finished.
  echo Report: MaterialAnalyzer\data\cluster_report.csv
)

echo.
if not "%NEWS_COLLECTOR_NO_PAUSE%"=="1" pause
exit /b %RC%
