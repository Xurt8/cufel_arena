"""
LangChain Agent - 全功能投资助手
功能全面的ETF/股票分析系统
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import os
from dotenv import load_dotenv

# 加载.env文件
load_dotenv()

from langchain.tools import tool
from langchain.chat_models import init_chat_model
from langgraph.checkpoint.memory import InMemorySaver
from langchain.agents import create_agent
from quantchdb import ClickHouseDatabase
import pandas as pd
import numpy as np
from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path


# ========== 从环境变量获取配置 ==========

# LLM配置
LLM_API_KEY = os.getenv('LLM_API_KEY')
LLM_API_BASE = os.getenv('LLM_API_BASE')
MODEL_NAME = os.getenv('MODEL_NAME', 'claude-sonnet-4-5')

# ClickHouse配置
CHDB_HOST = os.getenv('CHDB_HOST')
CHDB_PORT = int(os.getenv('CHDB_PORT', 20108))
CHDB_USER = os.getenv('CHDB_USER')
CHDB_PASSWORD = os.getenv('CHDB_PASSWORD')
CHDB_DATABASE = os.getenv('CHDB_DATABASE', 'etf')

# 本地数据路径（来自MacroDrivenETF的PracticeData）
DATA_PATH = os.getenv('DATA_PATH', '../../../PracticeData/')


# ========== 宏观数据加载（来自MacroDrivenETF）==========
"""宏观数据结构 - 用于宏观择时分析"""

class MacroDataLoader:
    """加载宏观数据的工具类"""

    def __init__(self, data_path: str = None):
        if data_path is None:
            # 使用绝对路径
            # 文件位置: cufel_arena/ETFAgents/MyETFassistant/langchain_full_investment_agent.py
            # 数据位置: 3月22日课程资料/PracticeData
            # 需要向上3级到"3月22日课程资料"
            base_dir = Path(__file__).parent  # MyETFassistant/
            data_path = base_dir / "../../../PracticeData"  # 向上3级
        self.data_path = str(Path(data_path).resolve())
        print(f"[MacroDataLoader] 数据路径: {self.data_path}")
        self._load_all()

    def _load_all(self):
        """加载所有宏观数据"""
        self._load_pmi()
        self._load_cpi()
        self._load_ppi()
        self._load_m2()
        self._load_sf()
        self._load_gdp()
        self._load_shibor()

    def _load_pmi(self):
        """加载PMI数据"""
        try:
            df = pd.read_csv(f"{self.data_path}/采购经理指数cn_pmi.csv", encoding='utf-8')
            df.columns = ['month', 'pmi']
            df['date'] = pd.to_datetime(df['month'].astype(str), format='%Y%m') + pd.offsets.MonthEnd(0)
            self.pmi_data = df.sort_values('date')
        except:
            self.pmi_data = pd.DataFrame()

    def _load_cpi(self):
        """加载CPI数据"""
        try:
            df = pd.read_csv(f"{self.data_path}/居民消费价格指数cn_cpi.csv", encoding='utf-8')
            df.columns = ['date_str', 'cpi_value', 'cpi_yoy']
            df['date'] = pd.to_datetime(df['date_str'].astype(str), format='%Y%m') + pd.offsets.MonthEnd(0)
            df = df[df['date'] >= '2020-01-01']
            self.cpi_data = df[['date', 'cpi_yoy']].sort_values('date')
        except:
            self.cpi_data = pd.DataFrame()

    def _load_ppi(self):
        """加载PPI数据"""
        try:
            df = pd.read_csv(f"{self.data_path}/工业生产者出厂价格指数cn_ppi.csv", encoding='utf-8')
            ppi_col = [c for c in df.columns if '同比' in c and '累计' not in c][0]
            df = df[['日期', ppi_col]].copy()
            df.columns = ['date_str', 'ppi_yoy']
            df['date'] = pd.to_datetime(df['date_str'].astype(str), format='%Y%m') + pd.offsets.MonthEnd(0)
            self.ppi_data = df[['date', 'ppi_yoy']].sort_values('date')
        except:
            self.ppi_data = pd.DataFrame()

    def _load_m2(self):
        """加载M2数据"""
        try:
            df = pd.read_csv(f"{self.data_path}/货币供应量cn_m.csv", encoding='utf-8')
            m2_col = [c for c in df.columns if '同比' in c][0]
            df = df[['month', m2_col]]
            df.columns = ['month', 'm2_yoy']
            df['date'] = pd.to_datetime(df['month'].astype(str), format='%Y%m') + pd.offsets.MonthEnd(0)
            self.m2_data = df[['date', 'm2_yoy']].sort_values('date')
        except:
            self.m2_data = pd.DataFrame()

    def _load_sf(self):
        """加载社融数据"""
        try:
            df = pd.read_csv(f"{self.data_path}/社融数据sf_month.csv", encoding='utf-8')
            sf_col = [c for c in df.columns if '当月值' in c][0]
            df = df[['month', sf_col]]
            df.columns = ['month', 'sf_month']
            df['date'] = pd.to_datetime(df['month'].astype(str), format='%Y%m') + pd.offsets.MonthEnd(0)
            self.sf_data = df[['date', 'sf_month']].sort_values('date')
        except:
            self.sf_data = pd.DataFrame()

    def _load_gdp(self):
        """加载GDP数据"""
        try:
            df = pd.read_csv(f"{self.data_path}/国内生产总值cn_gdp.csv", encoding='utf-8')
            gdp_col = [c for c in df.columns if '同比' in c][0]
            df = df[['quarter', gdp_col]]
            df.columns = ['quarter_str', 'gdp_yoy']

            def parse_quarter(q_str):
                year = int(q_str[:4])
                quarter = int(q_str[-1])
                month = quarter * 3
                return pd.Timestamp(year, month, 1) + pd.offsets.MonthEnd(0)

            df['date'] = df['quarter_str'].apply(parse_quarter)
            self.gdp_data = df[['date', 'gdp_yoy', 'quarter_str']].sort_values('date')
        except:
            self.gdp_data = pd.DataFrame()

    def _load_shibor(self):
        """加载SHIBOR数据"""
        try:
            df = pd.read_csv(f"{self.data_path}/shibor利率.csv", encoding='utf-8')
            date_col = [c for c in df.columns if '日期' in c][0] if '日期' in str(df.columns) else 'date'
            df = df.rename(columns={date_col: 'date_str'})
            df['date'] = pd.to_datetime(df['date_str'].astype(str), format='%Y%m%d')
            m1_col = [c for c in df.columns if '1m' in c.lower()][0]
            m3_col = [c for c in df.columns if '3m' in c.lower()][0]
            df = df[['date', m1_col, m3_col]]
            df.columns = ['date', 'shibor_1m', 'shibor_3m']
            self.shibor_data = df.sort_values('date')
        except:
            self.shibor_data = pd.DataFrame()

    def get_latest_macro(self) -> dict:
        """获取最新宏观数据"""
        result = {}

        if len(self.pmi_data) > 0:
            result['pmi'] = self.pmi_data.iloc[-1]['pmi']
            result['pmi_date'] = self.pmi_data.iloc[-1]['date']

        if len(self.cpi_data) > 0:
            result['cpi_yoy'] = self.cpi_data.iloc[-1]['cpi_yoy']
            result['cpi_date'] = self.cpi_data.iloc[-1]['date']

        if len(self.ppi_data) > 0:
            result['ppi_yoy'] = self.ppi_data.iloc[-1]['ppi_yoy']
            result['ppi_date'] = self.ppi_data.iloc[-1]['date']

        if len(self.m2_data) > 0:
            result['m2_yoy'] = self.m2_data.iloc[-1]['m2_yoy']
            result['m2_date'] = self.m2_data.iloc[-1]['date']

        if len(self.sf_data) > 0:
            result['sf_month'] = self.sf_data.iloc[-1]['sf_month']
            result['sf_date'] = self.sf_data.iloc[-1]['date']

        if len(self.gdp_data) > 0:
            result['gdp_yoy'] = self.gdp_data.iloc[-1]['gdp_yoy']
            result['gdp_quarter'] = self.gdp_data.iloc[-1]['quarter_str']

        if len(self.shibor_data) > 0:
            result['shibor_1m'] = self.shibor_data.iloc[-1]['shibor_1m']
            result['shibor_3m'] = self.shibor_data.iloc[-1]['shibor_3m']
            result['shibor_date'] = self.shibor_data.iloc[-1]['date']

        return result


# 初始化宏观数据加载器
macro_loader = MacroDataLoader()


# ========== 投资组合配置 ==========

# 用户持仓（最新数据 2026-04-）
USER_HOLDINGS = {
    '159915': {'name': '创业板ETF', 'shares': 3200, 'cost': 3.423, 'current': 3.621},
    '159934': {'name': '黄金ETF', 'shares': 1300, 'cost': 10.583, 'current': 10.549},
    '159994': {'name': '5GETF', 'shares': 5400, 'cost': 1.067, 'current': 1.130},
    '510880': {'name': '红利ETF', 'shares': 2900, 'cost': 3.223, 'current': 3.244},
    '512690': {'name': '酒ETF', 'shares': 24400, 'cost': 0.494, 'current': 0.494},
    '512880': {'name': '证券ETF', 'shares': 20200, 'cost': 1.071, 'current': 1.081},
    '516160': {'name': '新能源ETF', 'shares': 1800, 'cost': 3.078, 'current': 3.190},
    '002203': {'name': '海亮股份', 'shares': 300, 'cost': 0.000, 'current': 15.810},
    '601857': {'name': '中国石油', 'shares': 1000, 'cost': 11.835, 'current': 11.660},
}


# ========== 工具函数 ==========

def get_db_connection():
    """从环境变量获取数据库配置"""
    return {
        'host': CHDB_HOST,
        'port': CHDB_PORT,
        'user': CHDB_USER,
        'password': CHDB_PASSWORD,
        'database': CHDB_DATABASE
    }


def query_etf_data(code: str, days: int = 60):
    """查询ETF数据"""
    with ClickHouseDatabase(config=get_db_connection(), terminal_log=False, file_log=False) as db:
        df = db.fetch(f"""
            SELECT date, open, high, low, close, vol
            FROM etf_day
            WHERE code = '{code}'
            ORDER BY date DESC LIMIT {days}
        """)
    return df.sort_values('date', ascending=True) if len(df) > 0 else pd.DataFrame()


def calculate_ma(df: pd.DataFrame):
    """计算均线"""
    if len(df) < 5:
        return {}
    return {
        'MA5': df['close'].tail(5).mean(),
        'MA10': df['close'].tail(10).mean(),
        'MA20': df['close'].tail(20).mean(),
        'MA60': df['close'].tail(60).mean() if len(df) >= 60 else None
    }


def calculate_kdj(df: pd.DataFrame, n: int = 9, m1: int = 3, m2: int = 3):
    """计算KDJ指标"""
    if len(df) < n:
        return None

    low_list = df['low'].rolling(window=n).min()
    high_list = df['high'].rolling(window=n).max()

    rsv = (df['close'] - low_list) / (high_list - low_list) * 100
    rsv = rsv.fillna(50)

    k = rsv.ewm(alpha=1/m1, adjust=False).mean()
    d = k.ewm(alpha=1/m2, adjust=False).mean()
    j = 3 * k - 2 * d

    return {
        'K': k.iloc[-1],
        'D': d.iloc[-1],
        'J': j.iloc[-1]
    }


def calculate_rsi(df: pd.DataFrame, period: int = 14):
    """计算RSI指标"""
    if len(df) < period + 1:
        return None

    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    return rsi.iloc[-1]


def calculate_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9):
    """计算MACD指标"""
    if len(df) < slow:
        return None

    ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
    ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    macd = (dif - dea) * 2

    return {
        'DIF': dif.iloc[-1],
        'DEA': dea.iloc[-1],
        'MACD': macd.iloc[-1],
        'signal': '金叉' if dif.iloc[-1] > dea.iloc[-1] else '死叉'
    }


def calculate_boll(df: pd.DataFrame, period: int = 20):
    """计算布林带"""
    if len(df) < period:
        return None

    ma = df['close'].rolling(window=period).mean()
    std = df['close'].rolling(window=period).std()
    upper = ma + 2 * std
    lower = ma - 2 * std

    return {
        'upper': upper.iloc[-1],
        'middle': ma.iloc[-1],
        'lower': lower.iloc[-1],
        'position': (df['close'].iloc[-1] - lower.iloc[-1]) / (upper.iloc[-1] - lower.iloc[-1]) * 100
    }


# ========== LangChain Tools ==========

@tool
def get_etf_price(code: str) -> str:
    """获取ETF最新价格和基本信息"""
    df = query_etf_data(code, 1)
    if len(df) == 0:
        return f"未找到ETF {code}的数据"

    latest = df.iloc[-1]
    return f"📊 ETF {code} 最新数据 (日期: {latest['date']})\n" \
           f"  收盘价: {latest['close']:.3f}元\n" \
           f"  开盘: {latest['open']:.3f}  最高: {latest['high']:.3f}  最低: {latest['low']:.3f}\n" \
           f"  成交量: {latest['vol']/10000:.2f}万手"


@tool
def get_etf_60day_change(code: str) -> str:
    """获取ETF 60日涨跌幅"""
    df = query_etf_data(code, 60)
    if len(df) < 2:
        return f"数据不足"

    latest = df.iloc[-1]
    oldest = df.iloc[0]
    change = (latest['close'] - oldest['close']) / oldest['close'] * 100
    return f"📈 ETF {code} 60日涨跌幅: {change:+.2f}%\n  (从{oldest['close']:.3f}元到{latest['close']:.3f}元)"


@tool
def get_etf_ma(code: str) -> str:
    """获取ETF均线数据和技术分析"""
    df = query_etf_data(code, 60)
    if len(df) < 20:
        return "数据不足"

    ma = calculate_ma(df)

    # 判断趋势
    if ma['MA5'] > ma['MA10'] > ma['MA20']:
        trend = "📈 上升趋势"
    elif ma['MA5'] < ma['MA10'] < ma['MA20']:
        trend = "📉 下降趋势"
    else:
        trend = "➡️ 震荡整理"

    return f"📊 ETF {code} 均线分析:\n" \
           f"  MA5: {ma['MA5']:.3f}  MA10: {ma['MA10']:.3f}\n" \
           f"  MA20: {ma['MA20']:.3f}  MA60: {ma['MA60']:.3f if ma['MA60'] is not None and not pd.isna(ma['MA60']) else 'N/A'}\n" \
           f"  趋势: {trend}"


@tool
def get_full_technical_analysis(code: str) -> str:
    """获取ETF完整技术分析（均线+KDJ+RSI+MACD+布林带）"""
    df = query_etf_data(code, 60)
    if len(df) < 30:
        return "数据不足，无法进行完整分析"

    latest = df.iloc[-1]
    ma = calculate_ma(df)
    kdj = calculate_kdj(df)
    rsi = calculate_rsi(df)
    macd = calculate_macd(df)
    boll = calculate_boll(df)

    # 综合判断
    signals = []

    # 均线信号
    if ma['MA5'] > ma['MA10'] > ma['MA20']:
        signals.append("均线多头排列")
    elif ma['MA5'] < ma['MA10'] < ma['MA20']:
        signals.append("均线空头排列")

    # KDJ信号
    if kdj:
        if kdj['K'] < 20 and kdj['D'] < 20:
            signals.append("KDJ超卖")
        elif kdj['K'] > 80 and kdj['D'] > 80:
            signals.append("KDJ超买")
        if kdj['K'] > kdj['D'] and kdj['J'] > kdj['K']:
            signals.append("KDJ金叉")
        elif kdj['K'] < kdj['D'] and kdj['J'] < kdj['K']:
            signals.append("KDJ死叉")

    # RSI信号
    if rsi:
        if rsi < 30:
            signals.append("RSI超卖(买)")
        elif rsi > 70:
            signals.append("RSI超卖(卖)")

    # MACD信号
    if macd:
        signals.append(f"MACD{ macd['signal']}")

    # 布林带信号
    if boll and boll['position'] < 20:
        signals.append("布林下轨支撑")
    elif boll and boll['position'] > 80:
        signals.append("布林上轨压力")

    # 综合评分
    buy_signals = sum(1 for s in signals if '超卖' in s or '金叉' in s or '多头' in s)
    sell_signals = sum(1 for s in signals if '超买' in s or '死叉' in s or '空头' in s)

    if buy_signals > sell_signals + 1:
        recommendation = "🟢 强烈买入信号"
    elif buy_signals > sell_signals:
        recommendation = "🟡 谨慎买入"
    elif sell_signals > buy_signals + 1:
        recommendation = "🔴 建议卖出"
    elif sell_signals > buy_signals:
        recommendation = "🟠 谨慎持有"
    else:
        recommendation = "⚪ 中性观望"

    # 安全格式化MA60
    if ma['MA60'] is None or pd.isna(ma['MA60']):
        ma60_str = "N/A"
    else:
        ma60_str = f"{ma['MA60']:.3f}"

    result = f"🔍 ETF {code} 完整技术分析 ({(latest['date'])})\n\n" \
             f"【价格信息】\n  当前价: {latest['close']:.3f}元\n\n" \
             f"【均线系统】\n  MA5: {ma['MA5']:.3f}  MA10: {ma['MA10']:.3f}\n  MA20: {ma['MA20']:.3f}  MA60: {ma60_str}\n\n"

    result += f"【KDJ指标】\n  K: {kdj['K']:.2f}  D: {kdj['D']:.2f}  J: {kdj['J']:.2f}\n\n"

    if rsi:
        result += f"【RSI指标】\n  RSI(14): {rsi:.2f}\n\n"

    if macd:
        result += f"【MACD指标】\n  DIF: {macd['DIF']:.4f}  DEA: {macd['DEA']:.4f}\n  信号: {macd['signal']}\n\n"

    if boll:
        result += f"【布林带】\n  上轨: {boll['upper']:.3f}  中轨: {boll['middle']:.3f}  下轨: {boll['lower']:.3f}\n  价格位置: {boll['position']:.1f}%\n\n"

    result += f"【技术信号】\n  {' / '.join(signals) if signals else '暂无明确信号'}\n\n" \
              f"【综合判断】\n  {recommendation}\n" \
              f"  买入信号: {buy_signals}个  卖出信号: {sell_signals}个"

    return result


@tool
def get_portfolio_analysis() -> str:
    """分析用户整个持仓组合的状态"""
    total_value = 0
    total_cost = 0
    results = []

    for code, info in USER_HOLDINGS.items():
        market_value = info['shares'] * info['current']
        total_cost_val = info['shares'] * info['cost'] if info['cost'] > 0 else 0
        profit = market_value - total_cost_val
        # 避免除以0
        profit_pct = (info['current'] - info['cost']) / info['cost'] * 100 if info['cost'] > 0 else 0

        results.append({
            'code': code,
            'name': info['name'],
            'shares': info['shares'],
            'cost': info['cost'],
            'current': info['current'],
            'market_value': market_value,
            'profit': profit,
            'profit_pct': profit_pct
        })

        total_value += market_value
        total_cost += total_cost_val

    total_profit = total_value - total_cost
    total_profit_pct = total_profit / total_cost * 100 if total_cost > 0 else 0

    # 按盈亏排序
    results.sort(key=lambda x: x['profit_pct'], reverse=True)

    # 构建回复
    reply = f"💼 持仓组合分析 (总资产: {total_value:,.0f}元)\n\n"

    # 盈利排行
    reply += "【盈利排行】\n"
    profit_count = 0
    for r in results:
        if r['profit_pct'] > 0:
            profit_count += 1
            reply += f"  ✅ {r['name']}({r['code']}): {r['profit_pct']:+.2f}% ({r['profit']:+,.0f}元)\n"
    # 成本为0的老股单独显示
    for r in results:
        if r['cost'] == 0:
            reply += f"  ✅ {r['name']}({r['code']}): 老股(现值{r['market_value']:,.0f}元)\n"

    reply += "\n【亏损排行】\n"
    loss_count = 0
    for r in results:
        if r['profit_pct'] < 0:
            loss_count += 1
            reply += f"  ❌ {r['name']}({r['code']}): {r['profit_pct']:+.2f}% ({r['profit']:+,.0f}元)\n"

    if loss_count == 0:
        reply += "  🎉 全部盈利！\n"

    reply += f"\n【汇总】\n" \
             f"  总市值: {total_value:,.0f}元\n" \
             f"  总成本: {total_cost:,.0f}元\n" \
             f"  总盈亏: {total_profit:+,.0f}元 ({total_profit_pct:+.2f}%)\n"

    return reply


@tool
def get_single_holding_analysis(code: str) -> str:
    """分析用户持有的单个持仓"""
    if code not in USER_HOLDINGS:
        return f"您未持有 {code}"

    info = USER_HOLDINGS[code]
    market_value = info['shares'] * info['current']
    total_cost = info['shares'] * info['cost']
    profit = market_value - total_cost
    profit_pct = (info['current'] - info['cost']) / info['cost'] * 100

    # 获取技术分析
    df = query_etf_data(code, 60)
    analysis = ""
    if len(df) >= 30:
        ma = calculate_ma(df)
        latest = df.iloc[-1]
        change_60 = (latest['close'] - df.iloc[0]['close']) / df.iloc[0]['close'] * 100

        # 位置分析
        high_60 = df['high'].max()
        low_60 = df['low'].min()
        position = (info['current'] - low_60) / (high_60 - low_60) * 100

        # 趋势判断
        if ma['MA5'] > ma['MA10'] > ma['MA20']:
            trend = "📈 上升趋势"
        elif ma['MA5'] < ma['MA10'] < ma['MA20']:
            trend = "📉 下降趋势"
        else:
            trend = "➡️ 震荡整理"

        analysis = f"\n【技术分析】\n" \
                   f"  60日涨跌: {change_60:+.2f}%\n" \
                   f"  当前位置: {position:.0f}%\n" \
                   f"  趋势: {trend}\n" \
                   f"  当前价: {latest['close']:.3f}元\n" \
                   f"  60日区间: {low_60:.3f}~{high_60:.3f}元"

    # 操作建议
    if profit_pct > 30:
        action = "建议部分止盈，落袋为安"
    elif profit_pct > 10 and position > 70:
        action = "价格上涨较多，可考虑分批卖出"
    elif profit_pct < -10:
        action = "浮亏较大，可考虑加仓摊低成本"
    elif position < 20:
        action = "价格接近60日低点，可考虑加仓"
    else:
        action = "继续持有观望"

    return f"📊 {info['name']}({code}) 持仓分析\n\n" \
           f"【持仓信息】\n" \
           f"  持有数量: {info['shares']}股\n" \
           f"  成本价: {info['cost']:.3f}元\n" \
           f"  当前价: {info['current']:.3f}元\n" \
           f"  市值: {market_value:,.0f}元\n" \
           f"  盈亏: {profit:+,.0f}元 ({profit_pct:+.2f}%){analysis}\n\n" \
           f"【操作建议】\n  {action}"


@tool
def get_risk_assessment(code: str) -> str:
    """风险评估"""
    df = query_etf_data(code, 60)
    if len(df) < 20:
        return "数据不足"

    # 计算各种风险指标
    volatility = df['close'].pct_change().std() * 100  # 波动率
    max_drawdown = ((df['close'] - df['close'].cummax()) / df['close'].cummax()).min() * 100  # 最大回撤

    avg_vol = df['vol'].mean()  # 平均成交量
    vol_change = df['vol'].iloc[-1] / avg_vol if avg_vol > 0 else 1  # 成交量变化

    # 风险等级
    if volatility > 5:
        risk_level = "🔴 高风险"
    elif volatility > 2:
        risk_level = "🟡 中风险"
    else:
        risk_level = "🟢 低风险"

    return f"⚠️ ETF {code} 风险评估\n\n" \
           f"  波动率: {volatility:.2f}%\n" \
           f"  最大回撤: {max_drawdown:.2f}%\n" \
           f"  成交量变化: {vol_change:.2f}倍\n" \
           f"  风险等级: {risk_level}\n\n" \
           f"【说明】\n" \
           f"  - 波动率越高，价格波动越大\n" \
           f"  - 最大回撤越大，潜在亏损越高\n" \
           f"  - 成交量异常可能预示大幅波动"


@tool
def get_comparison_analysis(codes: str) -> str:
    """对比分析多个ETF"""
    code_list = [c.strip() for c in codes.split(',')]
    results = []

    for code in code_list:
        df = query_etf_data(code, 60)
        if len(df) < 2:
            continue

        latest = df.iloc[-1]
        oldest = df.iloc[0]
        change = (latest['close'] - oldest['close']) / oldest['close'] * 100

        volatility = df['close'].pct_change().std() * 100

        results.append({
            'code': code,
            'change': change,
            'volatility': volatility,
            'current': latest['close']
        })

    if not results:
        return "数据不足"

    # 排序
    results.sort(key=lambda x: x['change'], reverse=True)

    reply = "📊 多ETF对比分析\n\n"
    for i, r in enumerate(results):
        emoji = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "  "
        reply += f"{emoji} {r['code']}: {r['change']:+.2f}% (波动率: {r['volatility']:.2f}%)\n"

    return reply


@tool
def get_market_sentiment() -> str:
    """市场情绪分析"""
    # 获取所有持仓ETF的数据
    etf_codes = ['159915', '159934', '159994', '510880', '512880', '516160']
    results = []

    for code in etf_codes:
        df = query_etf_data(code, 20)  # 看20日表现
        if len(df) >= 2:
            latest = df.iloc[-1]
            oldest = df.iloc[0]
            change = (latest['close'] - oldest['close']) / oldest['close'] * 100
            results.append({'code': code, 'change_20': change})

    if not results:
        return "数据不足"

    # 计算市场情绪
    up_count = sum(1 for r in results if r['change_20'] > 0)
    down_count = len(results) - up_count

    avg_change = sum(r['change_20'] for r in results) / len(results)

    if up_count >= 5:
        sentiment = "🔥 极度乐观"
    elif up_count >= 4:
        sentiment = "😊 乐观"
    elif up_count >= 3:
        sentiment = "😐 中性"
    elif up_count >= 2:
        sentiment = "😟 谨慎"
    else:
        sentiment = "😰 恐慌"

    return f"📈 市场情绪分析\n\n" \
           f"  市场情绪: {sentiment}\n" \
           f"  上涨ETF: {up_count}/{len(results)}\n" \
           f"  平均涨跌幅: {avg_change:+.2f}%\n\n" \
           f"【建议】\n" \
           f"  {'控制仓位，注意风险' if up_count < 3 else '可以适当乐观' if up_count >= 4 else '保持中性观望'}"


@tool
def get_trading_signal(code: str) -> str:
    """综合买卖信号"""
    df = query_etf_data(code, 60)
    if len(df) < 30:
        return "数据不足"

    latest = df.iloc[-1]
    ma = calculate_ma(df)
    kdj = calculate_kdj(df)
    rsi = calculate_rsi(df)
    macd = calculate_macd(df)

    # 统计信号
    buy_score = 0
    sell_score = 0

    # 均线信号
    if ma['MA5'] > ma['MA10'] > ma['MA20']:
        buy_score += 2
    elif ma['MA5'] < ma['MA10'] < ma['MA20']:
        sell_score += 2

    # KDJ信号
    if kdj and kdj['K'] < 20:
        buy_score += 1
    elif kdj and kdj['K'] > 80:
        sell_score += 1
    if kdj and kdj['K'] > kdj['D'] and kdj['J'] > kdj['K']:
        buy_score += 1
    elif kdj and kdj['K'] < kdj['D']:
        sell_score += 1

    # RSI信号
    if rsi and rsi < 30:
        buy_score += 2
    elif rsi and rsi > 70:
        sell_score += 2

    # MACD信号
    if macd and macd['signal'] == '金叉':
        buy_score += 2
    elif macd and macd['signal'] == '死叉':
        sell_score += 2

    # 综合判断
    if buy_score >= 4:
        signal = "🟢 强烈买入"
    elif buy_score >= 2:
        signal = "🟡 买入"
    elif sell_score >= 4:
        signal = "🔴 强烈卖出"
    elif sell_score >= 2:
        signal = "🟠 卖出"
    else:
        signal = "⚪ 观望"

    # 目标价
    high_60 = df['high'].max()
    low_60 = df['low'].min()
    support = low_60
    resistance = high_60
    current = latest['close']

    return f"🎯 ETF {code} 交易信号\n\n" \
           f"  综合信号: {signal}\n" \
           f"  买入评分: {buy_score}  卖出评分: {sell_score}\n\n" \
           f"【价格区间】\n" \
           f"  当前价: {current:.3f}元\n" \
           f"  支撑位: {support:.3f}元\n" \
           f"  压力位: {resistance:.3f}元\n\n" \
           f"【建议】\n" \
           f"  {'分批建仓，跌破支撑考虑止损' if '买入' in signal else '分批减仓，突破压力考虑止盈' if '卖出' in signal else '继续观察，等待明确信号'}"


@tool
def get_macro_analysis() -> str:
    """获取最新宏观经济数据和分析"""
    macro = macro_loader.get_latest_macro()

    if not macro:
        return "暂无宏观数据"

    # 宏观分析
    signals = []

    # PMI分析
    if 'pmi' in macro:
        pmi = macro['pmi']
        if pmi > 50:
            signals.append(f"PMI={pmi:.1f} > 50，制造业扩张")
        else:
            signals.append(f"PMI={pmi:.1f} < 50，制造业收缩")

    # CPI分析
    if 'cpi_yoy' in macro:
        cpi = macro['cpi_yoy']
        if cpi > 3:
            signals.append(f"CPI同比={cpi:.1f}%，通胀压力")
        elif cpi < 1:
            signals.append(f"CPI同比={cpi:.1f}%，通缩风险")
        else:
            signals.append(f"CPI同比={cpi:.1f}%，温和通胀")

    # M2分析
    if 'm2_yoy' in macro:
        m2 = macro['m2_yoy']
        if m2 > 10:
            signals.append(f"M2同比={m2:.1f}%，货币宽松")
        elif m2 < 5:
            signals.append(f"M2同比={m2:.1f}%，货币收紧")
        else:
            signals.append(f"M2同比={m2:.1f}%，稳健")

    # 综合判断
    expansion_count = sum(1 for s in signals if '扩张' in s or '宽松' in s or '通胀' in s)
    contraction_count = sum(1 for s in signals if '收缩' in s or '收紧' in s or '通缩' in s)

    if expansion_count > contraction_count + 1:
        macro_sentiment = "📈 宏观经济扩张期"
    elif contraction_count > expansion_count + 1:
        macro_sentiment = "📉 宏观经济收缩期"
    else:
        macro_sentiment = "➡️ 宏观经济平稳期"

    # 构建回复
    result = f"📊 宏观经济数据分析\n\n"

    if 'pmi_date' in macro:
        result += f"【PMI】{macro['pmi']:.1f} (数据: {macro['pmi_date'].strftime('%Y-%m')})\n"
    if 'cpi_date' in macro:
        result += f"【CPI同比】{macro['cpi_yoy']:.1f}% (数据: {macro['cpi_date'].strftime('%Y-%m')})\n"
    if 'ppi_date' in macro:
        result += f"【PPI同比】{macro['ppi_yoy']:.1f}% (数据: {macro['ppi_date'].strftime('%Y-%m')})\n"
    if 'm2_date' in macro:
        result += f"【M2同比】{macro['m2_yoy']:.1f}% (数据: {macro['m2_date'].strftime('%Y-%m')})\n"
    if 'sf_date' in macro:
        result += f"【社融】{macro['sf_month']:.0f}亿 (数据: {macro['sf_date'].strftime('%Y-%m')})\n"
    if 'gdp_quarter' in macro:
        result += f"【GDP同比】{macro['gdp_yoy']:.1f}% (季度: {macro['gdp_quarter']})\n"
    if 'shibor_date' in macro:
        result += f"【SHIBOR】1M: {macro['shibor_1m']:.2f}%  3M: {macro['shibor_3m']:.2f}%\n"

    result += f"\n【宏观信号】\n"
    for s in signals:
        result += f"  • {s}\n"

    result += f"\n【周期判断】{macro_sentiment}\n"

    # 投资建议
    if expansion_count > contraction_count:
        result += "\n【投资建议】\n  经济扩张期，建议超配股票型ETF，尤其是成长风格"
    elif contraction_count > expansion_count:
        result += "\n【投资建议】\n  经济下行期，建议增配债券、黄金等防御性资产"
    else:
        result += "\n【投资建议】\n  经济平稳期，建议股债平衡配置"

    return result


@tool
def get_macro_timing(code: str) -> str:
    """结合宏观数据进行ETF投资时机分析"""
    # 获取ETF技术面
    df = query_etf_data(code, 60)
    if len(df) < 30:
        return "数据不足"

    # 获取宏观数据
    macro = macro_loader.get_latest_macro()

    # 技术面信号
    ma = calculate_ma(df)
    latest = df.iloc[-1]

    tech_score = 0
    if ma['MA5'] > ma['MA10'] > ma['MA20']:
        tech_score += 1

    kdj = calculate_kdj(df)
    if kdj and kdj['K'] > kdj['D']:
        tech_score += 1

    rsi = calculate_rsi(df)
    if rsi and rsi < 40:
        tech_score += 1
    elif rsi and rsi > 70:
        tech_score -= 1

    # 宏观信号
    macro_score = 0
    if 'pmi' in macro and macro['pmi'] > 50:
        macro_score += 1
    if 'm2_yoy' in macro and macro['m2_yoy'] > 8:
        macro_score += 1
    if 'cpi_yoy' in macro and macro['cpi_yoy'] < 3:
        macro_score += 1

    # 综合判断
    total_score = tech_score + macro_score

    if total_score >= 4:
        recommendation = "🟢 强烈推荐 - 技术面+宏观面双重支持"
    elif total_score >= 2:
        recommendation = "🟡 谨慎推荐 - 基本面有一定支撑"
    elif total_score <= -1:
        recommendation = "🔴 建议回避 - 宏观环境不利"
    else:
        recommendation = "⚪ 观望 - 需等待更多信号"

    return f"🎯 {code} 宏观择时分析\n\n" \
           f"【技术面得分】{tech_score}/3\n" \
           f"  - 均线多头: {'✅' if ma['MA5'] > ma['MA10'] > ma['MA20'] else '❌'}\n" \
           f"  - KDJ金叉: {'✅' if kdj and kdj['K'] > kdj['D'] else '❌'}\n" \
           f"  - RSI状态: {'超卖✅' if rsi and rsi < 40 else '超买❌' if rsi and rsi > 70 else '中性'}\n\n" \
           f"【宏观面得分】{macro_score}/3\n" \
           f"  - PMI: {'✅扩张' if 'pmi' in macro and macro['pmi'] > 50 else '❌收缩'}\n" \
           f"  - M2: {'✅宽松' if 'm2_yoy' in macro and macro['m2_yoy'] > 8 else '❌收紧'}\n" \
           f"  - CPI: {'✅温和' if 'cpi_yoy' in macro and macro['cpi_yoy'] < 3 else '❌通胀'}\n\n" \
           f"【综合评分】{total_score}/6\n" \
           f"【投资建议】{recommendation}"


@tool
def get_fund_recommendation(criteria: str) -> str:
    """智能基金推荐 - 根据用户需求推荐合适的ETF"""
    # 分析用户需求
    criteria = criteria.lower()

    if any(k in criteria for k in ['保守', '稳健', '低风险', '养老']):
        risk_level = 'low'
    elif any(k in criteria for k in ['激进', '高风险', '成长']):
        risk_level = 'high'
    else:
        risk_level = 'medium'

    # 从数据库获取所有ETF的表现
    etf_codes = ['159915', '159934', '159994', '510880', '512880', '516160']
    results = []

    for code in etf_codes:
        df = query_etf_data(code, 60)
        if len(df) >= 2:
            latest = df.iloc[-1]
            oldest = df.iloc[0]
            change = (latest['close'] - oldest['close']) / oldest['close'] * 100
            volatility = df['close'].pct_change().std() * 100
            results.append({'code': code, 'change': change, 'volatility': volatility})

    if not results:
        return "暂无数据"

    # 根据风险偏好推荐
    if risk_level == 'low':
        # 低风险：推荐低波动、高股息
        results.sort(key=lambda x: x['volatility'])
        recommendation = "低风险推荐：红利ETF(510880)、证券ETF(512880)"
    elif risk_level == 'high':
        # 高风险：推荐高成长
        results.sort(key=lambda x: x['change'], reverse=True)
        recommendation = "高风险推荐：创业板ETF(159915)、5GETF(159994)"
    else:
        # 中等风险：均衡配置
        results.sort(key=lambda x: x['change'], reverse=True)
        recommendation = "均衡推荐：创业板ETF(159915)、新能源ETF(516160)"

    return f"🎯 ETF智能推荐\n\n" \
           f"【您的风险偏好】{'保守型' if risk_level == 'low' else '激进型' if risk_level == 'high' else '平衡型'}\n\n" \
           f"【推荐策略】{recommendation}\n\n" \
           f"【近期表现】\n" \
           + "\n".join([f"  {r['code']}: {r['change']:+.2f}% (波动率: {r['volatility']:.2f}%)" for r in results])


# ========== 初始化Agent ==========

# 从环境变量获取模型配置
# DeepSeek模型格式: openai:deepseek-chat
model_name = 'openai:deepseek-chat' if 'DeepSeek' in MODEL_NAME else MODEL_NAME
base_url = 'https://api.deepseek.com/v1' if 'DeepSeek' in MODEL_NAME else LLM_API_BASE

model = init_chat_model(
    model=model_name,
    temperature=0.7,
    max_tokens=2000,
    api_key=LLM_API_KEY,
    base_url=base_url
)

checkpointer = InMemorySaver()

SYSTEM_PROMPT = """你是一位经验丰富、知识渊博的资深投资者和金融分析师。

