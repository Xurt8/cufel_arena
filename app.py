"""
cufel_arena — 宏观驱动 ETF 策略 · Streamlit 前端
启动: streamlit run app.py
"""
import sys
import os
import json
import math
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import requests
import time
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# ── 路径与导入 ─────────────────────────────────────────
_THIS_DIR = Path(__file__).parent
sys.path.insert(0, str(_THIS_DIR))

from src.agent.engine import MacroDrivenETFAgent, MacroAgent, PortfolioAgent, DataAgent, MacroData

# ── 持仓文件路径 ───────────────────────────────────────
# _THIS_DIR 已在上面定义
_HOLDINGS_DIR = _THIS_DIR / "持仓截图"
if not _HOLDINGS_DIR.exists():
    _HOLDINGS_DIR = Path("c:/Users/xrt85/Desktop/3月22日课程资料/持仓截图")

HOLDINGS_FILE = _THIS_DIR / "持仓分析结果.csv"

# ── 持仓加载函数 ───────────────────────────────────────
def parse_holdings_raw(raw_bytes: bytes, filename: str = "") -> pd.DataFrame:
    """解析持仓文件原始字节，支持券商的多种导出格式"""
    temp_path = _THIS_DIR / "_temp_upload.xls"
    with open(temp_path, "wb") as f:
        f.write(raw_bytes)

    result = None

    # 方式1: TSV/CSV 文本格式 (行内列数可能不一致，逐行读取)
    for sep, enc in [('\t', 'gbk'), ('\t', 'gb2312'), ('\t', 'utf-8'),
                     (',', 'gbk'), (',', 'utf-8')]:
        try:
            # 逐行读取，找最长列数的行作为标准
            lines = []
            raw_text = raw_bytes.decode(enc)
            for line in raw_text.strip().split('\n'):
                fields = line.split(sep)
                lines.append(fields)
            max_cols = max(len(r) for r in lines) if lines else 0
            if max_cols >= 10:
                df = pd.DataFrame(lines)
                result = _extract_holdings_from_df(df)
                if result is not None:
                    break
        except Exception:
            continue

    # 方式2: 真正的Excel格式
    if result is None:
        for engine in ['openpyxl', 'xlrd']:
            try:
                df = pd.read_excel(temp_path, engine=engine, header=None)
                if df.shape[1] >= 10:
                    result = _extract_holdings_from_df(df)
                    if result is not None:
                        break
            except Exception:
                continue

    temp_path.unlink(missing_ok=True)
    return result


def _clean_cell(val) -> str:
    """清理单元格值，去掉 ="..." 包裹"""
    s = str(val).strip()
    if s.startswith('="') and s.endswith('"'):
        s = s[2:-1]
    return s

def _extract_holdings_from_df(raw_df: pd.DataFrame) -> pd.DataFrame:
    """从原始DataFrame中提取持仓数据"""
    # 清理所有单元格的 ="..." 格式 (pandas 3.0+ Arrow后端)
    raw_df = raw_df.map(_clean_cell).astype(str)

    # 跳过前几行，从第一个6位代码行开始
    start_row = None
    for i in range(min(len(raw_df), 20)):
        val = str(raw_df.iloc[i, 0]).strip()
        if len(val) == 6 and val.isdigit():
            start_row = i
            break

    if start_row is None:
        return None

    df = raw_df.iloc[start_row:].copy()
    COLS = ['代码', '名称', '证券数量', '库存数量', '可卖数量', '成本价', '当前价',
            '市值', '盈亏', '盈亏比例', '股东账号', '持仓账号', '市场', '备注', '备用']
    df.columns = COLS[:df.shape[1]]
    # 以"库存数量"为准，缺失时用"证券数量"
    if df['库存数量'].sum() == 0:
        df['库存数量'] = df['证券数量']
    df['数量'] = df['库存数量']

    # 过滤：代码必须是6位数字
    df = df[df['代码'].astype(str).str.strip().str.fullmatch(r'\d{6}', na=False)].copy()

    # 数值列转换
    for col in ['数量', '成本价', '当前价', '市值', '盈亏']:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(',', '').str.strip(),
                errors='coerce').fillna(0)

    # 缺失市值用数量*当前价补
    if df['市值'].sum() == 0:
        df['市值'] = df['数量'] * df['当前价']

    df['仓位占比'] = df['市值'] / df['市值'].sum() * 100
    return df


