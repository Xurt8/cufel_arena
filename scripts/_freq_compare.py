"""Compare Monthly vs Quarterly rebalance on full framework"""
import sys, os, json, warnings; warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import pandas as pd, numpy as np
from datetime import datetime
from pathlib import Path

_PROJECT = Path(__file__).parent.parent
ma_df = pd.read_parquet(_PROJECT / "cache" / "ma200_cache.parquet"); ma_df["date"] = pd.to_datetime(ma_df["date"])
pdf_all = pd.read_parquet(_PROJECT / "data" / "etf_daily.parquet"); pdf_all["date"] = pd.to_datetime(pdf_all["date"])
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

from agent.engine import DataAgent, MacroAgent
da = DataAgent(); da.load_all_data(); ma = MacroAgent(use_llm=False)
cycle_cache = {}
def get_cycle(ds):
    if ds in cycle_cache: return cycle_cache[ds]
    r = ma.analyze(da.get_macro_for_decision(datetime.strptime(ds, "%Y-%m-%d")))
    cycle_cache[ds] = r["cycle_phase"]; return r["cycle_phase"]

from backtest.engine import BacktestEngine
ALLOC = {
    "复苏期": {"gold": 0.10, "bond": 0.25, "stock_core": 0.325, "stock_sat": 0.325},
    "扩张期": {"gold": 0.35, "bond": 0.15, "stock_core": 0.175, "stock_sat": 0.175},
    "滞胀期": {"gold": 0.30, "bond": 0.15, "stock_core": 0.10, "stock_sat": 0.10},
    "衰退期": {"gold": 0.10, "bond": 0.50, "stock_core": 0.10, "stock_sat": 0.10},
}
GOLD = "518860"; BOND = "511010"; CORE = {"563220": "A500"}; SAT_N = 4
W = {"mom": 0.20, "vol": 0.45, "sharpe": 0.20, "flow": 0.15}
INDEX_PATTERNS = [
    ("黄金", "黄金"), ("上海金", "黄金"), ("金ETF", "黄金"), ("国债", "国债"), ("城投债", "城投债"),
    ("转债", "可转债"), ("信用债", "信用债"), ("短融", "短融"), ("科创债", "科创债"), ("公司债", "公司债"),
    ("货币", "货币"), ("添益", "货币"), ("科创", "科创"), ("半导体", "芯片"), ("芯片", "芯片"),
    ("消费电子", "消费电子"), ("消电", "消费电子"), ("A500", "A500"), ("沪深300", "沪深300"),
    ("中证500", "中证500"), ("创业板", "创业板"), ("上证50", "上证50"), ("红利", "红利"),
    ("证券", "证券"), ("银行", "银行"), ("新能源", "新能源"), ("光伏", "新能源"),
    ("石油ETF", "石油"), ("养殖", "养殖"), ("粮食", "粮食"), ("医药", "医药"), ("医疗", "医药"),
    ("军工", "军工"), ("通信", "通信"), ("5G", "通信"), ("汽车", "汽车"), ("机器人", "机器人"),
    ("港股", "港股"), ("恒生", "港股"),
]

