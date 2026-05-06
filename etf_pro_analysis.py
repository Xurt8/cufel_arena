#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ETF持仓深度分析 - 使用PracticeData数据库
基于技术分析（均线、支撑压力）计算推荐买卖价格
"""
import pandas as pd
import numpy as np
import sys
sys.stdout.reconfigure(encoding='utf-8')

# ===== 使用PracticeData数据库 =====
data_file = 'C:/Users/xrt85/Desktop/3月22日课程资料/PracticeData/etf_day_with_basic_2022_2025.csv'
df = pd.read_csv(data_file, low_memory=False)
df['交易日期'] = df['交易日期'].astype(str)
df['ETF代码'] = df['ETF代码'].astype(str)

# ETF名称映射
ETF_NAMES = {
    '159934': '黄金ETF',
    '159994': '5GETF',
    '510880': '红利ETF',
    '512690': '酒ETF',
    '512760': '芯片ETF',
    '512880': '证券ETF',
    '516160': '新能源ETF',
    '510300': '沪深300',
    '588000': '科创50',
    '601857': '中国石油',
}

# ===== 用户实际持仓 =====
holdings = {
    '159934': {'qty':1300, 'cost':10.583},
    '159994': {'qty':3600, 'cost':1.036},
    '510880': {'qty':2900, 'cost':3.223},
    '512690': {'qty':24400, 'cost':0.494},
    '512760': {'qty':11400, 'cost':0.881},
    '512880': {'qty':20200, 'cost':1.071},
    '516160': {'qty':1000, 'cost':3.100},
    '601857': {'qty':1000, 'cost':11.835},
}

# ===== 推荐建仓ETF =====
recommend_codes = ['510300', '588000']

all_codes = list(holdings.keys()) + recommend_codes

results = []
for code in all_codes:
    df_etf = df[df['ETF代码']==code].sort_values('交易日期').tail(65)
    if len(df_etf) < 30:
        continue

    prices = df_etf['收盘价(元)'].values
    try:
        prices = prices.astype(float)
    except:
        continue

    try:
        current = float(prices[-1])
    except:
        continue

    if np.isnan(current) or current == 0:
        continue

    # 60日位置
    position = (np.sum(prices < current) / 60) * 100

    # 均线计算
    ma20 = np.mean(prices[-20:])
    ma60 = np.mean(prices[-60:])

    # 支撑：20日均线和60日均线中较低者
    support = min(ma20, ma60)
    # 压力：20日均线和60日均线中较高者
    resistance = max(ma20, ma60)

    # 合理买入价：支撑位以下2%
    buy_price = round(support * 0.98, 3)
    # 合理卖出价：压力位加2%
    sell_price = round(resistance * 1.02, 3)

    # 信号判断
    if position < 25:
        signal = 'BUY'
    elif position > 75:
        signal = 'SELL'
    else:
        signal = 'HOLD'

    name = ETF_NAMES.get(code, code)
    h = holdings.get(code, {})
    qty = h.get('qty')
    cost = h.get('cost')

    if qty and cost:
        pnl_pct = (current - cost) / cost * 100
        results.append({
            'code': code,
            'name': name,
            'qty': qty,
            'cost': cost,
            'current': current,
            'position': position,
            'buy_price': buy_price,
            'sell_price': sell_price,
            'signal': signal,
            'pnl_pct': pnl_pct,
            'type': 'HOLDING'
        })
    else:
        results.append({
            'code': code,
            'name': name,
            'qty': 0,
            'cost': 0,
            'current': current,
            'position': position,
            'buy_price': buy_price,
            'sell_price': sell_price,
            'signal': signal,
            'pnl_pct': 0,
            'type': 'RECOMMEND'
        })

# ===== 输出结果 =====
print("=" * 115)
print("ETF持仓深度分析 - PracticeData (2026-04-16)")
print("=" * 115)
print(f"{'Code':<8} {'Name':<10} {'Qty':<6} {'Cost':<7} {'Current':<7} {'Pos':<7} {'Buy':<9} {'Sell':<9} {'Signal':<6} {'P/L':<6}")
print("-" * 115)

for r in results:
    pos_str = f"{r['position']:.1f}%"
    if r['type'] == 'HOLDING':
        pnl_str = f"{r['pnl_pct']:.1f}%"
        print(f"{r['code']:<8} {r['name']:<10} {r['qty']:<6} {r['cost']:<7.3f} {r['current']:<7.3f} {pos_str:<7} {r['buy_price']:<9.3f} {r['sell_price']:<9.3f} {r['signal']:<6} {pnl_str:<6}")
    else:
        print(f"{r['code']:<8} {r['name']:<10} {'NEW':<6} {'-':<7} {r['current']:<7.3f} {pos_str:<7} {r['buy_price']:<9.3f} {r['sell_price']:<9.3f} {r['signal']:<6} {'-':<6}")

print("=" * 115)

# ===== 交易建议 =====
print("\n" + "=" * 115)
print("交易建议 (基于均线支撑压力计算)")
print("=" * 115)

for r in results:
    if r['signal'] == 'SELL' and r['type'] == 'HOLDING':
        print(f"\n🔴 SELL {r['code']} {r['name']}")
        print(f"  当前价: {r['current']:.3f}, 60日位置: {r['position']:.1f}%")
        print(f"  合理卖出价: {r['sell_price']:.3f}")
        print(f"  理由: 位置{r['position']:.1f}% > 75%，接近压力位")

for r in results:
    if r['signal'] == 'BUY':
        print(f"\n🟢 BUY {r['code']} {r['name']}")
        print(f"  当前价: {r['current']:.3f}, 60日位置: {r['position']:.1f}%")
        print(f"  合理买入价: {r['buy_price']:.3f}")
        if r['type'] == 'HOLDING':
            print(f"  理由: 位置{r['position']:.1f}% < 25%，低估区域，可加仓")
        else:
            print(f"  理由: 位置{r['position']:.1f}% < 25%，推荐建仓")

print("\n" + "=" * 115)