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
sys.path.insert(0, str(_THIS_DIR / "ETFAgents" / "MacroDrivenETF"))

from macro_driven_etf_agent import (
    MacroDrivenETFAgent, DataAgent, MacroAgent, PortfolioAgent,
    _DATA_PATH, _CACHE_PATH
)

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
    """清理单元格值，去掉 =\"...\" 包裹"""
    s = str(val).strip()
    if s.startswith('="') and s.endswith('"'):
        s = s[2:-1]
    return s

def _extract_holdings_from_df(raw_df: pd.DataFrame) -> pd.DataFrame:
    """从原始DataFrame中提取持仓数据"""
    # 清理所有单元格的 =\"...\" 格式 (pandas 3.0+ Arrow后端)
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
    """从持仓截图目录自动加载最新持仓"""
    xls_dir = _HOLDINGS_DIR
    if xls_dir.exists():
        files = sorted(xls_dir.glob("*资金股份查询*"), reverse=True)
        if files:
            raw = files[0].read_bytes()
            df = parse_holdings_raw(raw, files[0].name)
            if df is not None and len(df) > 0:
                return df

    # 回退到 CSV
    if HOLDINGS_FILE.exists():
        raw = HOLDINGS_FILE.read_bytes()
        return parse_holdings_raw(raw, HOLDINGS_FILE.name)
    return None

# ── ETF 名称映射 ───────────────────────────────────────
ETF_NAMES = {
    "510300": "沪深300ETF", "510500": "中证500ETF",
    "511010": "国债ETF", "511220": "城投债ETF", "518880": "黄金ETF",
    "159915": "创业板", "159934": "黄金ETF", "159994": "5GETF",
    "510880": "红利ETF", "512690": "酒ETF", "512760": "芯片ETF",
    "512880": "证券ETF", "516160": "新能源",
}

# ── ClickHouse 连接 ─────────────────────────────────────
CH_HOST = os.getenv("CHDB_HOST", "10.13.66.5")
CH_PORT = int(os.getenv("CHDB_PORT", "20107"))
CH_USER = os.getenv("CHDB_USER", "cufel_arena_etf_reader")
CH_PASSWORD = os.getenv("CHDB_PASSWORD", "cufel_arena_etf_404")
CH_DATABASE = os.getenv("CHDB_DATABASE", "etf")

@st.cache_resource
def get_clickhouse_client():
    from clickhouse_driver import Client
    return Client(host=CH_HOST, port=CH_PORT, user=CH_USER, password=CH_PASSWORD, database=CH_DATABASE)

@st.cache_data(ttl=300)
def fetch_live_prices(codes: list, target_date: str) -> dict:
    """获取指定日期的最新价格"""
    ch = get_clickhouse_client()
    codes_str = ",".join(f"'{c}'" for c in codes)
    sql = f"""
        SELECT code, close, pre_close, pct_chg
        FROM etf.etf_day
        WHERE code IN ({codes_str}) AND date <= '{target_date}'
        ORDER BY date DESC
        LIMIT 1 BY code
    """
    rows = ch.execute(sql)
    return {r[0]: {"close": r[1], "pre_close": r[2], "pct_chg": r[3]} for r in rows}

@st.cache_data(ttl=3600)
def fetch_etf_prices(codes: list, start: str, end: str) -> pd.DataFrame:
    ch = get_clickhouse_client()
    codes_str = ",".join(f"'{c}'" for c in codes)
    sql = f"""
        SELECT date, code, close, adj_factor
        FROM etf.etf_day
        WHERE code IN ({codes_str}) AND date BETWEEN '{start}' AND '{end}'
        ORDER BY date, code
    """
    rows = ch.execute(sql)
    df = pd.DataFrame(rows, columns=["date", "code", "close", "adj_factor"])
    # ClickHouse Date 转为 pd.Timestamp，避免 datetime.date vs str 比较报错
    df["date"] = pd.to_datetime(df["date"])
    df["close_adj"] = df["close"] * df["adj_factor"]
    return df

