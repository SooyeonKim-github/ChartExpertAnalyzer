@echo off
setlocal
cd /d "%~dp0\..\.."

echo ==========================================================
echo MaterialAnalyzer - NewsCollector V1.2 (7 live sources)
echo ==========================================================
echo.
echo [1/2] Local smoke test
python -m MaterialAnalyzer.news.smoke_test
if errorlevel 1 (
  echo.
  echo [ERROR] Smoke test failed. Collection was not started.
  exit /b 1
)

echo.
echo [2/2] Live collection
if "%OPENDART_API_KEY%"=="" (
  echo [WARN] OPENDART_API_KEY is not set. DART will report a configuration error.
)
python -m MaterialAnalyzer.news.main_collect
set RC=%ERRORLEVEL%

echo.
if not "%RC%"=="0" (
  echo [ERROR] NewsCollector exited with code %RC%.
) else (
  echo [DONE] NewsCollector finished.
)

echo.
echo Please share the 7 endpoint result lines and TOTAL line for verification.
exit /b %RC%
