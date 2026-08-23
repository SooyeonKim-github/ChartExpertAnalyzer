@echo off
chcp 65001 > nul
cd /d "%~dp0"
REM 날짜를 생략하면 오늘 날짜 기준으로 조회하며, 휴일이면 pykrx 마지막 거래일이 Actual_Date가 됩니다.
python main.py scan --top-n 0 --charts 20
pause