@st.cache_data(ttl=3600)
def fetch_kline_data(code: str, days: int = 90) -> pd.DataFrame:
    """获取单只股票/ETF的K线数据"""
    ch = get_clickhouse_client()
    sql = f"""
        SELECT date, open, high, low, close, vol, adj_factor
        FROM etf.etf_day
        WHERE code = '{code}'
        ORDER BY date DESC
        LIMIT {days}
    """
    rows = ch.execute(sql)
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "vol", "adj_factor"])
    df = df.sort_values("date").reset_index(drop=True)
    for col in ["open", "high", "low", "close"]:
        df[col] = df[col] * df["adj_factor"]
    df["date"] = pd.to_datetime(df["date"])
    return df

@st.cache_data(ttl=3600)
def fetch_date_range():
    ch = get_clickhouse_client()
    min_d, max_d = ch.execute("SELECT min(date), max(date) FROM etf.etf_day")[0]
    return pd.to_datetime(min_d).date(), pd.to_datetime(max_d).date()

# ── Agent 初始化 ───────────────────────────────────────
@st.cache_resource
def init_agent():
    agent = MacroDrivenETFAgent(use_llm=False)
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
    """从ClickHouse计算波动率、60日/120日位置"""
    try:
        ch = get_clickhouse_client()
        for days, label in [(60, "pos60"), (120, "pos120")]:
            sql = f"""
                SELECT max(high * adj_factor) as hh, min(low * adj_factor) as ll,
                       argMax(close * adj_factor, date) as last_close
                FROM etf.etf_day WHERE code = '{code}'
                  AND date >= today() - {days}
            """
            rows = ch.execute(sql)
            if rows and rows[0][0] is not None:
                hh, ll, last = rows[0]
                pos = (last - ll) / (hh - ll) * 100 if hh and hh != ll else 50
                if label == "pos60":
                    pos60 = pos
                else:
                    pos120 = pos
            else:
                if label == "pos60":
                    pos60 = 50
                else:
                    pos120 = 50

        # 年化波动率（近60日）
        sql_vol = f"""
            SELECT stddevPop(log(close * adj_factor / lagInFrame(close * adj_factor, 1) over (order by date))) * sqrt(252)
            FROM etf.etf_day WHERE code = '{code}' AND date >= today() - 60
        """
        rows_v = ch.execute(sql_vol)
        ann_vol = rows_v[0][0] * 100 if rows_v and rows_v[0][0] else 0

        return {"年化波动率": ann_vol, "60日位置": pos60, "120日位置": pos120}
    except Exception:
        return {"年化波动率": 0, "60日位置": 50, "120日位置": 50}


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

