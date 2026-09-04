@echo off
setlocal
cd /d "%~dp0\..\.."

echo ==========================================================
echo MaterialAnalyzer - NewsCollector V1
echo ==========================================================

python -m MaterialAnalyzer.news.main_collect
set RC=%ERRORLEVEL%

echo.
if not "%RC%"=="0" (
  echo [ERROR] NewsCollector exited with code %RC%.
) else (
  echo [DONE] NewsCollector finished.
)

exit /b %RC%
