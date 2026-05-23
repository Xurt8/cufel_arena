"""Compare fixed vs cycle-aware factor weights on full framework"""
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import pandas as pd, numpy as np
from datetime import datetime
from pathlib import Path

_PROJECT = Path(__file__).parent.parent

# Load data once
ma_df = pd.read_parquet(_PROJECT / "cache" / "ma200_cache.parquet")
ma_df["date"] = pd.to_datetime(ma_df["date"])
pdf_all = pd.read_parquet(_PROJECT / "data" / "etf_daily.parquet")
pdf_all["date"] = pd.to_datetime(pdf_all["date"])
with open(_PROJECT / "data" / "etf_names.json", "r", encoding="utf-8") as f: names = json.load(f)
from data.local_store import get_sector_map
c = get_sector_map(); GOLD_KW = ["黄金", "上海金", "金ETF"]
recent = pdf_all[pdf_all["date"] >= pd.Timestamp.now() - pd.Timedelta(days=60)]
vol_rank = recent.groupby("code")["vol"].mean().sort_values(ascending=False)

uni = {"Stock": [], "Bond": [], "Commodity": []}
for code in vol_rank.index.tolist():
    name = names.get(code, ""); qmt = f"{code}.SH" if code.startswith(("5","6","51","56","58","59")) else f"{code}.SZ"
    if not name or qmt in c["cross"]: continue
    if qmt in c["commodity"]:
        if any(kw in name for kw in GOLD_KW): uni["Commodity"].append((code, name))
    elif qmt in c["bond"] or qmt in c["money"]: uni["Bond"].append((code, name))
    elif qmt in c["stock"]: uni["Stock"].append((code, name))

from agent.engine import DataAgent, MacroAgent, PortfolioAgent as PA
da = DataAgent(); da.load_all_data()
ma = MacroAgent(use_llm=False)
cycle_cache = {}

def get_cycle(ds):
    if ds in cycle_cache: return cycle_cache[ds]
    r = ma.analyze(da.get_macro_for_decision(datetime.strptime(ds, "%Y-%m-%d")))
    cycle_cache[ds] = r["cycle_phase"]
    return r["cycle_phase"]

from backtest.engine import BacktestEngine
be = BacktestEngine.__new__(BacktestEngine); be.freq = "Q"
dates = be.generate_rebalance_dates(datetime(2021, 9, 30), datetime(2026, 5, 31))

CYCLE_ALLOC = PA.CYCLE_ALLOC
CORE_STOCKS = PA.CORE_STOCKS
GOLD_ETF = PA.GOLD_ETF; BOND_ETF = PA.BOND_ETF
SATELLITE_N = PA.SATELLITE_N
INDEX_PATTERNS = PA.INDEX_PATTERNS

fixed_weights = {"mom": 0.20, "vol": 0.45, "sharpe": 0.20, "flow": 0.15}
cycle_weights_map = PA.CYCLE_WEIGHTS