/* ── 持仓表内小按钮：所有按钮缩小 ── */
.st-key-btn_ .stButton button {
    font-size: 0.65rem !important; padding: 1px 5px !important;
    min-height: unset !important; height: auto !important;
    line-height: 1.15 !important; border-radius: 4px !important;
    font-weight: 500 !important;
}
</style>
""", unsafe_allow_html=True)

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
    agent = init_agent()

# ═══════════════════════════════════════════════════════════
# 第二个 Tab: 持仓分析
# ═══════════════════════════════════════════════════════════
tab_macro, tab_portfolio, tab_kline, tab_backtest = st.tabs(["🌍 宏观指标", "📌 持仓分析", "📉 持仓K线图", "📈 回测结果"])

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

            # 指标卡片 + 持仓表格 — 左右布局，整体居中
            _, outer_l, outer_r, _ = st.columns([0.5, 1.6, 3.5, 0.5])

            with outer_l:
                # 指标卡片框
                st.markdown(f"""
                <div style="background:#ffffff; border-radius:16px; padding:16px 18px;
                     box-shadow:0 1px 3px rgba(0,0,0,0.04), 0 4px 12px rgba(0,0,0,0.04);">
                <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px 16px;">
                <div>
                    <span style="font-size:0.65rem; color:#86868b; text-transform:uppercase; letter-spacing:0.04em;">总市值</span><br>
                    <span style="font-size:1.1rem; font-weight:700; color:#1d1d1f;">{total_rt_mv/10000:.1f}万</span>
                </div>
                <div>
                    <span style="font-size:0.65rem; color:#86868b; text-transform:uppercase; letter-spacing:0.04em;">总盈亏</span><br>
                    <span style="font-size:1.1rem; font-weight:700; color:{'#34c759' if total_pnl>=0 else '#ff3b30'};">
                    {total_pnl:+.0f}</span>
                    <span style="font-size:0.7rem; color:#86868b; margin-left:4px;">{total_pnl_pct:+.2f}%</span>
                </div>
                <div>
                    <span style="font-size:0.65rem; color:#86868b; text-transform:uppercase; letter-spacing:0.04em;">总成本</span><br>
                    <span style="font-size:1.1rem; font-weight:700; color:#1d1d1f;">{total_cost/10000:.1f}万</span>
                </div>
                <div>
                    <span style="font-size:0.65rem; color:#86868b; text-transform:uppercase; letter-spacing:0.04em;">持仓数</span><br>
                    <span style="font-size:1.1rem; font-weight:700; color:#1d1d1f;">{len(rt_data)}</span>
                </div>
                </div>
                <div style="margin-top:8px; padding-top:8px; border-top:1px solid #f5f5f7;">
                <span style="font-size:0.6rem; color:#86868b;">更新 {datetime.now().strftime('%H:%M:%S')}</span>
                </div>
                </div>
                """, unsafe_allow_html=True)

            with outer_r:
                # 紧凑表格 — 小按钮
                hcols = st.columns([0.55, 1.1, 0.8, 0.9, 0.9, 0.8, 0.7])
                for i, h in enumerate(["代码", "名称", "现价", "涨跌", "市值(万)", "盈亏", "盈亏%"]):
                    hcols[i].caption(h)

                selected_code = st.session_state.get("detail_code", None)
                for d in rt_data:
                    rcols = st.columns([0.55, 1.1, 0.8, 0.9, 0.9, 0.8, 0.7])
                    # 小按钮
                    is_sel = (selected_code == d["代码"])
                    btn_label = f"▸ {d['代码']}" if is_sel else d["代码"]
                    if rcols[0].button(btn_label, key=f"btn_{d['代码']}",
                                       help=f"查看{d['代码']}详情",
                                       type="primary" if is_sel else "secondary"):
                        st.session_state["detail_code"] = None if is_sel else d["代码"]
                        st.rerun()
                    rcols[1].caption(d["名称"])
                    rcols[2].caption(d["现价"])
                    rcols[3].caption(d["涨跌"])
                    rcols[4].caption(d["市值(万)"])
                    rcols[5].caption(d["盈亏"])
                    rcols[6].caption(d["盈亏%"])

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


# ═══════════════════════════════════════════════════════════
# 第三个 Tab: K线图
# ═══════════════════════════════════════════════════════════
with tab_kline:
    st.header("📉 持仓K线图")
    if actual_df is not None and len(actual_df) > 0:
        kline_codes = actual_df["代码"].tolist()
        kline_days = st.selectbox("周期", [30, 60, 90, 180, 360], index=2,
                                  format_func=lambda d: f"近{d}天", key="kline_period")
        cols_k = st.columns(min(len(kline_codes), 3))
        for i, code in enumerate(kline_codes):
            col_idx = i % 3
            with cols_k[col_idx]:
                try:
                    kdf = fetch_kline_data(code, kline_days)
                    if len(kdf) >= 5:
                        nm = actual_df[actual_df["代码"] == code]
                        name = nm["名称"].values[0] if len(nm) > 0 else code
                        fig = go.Figure()
                        fig.add_trace(go.Candlestick(
                            x=kdf["date"], open=kdf["open"], high=kdf["high"],
                            low=kdf["low"], close=kdf["close"],
                            name=code, increasing_line_color="#ef5350",
                            decreasing_line_color="#26a69a"))
                        fig.add_trace(go.Bar(x=kdf["date"], y=kdf["vol"],
                            name="量", marker_color="rgba(0,0,0,0.15)",
                            yaxis="y2", opacity=0.3))
                        fig.update_layout(
                            title=f"{name}({code})",
                            height=320, margin=dict(l=5, r=5, t=35, b=5),
                            xaxis_rangeslider_visible=False,
                            yaxis=dict(title=""), yaxis2=dict(overlaying="y", side="right", showticklabels=False),
                            showlegend=False, template="plotly_white")
                        st.plotly_chart(fig, use_container_width=True)
                except Exception:
                    pass
    else:
        st.info("请先加载持仓数据")

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
# 第三个 Tab: 回测结果
# ═══════════════════════════════════════════════════════════
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
