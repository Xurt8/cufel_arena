@echo off
chcp 65001 >nul
title 内网ETF数据更新
echo ========================================
echo   中央财经大学内网 ETF数据自动更新
echo ========================================
echo.
echo 请确保:
echo   1. 已连接校园网/VPN
echo   2. 网络可以访问 hq.sinajs.cn
echo.
echo 按任意键开始更新...
pause >nul

cd /d "%~dp0"
python 内网数据更新.py

echo.
echo 按任意键退出...
pause >nul