#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
今日持仓调整方案 (2026年4月13日)
策略: 70%ETF + 10%股票 + 20%现金
止盈止损规则已设置
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

print("="*70)
print("【今日持仓调整方案】")
print("   策略: 70%ETF + 10%股票 + 20%现金 + 止盈止损")
print("="*70)

# ==================== 当前市场情况 ====================
print("\n【一、当前市场情况 (2026-04-13)】")
print("-"*70)

# 今日数据
today_data = {
    'date': '2026-04-13',
    'close': 3971.20,
    'change': -0.27,
    'volume': 30738,
    'amplitude': 0.54,
}

# 近期趋势
trend = [
    ('04-07', -0.81),
    ('04-08', +1.72),
    ('04-09', -1.07),
    ('04-10', +0.54),
    ('04-13', -0.27),
]

print(f"上证指数: {today_data['close']}点")
print(f"今日涨跌: {today_data['change']:+.2f}%")
print(f"成交量: {today_data['volume']:,}亿")

print(f"\n近期走势:")
for t in trend:
    icon = '📈' if t[1] > 0 else '📉'
    print(f"  {t[0]}: {t[1]:+.2f}% {icon}")

# 极端情况判断
four_day_change = sum(t[1] for t in trend[-4:])
print(f"\n4日累计: {four_day_change:+.2f}%")

# ==================== 当前持仓 ====================
print("\n【二、当前持仓状况】")
print("-"*70)

# 当前持仓 (根据之前数据)
current_holdings = [
    {'code': '601857', 'name': '中国石油', 'shares': 1000, 'cost': 11.835, 'price': 11.96, 'pl': '+1.1%'},
    {'code': '002203', 'name': '海亮股份', 'shares': 1000, 'cost': 13.785, 'price': 14.67, 'pl': '+6.4%'},
    {'code': '600331', 'name': '宏达股份', 'shares': 300, 'cost': 25.830, 'price': 15.24, 'pl': '-41.0%'},
    {'code': '601319', 'name': '中国人保', 'shares': 1000, 'cost': 8.705, 'price': 7.46, 'pl': '-14.3%'},
    {'code': '601669', 'name': '中国电建', 'shares': 1000, 'cost': 6.125, 'price': 5.68, 'pl': '-7.3%'},
    {'code': '601933', 'name': '永辉超市', 'shares': 500, 'cost': 4.120, 'price': 3.75, 'pl': '-9.0%'},
    {'code': '159518', 'name': '标普油气', 'shares': 6900, 'cost': 1.544, 'price': 1.246, 'pl': '-19.3%'},
]

# ETF持仓
etf_holdings = [
    {'code': '159915', 'name': '创业板ETF', 'shares': 1100, 'cost': 3.457, 'price': 3.468, 'pl': '+0.3%'},
    {'code': '159994', 'name': '5GETF', 'shares': 3500, 'cost': 1.081, 'price': 1.088, 'pl': '+0.6%'},
    {'code': '516160', 'name': '新能源ETF', 'shares': 1300, 'cost': 3.093, 'price': 3.091, 'pl': '-0.1%'},
]

# 计算当前资产
stock_value = sum(h['shares'] * h['price'] for h in current_holdings)
etf_value = sum(e['shares'] * e['price'] for e in etf_holdings)
cash = 47705

total_value = stock_value + etf_value + cash
print(f"总资产: {total_value:,}元")
print(f"\n持仓分布:")
print(f"  股票: {stock_value:,.0f}元 ({stock_value/total_value*100:.1f}%)")
print(f"  ETF: {etf_value:,.0f}元 ({etf_value/total_value*100:.1f}%)")
print(f"  现金: {cash:,.0f}元 ({cash/total_value*100:.1f}%)")

# ==================== 持仓诊断 ====================
print("\n【三、持仓诊断】")
print("-"*70)

# 分类
good_stocks = []
bad_stocks = []
for h in current_holdings:
    pl = float(h['pl'].replace('%','').replace('+',''))
    if pl > 0:
        good_stocks.append(h)
    else:
        bad_stocks.append(h)

print("✅ 盈利股:")
for g in good_stocks:
    print(f"  {g['name']}: {g['pl']}")

