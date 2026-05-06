import pandas as pd

# 读取技术分析数据
tech = pd.read_csv('4.18/技术分析.csv')

# 读取放量增长分析
vol = pd.read_csv('4.18/放量增长分析.csv')

# 合并数据
merged = pd.merge(tech, vol, on='代码')

# 生成投资分析报告
results = []
for _, row in merged.iterrows():
    code = row['代码']
    name = row['名称']
    current = row['current']
    support = row['support']
    resistance = row['resistance']
    position = row['position']
    vol_growth = row['10日量增%']

    # 买入区间: 支撑位附近买入
    buy_low = support
    buy_high = current * 1.03

    # 止损位
    stop_loss = support * 0.95

    results.append({
        'code': code,
        'name': name,
        'current': current,
        'support': round(support, 2),
        'resistance': round(resistance, 2),
        'position': round(position, 1),
        'vol_growth': vol_growth,
        'buy_low': round(buy_low, 2),
        'buy_high': round(buy_high, 2),
        'stop_loss': round(stop_loss, 2)
    })

# 保存报告
result_df = pd.DataFrame(results)
result_df.to_csv('4.18/投资分析报告.csv', index=False, encoding='utf-8-sig')

print('投资分析报告生成完成!')
print('=' * 80)

# 输出前15只
for r in results[:15]:
    print(f"{r['code']} {r['name'][:6]:6s} 当前:{r['current']:.2f} 支撑:{r['support']:.2f} 买入区间:{r['buy_low']:.2f}-{r['buy_high']:.2f} 止损:{r['stop_loss']:.2f}")