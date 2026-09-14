@echo off
setlocal
cd /d "%~dp0\..\.."

python -m MaterialAnalyzer.news.theme_sector_smoke_test
if errorlevel 1 exit /b 1

python -m MaterialAnalyzer.news.run_theme_sector_analyzer --days 7
exit /b %ERRORLEVEL%