print("\n⚠️ 亏损股:")
for b in bad_stocks:
    print(f"  {b['name']}: {b['pl']}")

# ==================== 调整方案 ====================
print("\n【四、调整方案】")
print("-"*70)

target_cash_ratio = 0.20
target_etf_ratio = 0.70
target_stock_ratio = 0.10

target_cash = int(total_value * target_cash_ratio)
target_etf = int(total_value * target_etf_ratio)
target_stock = int(total_value * target_stock_ratio)

print(f"目标配置:")
print(f"  现金: {target_cash_ratio*100:.0f}% ({target_cash:,}元)")
print(f"  ETF: {target_etf_ratio*100:.0f}% ({target_etf:,}元)")
print(f"  股票: {target_stock_ratio*100:.0f}% ({target_stock:,}元)")

# 需要操作的
current_stock_ratio = stock_value / total_value
current_etf_ratio = etf_value / total_value
current_cash_ratio = cash / total_value

stock_diff = target_stock - stock_value
etf_diff = target_etf - etf_value
cash_diff = target_cash - cash

print(f"\n当前差距:")
print(f"  股票: {stock_value:,}元 → 需{'卖' if stock_diff < 0 else '买'}{abs(stock_diff):,}元")
print(f"  ETF: {etf_value:,}元 → 需{'卖' if etf_diff < 0 else '买'}{abs(etf_diff):,}元")
print(f"  现金: {cash:,}元 → 需{'卖' if cash_diff < 0 else '买'}{abs(cash_diff):,}元")

# ==================== 具体操作 ====================
print("\n【五、具体操作 (今日)】")
print("-"*70)

print("""
📊 卖出操作:
""")
# 卖出亏损股
to_sell = bad_stocks
sell_value = 0
for s in to_sell:
    value = s['shares'] * s['price']
    sell_value += value
    print(f"  {s['name']}: 卖出{s['shares']}股 @ {s['price']}元 = {value:,.0f}元")

# 卖出部分盈利股
print(f"\n  盈利股保留:")
for g in good_stocks:
    print(f"  {g['name']}: 持有{g['shares']}股 (目标保留)")

print("""
📊 买入操作:
""")
print(f"  目标ETF配置: {target_etf:,}元")
print(f"  建议分批建仓:")
print(f"    1. 创业板ETF (159915): 30%")
print(f"    2. 证券ETF (512880): 25%")
print(f"    3. 红利ETF (510880): 15%")

# ==================== 止盈止损提醒 ====================
print("\n【六、止盈止损提醒】")
print("-"*70)

current_profit = total_value - 114393
profit_pct = current_profit / 114393 * 100

print(f"当前收益率: {profit_pct:+.2f}%")

if profit_pct >= 15:
    action = "⚠️ 止盈线: 卖出50%ETF"
elif profit_pct >= 10:
    action = "⚠️ 止盈线: 停止放大新买入"
elif profit_pct <= -10:
    action = "⚠️ 止损线: 停止新买入"
elif profit_pct <= -15:
    action = "⚠️ 止损线: 必须清仓"
else:
    action = "✅ 正常运行"

print(f"状态: {action}")

# 极端情况判断
if today_data['change'] < -3:
    extreme = "📉 极端: 动用10%现金买入ETF"
elif four_day_change < -5:
    extreme = "📉 极端: 动用15%现金买入ETF"
else:
    extreme = "✅ 正常"

print(f"极端情况: {extreme}")

# ==================== 总结 ====================
print("\n【七、总结】")
print("="*70)

print(f"""
今日策略状态:
  - 总资产: {total_value:,}元
  - 收益率: {profit_pct:+.2f}%
  - 现金比例: {current_cash_ratio*100:.1f}% (目标20%)

今日操作:
  1. 卖出全部亏损股 ({len(to_sell)}只)
  2. 保留盈利股 (核心蓝筹)
  3. 逐步建仓ETF至70%

⚠️ 提醒:
  - 保持{int(total_value*0.2):,}元以上现金
  - 严格执行止盈止损
  - 逆向操作,别人恐惧我贪婪
""")

print("="*70)
print("✅ 调整方案生成完成")
print("="*70)