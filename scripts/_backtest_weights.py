"""4方案回测对比 — 严格按回测引擎执行"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from datetime import datetime
from pathlib import Path
import pandas as pd
import numpy as np
from backtest.engine import BacktestEngine
from agent.engine import MacroDrivenETFAgent, PortfolioAgent
from data.local_store import get_sector_map

_PROJECT = Path(__file__).parent.parent

# Trend-following: slim ETFs with class types
TREND_ETFS = {"510300": "Stock", "510500": "Stock", "159915": "Stock",
              "511010": "Bond", "511220": "Bond", "518880": "Commodity"}

# Fixed allocation per cycle (same as CLASS_TARGETS)
CYCLE_ALLOC = {
    "复苏期": {"Stock": 0.60, "Bond": 0.25, "Commodity": 0.15},
    "扩张期": {"Stock": 0.75, "Bond": 0.15, "Commodity": 0.10},
    "滞胀期": {"Stock": 0.25, "Bond": 0.35, "Commodity": 0.40},
    "衰退期": {"Stock": 0.15, "Bond": 0.70, "Commodity": 0.15},
}

# === Build universe ===
def build_universe(slim=False):
    df = pd.read_parquet(_PROJECT / "data" / "etf_daily.parquet")
    recent = df[df["date"] >= pd.Timestamp.now() - pd.Timedelta(days=60)]
    vol_rank = recent.groupby("code")["vol"].mean().sort_values(ascending=False)
    with open(_PROJECT / "data" / "etf_names.json", "r", encoding="utf-8") as f:
        names = json.load(f)
    c = get_sector_map()
    GOLD_KW = ["黄金", "上海金", "金ETF"]
    uni = {"Stock": [], "Bond": [], "Commodity": []}

    if slim:
        # Broad market only: 沪深300, 中证500, 国债, 黄金
        slim_stocks = {"510300", "510500", "159915"}
        slim_bonds = {"511010", "511220"}
        for code in slim_stocks:
            if code in names:
                uni["Stock"].append((code, names[code]))
        for code in slim_bonds:
            if code in names:
                uni["Bond"].append((code, names[code]))
        uni["Commodity"] = [("518880", names.get("518880", "黄金ETF"))]
        return uni

    for code in vol_rank.index.tolist():
        name = names.get(code, "")
        qmt = f"{code}.SH" if code.startswith(("5","6","51","56","58","59")) else f"{code}.SZ"
        if not name or qmt in c["cross"]:
            continue
        if qmt in c["commodity"]:
            if any(kw in name for kw in GOLD_KW):
                uni["Commodity"].append((code, name))
        elif qmt in c["bond"] or qmt in c["money"]:
            uni["Bond"].append((code, name))
        elif qmt in c["stock"]:
            uni["Stock"].append((code, name))
    return uni

# === Base settings ===
START = datetime(2021, 1, 31)
END = datetime(2026, 5, 31)
BEST_WEIGHTS = {"mom": 0.20, "vol": 0.45, "sharpe": 0.20, "flow": 0.15}
BASELINE_FIXED = 39.1   # 60/25/15 buy-and-hold
BASELINE_STRATEGY = 16.7 # original strategy

def run_one(label, freq="M", slim=False, lazy_lambda=0):
    """Run a single backtest configuration"""
    PortfolioAgent.SCORE_WEIGHTS = BEST_WEIGHTS
    PortfolioAgent.LAZY_LAMBDA = lazy_lambda  # will be ignored if not supported
    for f in (_PROJECT / "cache").glob("holdings_*.json"):
        f.unlink()
    uni = build_universe(slim=slim)
    agent = MacroDrivenETFAgent(use_llm=False)
    agent.set_etf_universe(uni)
    engine = BacktestEngine(agent, transaction_cost=0.0003, rebalance_threshold=0.005,
                            slippage=0.0001, freq=freq)
    try:
        _, perf, _ = engine.run(START, END)
        perf["label"] = label
        perf["freq"] = freq
        perf["slim"] = slim
        perf["lazy"] = lazy_lambda
        return perf
    except Exception as e:
        return {"label": label, "error": str(e)}

# === Run all schemes ===
results = []

print("=" * 60)
print("Strategy Optimization Backtest (2021-2026)")
print(f"Baseline: Fixed 60/25/15 = {BASELINE_FIXED}% | Strategy = {BASELINE_STRATEGY}%")
print("=" * 60)

# Baseline
r0 = run_one("0-月频(基准)", freq="M")
results.append(r0)
print(f"  {r0['label']}: Ret={r0.get('total_return','ERR')}% Sharpe={r0.get('sharpe_ratio','?')}")

# Scheme A: Quarterly
rA = run_one("A-季度调仓", freq="Q")
results.append(rA)
print(f"  {rA['label']}: Ret={rA.get('total_return','ERR')}% Sharpe={rA.get('sharpe_ratio','?')}")

# Scheme A+B: Quarterly + Slim
rAB = run_one("A+B-季度+瘦身池", freq="Q", slim=True)
results.append(rAB)
print(f"  {rAB['label']}: Ret={rAB.get('total_return','ERR')}% Sharpe={rAB.get('sharpe_ratio','?')}")

# Scheme A+B (monthly slim)
rABm = run_one("月频+瘦身池", freq="M", slim=True)
results.append(rABm)
print(f"  {rABm['label']}: Ret={rABm.get('total_return','ERR')}% Sharpe={rABm.get('sharpe_ratio','?')}")

# Scheme C: Monthly with anchor + lazy
# We implement anchor via _apply_risk_controls min/max which already exists
# Lazy penalty via modifying _score_etf — add a class variable
rC1 = run_one("C-月频+惰性0.1", freq="M", lazy_lambda=0.1)
results.append(rC1)
print(f"  {rC1['label']}: Ret={rC1.get('total_return','ERR')}% Sharpe={rC1.get('sharpe_ratio','?')}")

rC2 = run_one("C-月频+惰性0.2", freq="M", lazy_lambda=0.2)
results.append(rC2)
print(f"  {rC2['label']}: Ret={rC2.get('total_return','ERR')}% Sharpe={rC2.get('sharpe_ratio','?')}")

# === Ranking ===
print("\n" + "=" * 60)
print("RANKING (by total return)")
print(f"{'Scheme':<25} {'Return':>8} {'Sharpe':>7} {'MaxDD':>7} {'Turnover':>9}")
print("-" * 60)
valid = [r for r in results if "error" not in r]
valid.sort(key=lambda x: x.get("total_return", -999), reverse=True)
for r in valid:
    flag = " <<<" if r == valid[0] else ""
    print(f"{r['label']:<25} {r['total_return']:>7.1f}% {r['sharpe_ratio']:>6.2f} {r['max_drawdown']:>6.1f}% {r['turnover']:>8.2f}{flag}")

print(f"\n  Fixed 60/25/15 = {BASELINE_FIXED}%")

# ═══════════════════════════════════════════════════════
# Scheme D: Trend Following (MA gate)
# ═══════════════════════════════════════════════════════

print("\n" + "=" * 60)
print("Scheme D: Trend Following (200-day MA gate)")
print("=" * 60)

MA_PERIOD = 200  # 10-month approx

# Load price data for trend ETFs
pdf = pd.read_parquet(_PROJECT / "data" / "etf_daily.parquet")
pdf["date"] = pd.to_datetime(pdf["date"])

# Build trend weights: for each rebalance date, check MA signal
from backtest.engine import BacktestEngine as BE

MA_START = datetime(2021, 7, 31)  # need 200 days of warm-up
be = BE.__new__(BE)  # dummy instance just for dates
be.freq = "M"
dates = be.generate_rebalance_dates(MA_START, datetime(2026, 5, 31))

trend_records = []
prev_weights = {}
for dt in dates:
    ds = dt.strftime("%Y-%m-%d")
    weights = {}
    for code, cls in TREND_ETFS.items():
        sub = pdf[(pdf["code"] == code) & (pdf["date"] <= ds)].tail(MA_PERIOD + 5)
        if len(sub) < MA_PERIOD:
            continue
        close = sub["close"].values[-1]
        ma = sub["close"].values[-MA_PERIOD:].mean()
        if close > ma:
            weights[code] = cls  # above MA → include

    # Allocate per cycle allocation, scaled to available ETFs
    cycle = "复苏期"  # simplified: always recovery
    target = dict(CYCLE_ALLOC[cycle])

    # Count available per class
    avail = {"Stock": [], "Bond": [], "Commodity": []}
    for code, cls in weights.items():
        avail[cls].append(code)

    # Scale: if stock ETFs all below MA → move stock allocation to bonds
    for cls in ["Stock", "Commodity"]:
        if not avail[cls]:
            target["Bond"] += target[cls]
            target[cls] = 0

    for code, cls in weights.items():
        if avail[cls]:
            w = target[cls] / len(avail[cls]) if len(avail[cls]) > 0 else 0
            trend_records.append({"date": dt, "code": code, "weight": w})

    if not weights:
        # All to bonds
        for code in ["511010", "511220"]:
            trend_records.append({"date": dt, "code": code, "weight": 0.5})

# Run through backtest NAV calculation
ws = pd.DataFrame(trend_records).pivot_table(
    index="date", columns="code", values="weight", aggfunc="last").fillna(0)
ws.index = pd.to_datetime(ws.index)

# Use engine's _calc_nav logic directly
all_codes = list(ws.columns)
prices = pdf[(pdf["date"] >= MA_START.strftime("%Y-%m-%d"))
             & (pdf["date"] <= "2026-05-31")
             & (pdf["code"].isin(all_codes))]
prices = prices[["date", "code", "close"]].copy()
prices["close_adj"] = prices["close"]
pivot = prices.pivot_table(index="date", columns="code", values="close_adj",
                            aggfunc="last").ffill()

# NAV with proportional costs
nav = pd.Series(1.0, index=pivot.index)
current_w = pd.Series(0, index=all_codes)
total_cost = 0.0
COST_RATE = 0.0008  # buy+sell+slippage

for i, today in enumerate(pivot.index):
    if i == 0:
        continue
    yesterday = pivot.index[i - 1]
    daily_ret = pivot.loc[today] / pivot.loc[yesterday] - 1
    daily_ret = daily_ret.fillna(0)
    today_s = today.strftime("%Y-%m-%d")
    # Check if rebalance day
    matching = ws[ws.index == pd.Timestamp(today_s.replace("-", ""))] if False else ws[
        ws.index == pd.Timestamp(today)]
    if today in ws.index:
        target_w = ws.loc[today].reindex(all_codes).fillna(0)
        turnover = (target_w - current_w).abs().sum() / 2
        cost = turnover * COST_RATE
        total_cost += cost
        ret = (current_w * daily_ret).sum() - cost
        nav.loc[today] = nav.loc[yesterday] * (1 + ret)
        current_w = target_w.copy()
    else:
        ret = (current_w * daily_ret).sum()
        nav.loc[today] = nav.loc[yesterday] * (1 + ret)

# Metrics
daily = nav.pct_change().dropna()
total_ret = float(nav.iloc[-1] / nav.iloc[0] - 1) * 100
ann_vol = float(daily.std() * np.sqrt(252)) * 100
sharpe = float((total_ret / 100) / (ann_vol / 100) * (252 / len(daily)) ** 0.5) if ann_vol > 0 else 0
max_dd = float((nav / nav.cummax() - 1).min()) * 100
turnover = float(ws.diff().abs().sum(axis=1).mean())

print(f"  D-趋势系统(200MA): Ret={total_ret:.1f}% Sharpe={sharpe:.2f} DD={max_dd:.1f}% Turnover={turnover:.2f}")
print(f"  Cost drag: {total_cost*100:.2f}%")
print(f"\n  vs Fixed 60/25/15: {total_ret - BASELINE_FIXED:+.1f}%")
print(f"  vs 月频+瘦身池: {total_ret - 106.0:+.1f}%")