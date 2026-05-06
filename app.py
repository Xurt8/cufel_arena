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

# ── 持仓文件路径 ───────────────────────────────────────
_THIS_DIR = Path(__file__).parent
# 如果相对路径找不到，尝试父目录的持仓截图目录
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

    # 方式1: TSV/CSV 文本格式 (券商XLS导出通常是Tab分隔的文本)
    for sep, enc in [('\t', 'gbk'), ('\t', 'gb2312'), ('\t', 'utf-8'),
                     (',', 'gbk'), (',', 'utf-8')]:
        try:
            df = pd.read_csv(temp_path, sep=sep, encoding=enc, header=None)
            if df.shape[1] >= 10:
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


def _extract_holdings_from_df(raw_df: pd.DataFrame) -> pd.DataFrame:
    """从原始DataFrame中提取持仓数据"""
    # 跳过前几行（摘要行），从第一个6位代码行开始
    start_row = None
    for i in range(max(len(raw_df), 20)):
        val = str(raw_df.iloc[i, 0]).strip()
        if len(val) == 6 and val.isdigit():
            start_row = i
            break

    if start_row is None:
        return None

    df = raw_df.iloc[start_row:].copy()
    df.columns = ['代码', '名称', '数量', '可用', '持仓', '成本价', '当前价',
               '市值', '盈亏', '盈亏比例', '股东账号', '持仓账号', '市场', '备注'][:df.shape[1]]

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
    return agent

# ── 回测引擎 ───────────────────────────────────────────
def run_backtest(agent, start_date: str, end_date: str, theta: float = 1.0) -> pd.DataFrame:
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

    codes = list(weights_df.columns)
    prices = fetch_etf_prices(codes, start_date, end_date)
    pivot = prices.pivot_table(index="date", columns="code", values="close_adj", aggfunc="last").ffill()
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

date_str = today.strftime("%Y-%m-%d")

theta = st.sidebar.slider("风险偏好 θ", 0.0, 2.0, 1.0, 0.1,
    help="<1=保守（降低股票）  >1=激进（增持股票）")

st.sidebar.divider()
st.sidebar.header("📋 回测设置")
backtest_start = st.sidebar.date_input("回测起点", value=datetime(2022, 1, 1),
    min_value=min_date, max_value=max_date)
backtest_end = st.sidebar.date_input("回测终点", value=max_date,
    min_value=min_date, max_value=max_date)
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
# 第一个 Tab: 持仓分析
# ═══════════════════════════════════════════════════════════
tab1, tab2, tab3 = st.tabs(["📌 持仓分析", "🌍 宏观指标", "📈 回测结果"])

with tab1:
    # 获取策略持仓
    strategy_holdings = {}
    try:
        sh = agent.get_current_holdings(date_str, theta=theta)
        strategy_holdings = sh.get(date_str, {})
    except Exception as e:
        st.error(f"策略计算失败: {e}")

    # 获取实际持仓
    actual_df = st.session_state.get("holdings_df")
if actual_df is None or (isinstance(actual_df, pd.DataFrame) and actual_df.empty):
    actual_df = load_actual_holdings()
if actual_df is not None and not actual_df.empty:
    st.session_state["holdings_df"] = actual_df

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
# 第二个 Tab: 宏观指标
# ═══════════════════════════════════════════════════════════
with tab2:
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
with tab3:
    st.header("📈 回测结果")

    if run_backtest_btn:
        with st.spinner(f"回测中 {backtest_start} → {backtest_end}..."):
            try:
                bt_result = run_backtest(agent,
                    backtest_start.strftime("%Y-%m-%d"),
                    backtest_end.strftime("%Y-%m-%d"), theta=theta)

                if not bt_result.empty:
                    nav = bt_result["nav"]
                    total_ret = (nav.iloc[-1] / nav.iloc[0] - 1) * 100
                    years = (nav.index[-1] - nav.index[0]).days / 365.25
                    ann_ret = ((nav.iloc[-1] / nav.iloc[0]) ** (1/years) - 1) * 100 if years > 0 else 0
                    max_dd = ((nav - nav.cummax()) / nav.cummax()).min() * 100
                    ret_series = nav.pct_change().dropna()
                    sharpe = (ret_series.mean() / ret_series.std() * math.sqrt(252)) if ret_series.std() > 0 else 0

                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("累计收益", f"{total_ret:.2f}%")
                    m2.metric("年化收益", f"{ann_ret:.2f}%")
                    m3.metric("最大回撤", f"{max_dd:.2f}%")
                    m4.metric("夏普比率", f"{sharpe:.2f}")

                    fig_nav = px.line(x=nav.index, y=nav.values, title="净值曲线")
                    fig_nav.update_layout(height=400, margin=dict(l=10, r=10, t=30, b=10))
                    st.plotly_chart(fig_nav, use_container_width=True)

                    dd = (nav - nav.cummax()) / nav.cummax() * 100
                    fig_dd = px.area(x=dd.index, y=dd.values, title="回撤曲线 (%)")
                    fig_dd.update_layout(height=250, margin=dict(l=10, r=10, t=30, b=10))
                    st.plotly_chart(fig_dd, use_container_width=True)
                else:
                    st.warning("回测结果为空")
            except Exception as e:
                st.error(f"回测失败: {e}")
                import traceback; st.code(traceback.format_exc())
    else:
        st.info("👈 在侧边栏设置回测参数后，点击「运行回测」")

st.divider()
st.caption(f"数据来源: ClickHouse {CH_HOST}:{CH_PORT} | etf.etf_day ({min_date} ~ {max_date})")
