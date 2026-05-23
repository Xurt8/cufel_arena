"""Core-Satellite: fixed core (gold+bond+broad) + satellite (trend gate + factor on full pool)"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import pandas as pd, numpy as np
from datetime import datetime
from pathlib import Path

_PROJECT = Path(__file__).parent.parent

# === Allocation: core keeps 50% of stock, satellite gets 50% ===
# Spreading core stock across 300 and 500
CYCLE_ALLOC = {
    "复苏期": {"stock_core": 0.30, "stock_sat": 0.30, "bond": 0.25, "gold": 0.15},
    "扩张期": {"stock_core": 0.35, "stock_sat": 0.40, "bond": 0.15, "gold": 0.10},
    "滞胀期": {"stock_core": 0.10, "stock_sat": 0.15, "bond": 0.35, "gold": 0.40},
    "衰退期": {"stock_core": 0.05, "stock_sat": 0.10, "bond": 0.70, "gold": 0.15},
}
CYCLE = "复苏期"  # simplified
ALLOC = CYCLE_ALLOC[CYCLE]

CORE_STOCKS = {"510300": "沪深300", "510500": "中证500"}
CORE_BOND = "511010"
CORE_GOLD = "518880"
SATELLITE_TOP_N = 5  # top N sector ETFs for satellite

# === Load data ===
ma_df = pd.read_parquet(_PROJECT / "cache" / "ma200_cache.parquet")
ma_df["date"] = pd.to_datetime(ma_df["date"])
pdf_all = pd.read_parquet(_PROJECT / "data" / "etf_daily.parquet")
pdf_all["date"] = pd.to_datetime(pdf_all["date"])

with open(_PROJECT / "data" / "etf_names.json", "r", encoding="utf-8") as f:
    names = json.load(f)
from data.local_store import get_sector_map
c = get_sector_map()
recent = pdf_all[pdf_all["date"] >= pd.Timestamp.now() - pd.Timedelta(days=60)]
vol_rank = recent.groupby("code")["vol"].mean().sort_values(ascending=False)

# Full stock pool for satellite
sat_pool = []
for code in vol_rank.index.tolist():
    name = names.get(code, "")
    qmt = f"{code}.SH" if code.startswith(("5","6","51","56","58","59")) else f"{code}.SZ"
    if not name or qmt in c["cross"]: continue
    if qmt in c["stock"]:
        sat_pool.append((code, name))
print(f"Satellite pool: {len(sat_pool)} stock ETFs")

from backtest.engine import BacktestEngine
be = BacktestEngine.__new__(BacktestEngine); be.freq = "M"
dates = be.generate_rebalance_dates(datetime(2021, 7, 31), datetime(2026, 5, 31))
print(f"Backtest: {len(dates)} months")

records = []
for di, dt in enumerate(dates):
    ds = dt.strftime("%Y-%m-%d")
    if di % 10 == 0: print(f"  {di+1}/{len(dates)}: {ds}")

    # --- Core positions (fixed allocation, check MA gate for stocks) ---
    # Gold and bonds: always present
    records.append({"date": dt, "code": CORE_GOLD, "weight": ALLOC["gold"]})
    records.append({"date": dt, "code": CORE_BOND, "weight": ALLOC["bond"]})

    # Core stocks: split equally, gate by MA
    up_to = ma_df[ma_df["date"] <= ds]
    latest_ma = up_to.sort_values("date").groupby("code").last()
    above_ma = set(latest_ma[latest_ma["close"] > latest_ma["ma200"]].index)

    core_count = sum(1 for c in CORE_STOCKS if c in above_ma)
    if core_count > 0:
        per_core = ALLOC["stock_core"] / core_count
        for code in CORE_STOCKS:
            if code in above_ma:
                records.append({"date": dt, "code": code, "weight": per_core})
            # else: its share goes to bonds
            else:
                records.append({"date": dt, "code": CORE_BOND, "weight": per_core})

    # --- Satellite: trend gate + factor rotation ---
    score_cache = _PROJECT / "cache" / f"etf_scores_{ds}.json"
    scores = {}
    if score_cache.exists():
        with open(score_cache) as f: scores = json.load(f)

    candidates = []
    for code, name in sat_pool:
        if code not in above_ma: continue
        sc = scores.get(code, {})
        if not sc: continue
        mom = max(-0.5, min(0.5, sc.get("mom_60d", 0))) + 0.5
        vol_s = max(0, 1 - sc.get("ann_vol", 0.3) / 0.6)
        sh_s = max(0, min(1, (sc.get("sharpe60", 0) + 2) / 6))
        fl_s = min(1.5, max(0.5, sc.get("turnover", 1.0))) / 1.5
        score = mom * 0.20 + vol_s * 0.45 + sh_s * 0.20 + fl_s * 0.15
        candidates.append((code, score))

    candidates.sort(key=lambda x: x[1], reverse=True)
    selected = candidates[:SATELLITE_TOP_N]
    if selected:
        total_s = sum(s for _, s in selected)
        for code, sc in selected:
            w = ALLOC["stock_sat"] * sc / total_s if total_s > 0 else ALLOC["stock_sat"] / len(selected)
            records.append({"date": dt, "code": code, "weight": w})
    else:
        records.append({"date": dt, "code": CORE_BOND, "weight": ALLOC["stock_sat"]})

# === Merge weights and normalize ===
ws = pd.DataFrame(records).pivot_table(index="date", columns="code", values="weight",
                                         aggfunc="sum").fillna(0)
ws.index = pd.to_datetime(ws.index)
# Ensure sum=1
row_sums = ws.sum(axis=1)
ws = ws.div(row_sums, axis=0)
n_unique = len(ws.columns)
avg_etfs = ws.astype(bool).sum(axis=1).mean()
print(f"Portfolio: {n_unique} unique ETFs, avg {avg_etfs:.1f}/month")

# === NAV ===
all_codes = list(ws.columns)
start_s = "2021-07-01"
prices = pdf_all[(pdf_all["date"] >= start_s) & (pdf_all["date"] <= "2026-05-31")
                 & (pdf_all["code"].isin(all_codes))]
prices = prices[["date", "code", "close"]].copy(); prices["close_adj"] = prices["close"]
pivot = prices.pivot_table(index="date", columns="code", values="close_adj", aggfunc="last").ffill()

nav = pd.Series(1.0, index=pivot.index)
current_w = pd.Series(0, index=all_codes); total_cost = 0.0
for i, today in enumerate(pivot.index):
    if i == 0: continue
    yesterday = pivot.index[i - 1]
    daily_ret = pivot.loc[today] / pivot.loc[yesterday] - 1
    daily_ret = daily_ret.fillna(0)
    if today in ws.index:
        target = ws.loc[today].reindex(all_codes).fillna(0)
        cost = (target - current_w).abs().sum() / 2 * 0.0008
        total_cost += cost
        nav.loc[today] = nav.loc[yesterday] * (1 + (current_w * daily_ret).sum() - cost)
        current_w = target.copy()
    else:
        nav.loc[today] = nav.loc[yesterday] * (1 + (current_w * daily_ret).sum())

daily = nav.pct_change().dropna()
r = float(nav.iloc[-1] / nav.iloc[0] - 1) * 100
ann_r = float((1 + r/100) ** (252 / (len(daily) + 1)) - 1) * 100
sh = float(ann_r / (daily.std() * np.sqrt(252) * 100)) if daily.std() > 0 else 0
dd = float((nav / nav.cummax() - 1).min()) * 100
to = float(ws.diff().abs().sum(axis=1).mean())

# Monthly win rate
monthly_nav = nav.resample("ME").last()
monthly_ret = monthly_nav.pct_change().dropna() * 100
wins = (monthly_ret > 0).sum()
win_rate = wins / len(monthly_ret) * 100

print(f"\n{'='*60}")
print(f"  Core-Satellite Hybrid")
print(f"{'='*60}")
print(f"Total Return:    {r:.1f}%")
print(f"Annual Return:   {ann_r:.1f}%")
print(f"Sharpe Ratio:    {sh:.2f}")
print(f"Max Drawdown:    {dd:.1f}%")
print(f"Turnover:        {to:.2f}")
print(f"Cost Drag:       {total_cost*100:.2f}%")
print(f"Monthly Win:     {win_rate:.0f}% ({int(wins)}/{len(monthly_ret)})")
print()
print(f"--- Comparison ---")
print(f"  Trend+slim(no factor):   130.3%  Sharpe=2.02  DD=-23.7%  TO=0.02")
print(f"  Factor+slim(no trend):   106.0%  Sharpe=0.70  DD=-26.6%  TO=0.12")
print(f"  Full trend+factor:         9.9%  Sharpe=0.17  DD=-37.7%  TO=0.58")
print(f"  Fixed 60/25/15:           39.1%")