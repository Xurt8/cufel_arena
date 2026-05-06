import sys
sys.stdout.reconfigure(encoding='utf-8')

from quantchdb import ClickHouseDatabase
import pandas as pd

config = {
    'host': '10.13.66.5',
    'port': 20108,
    'user': 'cufel_arena_etf_reader',
    'password': 'cufel_arena_etf_404',
    'database': 'etf'
}

db = ClickHouseDatabase(config=config)
client = db.connect()

# 用户持仓ETF代码
etf_codes = ['159915', '159934', '159994', '510880', '512880', '516160']

# 当前价格（来自用户4月16日持仓）
current_prices = {
    '159915': 3.511,
    '159934': 10.511,
    '159994': 1.097,
    '510880': 3.240,
    '512880': 1.073,
    '516160': 3.113
}

etf_names = {
    '159915': '创业板ETF',
    '159934': '黄金ETF',
    '159994': '5GETF',
    '510880': '红利ETF',
    '512880': '证券ETF',
    '516160': '新能源ETF'
}

print("=" * 80)
print("ETF 60日交易分析报告 (内网数据: 2026-04-15)")
print("=" * 80)

results = []

for code in etf_codes:
    name = etf_names[code]

    # 获取60日数据
    query = f'''
    SELECT date, open, high, low, close, vol
    FROM etf_day
    WHERE code = '{code}'
    ORDER BY date DESC
    LIMIT 60
    '''
    result = client.execute(query)
    columns = ['date', 'open', 'high', 'low', 'close', 'vol']
    df = pd.DataFrame(result, columns=columns)
    df = df.sort_values('date', ascending=True)  # 按时间正序

    if len(df) == 0:
        print(f"\n{code} {name}: 无数据")
        continue

    # 统计
    latest = df.iloc[-1]
    oldest = df.iloc[0]

    high_60 = df['high'].max()
    low_60 = df['low'].min()
    avg_price = df['close'].mean()
    avg_vol = df['vol'].mean()

    change_60 = (latest['close'] - oldest['close']) / oldest['close'] * 100
    change_20 = (latest['close'] - df.iloc[-20]['close']) / df.iloc[-20]['close'] * 100

    current = current_prices[code]
    position_pct = (current - low_60) / (high_60 - low_60) * 100 if high_60 != low_60 else 50

    # 均线
    ma5 = df['close'].tail(5).mean()
    ma10 = df['close'].tail(10).mean()
    ma20 = df['close'].tail(20).mean()
    ma60 = df['close'].tail(60).mean()

    if ma5 > ma10 > ma20:
        trend = "上升趋势"
    elif ma5 < ma10 < ma20:
        trend = "下降趋势"
    else:
        trend = "震荡整理"

    volatility = df['pct_chg'].std() if 'pct_chg' in df.columns else df['close'].pct_change().std() * 100

    print(f"\n{'='*60}")
    print(f"{code} {name}")
    print(f"{'='*60}")
    print(f"当前价格(4月16日): {current:.3f}")
    print(f"数据最新(4月15日): {latest['close']:.3f}")
    print(f"60日涨跌: {change_60:+.2f}%")
    print(f"20日涨跌: {change_20:+.2f}%")
    print(f"60日区间: {low_60:.3f} ~ {high_60:.3f}")
    print(f"当前位置: {position_pct:.1f}%")
    print(f"60日均价: {avg_price:.3f}")
    print(f"波动率: {volatility:.2f}%")
    print(f"均线: MA5={ma5:.3f} MA10={ma10:.3f} MA20={ma20:.3f} MA60={ma60:.3f}")
    print(f"趋势: {trend}")

    results.append({
        'code': code,
        'name': name,
        'current': current,
        'change_60': change_60,
        'change_20': change_20,
        'position_pct': position_pct,
        'trend': trend,
        'volatility': volatility
    })

print("\n" + "=" * 80)
print("操作建议汇总")
print("=" * 80)

for r in results:
    if r['position_pct'] > 80:
        action = "接近60日高点，可考虑部分卖出"
    elif r['position_pct'] < 20:
        action = "接近60日低点，可考虑加仓"
    elif r['trend'] == '上升趋势':
        action = "上升趋势中，继续持有"
    elif r['trend'] == '下降趋势':
        action = "下降趋势，观望为主"
    else:
        action = "继续持有观望"

    r['action'] = action

# 按60日涨跌排序
results.sort(key=lambda x: x['change_60'], reverse=True)

for r in results:
    print(f"\n{r['name']:8s} ({r['code']}): 60日{r['change_60']:+.2f}%  位置{r['position_pct']:.0f}%  趋势:{r['trend']}")
    print(f"  >>> {r['action']}")