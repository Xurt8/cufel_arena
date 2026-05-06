import pandas as pd
import sys
sys.stdout.reconfigure(encoding='utf-8')

# 读取数据
df = pd.read_csv('4.18.csv', low_memory=False)

print('正在分析60日交易量和趋势...')

# 计算每只股票的统计
results = []
codes = df['code'].unique()[:300]  # 限制前300只

for code in codes:
    stock = df[df['code'] == code].sort_values('date', ascending=False).head(60)
    if len(stock) >= 20:
        avg_vol = stock['volume'].mean()
        first_price = stock.iloc[0]['close']
        last_price = stock.iloc[-1]['close']
        if first_price > 0:
            change = (last_price - first_price) / first_price * 100
            name = stock.iloc[0]['name']
            results.append({
                'code': code,
                'name': name,
                'avg_vol': avg_vol,
                'change': change,
                'first': first_price,
                'last': last_price
            })

result_df = pd.DataFrame(results)

# 筛选涨幅>0的股票，并按交易量和涨幅排序
positive = result_df[result_df['change'] > 0].sort_values(['avg_vol', 'change'], ascending=[False, False])

print('\n放量增长趋势前30 (60日涨幅>0):')
print('代码        名称         日均成交量(万) 60日涨跌幅  首日     末日')
print('-' * 70)

for _, row in positive.head(30).iterrows():
    change_str = f"{row['change']:.1f}%"
    vol_w = row['avg_vol'] / 1e4
    print(f"{row['code']:<10} {row['name'][:8]:<8} {vol_w:8.0f}  {change_str:>8}  {row['first']:6.2f}  {row['last']:6.2f}")