"""
LangChain Agent - 全功能投资助手
功能全面的ETF/股票分析系统
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

from langchain.tools import tool
from langchain.chat_models import init_chat_model
from langgraph.checkpoint.memory import InMemorySaver
from langchain.agents import create_agent
from quantchdb import ClickHouseDatabase
import pandas as pd
import numpy as np
from dataclasses import dataclass
from datetime import datetime


# ========== 投资组合配置 ==========

# 用户持仓（来自4月16日数据）
USER_HOLDINGS = {
    '159915': {'name': '创业板ETF', 'shares': 6200, 'cost': 3.49, 'current': 3.511},
    '159934': {'name': '黄金ETF', 'shares': 1300, 'cost': 10.58, 'current': 10.511},
    '159994': {'name': '5GETF', 'shares': 8000, 'cost': 1.09, 'current': 1.097},
    '510880': {'name': '红利ETF', 'shares': 2900, 'cost': 3.22, 'current': 3.240},
    '512880': {'name': '证券ETF', 'shares': 20200, 'cost': 1.07, 'current': 1.073},
    '516160': {'name': '新能源ETF', 'shares': 2600, 'cost': 3.11, 'current': 3.113},
    '002203': {'name': '海亮股份', 'shares': 300, 'cost': 9.77, 'current': 15.43},
    '601857': {'name': '中国石油', 'shares': 1000, 'cost': 11.84, 'current': 11.76},
}


# ========== 工具函数 ==========

def get_db_connection():
    return {
        'host': '10.13.66.5',
        'port': 20108,
        'user': 'cufel_arena_etf_reader',
        'password': 'cufel_arena_etf_404',
        'database': 'etf'
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
           f"  MA20: {ma['MA20']:.3f}  MA60: {ma['MA60']:.3f if ma['MA60'] else 'N/A'}\n" \
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

    result = f"🔍 ETF {code} 完整技术分析 ({(latest['date'])})\n\n" \
             f"【价格信息】\n  当前价: {latest['close']:.3f}元\n\n" \
             f"【均线系统】\n  MA5: {ma['MA5']:.3f}  MA10: {ma['MA10']:.3f}\n  MA20: {ma['MA20']:.3f}  MA60: {ma['MA60']:.3f}\n\n"

    if kdj:
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
        total_cost_val = info['shares'] * info['cost']
        profit = market_value - total_cost_val
        profit_pct = (info['current'] - info['cost']) / info['cost'] * 100

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
    total_profit_pct = total_profit / total_cost * 100

    # 按盈亏排序
    results.sort(key=lambda x: x['profit_pct'], reverse=True)

    # 构建回复
    reply = f"💼 持仓组合分析 (总资产: {total_value:,.0f}元)\n\n"

    # 盈利排行
    reply += "【盈利排行】\n"
    for r in results:
        if r['profit_pct'] > 0:
            reply += f"  ✅ {r['name']}({r['code']}): {r['profit_pct']:+.2f}% ({r['profit']:+,.0f}元)\n"

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


# ========== 初始化Agent ==========

model = init_chat_model(
    'anthropic:claude-sonnet-4-5',
    temperature=0.7,
    max_tokens=2000
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

请根据用户的问题，主动使用合适的工具进行分析，给出专业、全面的投资建议。
记住：你最关心的就是帮助用户赚钱！"""

agent = create_agent(
    model=model,
    system_prompt=SYSTEM_PROMPT,
    tools=[
        get_etf_price, get_etf_60day_change, get_etf_ma,
        get_full_technical_analysis, get_portfolio_analysis,
        get_single_holding_analysis, get_risk_assessment,
        get_comparison_analysis, get_market_sentiment, get_trading_signal
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