"""严格通过 src/backtest/engine.py BacktestEngine 对比月频 vs 季频"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import pandas as pd
from datetime import datetime
from pathlib import Path

_PROJECT = Path(__file__).parent.parent
from backtest.engine import BacktestEngine
from agent.engine import MacroDrivenETFAgent, PortfolioAgent
from data.local_store import get_sector_map

# Build universe
df = pd.read_parquet(_PROJECT / "data" / "etf_daily.parquet")
recent = df[df["date"] >= pd.Timestamp.now() - pd.Timedelta(days=60)]
vol_rank = recent.groupby("code")["vol"].mean().sort_values(ascending=False)
with open(_PROJECT / "data" / "etf_names.json", "r", encoding="utf-8") as f: names = json.load(f)
c = get_sector_map()
GOLD_KW = ["黄金", "上海金", "金ETF"]
uni = {"Stock": [], "Bond": [], "Commodity": []}
for code in vol_rank.index.tolist():
    name = names.get(code, "")
    qmt = f"{code}.SH" if code.startswith(("5","6","51","56","58","59")) else f"{code}.SZ"
    if not name or qmt in c["cross"]: continue
    if qmt in c["commodity"]:
        if any(kw in name for kw in GOLD_KW): uni["Commodity"].append((code, name))
    elif qmt in c["bond"] or qmt in c["money"]: uni["Bond"].append((code, name))
    elif qmt in c["stock"]: uni["Stock"].append((code, name))
print(f"Universe: S={len(uni['Stock'])} B={len(uni['Bond'])} C={len(uni['Commodity'])}")

START = datetime(2021, 9, 30)
END = datetime(2026, 5, 31)

for freq, label in [("M", "Monthly"), ("Q", "Quarterly")]:
    # Clear holdings cache
    for f in (_PROJECT / "cache").glob("holdings_*.json"): f.unlink()
    PortfolioAgent.SCORE_WEIGHTS = {"mom": 0.20, "vol": 0.45, "sharpe": 0.20, "flow": 0.15}
    agent = MacroDrivenETFAgent(use_llm=False)
    agent.set_etf_universe(uni)
    engine = BacktestEngine(agent, transaction_cost=0.0003, rebalance_threshold=0.005,
                            slippage=0.0001, freq=freq)
    try:
        _, perf, _ = engine.run(START, END)
        print(f"\n{label}: Ret={perf['total_return']:.1f}% Ann={perf['annual_return']:.1f}% "
              f"Sharpe={perf['sharpe_ratio']:.2f} DD={perf['max_drawdown']:.1f}% TO={perf['turnover']:.2f}")
    except Exception as e:
        print(f"{label}: ERROR {e}")