def run_framework(label, use_cycle):
    records = []
    for dt in dates:
        ds = dt.strftime("%Y-%m-%d"); cycle = get_cycle(ds)
        alloc = CYCLE_ALLOC.get(cycle, CYCLE_ALLOC["滞胀期"])
        w_map = cycle_weights_map.get(cycle, fixed_weights) if use_cycle else fixed_weights

        # Gold + Bond
        records.append({"date": dt, "code": GOLD_ETF, "weight": alloc["gold"]})
        records.append({"date": dt, "code": BOND_ETF, "weight": alloc["bond"] + alloc.get("cash", 0)})

        # Trend gate
        up_to = ma_df[ma_df["date"] <= ds]
        latest_ma = up_to.sort_values("date").groupby("code").last()
        above_ma = set(latest_ma[latest_ma["close"] > latest_ma["ma200"]].index)

        # Core stock
        core_codes = [co for co in CORE_STOCKS if co in above_ma]
        if core_codes:
            per_core = alloc["stock_core"] / len(core_codes)
            for co in core_codes: records.append({"date": dt, "code": co, "weight": per_core})
        elif alloc["stock_core"] > 0:
            records.append({"date": dt, "code": BOND_ETF, "weight": alloc["stock_core"]})

        # Satellite: percentile scoring
        score_cache = _PROJECT / "cache" / f"etf_scores_{ds}.json"
        scores = {}
        if score_cache.exists():
            with open(score_cache) as fh: scores = json.load(fh)

        raw_data = []
        for code, name in uni["Stock"]:
            if code not in above_ma: continue
            sc = scores.get(code, {})
            if not sc: continue
            raw_data.append((code, sc.get("mom_60d", 0), sc.get("ann_vol", 0.3),
                            sc.get("sharpe60", 0), sc.get("turnover", 1.0)))

        if raw_data:
            rf = pd.DataFrame(raw_data, columns=["code", "mom_60d", "ann_vol", "sharpe60", "turnover"])
            rf["mom_rank"] = rf["mom_60d"].rank(pct=True)
            rf["vol_rank"] = 1 - rf["ann_vol"].rank(pct=True)
            rf["sh_rank"] = rf["sharpe60"].rank(pct=True)
            rf["flow_rank"] = rf["turnover"].rank(pct=True)
            rf["score"] = (rf["mom_rank"] * w_map["mom"] + rf["vol_rank"] * w_map["vol"] +
                           rf["sh_rank"] * w_map["sharpe"] + rf["flow_rank"] * w_map["flow"])
            rf = rf.sort_values("score", ascending=False)

            # Dedup by tag
            seen_tags = set(); selected = []
            for _, row in rf.iterrows():
                name = "ETF"
                for item in uni["Stock"]:
                    if item[0] == row["code"]: name = item[1]; break
                tag = name
                for kw, idx in INDEX_PATTERNS:
                    if kw in name: tag = idx; break
                if tag in seen_tags: continue
                seen_tags.add(tag); selected.append((row["code"], row["score"]))
                if len(selected) >= SATELLITE_N: break

            if selected:
                total_s = sum(s for _, s in selected)
                for code, sc in selected:
                    w = alloc["stock_sat"] * sc / total_s if total_s > 0 else alloc["stock_sat"] / len(selected)
                    records.append({"date": dt, "code": code, "weight": w})
            else:
                records.append({"date": dt, "code": BOND_ETF, "weight": alloc["stock_sat"]})
        elif alloc["stock_sat"] > 0:
            records.append({"date": dt, "code": BOND_ETF, "weight": alloc["stock_sat"]})

    # Merge & normalize
    ws = pd.DataFrame(records).groupby(["date", "code"])["weight"].sum().unstack(fill_value=0)
    ws = ws.div(ws.sum(axis=1), axis=0); ws.index = pd.to_datetime(ws.index)

    # NAV
    all_codes = list(ws.columns)
    prices = pdf_all[(pdf_all["date"] >= "2021-09-01") & (pdf_all["date"] <= "2026-05-31")
                     & (pdf_all["code"].isin(all_codes))]
    prices = prices[["date", "code", "close"]].copy(); prices["close_adj"] = prices["close"]
    pivot = prices.pivot_table(index="date", columns="code", values="close_adj", aggfunc="last").ffill()

    nav = pd.Series(1.0, index=pivot.index); cw = pd.Series(0, index=all_codes); tc = 0.0
    for i, today in enumerate(pivot.index):
        if i == 0: continue
        yesterday = pivot.index[i - 1]
        dr = pivot.loc[today] / pivot.loc[yesterday] - 1; dr = dr.fillna(0)
        if today in ws.index:
            tw2 = ws.loc[today].reindex(all_codes).fillna(0)
            cost = (tw2 - cw).abs().sum() / 2 * 0.0008
            tc += cost
            nav.loc[today] = nav.loc[yesterday] * (1 + (cw * dr).sum() - cost)
            cw = tw2.copy()
        else:
            nav.loc[today] = nav.loc[yesterday] * (1 + (cw * dr).sum())

    daily = nav.pct_change().dropna()
    r = float(nav.iloc[-1] / nav.iloc[0] - 1) * 100
    ann_r = float((1 + r/100) ** (252 / max(len(daily) + 1, 1)) - 1) * 100
    ann_vol = float(daily.std() * np.sqrt(252) * 100)
    sh = float(ann_r / ann_vol) if ann_vol > 0 else 0
    dd = float((nav / nav.cummax() - 1).min()) * 100
    to = float(ws.diff().abs().sum(axis=1).mean())

    print(f"{label}: Ret={r:.1f}% Ann={ann_r:.1f}% Sharpe={sh:.2f} DD={dd:.1f}% TO={to:.2f}")
    return {"label": label, "total_return": r, "annual_return": ann_r, "sharpe": sh, "max_drawdown": dd, "turnover": to}

print("=" * 50)
print("  Fixed vs Cycle-Aware Factor Weights")
print("=" * 50)
r1 = run_framework("Fixed(20/45/20/15)", use_cycle=False)
r2 = run_framework("Cycle-Aware", use_cycle=True)
print()
best = r2 if r2["sharpe"] > r1["sharpe"] else r1
print(f"Winner: {best['label']} (Sharpe {best['sharpe']:.2f})")
