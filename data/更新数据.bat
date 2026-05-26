@echo off
cd /d "%~dp0\.."
echo ============================================
echo  CUFEL Arena 数据更新
echo  %date% %time%
echo ============================================
echo.
echo [1/4] 宏观数据更新 (akshare)...
python scripts\update_macro.py
if errorlevel 1 (
    echo [WARNING] 宏观数据更新失败，继续...
)
echo.
echo [2/4] 启动 MiniQMT...
start "" "D:\长城策略交易系统\bin.x64\XtMiniQmt.exe"
echo   等待 MiniQMT 启动...
timeout /t 20 /nobreak >nul
echo.
echo [3/4] ETF 数据同步 (MiniQMT)...
"D:\长城策略交易系统\bin.x64\pythonw.exe" "c:\Users\xrt85\Desktop\3月22日课程资料\cufel_arena\scripts\sync_data_light.py"
if errorlevel 1 (
    echo [WARNING] ETF 同步失败，检查 MiniQMT 是否运行
)
echo.
echo [4/4] CSV 合并到 parquet...
python -c "import pandas as pd; from pathlib import Path; csv=Path('data/_sync_pending.csv'); parquet='data/etf_daily.parquet'
if csv.exists():
    nd=pd.read_csv(csv,dtype={'code':str})
    nd['date']=pd.to_datetime(nd['date'],format='%%Y%%m%%d')
    ex=pd.read_parquet(parquet); ex['code']=ex['code'].astype(str)
    combined=pd.concat([ex,nd],ignore_index=True).drop_duplicates(subset=['code','date'])
    combined.to_parquet(parquet,index=False)
    csv.unlink()
    print(f'  Merged {len(nd)} rows, total {len(combined)} rows')
else:
    print('  No pending CSV to merge')"
echo.
echo [4/4] 因子数据下载 (MiniQMT)...
"D:\长城策略交易系统\bin.x64\pythonw.exe" scripts\download_factors.py
if errorlevel 1 (
    echo [WARNING] 因子下载失败，检查 MiniQMT 是否运行
)
echo.
echo ============================================
echo  更新完成
echo ============================================
pause
