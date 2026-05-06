import pandas as pd
import numpy as np
import sys
sys.stdout.reconfigure(encoding='utf-8')

# 读取最新ETF数据
df = pd.read_csv('C:/Users/xrt85/Desktop/3月22日课程资料/cufel_arena/ETFAgents/MacroDrivenETF/data/etf_day_with_basic_2022_2025.csv', low_memory=False)
df['交易日期'] = pd.to_datetime(df['交易日期'])

# 用户持仓的ETF
holdings = {
    '159915': '创业板ETF',
    '159934': '黄金ETF',
    '159994': '5GETF',
    '510880': '红利ETF',
    '512880': '证券ETF',
    '516160': '新能源ETF'
}

# 当前价格（来自用户持仓，4月16日）
current_prices = {
    '159915': 3.511,
    '159934': 10.511,
    '159994': 1.097,
    '510880': 3.240,
    '512880': 1.073,
    '516160': 3.113
}

print("=" * 80)
print("ETF 60日交易分析报告 (数据截止: 2026-04-11)")
print("=" * 80)

results = []

for code, name in holdings.items():
    etf_data = df[df['ETF代码'].astype(str) == code].copy()

    if len(etf_data) == 0:
        print(f"\n{code} {name}: 无数据")
        continue

    # 按日期排序，取最近60个交易日
    etf_data = etf_data.sort_values('交易日期', ascending=False).head(60)

    # 基本信息
    latest = etf_data.iloc[0]
    oldest = etf_data.iloc[-1]

    # 60日统计
    high_60 = etf_data['最高价(元)'].max()
    low_60 = etf_data['最低价(元)'].min()
    avg_vol = etf_data['成交量(手)'].mean()
    avg_price = etf_data['收盘价(元)'].mean()

    # 60日涨跌幅
    change_60 = (latest['收盘价(元)'] - oldest['收盘价(元)']) / oldest['收盘价(元)'] * 100

    # 当前价格
    current = current_prices[code]

    # 当前位置（在60日区间中的位置）
    position_pct = (current - low_60) / (high_60 - low_60) * 100 if high_60 != low_60 else 50

    # 计算均线
    etf_data_sorted = etf_data.sort_values('交易日期', ascending=True)
    ma5 = etf_data_sorted['收盘价(元)'].tail(5).mean()
    ma10 = etf_data_sorted['收盘价(元)'].tail(10).mean()
    ma20 = etf_data_sorted['收盘价(元)'].tail(20).mean()
    ma60 = etf_data_sorted['收盘价(元)'].tail(60).mean()

    # 均线排列（判断趋势）
    if ma5 > ma10 > ma20 > ma60:
        trend = "上升趋势"
    elif ma5 < ma10 < ma20 < ma60:
        trend = "下降趋势"
    else:
        trend = "震荡整理"

    # 20日涨跌幅
    change_20 = (latest['收盘价(元)'] - etf_data.head(20).iloc[-1]['收盘价(元)']) / etf_data.head(20).iloc[-1]['收盘价(元)'] * 100

    # 波动率
    volatility = etf_data['涨跌幅(%)'].std()

    print(f"\n{'='*60}")
    print(f"{code} {name}")
    print(f"{'='*60}")
    print(f"当前价格(4月16日): {current:.3f}")
    print(f"数据最新日期(4月11日): {latest['收盘价(元)']:.3f}")
    print(f"60日涨跌: {change_60:+.2f}%")
    print(f"20日涨跌: {change_20:+.2f}%")
    print(f"60日区间: {low_60:.3f} ~ {high_60:.3f}")
    print(f"当前位置: {position_pct:.1f}% (在60日区间中)")
    print(f"60日均价: {avg_price:.3f}")
    print(f"60日均量: {avg_vol/10000:.2f}万手")
    print(f"波动率: {volatility:.2f}%")
    print(f"\n均线状态:")
    print(f"  MA5: {ma5:.3f}  MA10: {ma10:.3f}  MA20: {ma20:.3f}  MA60: {ma60:.3f}")
    print(f"  趋势判断: {trend}")

    results.append({
        'code': code,
        'name': name,
        'current': current,
        'data_price': latest['收盘价(元)'],
        'change_60': change_60,
        'change_20': change_20,
        'high_60': high_60,
        'low_60': low_60,
        'position_pct': position_pct,
        'ma5': ma5,
        'ma10': ma10,
        'ma20': ma20,
        'ma60': ma60,
        'trend': trend,
        'volatility': volatility
    })

print("\n" + "=" * 80)
print("操作建议汇总")
print("=" * 80)

# 生成建议
for r in results:
    # 综合判断
    if r['ma5'] > r['ma10'] > r['ma20'] and r['change_60'] > 5:
        action = "持有，可考虑部分止盈"
        priority = 1
    elif r['ma5'] < r['ma10'] and r['change_60'] < -5:
        action = "观望，等待止跌信号"
        priority = 3
    elif r['position_pct'] > 80:
        action = "接近60日高点，可考虑部分卖出"
        priority = 2
    elif r['position_pct'] < 20:
        action = "接近60日低点，可考虑加仓"
        priority = 1
    else:
        action = "继续持有观望"
        priority = 2

    r['action'] = action
    r['priority'] = priority

# 按优先级和涨幅排序
results.sort(key=lambda x: (x['priority'], -x['change_60']))

for r in results:
    print(f"\n{r['name']:8s} ({r['code']:6s})")
    print(f"  60日涨跌: {r['change_60']:+.2f}%  位置: {r['position_pct']:.0f}%  波动率: {r['volatility']:.2f}%")
    print(f"  趋势: {r['trend']}")
    print(f"  >>> 操作建议: {r['action']}")

print("\n" + "=" * 80)
print("ETF组合配置建议")
print("=" * 80)

# 分类建议
uptrend = [r for r in results if r['trend'] == '上升趋势']
downtrend = [r for r in results if r['trend'] == '下降趋势']
oscillation = [r for r in results if r['trend'] == '震荡整理']

print(f"\n上升趋势 ({len(uptrend)}只): {', '.join([r['name'] for r in uptrend])}")
print(f"震荡整理 ({len(oscillation)}只): {', '.join([r['name'] for r in oscillation])}")
print(f"下降趋势 ({len(downtrend)}只): {', '.join([r['name'] for r in downtrend]) if downtrend else '无'}")

print("\n配置建议:")
if uptrend:
    print(f"- 增加配置: {', '.join([r['name'] for r in uptrend])}")
if downtrend:
    print(f"- 减少配置: {', '.join([r['name'] for r in downtrend])}")
if oscillation:
    print(f"- 保持配置: {', '.join([r['name'] for r in oscillation])}")