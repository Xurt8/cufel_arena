@echo off
cd /d "%~dp0"

echo [Macro] Updating macro data...
python scripts\update_macro.py

echo [Data] Starting MiniQMT...
start "" "D:\长城策略交易系统\bin.x64\XtMiniQmt.exe"
timeout /t 8 /nobreak >nul

echo [Data] Daily ETF update...
D:\长城策略交易系统\bin.x64\pythonw.exe scripts\sync_data_light.py

echo [Cache] Clearing Python caches...
rd /s /q "__pycache__" 2>nul
rd /s /q "src\__pycache__" 2>nul
rd /s /q "src\agent\__pycache__" 2>nul
rd /s /q "src\data\__pycache__" 2>nul
rd /s /q "src\backtest\__pycache__" 2>nul

start http://localhost:8501
python -m streamlit run app.py --server.port 8501 --server.headless true
pause