你的特点是：
1. 既有扎实的金融理论知识，又有丰富的实战经验
2. 投资风格稳健但不失进取，注重风险控制
3. 善于从多角度分析问题，给出全面的投资建议
4. 表达专业但易懂，会用数据和逻辑说服用户
5. 极度渴望通过分析帮助用户赚钱

你可以使用的工具有：
- get_etf_price: 查询ETF最新价格
- get_etf_60day_change: 查询60日涨跌幅
- get_etf_ma: 均线分析
- get_full_technical_analysis: 完整技术分析（均线+KDJ+RSI+MACD+布林带）
- get_portfolio_analysis: 分析用户整个持仓组合
- get_single_holding_analysis: 分析用户持有的单个持仓
- get_risk_assessment: 风险评估
- get_comparison_analysis: 多ETF对比分析
- get_market_sentiment: 市场情绪分析
- get_trading_signal: 综合买卖信号
- get_macro_analysis: 宏观经济数据分析（PMI/CPI/M2/GDP/SHIBOR）
- get_macro_timing: 宏观择时分析（结合宏观面和技术面）
- get_fund_recommendation: 智能基金推荐（根据风险偏好）
- get_trading_signal: 综合买卖信号

请根据用户的问题，主动使用合适的工具进行分析，给出专业、全面的投资建议。
记住：你最关心的就是帮助用户赚钱！"""

agent = create_agent(
    model=model,
    system_prompt=SYSTEM_PROMPT,
    tools=[
        get_etf_price, get_etf_60day_change, get_etf_ma,
        get_full_technical_analysis, get_portfolio_analysis,
        get_single_holding_analysis, get_risk_assessment,
        get_comparison_analysis, get_market_sentiment, get_trading_signal,
        get_macro_analysis, get_macro_timing, get_fund_recommendation
    ],
    checkpointer=checkpointer
)


# ========== 演示 ==========

if __name__ == "__main__":
    config = {'configurable': {'thread_id': 'full-invest-assistant'}}

    print("=" * 60)
    print("💰 全功能投资助手 - 演示")
    print("=" * 60)

    # 测试1: 完整技术分析
    print("\n【测试1】完整技术分析")
    r1 = agent.invoke(
        {'messages': [{'role': 'user', 'content': '帮我分析一下159915创业板的完整技术面'}]},
        config=config
    )
    for msg in r1['messages']:
        if hasattr(msg, 'content') and isinstance(msg.content, list):
            for item in msg.content:
                if item.get('type') == 'text':
                    print(item.get('text', '')[:800] if len(item.get('text', '')) > 800 else item.get('text', ''))

    # 测试2: 持仓分析
    print("\n【测试2】持仓分析")
    r2 = agent.invoke(
        {'messages': [{'role': 'user', 'content': '我的持仓整体情况怎么样'}]},
        config=config
    )
    for msg in r2['messages']:
        if hasattr(msg, 'content') and isinstance(msg.content, list):
            for item in msg.content:
                if item.get('type') == 'text':
                    print(item.get('text', '')[:800] if len(item.get('text', '')) > 800 else item.get('text', ''))

    # 测试3: 交易信号
    print("\n【测试3】交易信号")
    r3 = agent.invoke(
        {'messages': [{'role': 'user', 'content': '159915现在可以买吗'}]},
        config=config
    )
    for msg in r3['messages']:
        if hasattr(msg, 'content') and isinstance(msg.content, list):
            for item in msg.content:
                if item.get('type') == 'text':
                    print(item.get('text', '')[:800] if len(item.get('text', '')) > 800 else item.get('text', ''))

    # 测试4: 市场情绪
    print("\n【测试4】市场情绪")
    r4 = agent.invoke(
        {'messages': [{'role': 'user', 'content': '现在市场情绪怎么样'}]},
        config=config
    )
    for msg in r4['messages']:
        if hasattr(msg, 'content') and isinstance(msg.content, list):
            for item in msg.content:
                if item.get('type') == 'text':
                    print(item.get('text', '')[:800] if len(item.get('text', '')) > 800 else item.get('text', ''))

    # 测试5: ETF对比
    print("\n【测试5】ETF对比")
    r5 = agent.invoke(
        {'messages': [{'role': 'user', 'content': '帮我对比一下159915、159934、510880这三个ETF'}]},
        config=config
    )
    for msg in r5['messages']:
        if hasattr(msg, 'content') and isinstance(msg.content, list):
            for item in msg.content:
                if item.get('type') == 'text':
                    print(item.get('text', '')[:800] if len(item.get('text', '')) > 800 else item.get('text', ''))

    print("\n" + "=" * 60)
    print("演示结束！")
    print("=" * 60)