def load_actual_holdings():
    """加载实际持仓 — 仅从QMT实时导出读取"""
    import json
    qmt_path = r"D:\长城策略交易系统\bin.x64\qmt_holdings.json"
    if not os.path.exists(qmt_path):
        qmt_path = r"D:\长城策略交易系统\python\qmt_holdings.json"
    if not os.path.exists(qmt_path):
        return None
    try:
        with open(qmt_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        positions = data.get("positions", [])
        active = [p for p in positions if p.get("shares", 0) > 0]
        if not active:
            return None
        from src.data.local_store import get_names, get_latest_close
        name_map = get_names()
        all_codes = [p["code"] for p in active]
        prices = get_latest_close(all_codes)
        rows = []
        for p in active:
            code = p["code"]
            price = prices.get(code, p.get("price", 0))
            cost = p.get("cost", price) if p.get("cost", 0) > 0 else price
            rows.append({
                "代码": code, "名称": name_map.get(code, code),
                "数量": p["shares"], "当前价": price,
                "成本价": cost, "市值": p["shares"] * price
            })
        return pd.DataFrame(rows)
    except Exception:
        return None

# ── ETF 名称映射 ───────────────────────────────────────
ETF_NAMES = {
    "510300": "沪深300ETF", "510500": "中证500ETF",
    "511010": "国债ETF", "511220": "城投债ETF", "518880": "黄金ETF",
    "159915": "创业板", "159934": "黄金ETF", "159994": "5GETF",
    "510880": "红利ETF", "512690": "酒ETF", "512760": "芯片ETF",
    "512880": "证券ETF", "516160": "新能源",
}

# ── ClickHouse 连接（quantchdb） ──────────────────────
CH_HOST = os.getenv("CHDB_HOST", "10.13.66.5")
CH_PORT = int(os.getenv("CHDB_PORT", "20107"))
CH_USER = os.getenv("CHDB_USER", "cufel_arena_etf_reader")
CH_PASSWORD = os.getenv("CHDB_PASSWORD", "cufel_arena_etf_404")
CH_DATABASE = os.getenv("CHDB_DATABASE", "etf")

CH_CONFIG = {"host": CH_HOST, "port": CH_PORT, "user": CH_USER,
             "password": CH_PASSWORD, "database": CH_DATABASE}

def _ch_fetch(sql: str):
    """安全查询 ClickHouse"""
    from quantchdb import ClickHouseDatabase
    with ClickHouseDatabase(config=CH_CONFIG, terminal_log=False) as db:
        return db.fetch(sql)

def _ch_execute_rows(sql: str):
    """执行并返回原始行列表"""
    from quantchdb import ClickHouseDatabase
    with ClickHouseDatabase(config=CH_CONFIG, terminal_log=False) as db:
        return db.fetch(sql).values.tolist()

@st.cache_data(ttl=300)
def fetch_live_prices(codes: list, target_date: str) -> dict:
    codes_str = ",".join(f"'{c}'" for c in codes)
    sql = f"""
        SELECT code, close, pre_close, pct_chg
        FROM etf.etf_day
        WHERE code IN ({codes_str}) AND date <= '{target_date}'
        ORDER BY date DESC
        LIMIT 1 BY code
    """
    df = _ch_fetch(sql)
    if df.empty: return {}
    return {r["code"]: {"close": r["close"], "pre_close": r["pre_close"], "pct_chg": r["pct_chg"]}
            for _, r in df.iterrows()}

@st.cache_data(ttl=3600)
def fetch_etf_prices(codes: list, start: str, end: str) -> pd.DataFrame:
    codes_str = ",".join(f"'{c}'" for c in codes)
    sql = f"""
        SELECT date, code, close, adj_factor
        FROM etf.etf_day
        WHERE code IN ({codes_str}) AND date BETWEEN '{start}' AND '{end}'
        ORDER BY date, code
    """
    df = _ch_fetch(sql)
    if df.empty: return df
    df["date"] = pd.to_datetime(df["date"])
    df["close_adj"] = df["close"] * df["adj_factor"]
    return df

@st.cache_data(ttl=3600)
@st.cache_data(ttl=3600)
def fetch_date_range():
    df = _ch_fetch("SELECT min(date) as mi, max(date) as ma FROM etf.etf_day")
    if df.empty: return None, None
    return pd.to_datetime(df["mi"].iloc[0]).date(), pd.to_datetime(df["ma"].iloc[0]).date()

# ── Agent 初始化 ───────────────────────────────────────
TRAIL_PROFIT = {
    "扩张期": 0.40,
    "复苏期": 0.30,
    "滞胀期": 0.20,
    "衰退期": 0.15,
}

def compute_stoploss(code, cost, cycle_phase=None):
    from src.data.local_store import get_bars
    bars = get_bars([code], days=120)
    if code not in bars or bars[code] is None or len(bars[code]) < 10:
        tp = TRAIL_PROFIT.get(cycle_phase, 0.30) if cycle_phase else 0.30
        return {'stop_price': round(cost * 0.90, 3), 'peak': cost, 'threshold_pct': 10,
                'trail_profit_pct': round(tp * 100, 1), 'trail_profit_price': round(cost * (1 - tp), 3)}

    df = bars[code]
    closes = df['close'].values
    rets = np.diff(np.log(np.maximum(closes, 0.001)))

    # 1. 异常单日波动过滤(>15%=除权/分拆/数据错误)
    bad_mask = np.abs(rets) >= np.log(1.15)
    clean_rets = rets[~bad_mask]
    if len(clean_rets) < 20:
        clean_rets = rets[-60:]

    # 2. Winsorize (3σ)
    if len(clean_rets) >= 10:
        mu, sigma = np.mean(clean_rets), np.std(clean_rets)
        clean_rets = np.clip(clean_rets, mu - 3 * sigma, mu + 3 * sigma)

    # 3. 年化波动率 → 止损阈值 = 1σ年化, 区间[10%, 25%]
    ann_vol = float(np.std(clean_rets) * np.sqrt(252)) if len(clean_rets) > 5 else 0.3
    threshold_pct = round(max(10, min(25, ann_vol * 100)), 1)

    # 4. Peak: 如有分拆/除权，只用事件后的数据
    bad_idx = np.where(bad_mask)[0]
    if len(bad_idx) > 0:
        split_pos = bad_idx[-1] + 1  # closes 中的位置 (rets[i] = close[i+1]/close[i])
        peak_closes = closes[split_pos:]
    else:
        peak_closes = closes
    n60 = min(60, len(peak_closes))
    peak = float(np.median(np.sort(peak_closes[-n60:])[-3:])) if n60 >= 3 else float(peak_closes[-1])
    if cost > 0 and cost > peak:
        peak = cost
    stop_price = round(peak * (1 - threshold_pct / 100), 3)

    # 全周期 trailing profit
    tp = TRAIL_PROFIT.get(cycle_phase, 0.30) if cycle_phase else 0.30
    tp_price = round(peak * (1 - tp), 3)
    return {'stop_price': stop_price, 'peak': round(peak, 3), 'threshold_pct': threshold_pct,
            'trail_profit_pct': round(tp * 100, 1), 'trail_profit_price': tp_price}

@st.cache_data(ttl=86400)
def build_dynamic_universe() -> dict:
    import json
    df = pd.read_parquet("data/etf_daily.parquet")
    recent = df[df["date"] >= pd.Timestamp.now() - pd.Timedelta(days=60)]
    vol_rank = recent.groupby("code")["vol"].mean().sort_values(ascending=False)
    top_codes = vol_rank.index.tolist()
    with open("data/etf_names.json", "r", encoding="utf-8") as f: names = json.load(f)
    from src.data.local_store import get_sector_map
    c = get_sector_map()
    if not c: raise RuntimeError("板块缓存为空")
    GOLD_KW = ["黄金","上海金","金ETF"]
    uni = {"Stock":[],"Bond":[],"Commodity":[]}
    for code in top_codes:
        name = names.get(code,""); qmt = f"{code}.SH" if code.startswith(("5","6","51","56","58","59")) else f"{code}.SZ"
        if not name or qmt in c["cross"]: continue
        if qmt in c["commodity"]:
            if any(kw in name for kw in GOLD_KW): uni["Commodity"].append((code, name))
        elif qmt in c["bond"] or qmt in c["money"]: uni["Bond"].append((code, name))
        elif qmt in c["stock"]: uni["Stock"].append((code, name))
    return uni

@st.cache_resource
def init_agent():
    agent = MacroDrivenETFAgent(use_llm=True)
    uni = build_dynamic_universe()
    if uni and uni.get("Stock"): agent.set_etf_universe(uni)
    return agent

# ── 回测引擎 ───────────────────────────────────────────
def _calc_nav(weights_df: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    """根据权重DataFrame计算净值"""
    codes = list(weights_df.columns)
    prices = fetch_etf_prices(codes, str(start_date), str(end_date))
    pivot = prices.pivot_table(index="date", columns="code", values="close_adj", aggfunc="last").ffill()
    aligned = weights_df.reindex(pivot.index, method="ffill")
    returns = pivot.pct_change().fillna(0)
    daily_ret = (aligned * returns).sum(axis=1)
    nav = (1 + daily_ret).cumprod()
    return pd.DataFrame({"date": nav.index, "nav": nav.values}).set_index("date")

def run_backtest(agent, start_date: str, end_date: str, theta: float = 1.0) -> pd.DataFrame:
    """策略回测：每月动态调仓"""
    date_range = pd.date_range(start=start_date, end=end_date, freq="ME")
    records = []
    for dt in date_range:
        date_str = dt.strftime("%Y-%m-%d")
        try:
            holdings = agent.get_current_holdings(date_str, theta=theta)
            weights = holdings.get(date_str, {})
        except Exception:
            weights = {}
        records.append({"date": date_str, **weights})
    weights_df = pd.DataFrame(records).set_index("date").fillna(0)
    weights_df.index = pd.to_datetime(weights_df.index)
    if weights_df.empty:
        return pd.DataFrame()
    return _calc_nav(weights_df, start_date, end_date)

def run_backtest_actual(holdings_df: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    """实盘回测：固定当前持仓权重"""
    if holdings_df is None or len(holdings_df) == 0:
        return pd.DataFrame()
    total_mv = holdings_df["市值"].sum()
    weights = {}
    for _, row in holdings_df.iterrows():
        code = str(row["代码"])
        mv = float(row["数量"]) * float(row["成本价"])
        if total_mv > 0:
            weights[code] = mv / total_mv
    date_range = pd.date_range(start=start_date, end=end_date, freq="ME")
    records = [{"date": dt.strftime("%Y-%m-%d"), **weights} for dt in date_range]
    weights_df = pd.DataFrame(records).set_index("date").fillna(0)
    weights_df.index = pd.to_datetime(weights_df.index)
    return _calc_nav(weights_df, start_date, end_date)


# ── LLM 宏观分析 ──────────────────────────────────────
LLM_URL = "http://10.13.66.5:20168/v1/chat/completions"
LLM_KEY = "sk-2025210589-fb1bf3c5"
LLM_MODEL = "Qwen/Qwen3-Next-80B-A3B-Instruct"

def _llm_call(system_prompt: str, user_prompt: str) -> str:
    """通用 LLM 调用"""
    r = requests.post(LLM_URL,
        headers={"Authorization": f"Bearer {LLM_KEY}", "Content-Type": "application/json"},
        json={"model": LLM_MODEL,
              "messages": [{"role":"system","content":system_prompt},
                          {"role":"user","content":user_prompt}],
              "max_tokens": 300, "temperature": 0.4},
        timeout=20)
    if r.status_code == 200:
        return r.json()["choices"][0]["message"]["content"]
    return ""

def llm_analyze_macro(pmi, cpi, ppi, m2, sf, gdp, s1m, s3m) -> dict:
    """MAS 多智能体辩论：Bull vs Bear 双向分析后综合判断"""
    indicators = f"""PMI={pmi}, CPI同比={cpi}%, PPI同比={ppi}%, M2同比={m2}%,
社融增量={sf}亿元, GDP当季同比={gdp}%, SHIBOR 1M/3M={s1m}/{s3m}"""

    bull_prompt = f"""你是多头分析师。基于以下宏观经济指标，尽力找出支撑股市上涨的理由：
{indicators}
请给出看涨判断和经济周期阶段，回复JSON：
{{"view":"bull","cycle":"周期阶段","reason":"看涨理由","confidence":0.0到1.0}}"""

    bear_prompt = f"""你是空头分析师。基于以下宏观经济指标，尽力找出股市可能下跌的风险：
{indicators}
请给出看跌判断和经济周期阶段，回复JSON：
{{"view":"bear","cycle":"周期阶段","reason":"看跌理由","risk":"主要风险","confidence":0.0到1.0}}"""

    try:
        bull_raw = _llm_call("回复严格JSON，不要其他文字。", bull_prompt)
        bear_raw = _llm_call("回复严格JSON，不要其他文字。", bear_prompt)

        import re
        bull = json.loads(re.search(r'\{[^{}]*\}', bull_raw).group()) if re.search(r'\{[^{}]*\}', bull_raw) else {}
        bear = json.loads(re.search(r'\{[^{}]*\}', bear_raw).group()) if re.search(r'\{[^{}]*\}', bear_raw) else {}

        if bull or bear:
            # 综合：多头置信减空头置信，偏向高置信方
            b_conf = bull.get("confidence", 0.5)
            br_conf = bear.get("confidence", 0.5)
            net = b_conf - br_conf
            cycle = bull.get("cycle", bear.get("cycle", "N/A"))
            conf = (b_conf + (1 - br_conf)) / 2  # 综合置信
            analysis = f"🟢多头({bull.get('reason','')[:60]}) | 🔴空头({bear.get('reason','')[:60]})"
            return {"cycle": cycle, "confidence": round(conf, 3),
                    "analysis": analysis, "bull": bull, "bear": bear}
    except Exception:
        pass
    return None



# ── TDA 舆情指标（占位，nlp 库授权后启用）───────────
def fetch_tda_sentiment(date_str: str) -> dict:
    """从 nlp 库获取 TDA 舆情分歧度指标"""
    try:
        sql = f"""SELECT h1_count, h1_size, h2_count, h2_size
        FROM nlp.zong_TDA WHERE date = '{date_str}'"""
        df = _ch_fetch(sql)
        if not df.empty:
            return {"h1_count": df["h1_count"].iloc[0], "h1_size": df["h1_size"].iloc[0],
                    "h2_count": df["h2_count"].iloc[0], "h2_size": df["h2_size"].iloc[0]}
    except Exception:
        pass
    return {}


# ── 实时行情 ───────────────────────────────────────────
SINA_HEADERS = {"Referer": "https://finance.sina.com.cn"}

def get_market_prefix(code: str) -> str:
    return "sh" if code.startswith(("5", "6")) else "sz"

def fetch_realtime_prices(codes: list) -> dict:
    symbols = [f"{get_market_prefix(c)}{c}" for c in codes]
    url = "https://hq.sinajs.cn/list=" + ",".join(symbols)
    try:
        resp = requests.get(url, headers=SINA_HEADERS, timeout=5)
        resp.encoding = "gbk"
        result = {}
        for line in resp.text.strip().split("\n"):
            if '="' not in line:
                continue
            _, data = line.split('="', 1)
            data = data.rstrip('";')
            parts = data.split(",")
            if len(parts) < 32:
                continue
            code = line.split("=")[0].replace("var hq_str_", "")[2:]
            result[code] = {
                "名称": parts[0],
                "今开": float(parts[1]) if parts[1] else 0,
                "昨收": float(parts[2]) if parts[2] else 0,
                "最新价": float(parts[3]) if parts[3] else 0,
                "最高": float(parts[4]) if parts[4] else 0,
                "最低": float(parts[5]) if parts[5] else 0,
                "涨跌额": float(parts[3]) - float(parts[2]) if parts[3] and parts[2] else 0,
                "涨跌幅": (float(parts[3]) / float(parts[2]) - 1) * 100 if parts[3] and parts[2] and float(parts[2]) != 0 else 0,
                "成交量": int(parts[8]) if parts[8] else 0,
                "成交额": float(parts[9]) if parts[9] else 0,
                "日期": parts[30],
                "时间": parts[31],
            }
        return result
    except Exception:
        return {}


# ── 东方财富 API ───────────────────────────────────────
EM_HEADERS = {"Referer": "https://quote.eastmoney.com", "User-Agent": "Mozilla/5.0"}

def _em_market(code: str) -> str:
    """东方财富市场代码: 1=SH, 0=SZ"""
    return "1" if code.startswith(("5", "6")) else "0"

def fetch_em_quote(code: str) -> dict:
    """东方财富实时行情详情（量比、换手率、盘口等）"""
    try:
        secid = f"{_em_market(code)}.{code}"
        url = f"https://push2.eastmoney.com/api/qt/stock/get?secid={secid}" \
              f"&fields=f43,f44,f45,f46,f47,f48,f50,f55,f57,f58,f60,f116,f117,f162,f167,f168,f169,f170,f171"
        resp = requests.get(url, headers=EM_HEADERS, timeout=5)
        data = resp.json().get("data", {})
        if not data:
            return {}
        return {
            "名称": data.get("f58", ""), "最新价": data.get("f43", 0) / 100 if data.get("f43") else 0,
            "今开": data.get("f46", 0) / 100 if data.get("f46") else 0,
            "最高": data.get("f44", 0) / 100 if data.get("f44") else 0,
            "最低": data.get("f45", 0) / 100 if data.get("f45") else 0,
            "涨跌幅": data.get("f170", 0) / 100 if data.get("f170") else 0,
            "成交量": data.get("f47", 0), "成交额": data.get("f48", 0),
            "量比": data.get("f50", 0) / 100 if data.get("f50") else 0,
            "换手率": data.get("f168", 0) / 100 if data.get("f168") else 0,
            "总市值": data.get("f116", 0), "流通市值": data.get("f117", 0),
            "涨速": data.get("f169", 0) / 100 if data.get("f169") else 0,
            "60日涨跌幅": data.get("f171", 0) / 100 if data.get("f171") else 0,
        }
    except Exception:
        return {}

@st.cache_data(ttl=300)
def fetch_em_kline(code: str, klt: int = 101, limit: int = 120) -> pd.DataFrame:
    """东方财富K线: klt=1(1m),5,15,30,60,101(日),102(周),103(月)"""
    try:
        secid = f"{_em_market(code)}.{code}"
        url = f"https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={secid}" \
              f"&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61" \
              f"&klt={klt}&fqt=1&end=20500101&lmt={limit}"
        resp = requests.get(url, headers=EM_HEADERS, timeout=10)
        rows = resp.json().get("data", {}).get("klines", [])
        if not rows:
            return pd.DataFrame()
        data = [r.split(",") for r in rows]
        df = pd.DataFrame(data, columns=["date","open","close","high","low","vol","amount","amp","pct","chg","turn"])
        for col in ["open","close","high","low","vol","amount","amp","pct","turn"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["date"] = pd.to_datetime(df["date"])
        return df
    except Exception:
        return pd.DataFrame()

def calc_metrics(code: str) -> dict:
    """从本地parquet计算 _score_etf 所需因子"""
    try:
        from src.data.local_store import get_bars
        import numpy as np
        bars = get_bars([code], days=130)
        if code not in bars or bars[code] is None or len(bars[code]) < 22:
            return {"mom_60d": 0, "ann_vol": 0.3, "sharpe60": 0, "turnover": 1.0}
        df = bars[code]
        c = df['close'].values
        # 60日动量
        mom_60d = float(c[-1] / c[-61] - 1) if len(c) >= 61 else 0
        # 年化波动率
        r = np.diff(np.log(c[-60:])) if len(c) >= 60 else [0]
        ann_vol = float(np.std(r) * np.sqrt(252)) if len(r) > 5 else 0.3
        # 夏普比率60日
        sharpe60 = float(np.mean(r) / (np.std(r) + 0.0001) * np.sqrt(252)) if len(r) > 5 else 0
        # 量比: 5日均量/20日均量
        vol_col = 'volume' if 'volume' in df.columns else ('vol' if 'vol' in df.columns else None)
        if vol_col:
            v = df[vol_col].values[-20:].astype(float)
        else:
            v = np.ones(20)
        v5 = v[-5:] if len(v) >= 5 else v
        turnover = float(np.nanmean(v5) / (np.nanmean(v) + 0.0001))
        return {"mom_60d": round(mom_60d, 4), "ann_vol": round(ann_vol, 4),
                "sharpe60": round(sharpe60, 4), "turnover": round(turnover, 4)}
    except Exception:
        return {"mom_60d": 0, "ann_vol": 0.3, "sharpe60": 0, "turnover": 1.0}


# ═══════════════════════════════════════════════════════════
# Streamlit UI
# ═══════════════════════════════════════════════════════════
st.set_page_config(page_title="cufel_arena · 宏观驱动ETF", page_icon="📊", layout="wide")

st.markdown("""
<style>
/* ── Apple 风格全局 ── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

.main { background: #f5f5f7; }
.stApp { background: #f5f5f7; font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; }
h1 { font-size: 2rem !important; font-weight: 700 !important; color: #1d1d1f !important; letter-spacing: -0.02em; }
h2 { font-size: 1.4rem !important; font-weight: 600 !important; color: #1d1d1f !important; }
h3 { font-size: 1.1rem !important; font-weight: 600 !important; color: #86868b !important; }
p, span, div, label { color: #1d1d1f !important; }
.st-caption { color: #86868b !important; font-size: 0.8rem !important; }

/* ── 指标卡片 — Apple 风格 ── */
div[data-testid="stMetric"] {
    background: #ffffff;
    border: none;
    border-radius: 18px;
    padding: 20px 24px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04), 0 4px 12px rgba(0,0,0,0.04);
    transition: all 0.35s cubic-bezier(0.25, 0.1, 0.25, 1);
}
div[data-testid="stMetric"]:hover {
    transform: translateY(-2px);
    box-shadow: 0 2px 6px rgba(0,0,0,0.06), 0 8px 24px rgba(0,0,0,0.08);
}
div[data-testid="stMetric"] label {
    color: #86868b !important; font-size: 0.7rem !important;
    font-weight: 500 !important; text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
}
div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
    color: #1d1d1f !important; font-size: 1.5rem !important;
    font-weight: 700 !important; letter-spacing: -0.02em !important;
}
div[data-testid="stMetric"] div[data-testid="stMetricDelta"] {
    color: #86868b !important; font-size: 0.85rem !important;
}

/* ── 按钮 ── */
.stButton > button {
    border-radius: 980px !important;
    font-weight: 500 !important; font-size: 0.82rem !important;
    padding: 6px 20px !important;
    border: none !important;
    background: #1d1d1f !important; color: #ffffff !important;
    transition: all 0.3s cubic-bezier(0.25, 0.1, 0.25, 1) !important;
}
.stButton > button:hover {
    background: #333 !important;
    transform: scale(1.02);
}

/* ── 侧边栏 ── */
section[data-testid="stSidebar"] {
    background: #fafafa !important;
    border-right: 1px solid #e8e8ed !important;
}

/* ── Tab ── */
button[data-baseweb="tab"] {
    color: #86868b !important; font-weight: 500 !important;
    font-size: 0.9rem !important; padding: 8px 24px !important;
    border-radius: 12px 12px 0 0 !important;
}
button[data-baseweb="tab"][aria-selected="true"] {
    color: #1d1d1f !important; background: #ffffff !important;
}

/* ── 表格 ── */
div[data-testid="stDataFrame"] {
    border-radius: 16px; overflow: hidden;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
div[data-testid="stDataFrame"] th {
    background: #fafafa !important; color: #86868b !important;
    font-size: 0.72rem !important; font-weight: 600 !important;
    text-transform: uppercase; letter-spacing: 0.04em;
    border-bottom: 1px solid #e8e8ed !important; padding: 10px 16px !important;
}
div[data-testid="stDataFrame"] td {
    background: #ffffff !important; padding: 12px 16px !important;
    border-bottom: 1px solid #f5f5f7 !important;
}

/* ── Divider ── */
hr { border-color: #e8e8ed !important; }

/* ── 进度条 ── */
div[data-testid="stProgress"] > div {
    background: #e8e8ed !important; border-radius: 980px; height: 6px !important;
}
div[data-testid="stProgress"] > div > div {
    background: #0071e3 !important; border-radius: 980px;
}

/* ── 大盘涨跌色 ── */
.green { color: #34c759 !important; font-weight: 600; }
.red { color: #ff3b30 !important; font-weight: 600; }

/* ── Radio ── */
div[role="radiogroup"] label {
    background: #ffffff !important; border: 1px solid #e8e8ed !important;
    border-radius: 980px !important; padding: 6px 18px !important;
    font-size: 0.82rem !important; color: #1d1d1f !important;
    transition: all 0.2s !important;
}
div[role="radiogroup"] label:hover { border-color: #0071e3 !important; }

/* ── Checkbox ── */
label[data-baseweb="checkbox"] { color: #1d1d1f !important; }

/* ── 持仓表内小按钮：单行紧凑，字号与名称一致 ── */
.st-key-btn_ .stButton button {
    font-size: 0.7rem !important; padding: 0 5px !important;
    min-height: unset !important; height: 22px !important;
    line-height: 22px !important; border-radius: 3px !important;
    font-weight: 500 !important; letter-spacing: -0.01em;
}

""", unsafe_allow_html=True)

# 启动时合并待处理数据
_sync_csv = Path("data/_sync_pending.csv")
if _sync_csv.exists():
    try:
        nd = pd.read_csv(_sync_csv, dtype={"code": str})
        nd["date"] = pd.to_datetime(nd["date"], format="%Y%m%d")
        ex = pd.read_parquet("data/etf_daily.parquet"); ex["code"] = ex["code"].astype(str)
        combined = pd.concat([ex, nd], ignore_index=True).drop_duplicates(subset=["code","date"])
        combined.to_parquet("data/etf_daily.parquet", index=False)
        _sync_csv.unlink()
    except Exception: pass

# 清除旧缓存
st.cache_resource.clear()
st.cache_data.clear()

st.title("cufel_arena")
st.caption("宏观驱动 ETF 策略 · Macro-Driven ETF Strategy")

# ── Sidebar ──────────────────────────────────────────────
st.sidebar.header("⚙️ 参数设置")
min_date, max_date = fetch_date_range()

today = st.sidebar.date_input("分析日期",
    value=max_date if max_date else datetime(2026, 4, 30),
    min_value=min_date, max_value=max_date)

date_str = today.strftime("%Y-%m-%d")

theta = st.sidebar.slider("风险偏好 θ", 0.0, 2.0, 1.0, 0.1,
    help="<1=保守（降低股票）  >1=激进（增持股票）")

st.sidebar.divider()
st.sidebar.header("📋 回测设置")
bt_mode = st.sidebar.radio("回测对象", ["策略建议持仓", "实际持仓"],
    help="策略建议=每月动态调仓 | 实际持仓=固定当前仓位权重")
backtest_start = st.sidebar.date_input("回测起点", value=datetime(2022, 1, 1),
    min_value=min_date, max_value=max_date)
backtest_end = st.sidebar.date_input("回测终点", value=max_date,
    min_value=min_date, max_value=max_date)
compare_mode = st.sidebar.checkbox("对比策略 vs 实盘", value=False,
    help="同时运行两种回测并对比")
run_backtest_btn = st.sidebar.button("🚀 运行回测", type="primary", use_container_width=True)

st.sidebar.divider()
st.sidebar.header("📂 持仓数据")
use_real_holdings = st.sidebar.checkbox("使用我的实际持仓", value=True,
    help="从 持仓分析结果.csv 读取；取消则显示策略建议持仓")
uploaded_file = st.sidebar.file_uploader(
    "上传券商持仓文件", type=["xls", "xlsx", "csv", "txt"],
    help="支持券商导出的 .xls / .xlsx / .csv 格式，自动解析")

# 处理上传
if uploaded_file:
    df = parse_holdings_raw(uploaded_file.getvalue(), uploaded_file.name)
    if df is not None and len(df) > 0:
        st.session_state["holdings_df"] = df
        st.sidebar.success(f"已解析 {len(df)} 只持仓，总市值 {df['市值'].sum()/10000:.2f}万")
        st.cache_data.clear()
    else:
        st.sidebar.error("无法解析文件，请确认是券商导出的持仓表格")

# ── 初始化 Agent ─────────────────────────────────────────
with st.spinner("初始化 Agent..."):
    DYNAMIC_UNIVERSE = build_dynamic_universe()
    for cat in DYNAMIC_UNIVERSE.values():
        for code, name in cat:
            ETF_NAMES[code] = name
    agent = init_agent()

# ═══════════════════════════════════════════════════════════
# 第二个 Tab: 持仓分析
# ═══════════════════════════════════════════════════════════
tab_macro, tab_portfolio, tab_signal, tab_backtest = st.tabs(["🌍 宏观指标", "📌 持仓分析", "📡 策略信号", "📈 回测结果"])

with tab_portfolio:
    # ── 实时行情条 ─────────────────────────────────────
    actual_df = st.session_state.get("holdings_df")
    if actual_df is None or (isinstance(actual_df, pd.DataFrame) and actual_df.empty):
        actual_df = load_actual_holdings()
    if actual_df is not None and not actual_df.empty:
        st.session_state["holdings_df"] = actual_df

    auto_refresh = st.checkbox("🔄 实时刷新 (3s)", value=False, key="auto_reload")
    if actual_df is not None and len(actual_df) > 0:
        codes = actual_df["代码"].tolist()
        rt = fetch_realtime_prices(codes)
        if rt:
            rt_data = []
            total_rt_mv = 0
            total_cost = 0
            for _, row in actual_df.iterrows():
                code = str(row["代码"])
                qty = float(row["数量"])
                cost = float(row["成本价"])
                if code in rt:
                    cp = rt[code]["最新价"]
                    mv = qty * cp
                    pnl = mv - qty * cost
                    pnl_pct = (cp / cost - 1) * 100 if cost > 0 else 0
                    total_rt_mv += mv
                    total_cost += qty * cost
                    clr = "🟢" if rt[code]["涨跌幅"] > 0 else "🔴" if rt[code]["涨跌幅"] < 0 else "⚪"
                    rt_data.append({"代码": code, "名称": rt[code]["名称"], "持仓": int(qty),
                        "成本": f"{cost:.3f}", "现价": f"{cp:.3f}", "涨跌": f"{clr} {rt[code]['涨跌幅']:+.2f}%",
                        "市值(万)": f"{mv/10000:.2f}", "盈亏": f"{pnl:+.0f}", "盈亏%": f"{pnl_pct:+.2f}%"})
                else:
                    total_cost += qty * cost
                    rt_data.append({"代码": code, "名称": "", "持仓": int(qty),
                        "成本": f"{cost:.3f}", "现价": "—", "涨跌": "—",
                        "市值(万)": "—", "盈亏": "—", "盈亏%": "—"})
            total_pnl = total_rt_mv - total_cost
            total_pnl_pct = (total_rt_mv / total_cost - 1) * 100 if total_cost > 0 else 0

            # ── 持仓总览 + 实仓表：左卡右表 ───────────
            card_w, table_w = st.columns([0.6, 4.6])

            with card_w:
                pnl_color = "#34c759" if total_pnl >= 0 else "#ff3b30"
                rows = len(rt_data)
                # 估算卡片高度以匹配表格行数（每行约28px + 表头30px）
                card_min_h = max(200, rows * 28 + 30)
                st.markdown(f"""
                <div style="background:#ffffff; border-radius:14px; padding:18px 14px;
                     box-shadow:0 1px 3px rgba(0,0,0,0.03), 0 3px 8px rgba(0,0,0,0.03);
                     text-align:center; min-height:{card_min_h}px;
                     display:flex; flex-direction:column; justify-content:center;">
                <div style="font-size:0.72rem; font-weight:600; color:#1d1d1f; margin-bottom:12px;">持仓总览</div>
                <div style="font-size:0.58rem; color:#86868b; letter-spacing:0.04em;">总市值</div>
                <div style="font-size:1.05rem; font-weight:700; color:#1d1d1f; margin-bottom:10px;">{total_rt_mv/10000:.1f}万</div>
                <div style="font-size:0.58rem; color:#86868b; letter-spacing:0.04em;">总成本</div>
                <div style="font-size:1.05rem; font-weight:700; color:#1d1d1f; margin-bottom:10px;">{total_cost/10000:.1f}万</div>
                <div style="font-size:0.58rem; color:#86868b; letter-spacing:0.04em;">总盈亏</div>
                <div style="font-size:1.05rem; font-weight:700; color:{pnl_color};">{total_pnl:+.0f}</div>
                <div style="font-size:0.65rem; color:#86868b; margin-bottom:10px;">{total_pnl_pct:+.2f}%</div>
                <div style="font-size:0.58rem; color:#86868b; letter-spacing:0.04em;">持仓数</div>
                <div style="font-size:1.05rem; font-weight:700; color:#1d1d1f; margin-bottom:10px;">{len(rt_data)}</div>
                <div style="margin-top:auto; padding-top:8px; border-top:1px solid #f5f5f7;">
                <span style="font-size:0.58rem; color:#86868b;">{datetime.now().strftime('%H:%M:%S')}</span>
                </div>
                </div>
                """, unsafe_allow_html=True)

            with table_w:
                st.caption("实仓表")
                hcols = st.columns([0.5, 0.9, 0.7, 0.8, 0.8, 0.7, 0.65])
                for i, h in enumerate(["代码", "名称", "现价", "涨跌", "市值(万)", "盈亏", "盈亏%"]):
                    hcols[i].markdown(f"<span style='font-size:0.7rem;color:#86868b;'>{h}</span>", unsafe_allow_html=True)

                selected_code = st.session_state.get("detail_code", None)
                for d in rt_data:
                    rcols = st.columns([0.5, 0.9, 0.7, 0.8, 0.8, 0.7, 0.65])
                    is_sel = (selected_code == d["代码"])
                    lbl = f"▸{d['代码']}" if is_sel else d["代码"]
                    if rcols[0].button(lbl, key=f"btn_{d['代码']}", help=f"查看{d['代码']}详情",
                                       type="primary" if is_sel else "secondary"):
                        st.session_state["detail_code"] = None if is_sel else d["代码"]
                        st.rerun()
                    for j, k in enumerate(["名称", "现价", "涨跌", "市值(万)", "盈亏", "盈亏%"]):
                        rcols[j+1].markdown(f"<span style='font-size:0.7rem;color:#1d1d1f;line-height:1;'>{d[k]}</span>", unsafe_allow_html=True)

            # ── 持仓详情面板 ─────────────────────────
            if selected_code and selected_code in [d["代码"] for d in rt_data]:
                st.divider()
                st.subheader(f"📋 {selected_code} 详情")

                em_q = fetch_em_quote(selected_code)
                metrics = calc_metrics(selected_code)

                # 实时行情指标
                mc = st.columns(6)
                mc[0].metric("最新价", f"{em_q.get('最新价', 0):.3f}" if em_q else "—")
                mc[1].metric("涨跌幅", f"{em_q.get('涨跌幅', 0):+.2f}%" if em_q else "—")
                mc[2].metric("换手率", f"{em_q.get('换手率', 0):.2f}%" if em_q else "—")
                mc[3].metric("量比", f"{em_q.get('量比', 0):.2f}" if em_q else "—")
                mc[4].metric("年化波动率", f"{metrics.get('年化波动率', 0):.1f}%")
                mc[5].metric("60日涨跌", f"{em_q.get('60日涨跌幅', 0):+.2f}%" if em_q else "—")

                # 位置指标
                pos_cols = st.columns(2)
                with pos_cols[0]:
                    p60 = metrics.get("60日位置", 50)
                    st.caption(f"60日位置: {p60:.1f}%")
                    st.progress(p60 / 100)
                with pos_cols[1]:
                    p120 = metrics.get("120日位置", 50)
                    st.caption(f"120日位置: {p120:.1f}%")
                    st.progress(p120 / 100)

                # K线图：5日分时 / 日K / 月K
                klt_tabs = st.radio("K线周期", ["5日分时(60m)", "日K", "月K"], horizontal=True, key=f"klt_{selected_code}")
                klt_map = {"5日分时(60m)": (60, 5*4), "日K": (101, 90), "月K": (103, 36)}
                klt, lmt = klt_map[klt_tabs]

                kdf = fetch_em_kline(selected_code, klt=klt, limit=lmt)
                if not kdf.empty:
                    fig = go.Figure()
                    fig.add_trace(go.Candlestick(
                        x=kdf["date"], open=kdf["open"], high=kdf["high"],
                        low=kdf["low"], close=kdf["close"],
                        increasing_line_color="#ef5350", decreasing_line_color="#26a69a"))
                    fig.add_trace(go.Bar(x=kdf["date"], y=kdf["vol"],
                        name="量", marker_color="rgba(0,0,0,0.12)",
                        yaxis="y2", opacity=0.3))
                    fig.update_layout(
                        title=f"{selected_code} — {klt_tabs}",
                        height=400, margin=dict(l=5, r=5, t=30, b=5),
                        xaxis_rangeslider_visible=False,
                        yaxis=dict(title=""), yaxis2=dict(overlaying="y", side="right", showticklabels=False),
                        showlegend=False, template="plotly_white")
                    st.plotly_chart(fig, use_container_width=True)

        if auto_refresh:
            time.sleep(3)
            st.rerun()

    # 获取策略持仓
    strategy_holdings = {}
    try:
        sh = agent.get_current_holdings(date_str, theta=theta)
        strategy_holdings = sh.get(date_str, {})
    except Exception as e:
        st.error(f"策略计算失败: {e}")

    # actual_df 已在实时行情条加载

    # 三列布局
    if use_real_holdings and actual_df is not None:
        col_left, col_mid, col_right = st.columns([1, 0.05, 1])
    else:
        col_left, col_right = st.columns([1, 1])

    # ── 左侧: 实际持仓 ──────────────────────────────
    with col_left:
        if use_real_holdings and actual_df is not None:
            st.subheader("💰 我的实际持仓")

            # 获取实时价格
            codes = actual_df["代码"].tolist()
            live = fetch_live_prices(codes, date_str)

            # 更新市值
            actual_data = []
            for _, row in actual_df.iterrows():
                code = str(row["代码"])
                qty = float(row["数量"])
                cost = float(row["成本价"])
                name = row.get("名称", ETF_NAMES.get(code, code))
                cat = row.get("类别", "其他")

                if code in live:
                    cur_price = float(live[code]["close"])
                    pct = float(live[code].get("pct_chg", 0))
                else:
                    cur_price = float(row["当前价"])
                    pct = 0

                market_val = qty * cur_price
                cost_val = qty * cost
                pnl = market_val - cost_val
                pnl_pct = (pnl / cost_val * 100) if cost_val else 0

                actual_data.append({
                    "代码": code, "名称": name, "数量": int(qty),
                    "成本价": cost, "当前价": cur_price,
                    "市值": market_val, "盈亏": pnl,
                    "盈亏%": pnl_pct, "类别": cat,
                    "涨跌幅%": pct,
                })

            df_real = pd.DataFrame(actual_data)
            total_mv = df_real["市值"].sum()

            # 饼图
            fig_real = px.pie(df_real, values="市值", names="代码",
                title=f"实际持仓分布 (总市值 {total_mv/10000:.1f}万)",
                hole=0.4, hover_data=["名称", "盈亏%"])
            fig_real.update_traces(texttemplate="%{percent:.1%}", textposition="inside")
            st.plotly_chart(fig_real, use_container_width=True)

            # 盈亏表格
            st.subheader("盈亏明细")
            display_df = df_real[["代码", "名称", "数量", "当前价", "市值", "盈亏", "盈亏%", "涨跌幅%"]].copy()
            display_df["市值"] = display_df["市值"].apply(lambda x: f"{x/10000:.2f}万")
            display_df["盈亏"] = display_df["盈亏"].apply(lambda x: f"{x:+.0f}")
            display_df["盈亏%"] = display_df["盈亏%"].apply(lambda x: f"{x:+.2f}%")
            display_df["涨跌幅%"] = display_df["涨跌幅%"].apply(lambda x: f"{x:+.2f}%")
            st.dataframe(display_df, use_container_width=True, hide_index=True)

            # 类别分布
            cat_sum = df_real.groupby("类别")["市值"].sum()
            cat_pct = (cat_sum / total_mv * 100).round(1)
            st.subheader("类别分布")
            c_cols = st.columns(len(cat_sum))
            for i, (cat, pct) in enumerate(cat_pct.items()):
                c_cols[i].metric(cat, f"{pct}%")

        else:
            st.subheader("🎯 策略建议持仓")
            if strategy_holdings:
                fig = px.pie(values=list(strategy_holdings.values()),
                    names=list(strategy_holdings.keys()),
                    title="策略建议权重", hole=0.4)
                fig.update_traces(texttemplate="%{percent:.1%}")
                st.plotly_chart(fig, use_container_width=True)

    # ── 右侧: 策略持仓/对比 ───────────────────────────
    with col_right:
        if use_real_holdings and actual_df is not None and strategy_holdings:
            st.subheader("🎯 策略建议持仓")

            fig_strat = px.pie(values=list(strategy_holdings.values()),
                names=list(strategy_holdings.keys()),
                title="策略建议权重", hole=0.4)
            fig_strat.update_traces(texttemplate="%{percent:.1%}")
            st.plotly_chart(fig_strat, use_container_width=True)

            # 持仓对比
            st.subheader("📊 实盘 vs 策略对比")
            actual_weights = {}
            for _, r in df_real.iterrows():
                actual_weights[r["代码"]] = r["市值"] / total_mv

            all_codes = sorted(set(list(actual_weights.keys()) + list(strategy_holdings.keys())))
            compare_data = []
            for c in all_codes:
                aw = actual_weights.get(c, 0)
                sw = strategy_holdings.get(c, 0)
                diff = sw - aw
                compare_data.append({
                    "代码": c,
                    "名称": ETF_NAMES.get(c, c),
                    "实际权重": f"{aw*100:.1f}%",
                    "策略权重": f"{sw*100:.1f}%",
                    "差异": f"{diff*100:+.1f}%",
                    "操作建议": "⬆增持" if diff > 0.03 else "⬇减持" if diff < -0.03 else "—持有"
                })

            st.dataframe(pd.DataFrame(compare_data),
                use_container_width=True, hide_index=True,
                column_config={"操作建议": st.column_config.TextColumn(width="small")})

        elif strategy_holdings:
            df_hold = pd.DataFrame({
                "代码": list(strategy_holdings.keys()),
                "名称": [ETF_NAMES.get(c, c) for c in strategy_holdings.keys()],
                "权重": [f"{v*100:.1f}%" for v in strategy_holdings.values()]
            })
            st.dataframe(df_hold, use_container_width=True, hide_index=True)


    # ── 交易信号区（持仓分析底部）─────────────────────
    if actual_df is not None and len(actual_df) > 0:
        st.divider()
        st.subheader("📡 策略信号")
        llm_result = None
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            macro_data = agent.data_agent.get_macro_for_decision(date_obj)

            # ── LLM 分析（优先）──
            llm_result = llm_analyze_macro(
                macro_data.pmi, macro_data.cpi_yoy, macro_data.ppi_yoy,
                macro_data.m2_yoy, macro_data.sf_month, macro_data.gdp_yoy,
                macro_data.shibor_1m, macro_data.shibor_3m)

            if llm_result:
                cycle = llm_result.get("cycle", "N/A")
                conf = llm_result.get("confidence", 0.5)
                summary = llm_result.get("analysis", "")
                source = "🤖 LLM"
            else:
                # 回退到规则打分
                analysis = agent.macro_agent.analyze(macro_data)
                cycle = analysis.get("cycle_phase", "N/A")
                conf = analysis.get("confidence", 0)
                summary = analysis.get("analysis", "")
                source = "📏 规则"
        except Exception:
            cycle, conf, summary, source = "N/A", 0, "", "—"

        sig_l, sig_r = st.columns([1.5, 3.5])

        with sig_l:
            clr_map = {"复苏期": "green", "扩张期": "green", "滞胀期": "orange", "衰退期": "red", "N/A": "gray"}
            st.markdown(f"### :{clr_map.get(cycle, 'gray')}[{cycle}]")
            st.caption(f"来源: {source}")
            st.caption(f"置信 {conf:.0%}")
            if summary:
                st.caption(summary)

            # MAS 辩论详情
            if llm_result and "bull" in llm_result:
                bc = llm_result["bull"].get("confidence", 0.5)
                brc = llm_result["bear"].get("confidence", 0.5)
                st.caption(f"🟢 多头: {bc:.0%}  |  🔴 空头: {brc:.0%}")
                st.progress(bc / max(bc + brc, 0.01), text="多空平衡")

            st.caption(f"PMI {macro_data.pmi:.1f} | CPI {macro_data.cpi_yoy:.1f}% | M2 {macro_data.m2_yoy:.1f}%")

            if strategy_holdings:
                st.caption("策略建议池")
                for code, w in strategy_holdings.items():
                    st.caption(f"{ETF_NAMES.get(code, code)}({code}): **{w*100:.1f}%**")

        with sig_r:
            # 实际持仓按资产类别汇总 → 对比策略建议的股票/债券/商品比例
            if actual_df is not None and len(actual_df) > 0:
                # 分类实际持仓
                type_map = {
                    "510300": "股票", "510500": "股票", "159915": "股票", "159994": "股票",
                    "510880": "股票", "512690": "股票", "512760": "股票", "512880": "股票",
                    "516160": "股票", "159185": "股票", "159672": "股票", "002506": "股票",
                    "511010": "债券", "511220": "债券",
                    "518880": "商品", "159934": "商品",
                }
                actual_types = {"股票": 0.0, "债券": 0.0, "商品": 0.0}
                total_mv = 0
                for _, r in actual_df.iterrows():
                    code = str(r["代码"])
                    mv = float(r["数量"]) * float(r["当前价"])
                    t = type_map.get(code, "股票")
                    actual_types[t] += mv
                    total_mv += mv

                # 策略建议的类别比例
                strategy_types = {"股票": 0.0, "债券": 0.0, "商品": 0.0}
                for code, w in strategy_holdings.items():
                    t = type_map.get(code, "股票")
                    strategy_types[t] += w

                st.caption("资产类别对比（实际 vs 策略）")
                tc = st.columns(3)
                for i, (t, label) in enumerate([("股票", "🟢"), ("债券", "🔵"), ("商品", "🟡")]):
                    ap = actual_types[t] / total_mv * 100 if total_mv > 0 else 0
                    sp = strategy_types[t] * 100
                    diff = sp - ap
                    tc[i].metric(f"{label} {t}",
                                 f"{ap:.1f}% → {sp:.1f}%",
                                 delta=f"{diff:+.1f}%")

                # ── 持仓强弱评分（统一 _score_etf 公式）─────────
                scores = {}
                for _, r in actual_df.iterrows():
                    code = str(r["代码"])
                    try:
                        m = calc_metrics(code)
                        score = PortfolioAgent._score_etf(m)
                    except Exception:
                        score = 0.5
                    scores[code] = score

                # ── 按类别智能分配 ────────────────────
                st.caption("实盘调整建议（按强弱排序）")
                adj_plan = []
                for t in ["股票", "商品", "债券"]:
                    in_type = [(str(r["代码"]), float(r["数量"]), float(r["当前价"]))
                               for _, r in actual_df.iterrows()
                               if type_map.get(str(r["代码"]), "股票") == t]
                    if len(in_type) == 0:
                        continue

                    target_type_w = strategy_types.get(t, 0)
                    type_total_mv = sum(qty * price for _, qty, price in in_type)
                    target_type_mv = total_mv * target_type_w  # 该类别总目标市值
                    diff_type_mv = target_type_mv - type_total_mv  # 需增减的总金额

                    # 按评分排序 → 高分多配，低分少配
                    in_type.sort(key=lambda x: scores.get(x[0], 0.5), reverse=True)
                    total_score = sum(scores.get(c, 0.5) for c, _, _ in in_type)
                    if total_score == 0:
                        total_score = len(in_type)

                    for code, qty, price in in_type:
                        cur_mv = qty * price
                        cur_w = cur_mv / total_mv if total_mv > 0 else 0
                        sc = scores.get(code, 0.5)
                        target_w = target_type_w * sc / total_score
                        diff_mv = total_mv * target_w - cur_mv
                        stars = "⭐" if sc > 0.65 else "👍" if sc > 0.5 else "👎" if sc < 0.35 else "—"
                        action = "增持" if diff_mv > 500 else "减持" if diff_mv < -500 else "—"
                        est_cost = abs(diff_mv) * 0.0004 if action != "—" else 0
                        adj_plan.append({
                            "代码": code, "名称": ETF_NAMES.get(code, code),
                            "类别": t, "评分": f"{sc:.2f}",
                            "强弱": stars,
                            "当前": f"{cur_w*100:.1f}%", "目标": f"{target_w*100:.1f}%",
                            "操作": action, "差额": f"{diff_mv:+,.0f}元",
                            "预估成本": f"~{est_cost:.0f}元" if est_cost > 0 else "—",
                        })

                if adj_plan:
                    st.dataframe(pd.DataFrame(adj_plan), use_container_width=True, hide_index=True,
                        column_config={
                            "强弱": st.column_config.TextColumn(width="small"),
                            "操作": st.column_config.TextColumn(width="small"),
                        })
                    st.caption("评分：动量30% + 低波30% + 夏普25% + 量比15% | ⭐强势 > 👍稳健 > 👎弱势")
                else:
                    st.success("各类别比例合理，无需调整")



# ═══════════════════════════════════════════════════════════
# 第一个 Tab: 宏观指标
# ═══════════════════════════════════════════════════════════
with tab_macro:
    st.header("🌍 宏观指标分析")
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        macro_data = agent.data_agent.get_macro_for_decision(date_obj)
        analysis = agent.macro_agent.analyze(macro_data)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("PMI", f"{macro_data.pmi:.1f}")
        c2.metric("CPI 同比", f"{macro_data.cpi_yoy:.1f}%")
        c3.metric("M2 同比", f"{macro_data.m2_yoy:.1f}%")
        c4.metric("SHIBOR 1M", f"{macro_data.shibor_1m:.2f}%")

        st.info(f"**经济周期判断**: {analysis.get('cycle_phase', 'N/A')}  |  "
                f"**置信度**: {analysis.get('confidence', 0):.2f}  |  "
                f"**分析**: {analysis.get('analysis', '')}")

        # 宏观走势图
        metrics_tab = ["PMI", "CPI", "M2", "社融"]
        figs_data = [
            (macro_data.pmi_history, "PMI 近6期", "#2196F3"),
            (macro_data.cpi_history, "CPI 近6期", "#FF5722"),
            (macro_data.m2_history, "M2 近6期", "#4CAF50"),
            (macro_data.sf_history, "社融 近6期", "#9C27B0"),
        ]
        cols = st.columns(4)
        for i, (data, title, color) in enumerate(figs_data):
            if data:
                fig = go.Figure()
                fig.add_trace(go.Scatter(y=data, mode="lines+markers",
                    name=title, line=dict(color=color)))
                fig.update_layout(title=title, height=220,
                    margin=dict(l=5, r=5, t=25, b=5))
                cols[i].plotly_chart(fig, use_container_width=True)

        # 经济周期矩阵
        st.subheader("周期阶段与配置建议")
        cycle_info = {
            "复苏期": ("增持股票", "沪深300+中证500 为主", "🟢", 0.60),
            "扩张期": ("重仓股票", "沪深300+行业ETF", "🟢🟢", 0.75),
            "滞胀期": ("防御为主", "国债+黄金 为主", "🟡", 0.25),
            "衰退期": ("避险优先", "国债+城投债+黄金", "🔴", 0.15),
        }
        current_cycle = analysis.get("cycle_phase", "N/A")
        ci = cycle_info.get(current_cycle, ("—", "—", "—", 0))

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("当前周期", f"{ci[2]} {current_cycle}")
        c2.metric("操作策略", ci[0])
        c3.metric("配置重点", ci[1])
        c4.metric("建议股票仓位", f"{ci[3]*100:.0f}%")

    except Exception as e:
        st.error(f"宏观分析失败: {e}")


# ═══════════════════════════════════════════════════════════
# 第四个 Tab: 回测结果
# ═══════════════════════════════════════════════════════════
# (注：Arena 基准已整合到宏观指标 Tab 中)
# Tab: 策略信号 + QMT 指令
with tab_signal:
    st.header("📡 策略信号 · QMT 指令")

    strategy_holdings = {}
    try:
        sh = agent.get_current_holdings(date_str, theta=theta)
        strategy_holdings = sh.get(date_str, {})
        if strategy_holdings:
            st.success(f"策略计算完成 · {date_str}")
            cols = st.columns(min(len(strategy_holdings), 5))
            for i, (code, w) in enumerate(sorted(strategy_holdings.items(), key=lambda x: x[1], reverse=True)):
                name = ETF_NAMES.get(code, code)
                cols[i % 5].metric(name, f"{w*100:.1f}%", f"{code}")
        else:
            st.warning("策略计算返回空持仓")
    except Exception as e:
        st.error(f"策略计算失败: {e}")

    # 导出 QMT
    actual_df = st.session_state.get("holdings_df")
    if strategy_holdings and actual_df is not None and len(actual_df) > 0:
        # 获取当前周期（用于止盈阈值）
        signal_cycle = "N/A"
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            macro_data = agent.data_agent.get_macro_for_decision(date_obj)
            analysis = agent.macro_agent.analyze(macro_data)
            signal_cycle = analysis.get("cycle_phase", "N/A")
        except Exception:
            pass
        try:
            qmt_dir = r"D:\长城策略交易系统\python"
            os.makedirs(qmt_dir, exist_ok=True)
            stops_export = []
            for _, row in actual_df.iterrows():
                code = str(row["代码"]); cost = float(row["成本价"])
                sl = compute_stoploss(code, cost, cycle_phase=signal_cycle)
                stops_export.append({"code": code, "name": ETF_NAMES.get(code, row.get("名称", code)),
                    "cost": cost, "stop_price": sl["stop_price"], "peak": sl["peak"],
                    "qty": int(float(row["数量"])), "threshold_pct": sl.get("threshold_pct", 8),
                    "trail_profit_pct": sl.get("trail_profit_pct", 30),
                    "trail_profit_price": sl.get("trail_profit_price", round(cost * 0.70, 3))})
            export_data = {"date": date_str, "cycle_id": datetime.now().strftime("%Y%m"),
                           "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                           "target_weights": {c2: round(w2, 4) for c2, w2 in strategy_holdings.items()},
                           "stops": stops_export,
                           "trades": {"止损卖出": [], "调仓": []}}
            with open(os.path.join(qmt_dir, "qmt_orders_latest.json"), "w", encoding="utf-8") as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            # Also write a copy to D:\ for QMT discovery
            with open(r"D:\qmt_orders_latest.json", "w", encoding="utf-8") as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            st.success(f"已导出 QMT 指令 ({len(stops_export)} 只止损监控)")
        except Exception as e:
            st.warning(f"QMT 导出失败: {e}")

    # 当前 QMT 指令快照
    st.divider()
    st.subheader("📋 QMT 当前指令")
    qmt_path = r"D:\长城策略交易系统\python\qmt_orders_latest.json"
    if os.path.exists(qmt_path):
        try:
            with open(qmt_path, "r", encoding="utf-8") as f_q:
                qd = json.load(f_q)
            c1, c2, c3 = st.columns(3)
            c1.metric("日期", qd.get("date", "?"))
            c2.metric("生成", qd.get("generated", "?")[-5:])
            c3.metric("监控", f"{len(qd.get("stops", []))} 只")
            tw = qd.get("target_weights", {})
            if tw:
                st.caption("目标权重")
                tcs = st.columns(min(len(tw), 6))
                for i, (code, w) in enumerate(sorted(tw.items(), key=lambda x: x[1], reverse=True)):
                    name = ETF_NAMES.get(code, code)
                    tcs[i % 6].metric(name, f"{w*100:.1f}%", code)
            stops = qd.get("stops", [])
            if stops:
                with st.expander(f"止损/止盈明细 ({len(stops)} 只)"):
                    sd = [{"代码": s["code"], "名称": ETF_NAMES.get(s["code"], s.get("name","")), "持仓": s.get("qty",0),
                           "止损价": s.get("stop_price",0), "止损阈值": f"{s.get('threshold_pct',8)}%",
                           "止盈价": s.get("trail_profit_price", 0),
                           "止盈阈值": f"{s.get('trail_profit_pct',30)}%",
                           "预估成本": f"~{s.get('qty',0) * s.get('stop_price',0) * 0.0004:.0f}元"}
                          for s in stops]
                    st.dataframe(pd.DataFrame(sd), use_container_width=True, hide_index=True)
        except Exception:
            st.caption("读取失败")

    # 止损触发记录
    sl_log_path = r"D:\长城策略交易系统\bin.x64\stoploss_log.json"
    if os.path.exists(sl_log_path):
        try:
            with open(sl_log_path, "r", encoding="utf-8") as f:
                sl_log = json.load(f)
            events = sl_log.get("events", [])
            if events:
                st.divider()
                st.subheader(f"🛑 止损触发记录 ({len(events)} 次)")
                ed = [{"时间": e["time"], "代码": e["code"], "名称": e.get("name",""),
                       "数量": e.get("qty",0), "成交价": e.get("price",0),
                       "回撤": f"{e.get('drawdown',0):.1f}%", "类型": e.get("reason","")}
                      for e in events]
                st.dataframe(pd.DataFrame(ed), use_container_width=True, hide_index=True)
        except Exception:
            pass

    else:
        st.caption("尚未生成 QMT 指令")

with tab_backtest:
    st.header("📈 回测结果")

    if run_backtest_btn:
        bs = backtest_start.strftime("%Y-%m-%d")
        be = backtest_end.strftime("%Y-%m-%d")
        with st.spinner(f"回测中 {bs} → {be}..."):
            try:
                # 运行回测
                if compare_mode and actual_df is not None and len(actual_df) > 0:
                    bt1 = run_backtest(agent, bs, be, theta=theta)
                    bt2 = run_backtest_actual(actual_df, bs, be)
                    results = [("策略建议", bt1, "#2196F3"), ("实际持仓", bt2, "#FF5722")]
                elif bt_mode == "实际持仓" and actual_df is not None and len(actual_df) > 0:
                    results = [("实际持仓", run_backtest_actual(actual_df, bs, be), "#FF5722")]
                else:
                    results = [("策略建议", run_backtest(agent, bs, be, theta=theta), "#2196F3")]

                if all(r[1].empty for r in results):
                    st.warning("回测结果为空")
                else:
                    # 合并净值曲线
                    fig_nav = go.Figure()
                    fig_dd = go.Figure()
                    metrics_data = []

                    for label, bt, color in results:
                        if bt.empty:
                            continue
                        nav = bt["nav"]
                        dd = (nav - nav.cummax()) / nav.cummax() * 100
                        total_ret = (nav.iloc[-1] / nav.iloc[0] - 1) * 100
                        years = (nav.index[-1] - nav.index[0]).days / 365.25
                        ann_ret = ((nav.iloc[-1] / nav.iloc[0]) ** (1/years) - 1) * 100 if years > 0 else 0
                        max_dd_val = dd.min()
                        ret_series = nav.pct_change().dropna()
                        sharpe = (ret_series.mean() / ret_series.std() * math.sqrt(252)) if ret_series.std() > 0 else 0

                        metrics_data.append({
                            "": label, "累计收益": f"{total_ret:.2f}%",
                            "年化收益": f"{ann_ret:.2f}%", "最大回撤": f"{max_dd_val:.2f}%",
                            "夏普比率": f"{sharpe:.2f}",
                        })

                        fig_nav.add_trace(go.Scatter(x=nav.index, y=nav.values,
                            name=label, line=dict(color=color, width=2)))
                        fig_dd.add_trace(go.Scatter(x=dd.index, y=dd.values,
                            name=label, line=dict(color=color, width=1.5),
                            fill="tozeroy", fillcolor=f"rgba({','.join(str(int(color[i:i+2],16)) for i in (1,3,5))},0.1)"))

                    # 指标对比表
                    if len(metrics_data) > 1:
                        st.subheader("📊 指标对比")
                        st.dataframe(pd.DataFrame(metrics_data), use_container_width=True, hide_index=True)

                    # 单指标行（非对比模式）
                    if len(metrics_data) == 1:
                        d = metrics_data[0]
                        cols = st.columns(4)
                        cols[0].metric("累计收益", d["累计收益"])
                        cols[1].metric("年化收益", d["年化收益"])
                        cols[2].metric("最大回撤", d["最大回撤"])
                        cols[3].metric("夏普比率", d["夏普比率"])

                    # 净值曲线图
                    fig_nav.update_layout(title="净值曲线对比" if compare_mode else "净值曲线",
                        height=400, margin=dict(l=10, r=10, t=30, b=10),
                        hovermode="x unified")
                    st.plotly_chart(fig_nav, use_container_width=True)

                    # 回撤曲线图
                    fig_dd.update_layout(title="回撤曲线对比 (%)" if compare_mode else "回撤曲线 (%)",
                        height=280, margin=dict(l=10, r=10, t=30, b=10),
                        hovermode="x unified")
                    st.plotly_chart(fig_dd, use_container_width=True)

            except Exception as e:
                st.error(f"回测失败: {e}")
                import traceback; st.code(traceback.format_exc())
    else:
        st.info("👈 在侧边栏设置回测参数后，点击「运行回测」")

st.divider()
st.caption(f"数据来源: ClickHouse {CH_HOST}:{CH_PORT} | etf.etf_day ({min_date} ~ {max_date}) | 实时行情: 新浪财经")
