"""每日数据更新 — 用 xtquant Python 3.11 执行"""
import sys, warnings, os
from datetime import datetime
from pathlib import Path
warnings.filterwarnings('ignore')
sys.path.insert(0, str(Path(__file__).parent.parent))

# 只在交易日运行，且每天只跑一次
today = datetime.now().strftime("%Y%m%d")
if datetime.now().weekday() >= 5:
    print(f"Skip: weekend ({today})")
    sys.exit(0)

flag = Path(__file__).parent.parent / "cache" / "_last_update.txt"
if flag.exists() and flag.read_text().strip() == today:
    print(f"Skip: already updated ({today})")
    sys.exit(0)

from src.data.local_store import sync_names, sync_sectors, sync_etf_latest

print(f"Update start: {today}")
sync_names()
sync_sectors()
sync_etf_latest()
flag.parent.mkdir(parents=True, exist_ok=True)
flag.write_text(today)
print(f"Update done: {today}")