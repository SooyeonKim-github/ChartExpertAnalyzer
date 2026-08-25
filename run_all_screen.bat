@echo off
setlocal EnableExtensions
chcp 65001 > nul
cd /d "%~dp0"

echo ============================================
echo   Chart Expert Analyzer - Run All Screens
echo ============================================
echo.

set "NO_PAUSE=1"

echo [1/3] Running KJBChartAnalyzer\run_screen.bat ...
call "%~dp0KJBChartAnalyzer\run_screen.bat"
if errorlevel 1 (
    echo.
    echo [ERROR] KJBChartAnalyzer screening failed.
    pause
    exit /b 1
)

echo.
echo [2/3] Running SwingChartProbabilityAnalyzer\run_screen.bat ...
call "%~dp0SwingChartProbabilityAnalyzer\run_screen.bat"
if errorlevel 1 (
    echo.
    echo [ERROR] SwingChartProbabilityAnalyzer screening failed.
    pause
    exit /b 1
)

echo.
echo [3/3] Running BullishPatternAnalyzer\run_screen.bat ...
call "%~dp0BullishPatternAnalyzer\run_screen.bat"
if errorlevel 1 (
    echo.
    echo [ERROR] BullishPatternAnalyzer screening failed.
    pause
    exit /b 1
)

set "NO_PAUSE="

echo.
echo ============================================
echo [DONE] All analyzer screenings finished.
echo ============================================
echo [KJB Agent]
echo   KJBChartAnalyzer\output\agent\candidates.json
echo   KJBChartAnalyzer\output\agent\candidates.md
echo.
echo [Siyoon Agent]
echo   SwingChartProbabilityAnalyzer\results\YYYYMMDD\agent\candidates.json
echo   SwingChartProbabilityAnalyzer\results\YYYYMMDD\agent\candidates.md
echo.
echo [Bullish Pattern]
echo   BullishPatternAnalyzer\results\YYYYMMDD\bullish_pattern_all.csv
echo   BullishPatternAnalyzer\results\YYYYMMDD\bullish_pattern_candidates.csv
echo   BullishPatternAnalyzer\results\YYYYMMDD\bullish_pattern_watchlist.csv
echo   BullishPatternAnalyzer\results\YYYYMMDD\summary.md
echo ============================================
pause
exit /b 0
