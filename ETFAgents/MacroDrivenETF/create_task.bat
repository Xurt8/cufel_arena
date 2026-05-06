@echo off
schtasks /create /tn "StockDataUpdate" /tr "python C:\Users\xrt85\Desktop\3月22日课程资料\cufel_arena\ETFAgents\MacroDrivenETF\daily_update.py" /sc daily /st 15:30 /f
pause