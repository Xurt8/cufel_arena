@echo off
REM 创建Windows定时任务: 每天15:30更新股票数据

REM 创建任务计划
schtasks /create /tn "StockDataUpdate" /tr "%~dp0update_stocks.bat" /sc daily /st 15:30 /f

echo 任务创建成功!
echo 每天15:30会自动更新股票数据
pause