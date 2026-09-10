@echo off
setlocal EnableExtensions
chcp 65001 >nul

set "ROOT=%~dp0"
call "%ROOT%scripts\run_material_issue.bat"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
    echo [FAILED] Material issue run failed with code %RC%.
    pause
    exit /b %RC%
)

call "%ROOT%scripts\push_daily_results.bat"
echo [DONE] Material issue run finished.
pause
exit /b 0
