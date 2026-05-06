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

@st.cache_data(ttl=3600)
def fetch_etf_prices(codes: list, start: str, end: str) -> pd.DataFrame:
    """从 ClickHouse 获取 ETF 日线数据"""
    ch = get_clickhouse_client()
    codes_str = ",".join(f"'{c}'" for c in codes)
    sql = f"""
        SELECT date, code, close, adj_factor
        FROM etf.etf_day
        WHERE code IN ({codes_str})
          AND date BETWEEN '{start}' AND '{end}'
        ORDER BY date, code
    """
    rows = ch.execute(sql)
    df = pd.DataFrame(rows, columns=["date", "code", "close", "adj_factor"])
    df["close_adj"] = df["close"] * df["adj_factor"]
    return df

@st.cache_data(ttl=3600)
def fetch_date_range():
    ch = get_clickhouse_client()
    min_d, max_d = ch.execute("SELECT min(date), max(date) FROM etf.etf_day")[0]
    return min_d, max_d

# ── Agent 初始化 ───────────────────────────────────────
@st.cache_resource
def init_agent():
    agent = MacroDrivenETFAgent(use_llm=False)
    agent.CH_CONFIG = {"host": CH_HOST, "port": CH_PORT, "user": CH_USER,
                       "password": CH_PASSWORD, "database": CH_DATABASE}
    return agent

# ── 回测引擎（简化版）───────────────────────────────────
def run_backtest(agent, start_date: str, end_date: str, theta: float = 1.0) -> pd.DataFrame:
    """月度调仓回测"""
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
    if weights_df.empty:
        return pd.DataFrame()

    # 获取价格
    codes = list(weights_df.columns)
    prices = fetch_etf_prices(codes, start_date, end_date)
    pivot = prices.pivot_table(index="date", columns="code", values="close_adj", aggfunc="last").ffill()

    # 计算净值
    aligned = weights_df.reindex(pivot.index, method="ffill")
    returns = pivot.pct_change().fillna(0)
    daily_ret = (aligned * returns).sum(axis=1)
    nav = (1 + daily_ret).cumprod()

    return pd.DataFrame({"date": nav.index, "nav": nav.values}).set_index("date")


# ═══════════════════════════════════════════════════════════
# Streamlit UI
# ═══════════════════════════════════════════════════════════
st.set_page_config(page_title="cufel_arena · 宏观驱动ETF", page_icon="📊", layout="wide")
st.title("📊 cufel_arena — 宏观驱动 ETF 策略")

# ── Sidebar ──────────────────────────────────────────────
st.sidebar.header("⚙️ 参数设置")
min_date, max_date = fetch_date_range()

today = st.sidebar.date_input("分析日期",
    value=max_date if max_date else datetime(2026, 4, 30),
    min_value=min_date, max_value=max_date)

theta = st.sidebar.slider("风险偏好 θ", 0.0, 2.0, 1.0, 0.1,
    help="<1=保守（降低股票）  >1=激进（增持股票）")

st.sidebar.divider()
st.sidebar.header("📋 回测设置")
backtest_start = st.sidebar.date_input("回测起点", value=datetime(2022, 1, 1),
    min_value=min_date, max_value=max_date)
backtest_end = st.sidebar.date_input("回测终点", value=max_date,
    min_value=min_date, max_value=max_date)

run_backtest_btn = st.sidebar.button("🚀 运行回测", type="primary", use_container_width=True)

# ── 初始化 Agent ─────────────────────────────────────────
with st.spinner("初始化 Agent..."):
    agent = init_agent()

# ── 主面板: 当前持仓 ─────────────────────────────────────
st.header(f"📌 {today} 持仓分析")

col1, col2 = st.columns([1, 1])
with col1:
    date_str = today.strftime("%Y-%m-%d")
    try:
        holdings = agent.get_current_holdings(date_str, theta=theta)
        if holdings and date_str in holdings:
            w = holdings[date_str]
            df_hold = pd.DataFrame({"权重": w}).sort_values("权重", ascending=False)
            df_hold["比例"] = df_hold["权重"].apply(lambda x: f"{x*100:.1f}%")

            # 饼图
            fig = px.pie(values=list(w.values()), names=list(w.keys()),
                         title="持仓权重分布", hole=0.4)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("未获取到持仓数据")
            df_hold = pd.DataFrame()
    except Exception as e:
        st.error(f"获取持仓失败: {e}")
        df_hold = pd.DataFrame()

