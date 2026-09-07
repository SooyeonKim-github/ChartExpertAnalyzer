@echo off
setlocal
cd /d "%~dp0\.."

echo ==============================================================================
echo MaterialAnalyzer - MaterialQualityOptimizer V1
echo Catalyst quality / taxonomy / linkage / coverage audit - NO RETURN OBJECTIVE
echo ==============================================================================
echo.
echo [1/2] Smoke test
python -m MaterialAnalyzer.material_optimizer_smoke_test
if errorlevel 1 (
  echo.
  echo [ERROR] MaterialQualityOptimizer smoke test failed.
  pause
  exit /b 1
)

echo.
echo [2/2] Material quality optimizer
python -m MaterialAnalyzer.run_material_optimizer %*
set RC=%ERRORLEVEL%

echo.
if not "%RC%"=="0" (
  echo [ERROR] MaterialQualityOptimizer exited with code %RC%.
) else (
  echo [DONE] MaterialQualityOptimizer finished.
  echo Metrics        : MaterialAnalyzer\data\history\quality_optimizer\material_quality_metrics.csv
  echo Event Types    : MaterialAnalyzer\data\history\quality_optimizer\material_quality_event_types.csv
  echo Thresholds     : MaterialAnalyzer\data\history\quality_optimizer\material_quality_threshold_candidates.csv
  echo Comparison     : MaterialAnalyzer\data\history\quality_optimizer\material_quality_threshold_comparison.csv
  echo Recommendation : MaterialAnalyzer\data\history\quality_optimizer\material_quality_recommendation.json
  echo.
  echo FORWARD RETURNS ARE NOT USED BY THIS OPTIMIZER.
  echo Candidate thresholds are audit suggestions only. MaterialScorer is NOT modified automatically.
)

echo.
pause
exit /b %RC%
