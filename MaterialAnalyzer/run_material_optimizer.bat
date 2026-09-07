@echo off
setlocal
cd /d "%~dp0\.."

echo ==============================================================================
echo MaterialAnalyzer - MaterialThresholdOptimizer V1
echo Candidate weights / thresholds / validation only - NO AUTO APPLY
echo ==============================================================================
echo.
echo [1/2] Smoke test
python -m MaterialAnalyzer.material_optimizer_smoke_test
if errorlevel 1 (
  echo.
  echo [ERROR] MaterialThresholdOptimizer smoke test failed.
  pause
  exit /b 1
)

echo.
echo [2/2] Material optimizer
python -m MaterialAnalyzer.run_material_optimizer %*
set RC=%ERRORLEVEL%

echo.
if not "%RC%"=="0" (
  echo [ERROR] MaterialThresholdOptimizer exited with code %RC%.
) else (
  echo [DONE] MaterialThresholdOptimizer finished.
  echo Weights        : MaterialAnalyzer\data\history\optimizer\material_optimizer_weights.csv
  echo Candidates     : MaterialAnalyzer\data\history\optimizer\material_optimizer_candidates.csv
  echo Validation     : MaterialAnalyzer\data\history\optimizer\material_optimizer_validation.csv
  echo Scored         : MaterialAnalyzer\data\history\optimizer\material_optimizer_scored.csv
  echo Recommendation : MaterialAnalyzer\data\history\optimizer\material_optimizer_recommendation.json
  echo.
  echo IMPORTANT: optimized values are candidates only. MaterialScorer is NOT modified automatically.
)

echo.
pause
exit /b %RC%
