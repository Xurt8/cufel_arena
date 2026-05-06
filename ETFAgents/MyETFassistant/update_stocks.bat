@echo off
REM 每日股票数据更新脚本
REM 建议每天15:30运行

cd /d "C:\Users\xrt85\Desktop\3月22日课程资料\cufel_arena\ETFAgents\MyETFassistant"

python update_stocks.py

pause