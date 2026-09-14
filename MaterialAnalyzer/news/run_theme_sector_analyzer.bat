@echo off
setlocal
cd /d "%~dp0\..\.."

python -m MaterialAnalyzer.news.theme_sector_smoke_test
if errorlevel 1 exit /b 1

rem Keep sector-only rows in the detail report for precision/recall review.
rem Daily summary still contains THEME rows only.
python -m MaterialAnalyzer.news.run_theme_sector_analyzer --days 7 --include-sector-only
exit /b %ERRORLEVEL%
