@echo off
setlocal
call "%~dp0run_material_optimizer.bat" %*
exit /b %ERRORLEVEL%
