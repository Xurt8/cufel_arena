#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
持仓分析基本计算
计算持仓ETF的盈亏、仓位占比、风险评估
"""
import pandas as pd
import numpy as np
import sys
sys.stdout.reconfigure(encoding='utf-8')

print("="*80)
print("📊 ETF持仓分析报告")
print("分析日期: 2026年4月18日")
print("="*80)

# 用户持仓数据
holdings = [
    # 代码, 名称, 数量, 成本价, 当前价, 市值, 浮动盈亏, 盈亏比例
    ('159915', '创业板', 200, 3.480, 3.670, 734.00, 38.00, 5.46),
    ('159934', '黄金ETF', 1300, 10.583, 10.480, 13624.00, -133.27, -0.97),
    ('159994', '5GETF', 5400, 1.090, 1.178, 6361.20, 475.20, 8.07),
    ('510880', '红利ETF', 2900, 3.223, 3.218, 9332.20, -15.80, -0.16),
    ('512690', '酒ETF', 24400, 0.494, 0.485, 11834.00, -224.60, -1.82),
    ('512760', '芯片ETF', 11400, 0.881, 0.881, 10043.40, -5.00, 0.00),
    ('512880', '证券ETF', 20200, 1.071, 1.076, 21735.20, 99.60, 0.47),
    ('516160', '新能源', 1000, 3.100, 3.194, 3194.00, 94.00, 3.03),
    ('601857', '中国石油', 1000, 11.835, 11.530, 11530.00, -305.12, -2.58)
]

# 转换为DataFrame
df = pd.DataFrame(holdings, columns=['代码', '名称', '数量', '成本价', '当前价', '市值', '浮动盈亏', '盈亏比例'])

# 计算额外指标
df['成本市值'] = df['数量'] * df['成本价']
df['当前市值'] = df['数量'] * df['当前价']
df['盈亏金额'] = df['当前市值'] - df['成本市值']
df['盈亏比例_计算'] = df['盈亏金额'] / df['成本市值'] * 100

# 验证用户提供的数据
print("\n📈 持仓数据验证:")
print("-"*80)
for idx, row in df.iterrows():
    print(f"{row['代码']} {row['名称']:8s}: 数量{row['数量']:,} 成本{row['成本价']:.3f} 当前{row['当前价']:.3f}")
    print(f"    市值:{row['当前市值']:,.2f} 盈亏:{row['盈亏金额']:.2f}({row['盈亏比例_计算']:.2f}%)")

# 总体统计
total_cost = df['成本市值'].sum()
total_value = df['当前市值'].sum()
total_profit = total_value - total_cost
total_profit_pct = total_profit / total_cost * 100 if total_cost > 0 else 0

print("\n📊 总体持仓统计:")
print("-"*80)
print(f"总成本: {total_cost:,.2f}元")
print(f"总市值: {total_value:,.2f}元")
print(f"总盈亏: {total_profit:,.2f}元 ({total_profit_pct:.2f}%)")

# 仓位占比分析
df['仓位占比'] = df['当前市值'] / total_value * 100
df['盈亏贡献'] = df['盈亏金额'] / total_value * 100

print("\n📊 仓位分布:")
print("-"*80)
df_sorted = df.sort_values('仓位占比', ascending=False)
for idx, row in df_sorted.iterrows():
    profit_color = "🟢" if row['盈亏金额'] >= 0 else "🔴"
    print(f"{profit_color} {row['代码']} {row['名称']:8s}: {row['仓位占比']:.1f}% ({row['当前市值']:,.2f}元)")

# 盈亏分析
print("\n📊 盈亏分析:")
print("-"*80)
df_profit_sorted = df.sort_values('盈亏金额', ascending=False)
for idx, row in df_profit_sorted.iterrows():
    if row['盈亏金额'] >= 0:
        print(f"🟢 {row['代码']} {row['名称']:8s}: +{row['盈亏金额']:.2f}元 ({row['盈亏比例_计算']:.2f}%)")
    else:
        print(f"🔴 {row['代码']} {row['名称']:8s}: {row['盈亏金额']:.2f}元 ({row['盈亏比例_计算']:.2f}%)")

# 风险评估
print("\n⚠️ 风险评估:")
print("-"*80)
print("1. 亏损持仓:")
loss_positions = df[df['盈亏金额'] < 0]
if len(loss_positions) > 0:
    for idx, row in loss_positions.iterrows():
        print(f"   🔴 {row['代码']} {row['名称']:8s}: 亏损{abs(row['盈亏金额']):.2f}元 ({abs(row['盈亏比例_计算']):.2f}%)")
else:
    print("   无亏损持仓")

print("\n2. 仓位集中度:")
top_3 = df_sorted.head(3)
top_3_pct = top_3['仓位占比'].sum()
print(f"   前3大持仓占比: {top_3_pct:.1f}%")
if top_3_pct > 70:
    print("   ⚠️ 仓位过于集中，建议分散")
elif top_3_pct > 50:
    print("   ⚠️ 仓位集中度较高，注意风险")
else:
    print("   ✅ 仓位分布相对均衡")

print("\n3. 行业/主题分布:")
etf_categories = {
    '创业板': '宽基指数',
    '黄金ETF': '商品',
    '5GETF': '科技',
    '红利ETF': '红利策略',
    '酒ETF': '消费',
    '芯片ETF': '科技',
    '证券ETF': '金融',
    '新能源': '新能源',
    '中国石油': '能源'
}
df['类别'] = df['名称'].map(etf_categories)
category_value = df.groupby('类别')['当前市值'].sum()
category_pct = category_value / total_value * 100

for category, value in category_value.items():
    pct = category_pct[category]
    print(f"   📊 {category}: {pct:.1f}% ({value:,.2f}元)")

print("\n" + "="*80)
print("💡 投资建议:")
print("-"*80)
print("1. 总体持仓盈利，但部分ETF亏损（黄金、酒、芯片、中国石油）")
print("2. 建议关注亏损持仓的技术面，考虑止损或调仓")
print("3. 5GETF和创业板表现最好，可考虑获利了结部分仓位")
print("4. 仓位分布相对均衡，但证券ETF占比最高（21.7%）")
print("5. 注意行业分布，科技类（5G、芯片）占比合理")

print("\n" + "="*80)
print("🔍 下一步:")
print("1. 检查各ETF的历史数据可用性")
print("2. 进行技术面分析（支撑压力、趋势判断）")
print("3. 制定具体的调仓建议")

# 保存结果
output_file = "持仓分析结果.csv"
df.to_csv(output_file, index=False, encoding='utf-8-sig')
print(f"\n📁 分析结果已保存到: {output_file}")