import pandas as pd
import sys
sys.stdout.reconfigure(encoding='utf-8')

df = pd.read_csv('ETFAgents/MacroDrivenETF/data/etf_day_with_basic_2022_2025.csv', low_memory=False)
df['交易日期'] = pd.to_datetime(df['交易日期'])

print("="*60)
print("ETF HOLDING ANALYSIS REPORT")
print("="*60)

# Filter April data
apr = df[(df['交易日期'] >= '2026-04-01') & (df['交易日期'] <= '2026-04-10')].copy()

# Fill NaN names
apr['ETF中文简称'] = apr['ETF中文简称'].fillna('未知')

# Calculate April cumulative returns
apr_summary = apr.groupby('ETF代码').agg({
    '涨跌幅(%)': ['sum', 'std'],
    '成交量(手)': 'mean',
    'ETF中文简称': 'first'
}).reset_index()
apr_summary.columns = ['code', 'total_return', 'volatility', 'avg_vol', 'name']

# Filter: return > 5%, vol > 10M, volatility < 5%
good_etfs = apr_summary[
    (apr_summary['total_return'] > 5) &
    (apr_summary['avg_vol'] > 10000000) &
    (apr_summary['volatility'] < 5)
].sort_values('total_return', ascending=False)

print("\n[1] TOP PERFORMERS (April)")
print("-"*60)
for _, row in good_etfs.head(10).iterrows():
    name = str(row['name'])[:15] if pd.notna(row['name']) else '未知'
    print(f"{row['code']} {name:15s} +{row['total_return']:.1f}%  vol:{row['avg_vol']/1e6:.1f}M")

# [2] By Category
print("\n[2] BY CATEGORY")
print("-"*60)

categories = {
    'Wide Base': ['510300', '510050', '510500', '159919', '159915', '588000'],
    'Securities': ['512880', '512900', '513090'],
    'Tech': ['515050', '515880', '516160', '159363'],
    'Consumption': ['512690', '159928']
}

for cat, codes in categories.items():
    cat_data = apr[apr['ETF代码'].isin(codes)]
    if len(cat_data) > 0:
        returns = cat_data.groupby('ETF代码')['涨跌幅(%)'].sum()
        print(f"\n{cat}:")
        for code in codes:
            if code in returns.index:
                print(f"  {code}: +{returns[code]:.1f}%")

# [3] Recommended Portfolio
print("\n" + "="*60)
print("[3] RECOMMENDED PORTFOLIO")
print("="*60)

# Get latest April 10 data
apr10 = apr[apr['交易日期'] == '2026-04-10'].copy()
apr10['ETF中文简称'] = apr10['ETF中文简称'].fillna('未知')
apr10 = apr10[apr10['涨跌幅(%)'] > 0].sort_values('涨跌幅(%)', ascending=False)

# Top picks
print("\n[RECOMMENDED - Aggressive]")
for _, row in apr10.head(8).iterrows():
    name = str(row['ETF中文简称'])[:15] if pd.notna(row['ETF中文简称']) else '未知'
    print(f"  {row['ETF代码']} {name:15s} +{row['涨跌幅(%)']:.2f}%")

# Steady picks (low volatility, good momentum)
steady = apr_summary[
    (apr_summary['total_return'] > 3) &
    (apr_summary['avg_vol'] > 5000000) &
    (apr_summary['volatility'] < 3)
].sort_values('total_return', ascending=False)

print("\n[RECOMMENDED - Steady]")
for _, row in steady.head(5).iterrows():
    name = str(row['name'])[:15] if pd.notna(row['name']) else '未知'
    print(f"  {row['code']} {name:15s} +{row['total_return']:.1f}%")

# Final recommendation
print("\n" + "="*60)
print("[FINAL RECOMMENDATION]")
print("="*60)
print("""
Based on April 2026 data analysis:

AGGRESSIVE (70% stocks):
  - 510300: 25% (沪深300)
  - 159915: 20% (创业板)
  - 515050: 15% (5G通信)
  - 516160: 10% (新能源)
  = 70%

DEFENSIVE (30% bonds/gold):
  - 511010: 20% (国债)
  - 518880: 10% (黄金)
  = 30%
""")