def run_freq(label, freq):
    be = BacktestEngine.__new__(BacktestEngine); be.freq = freq
    dates = be.generate_rebalance_dates(datetime(2021, 9, 30), datetime(2026, 5, 31))
    records = []
    for dt in dates:
        ds = dt.strftime("%Y-%m-%d"); cycle = get_cycle(ds)
        alloc = ALLOC.get(cycle, ALLOC["衰退期"])
        records.append({"date": dt, "code": GOLD, "weight": alloc["gold"]})
        records.append({"date": dt, "code": BOND, "weight": alloc["bond"]})
        up_to = ma_df[ma_df["date"] <= ds]; latest = up_to.sort_values("date").groupby("code").last()
        above_ma = set(latest[latest["close"] > latest["ma200"]].index)
        core_codes = [co for co in CORE if co in above_ma]
        if core_codes:
            per = alloc["stock_core"] / len(core_codes)
            for co in core_codes: records.append({"date": dt, "code": co, "weight": per})
        elif alloc["stock_core"] > 0:
            records.append({"date": dt, "code": BOND, "weight": alloc["stock_core"]})
        sc_path = _PROJECT / "cache" / f"etf_scores_{ds}.json"; scores = {}
        if sc_path.exists():
            with open(sc_path) as fh: scores = json.load(fh)
        raw_data = []
        for code, name in uni["Stock"]:
            if code not in above_ma: continue
            sc = scores.get(code, {})
            if not sc: continue
            raw_data.append((code, sc.get("mom_60d", 0), sc.get("ann_vol", 0.3), sc.get("sharpe60", 0), sc.get("turnover", 1.0)))
        if raw_data:
            rf = pd.DataFrame(raw_data, columns=["code", "mom_60d", "ann_vol", "sharpe60", "turnover"])
            rf["mom_r"] = rf["mom_60d"].rank(pct=True); rf["vol_r"] = 1 - rf["ann_vol"].rank(pct=True)
            rf["sh_r"] = rf["sharpe60"].rank(pct=True); rf["flow_r"] = rf["turnover"].rank(pct=True)
            rf["score"] = rf["mom_r"] * W["mom"] + rf["vol_r"] * W["vol"] + rf["sh_r"] * W["sharpe"] + rf["flow_r"] * W["flow"]
            rf = rf.sort_values("score", ascending=False)
            seen = set(); sel = []
            for _, row in rf.iterrows():
                item_name = "ETF"
                for it in uni["Stock"]:
                    if it[0] == row["code"]: item_name = it[1]; break
                tag = item_name
                for kw, idx in INDEX_PATTERNS:
                    if kw in item_name: tag = idx; break
                if tag in seen: continue
                seen.add(tag); sel.append((row["code"], row["score"]))
                if len(sel) >= SAT_N: break
            if sel:
                ts = sum(s for _, s in sel)
                for code, sc in sel:
                    w = alloc["stock_sat"] * sc / ts if ts > 0 else alloc["stock_sat"] / len(sel)
                    records.append({"date": dt, "code": code, "weight": w})
            else:
                records.append({"date": dt, "code": BOND, "weight": alloc["stock_sat"]})
        elif alloc["stock_sat"] > 0:
            records.append({"date": dt, "code": BOND, "weight": alloc["stock_sat"]})

    ws = pd.DataFrame(records).groupby(["date", "code"])["weight"].sum().unstack(fill_value=0)
    ws = ws.div(ws.sum(axis=1), axis=0); ws.index = pd.to_datetime(ws.index)
    all_codes = list(ws.columns)
    prices = pdf_all[(pdf_all["date"] >= "2021-09-01") & (pdf_all["date"] <= "2026-05-31") & (pdf_all["code"].isin(all_codes))]
    prices = prices[["date", "code", "close"]].copy(); prices["close_adj"] = prices["close"]
    pivot = prices.pivot_table(index="date", columns="code", values="close_adj", aggfunc="last").ffill()
    nav = pd.Series(1.0, index=pivot.index); cw = pd.Series(0, index=all_codes)
    for i, today in enumerate(pivot.index):
        if i == 0: continue
        yesterday = pivot.index[i - 1]
        dr = pivot.loc[today] / pivot.loc[yesterday] - 1; dr = dr.fillna(0)
        if today in ws.index:
            tw = ws.loc[today].reindex(all_codes).fillna(0)
            cost = (tw - cw).abs().sum() / 2 * 0.0008
            nav.loc[today] = nav.loc[yesterday] * (1 + (cw * dr).sum() - cost)
            cw = tw.copy()
        else:
            nav.loc[today] = nav.loc[yesterday] * (1 + (cw * dr).sum())
    daily = nav.pct_change().dropna()
    r = float(nav.iloc[-1] / nav.iloc[0] - 1) * 100
    ann_r = float((1 + r/100) ** (252 / (len(daily) + 1)) - 1) * 100
    ann_vol = float(daily.std() * np.sqrt(252) * 100)
    sh = float(ann_r / ann_vol) if ann_vol > 0 else 0
    dd = float((nav / nav.cummax() - 1).min()) * 100
    to = float(ws.diff().abs().sum(axis=1).mean())
    print(f"  {label}: Ret={r:.1f}% Ann={ann_r:.1f}% Sharpe={sh:.2f} DD={dd:.1f}% TO={to:.2f}")
    return r, sh, dd, to

print("=== Monthly vs Quarterly Rebalance ===\n")
run_freq("Monthly", "M")
run_freq("Quarterly", "Q")
print()
