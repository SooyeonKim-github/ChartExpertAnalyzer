@echo off
setlocal EnableExtensions
chcp 65001 > nul
cd /d "%~dp0"

echo ============================================
echo   Chart Expert Analyzer - Run All Screens
echo ============================================
echo.

echo [1/2] Running KJBChartAnalyzer\run_screen.bat ...
call "%~dp0KJBChartAnalyzer\run_screen.bat"
if errorlevel 1 (
    echo.
    echo [ERROR] KJBChartAnalyzer screening failed.
    pause
    exit /b 1
)

echo.
echo [2/2] Running SwingChartProbabilityAnalyzer\run_screen.bat ...
call "%~dp0SwingChartProbabilityAnalyzer\run_screen.bat"
if errorlevel 1 (
    echo.
    echo [ERROR] SwingChartProbabilityAnalyzer screening failed.
    pause
    exit /b 1
)

echo.
echo ============================================
echo [DONE] All analyzer screenings finished.
echo ============================================
pause
exit /b 0
