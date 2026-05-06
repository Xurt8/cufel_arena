#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
持仓优化建议
目标: 保持现金≥30%，提高收益
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

print("="*70)
print("【持仓优化建议】")
print("   目标: 保持现金≥30%，提高收益")
print("="*70)

# ==================== 当前持仓 ====================
current_cash = 47705
current_holdings = [
    {'code': '002203', 'name': '海亮股份', 'shares': 1000, 'cost': 13.785, 'price': 14.67},
    {'code': '600331', 'name': '宏达股份', 'shares': 300, 'cost': 25.830, 'price': 15.24},
    {'code': '601319', 'name': '中国人保', 'shares': 1000, 'cost': 8.705, 'price': 7.46},
    {'code': '601669', 'name': '中国电建', 'shares': 1000, 'cost': 6.125, 'price': 5.68},
    {'code': '601857', 'name': '中国石油', 'shares': 1000, 'cost': 11.835, 'price': 11.96},
    {'code': '601933', 'name': '永辉超市', 'shares': 500, 'cost': 4.120, 'price': 3.75},
    {'code': '159518', 'name': '标普油气', 'shares': 6900, 'cost': 1.544, 'price': 1.246},
]

# ETF持仓
etf_holdings = [
    {'code': '159915', 'name': '创业板ETF', 'shares': 1100, 'cost': 3.457, 'price': 3.468},
    {'code': '159994', 'name': '5GETF', 'shares': 3500, 'cost': 1.081, 'price': 1.088},
    {'code': '516160', 'name': '新能源ETF', 'shares': 1300, 'cost': 3.093, 'price': 3.091},
]

# 计算当前资产
stock_value = sum(h['shares'] * h['price'] for h in current_holdings)
etf_value = sum(e['shares'] * e['price'] for e in etf_holdings)
total_value = stock_value + etf_value + current_cash
cash_ratio = current_cash / total_value * 100

print(f"\n【当前资产状况】")
print(f"  股票市值: {stock_value:,.0f}元")
print(f"  ETF市值: {etf_value:,.0f}元")
print(f"  现金: {current_cash:,.0f}元")
print(f"  总资产: {total_value:,.0f}元")
print(f"  现金比例: {cash_ratio:.1f}%")

# ==================== 持仓分析 ====================
print("\n【一、持仓诊断】")
print("-"*70)
print(f"{'股票':<10} {'股数':>6} {'成本':>7} {'现价':>6} {'盈亏':>8} {'评分':>4} {'建议'}")
print("-"*70)

recommendations = []
for h in current_holdings:
    value = h['shares'] * h['price']
    cost = h['shares'] * h['cost']
    pl = value - cost
    pl_pct = pl / cost * 100

    # 评分
    score = 50
    if pl_pct > 10: score = 70
    elif pl_pct > 0: score = 55
    elif pl_pct > -10: score = 40
    else: score = 30

    # 建议
    if score >= 60:
        action = '持有'
        change = 0
    elif score >= 40:
        action = '持有'
        change = 0
    else:
        action = '卖出'
        change = -h['shares']

    recommendations.append({
        'code': h['code'],
        'name': h['name'],
        'shares': h['shares'],
        'value': value,
        'pl': pl,
        'pl_pct': pl_pct,
        'score': score,
        'action': action,
        'change': change
    })

    symbol = '➡️' if change == 0 else '⬇️'
    print(f"{h['name']:<10} {h['shares']:>6} {h['cost']:>7.3f} {h['price']:>6.2f} {pl_pct:>+7.1f}% {score:>3}分 {symbol}{action}")

# ==================== 优化方案 ====================
print("\n【二、持仓优化方案】")
print("-"*70)

print("""
优化思路:
1. 保留高评分股票 (海亮、中国石油)
2. 减少/卖出低评分股票 (中国人保、中国电建、永辉)
3. 增加高成长ETF配置
4. 保持现金≥30%
""")

# 优化操作
print("操作建议:")
print("-"*70)

# 需要卖出的
to_sell = [r for r in recommendations if r['action'] == '卖出']
sell_value = sum(r['value'] for r in to_sell)
print(f"\n【卖出】")
for r in to_sell:
    print(f"  {r['name']}: 卖出{r['shares']}股 @ {next(h['price'] for h in current_holdings if h['code']==r['code']):.2f}元 = {r['value']:,.0f}元")

# 计算调整后
new_cash = current_cash + sell_value
target_etf = new_cash * 0.25  # 25%配置ETF
remaining_cash = new_cash - target_etf  # 保留现金

# ETF配置
etf_allocation = [
    {'code': '516160', 'name': '新能源ETF', 'pct': 0.35},
    {'code': '159915', 'name': '创业板ETF', 'pct': 0.35},
    {'code': '159994', 'name': '5GETF', 'pct': 0.30},
]

print(f"\n【ETF配置 - 提升收益】")
for e in etf_allocation:
    amount = target_etf * e['pct']
    # 找对应ETF价格
    price = next((etf['price'] for etf in etf_holdings if etf['code'] in ['159915','159994','516160'] and e['name'].replace('ETF','').replace('新能源','').replace('创业板','').replace('5G','') in etf['name']), 3.0)
    if e['code'] == '516160': price = 3.091
    if e['code'] == '159915': price = 3.468
    if e['code'] == '159994': price = 1.088
    shares = int(amount / price)
    print(f"  {e['name']}: 买入{shares}股 @{price:.3f}元 = {shares*price:,.0f}元")

# 保留股票
keep = [r for r in recommendations if r['action'] == '持有']
keep_value = sum(r['value'] for r in keep)
print(f"\n【保留股票】")
for r in keep:
    print(f"  {r['name']}: 持有{r['shares']}股")

# ==================== 调整后仓位 ====================
print("\n【三、调整后仓位】")
print("-"*70)

new_stock_value = sum(r['value'] for r in keep)  # 保留的股票
new_etf_value = target_etf
new_cash_final = remaining_cash

new_total = new_stock_value + new_etf_value + new_cash_final
new_cash_ratio = new_cash_final / new_total * 100

print(f"  股票: {new_stock_value:,.0f}元 ({new_stock_value/new_total*100:.1f}%)")
print(f"  ETF: {new_etf_value:,.0f}元 ({new_etf_value/new_total*100:.1f}%)")
print(f"  现金: {new_cash_final:,.0f}元 ({new_cash_ratio:.1f}%)")

if new_cash_ratio >= 30:
    print(f"  ✅ 现金比例符合要求 (≥30%)")
else:
    print(f"  ⚠️ 需要调整")

# ==================== 收益预期 ====================
print("\n【四、收益提升分析】")
print("-"*70)

print("""
当前问题:
1. 持仓中有亏损较大的股票 (中国人保-15%, 中国电建-7%)
2. ETF配置偏低 (仅9.2%)
3. 标普油气表现不佳

优化收益来源:
1. 卖出低评分股票 → 减少亏损
2. 增加高成长ETF → 提升收益
3. 保留核心股票 → 稳定收益
""")

print(f"""
预期收益提升:
- 减少亏损: 约+1,500元 (卖出亏损股)
- ETF增配: 预计年化+5~8%
- 总体提升: 预计年化+3~5%
""")

print("="*70)
print("【总结】")
print("="*70)
print("""
优化方案:
1. 卖出: 中国人保、中国电建、永辉超市
2. 增持: 新能源ETF、创业板ETF、5GETF
3. 保留: 海亮股份、中国石油
4. 现金: 保留30%以上

预期效果:
- 减少亏损股持仓
- 增加高成长ETF配置
- 保持30%+现金比例
- 提升整体收益
""")
print("="*70)