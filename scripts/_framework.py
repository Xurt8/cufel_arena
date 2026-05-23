"""完整框架: 宏观周期 + 核心卫星 + 趋势门控 + 因子轮动"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import pandas as pd, numpy as np
from datetime import datetime, timedelta
from pathlib import Path

_PROJECT = Path(__file__).parent.parent

# ============================================================
# 1. 宏观周期判定 (VibeCodingPrompts 03 MacroAgent 规范)
# ============================================================
from agent.engine import DataAgent, MacroAgent
data_agent = DataAgent()
data_agent.load_all_data()
macro_agent = MacroAgent(use_llm=False)
cycle_cache = {}

def classify_cycle(ds: str) -> str:
    """七维宏观指标(PMI/CPI/PPI/M2/社融/GDP/SHIBOR) -> 经济周期"""
    if ds in cycle_cache:
        return cycle_cache[ds]
    target = datetime.strptime(ds, "%Y-%m-%d")
    macro_data = data_agent.get_macro_for_decision(target)
    result = macro_agent.analyze(macro_data)
    cycle = result["cycle_phase"]
    cycle_cache[ds] = cycle
    return cycle

# ============================================================
# 2. 宏观周期 -> 大类资产配置比例
# ============================================================
CYCLE_ALLOC = {
    "复苏期": {"gold": 0.10, "bond": 0.25, "stock_core": 0.325, "stock_sat": 0.325, "cash": 0.00},
    "扩张期": {"gold": 0.35, "bond": 0.15, "stock_core": 0.175, "stock_sat": 0.175, "cash": 0.15},
    "滞胀期": {"gold": 0.30, "bond": 0.15, "stock_core": 0.10, "stock_sat": 0.10, "cash": 0.35},
    "衰退期": {"gold": 0.10, "bond": 0.50, "stock_core": 0.10, "stock_sat": 0.10, "cash": 0.20},
}
GOLD_ETF = "518880"
BOND_ETF = "511010"
CORE_STOCKS = {"510300": "沪深300", "510500": "中证500"}
SATELLITE_N = 4  # top N sector ETFs for satellite
SCHEME_WEIGHTS = [0.30, 0.30, 0.25, 0.15]  # [mom, vol, sharpe, flow] — default balanced

# ============================================================
# 3. 加载数据
# ============================================================
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

sat_pool = []
for code in vol_rank.index.tolist():
    name = names.get(code, "")
    qmt = f"{code}.SH" if code.startswith(("5","6","51","56","58","59")) else f"{code}.SZ"
    if not name or qmt in c["cross"]: continue
    if qmt in c["stock"]: sat_pool.append((code, name))
print(f"Satellite pool: {len(sat_pool)} stock ETFs")

# ============================================================
# 4. 季度调仓日期
# ============================================================
from backtest.engine import BacktestEngine
be = BacktestEngine.__new__(BacktestEngine); be.freq = "Q"
dates = be.generate_rebalance_dates(datetime(2021, 9, 30), datetime(2026, 5, 31))
print(f"Quarterly rebalance: {len(dates)} dates")

# ============================================================
# 5. 生成权重
# ============================================================
records = []
cycle_log = []
for di, dt in enumerate(dates):
    ds = dt.strftime("%Y-%m-%d")
    cycle = classify_cycle(ds)
    alloc = CYCLE_ALLOC[cycle]
    cycle_log.append({"date": ds, "cycle": cycle, **alloc})

    # --- Gold & Bond: fixed, no rotation ---
    records.append({"date": dt, "code": GOLD_ETF, "weight": alloc["gold"]})
    records.append({"date": dt, "code": BOND_ETF, "weight": alloc["bond"]})
    # Cash: represented by BOND_ETF (low vol proxy)
    if alloc.get("cash", 0) > 0:
        records.append({"date": dt, "code": BOND_ETF, "weight": alloc["cash"]})

    # --- Trend gate MA lookup ---
    up_to = ma_df[ma_df["date"] <= ds]
    latest_ma = up_to.sort_values("date").groupby("code").last()
    above_ma = set(latest_ma[latest_ma["close"] > latest_ma["ma200"]].index)

    # --- Stock Core: split equally, MA gate for safety ---
    core_count = sum(1 for c in CORE_STOCKS if c in above_ma)
    if core_count > 0:
        per_core = alloc["stock_core"] / core_count
        for code in CORE_STOCKS:
            if code in above_ma:
                records.append({"date": dt, "code": code, "weight": per_core})
            else:
                records.append({"date": dt, "code": BOND_ETF, "weight": per_core})

    # --- Stock Satellite: trend gate + cross-sectional percentile factor ---
    score_cache = _PROJECT / "cache" / f"etf_scores_{ds}.json"
    scores = {}
    if score_cache.exists():
        with open(score_cache) as f: scores = json.load(f)

    raw = []
    for code, name in sat_pool:
        if code not in above_ma: continue
        sc = scores.get(code, {})
        if not sc: continue
        raw.append({"code": code, "mom_60d": sc.get("mom_60d", 0),
                     "ann_vol": sc.get("ann_vol", 0.3),
                     "sharpe60": sc.get("sharpe60", 0),
                     "turnover": sc.get("turnover", 1.0)})
    if not raw:
        # Fallback: satellite allocation goes to core stocks
        if alloc["stock_sat"] > 0 and core_count > 0:
            per_core_extra = alloc["stock_sat"] / core_count
            for code in CORE_STOCKS:
                if code in above_ma:
                    records.append({"date": dt, "code": code, "weight": per_core_extra})
        elif alloc["stock_sat"] > 0:
            records.append({"date": dt, "code": BOND_ETF, "weight": alloc["stock_sat"]})
        if di % 10 == 0: print(f"  {di+1}/{len(dates)}: {ds} -> {cycle}")
        continue

    rf = pd.DataFrame(raw)
    # Cross-sectional percentile ranking (0~1)
    rf["mom_rank"] = rf["mom_60d"].rank(pct=True)  # higher momentum = better
    rf["vol_rank"] = 1 - rf["ann_vol"].rank(pct=True)  # lower vol = better
    rf["sh_rank"] = rf["sharpe60"].rank(pct=True)  # higher sharpe = better
    rf["flow_rank"] = rf["turnover"].rank(pct=True)  # higher turnover = better

    w = SCHEME_WEIGHTS
    rf["score"] = (rf["mom_rank"] * w[0] + rf["vol_rank"] * w[1] +
                   rf["sh_rank"] * w[2] + rf["flow_rank"] * w[3])
    rf = rf.sort_values("score", ascending=False)
    selected = rf.head(SATELLITE_N)
    total_s = selected["score"].sum()
    for _, row in selected.iterrows():
        wt = alloc["stock_sat"] * row["score"] / total_s if total_s > 0 else alloc["stock_sat"] / SATELLITE_N
        records.append({"date": dt, "code": row["code"], "weight": wt})

    if di % 10 == 0: print(f"  {di+1}/{len(dates)}: {ds} -> {cycle}")

# ============================================================
# 6. NAV 计算
# ============================================================
ws = pd.DataFrame(records).pivot_table(index="date", columns="code", values="weight",
                                         aggfunc="sum").fillna(0)
ws.index = pd.to_datetime(ws.index)
row_sums = ws.sum(axis=1)
ws = ws.div(row_sums, axis=0)
n_unique = len(ws.columns)
avg_etfs = ws.astype(bool).sum(axis=1).mean()
print(f"Portfolio: {n_unique} unique ETFs, avg {avg_etfs:.1f}/month")

# Build composite: gold (518880), bond (511010), stock core, stock sat
# Map bond+cash together: if BOND_ETF weight > bond alloc, the excess = cash
bonds_total = ws.get(BOND_ETF, 0)
gold_total = ws.get(GOLD_ETF, 0)
core_total = sum(ws.get(c, 0) for c in CORE_STOCKS)
sat_total = ws.sum(axis=1) - bonds_total - gold_total - core_total
sat_total = sat_total.clip(lower=0)

all_codes = list(ws.columns)
start_s = "2021-09-01"
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
monthly = nav.resample("ME").last().pct_change().dropna() * 100
wins = (monthly > 0).sum()
wr = wins / len(monthly) * 100

# === 周期分布 ===
clog = pd.DataFrame(cycle_log)
cycle_counts = clog["cycle"].value_counts()
print(f"\n{'='*60}")
print(f"  完整框架: 宏观周期 + 核心卫星 + 趋势门控 + 因子轮动")
print(f"{'='*60}")
print(f"周期分布: {dict(cycle_counts)}")
print(f"Total Return:    {r:.1f}%")
print(f"Annual Return:   {ann_r:.1f}%")
print(f"Sharpe Ratio:    {sh:.2f}")
print(f"Max Drawdown:    {dd:.1f}%")
print(f"Turnover:        {to:.2f}")
print(f"Monthly Win:     {wr:.0f}% ({int(wins)}/{len(monthly)})")
print(f"Cost Drag:       {total_cost*100:.2f}%")
print()
print(f"--- vs Benchmarks ---")
print(f"Fixed 60/25/15:      39.1%")
print(f"Trend+slim (no fac): 130.3%  Sharpe=2.02  TO=0.02")
print(f"Core-Sat (static):    50.3%  Sharpe=0.60  TO=0.41")
print(f"Original full pool:   16.7%  Sharpe=0.66  TO=0.12")
