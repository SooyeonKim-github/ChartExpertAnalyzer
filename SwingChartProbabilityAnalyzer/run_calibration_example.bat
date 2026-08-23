@echo off
chcp 65001 > nul
cd /d "%~dp0"
REM 충분한 표본을 먼저 만든 뒤 scan 결과에 '과거 동일패턴 성공확률'이 표시됩니다.
python main.py calibrate --start 2024-01-01 --end 2026-06-30 --top-n 200 --step 3
pause