with col2:
    if not df_hold.empty:
        st.dataframe(df_hold, use_container_width=True)

        # 持仓类型分析
        etf_types = {
            "510300": ("沪深300ETF", "股票"),
            "510500": ("中证500ETF", "股票"),
            "511010": ("国债ETF", "债券"),
            "511220": ("城投债ETF", "债券"),
            "518880": ("黄金ETF", "商品"),
        }
        types = {}
        for code, weight in w.items():
            info = etf_types.get(code, (code, "其他"))
            t = info[1]
            types[t] = types.get(t, 0) + weight

        st.subheader("资产类别分布")
        for t, tw in types.items():
            st.metric(t, f"{tw*100:.1f}%")
        st.caption(f"总权重: {sum(w.values())*100:.1f}%")

# ── 宏观分析 ─────────────────────────────────────────────
st.header("🌍 宏观指标分析")
try:
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    macro_data = agent.data_agent.get_macro_for_decision(date_obj)
    analysis = agent.macro_agent.analyze(macro_data)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("PMI", f"{macro_data.pmi:.1f}", help="制造业采购经理指数")
    c2.metric("CPI 同比", f"{macro_data.cpi_yoy:.1f}%")
    c3.metric("M2 同比", f"{macro_data.m2_yoy:.1f}%")
    c4.metric("SHIBOR 1M", f"{macro_data.shibor_1m:.2f}%")

    st.info(f"**经济周期判断**: {analysis.get('cycle_phase', 'N/A')}  |  "
            f"**置信度**: {analysis.get('confidence', 0):.2f}  |  "
            f"**分析**: {analysis.get('analysis', '')}")

    # 宏观指标走势图
    if macro_data.pmi_history:
        fig_macro = go.Figure()
        fig_macro.add_trace(go.Scatter(
            y=macro_data.pmi_history, mode="lines+markers", name="PMI 近6期",
            line=dict(color="#2196F3")))
        fig_macro.update_layout(title="PMI 近期走势", height=250, margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig_macro, use_container_width=True)

except Exception as e:
    st.error(f"宏观分析失败: {e}")

# ── 回测结果 ─────────────────────────────────────────────
if run_backtest_btn:
    st.header("📈 回测结果")
    with st.spinner(f"回测中 {backtest_start} → {backtest_end}..."):
        try:
            bt_result = run_backtest(agent,
                backtest_start.strftime("%Y-%m-%d"),
                backtest_end.strftime("%Y-%m-%d"),
                theta=theta)

            if not bt_result.empty:
                # 收益指标
                nav = bt_result["nav"]
                total_ret = (nav.iloc[-1] / nav.iloc[0] - 1) * 100
                years = (nav.index[-1] - nav.index[0]).days / 365.25
                ann_ret = ((nav.iloc[-1] / nav.iloc[0]) ** (1/years) - 1) * 100 if years > 0 else 0
                rolling_max = nav.cummax()
                drawdown = (nav - rolling_max) / rolling_max
                max_dd = drawdown.min() * 100
                ret_series = nav.pct_change().dropna()
                sharpe = (ret_series.mean() / ret_series.std() * math.sqrt(252)) if ret_series.std() > 0 else 0

                m1, m2, m3, m4 = st.columns(4)
                m1.metric("累计收益", f"{total_ret:.2f}%")
                m2.metric("年化收益", f"{ann_ret:.2f}%")
                m3.metric("最大回撤", f"{max_dd:.2f}%")
                m4.metric("夏普比率", f"{sharpe:.2f}")

                # 净值曲线
                fig_nav = px.line(x=nav.index, y=nav.values, title="净值曲线")
                fig_nav.update_layout(height=350, margin=dict(l=10, r=10, t=30, b=10))
                st.plotly_chart(fig_nav, use_container_width=True)

                # 回撤曲线
                fig_dd = px.area(x=drawdown.index, y=drawdown.values * 100, title="回撤曲线 (%)")
                fig_dd.update_layout(height=250, margin=dict(l=10, r=10, t=30, b=10))
                st.plotly_chart(fig_dd, use_container_width=True)
            else:
                st.warning("回测结果为空")
        except Exception as e:
            st.error(f"回测失败: {e}")
            import traceback
            st.code(traceback.format_exc())

st.divider()
st.caption(f"数据来源: ClickHouse {CH_HOST}:{CH_PORT} | etf.etf_day ({min_date} ~ {max_date})")
