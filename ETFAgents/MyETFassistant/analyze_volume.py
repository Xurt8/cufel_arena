import pandas as pd
import sys
sys.stdout.reconfigure(encoding='utf-8')

# 读取数据
df = pd.read_csv('4.18.csv', low_memory=False)

print('正在分析10日放量+60日低位...')

# 计算每只股票的统计
results = []
for code in df['code'].unique():
    stock = df[df['code'] == code].sort_values('date', ascending=False).head(60)
    if len(stock) < 20:
        continue

    # 10日成交量 vs 60日平均成交量
    recent_10 = stock.head(10)
    vol_10 = recent_10['volume'].mean()
    vol_60 = stock['volume'].mean()

    # 判断是否放量（10日均量 > 60日均量）
    if vol_10 <= vol_60:
        continue

    # 判断60日位置是否低位（涨跌幅 < 0）
    first_price = stock.iloc[9]['close']  # 10日前的价格
    last_price = stock.iloc[0]['close']   # 最新价格
    if first_price <= 0:
        continue

    change = (last_price - first_price) / first_price * 100
    if change >= 0:  # 股价在60日内是下跌的
        continue

    # 计算60日位置
    high_60 = stock['close'].max()
    low_60 = stock['close'].min()
    if high_60 == low_60:
        continue
    position = (last_price - low_60) / (high_60 - low_60) * 100

    name = stock.iloc[0]['name']
    results.append({
        'code': code,
        'name': name,
        'vol_10': vol_10,
        'vol_60': vol_60,
        'vol_growth': (vol_10 - vol_60) / vol_60 * 100,
        'position': position,
        'price_10d_ago': first_price,
        'price_now': last_price,
        'change_60d': change
    })

# 转为DataFrame并筛选
result_df = pd.DataFrame(results)

# 筛选：放量增长 + 60日位置<30%
filtered = result_df[(result_df['vol_growth'] > 0) & (result_df['position'] < 30)]

# 按放量幅度排序
filtered = filtered.sort_values('vol_growth', ascending=False)

print('\n放量增长（10日放量 + 60日低位）前30:')
print('代码        名称         10日量增%   60日位置%   10日前价  当前价   60日涨跌幅')
print('-' * 85)

for _, row in filtered.head(30).iterrows():
    print(f"{row['code']:<10} {row['name'][:8]:<8} {row['vol_growth']:>6.1f}%   {row['position']:>5.1f}%   {row['price_10d_ago']:6.2f}  {row['price_now']:6.2f}  {row['change_60d']:>7.1f}%")