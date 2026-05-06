#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ETF综合技术分析 - 增强版（包含动态仓位计算和具体数量建议）
基于优化版增加：
1. 具体买卖数量计算
2. 动态仓位调整模拟
3. 现金管理（保持20%现金）
分析日期：2026年4月21日
"""
import pandas as pd
import numpy as np
import warnings
import sys
from datetime import datetime, timedelta
warnings.filterwarnings('ignore')

sys.stdout.reconfigure(encoding='utf-8')

print("="*80)
print("📈 ETF综合技术分析 - 增强版（动态仓位+具体数量建议）")
print("分析日期: 2026年4月21日")
print("="*80)

# 用户持仓数据（4月21日实际持仓）
holdings = [
    ('159934', '黄金ETF', 1300, 10.583, 10.480),
    ('159994', '5GETF', 3600, 1.036, 1.195),
    ('510880', '红利ETF', 2900, 3.223, 3.225),
    ('512690', '酒ETF', 24400, 0.494, 0.484),
    ('512760', '芯片ETF', 11400, 0.881, 0.897),
    ('512880', '证券ETF', 20200, 1.071, 1.075),
    ('516160', '新能源', 1000, 3.100, 3.201),
    ('601857', '中国石油', 1000, 11.835, 11.480)
]

# 初始现金（实际账户，保持20%）
INITIAL_CASH = 22000  # 实际约107,710元总资产，保持20%现金

# ETF数据文件路径
etf_data_file = 'C:/Users/xrt85/Desktop/3月22日课程资料/cufel_arena/ETFAgents/MacroDrivenETF/data/etf_day_with_basic_2022_2025.csv'

# ETF专用参数（根据用户规则调整）
ETF_PARAMS = {
    'position_period': 60,  # 用户核心规则：60日位置
    'buy_threshold': 25,    # 买入阈值：<25%
    'sell_threshold': 75,   # 卖出阈值：>75%
    'ma_periods': [20, 60, 120],  # ETF注重中长期趋势
    'macd_fast': 15,        # 适应ETF较慢节奏
    'macd_slow': 30,
    'macd_signal': 9,
    'stop_loss_range': [5, 8],  # ETF止损较小：5-8%
    'volume_ratio': 1.5,    # 放量标准（比个股宽松）
    'position_categories': {  # 位置分类
        'historical_low': 20,
        'relative_low': 40,
        'neutral': 60,
        'relative_high': 80,
        'historical_high': 100
    },
    'max_single_position': 20,  # 单只ETF最大仓位占比
    'cash_reserve_pct': 20,     # 现金预留比例
    'min_trade_unit': 100,      # 最小交易单位（股）
    'commission_rate': 0.0003,  # 交易佣金率（万分之三）
    'stamp_tax_rate': 0.001     # 印花税率（卖出时千分之一）
}

# ==================== 动态仓位计算函数 ====================

class PortfolioSimulator:
    """投资组合模拟器（动态计算仓位）"""

    def __init__(self, holdings, initial_cash):
        """初始化投资组合"""
        self.holdings = {}
        self.cash = initial_cash
        self.transactions = []
        self.initial_state = {}

        # 初始化持仓
        for code, name, quantity, cost_price, current_price in holdings:
            market_value = quantity * current_price
            self.holdings[code] = {
                'name': name,
                'quantity': quantity,
                'cost_price': cost_price,
                'current_price': current_price,
                'market_value': market_value,
                'type': 'etf' if code != '601857' else 'stock'
            }
            self.initial_state[code] = quantity

        # 计算初始总资产
        self.update_total_assets()

    def update_total_assets(self):
        """更新总资产"""
        self.total_equity = self.cash
        for holding in self.holdings.values():
            self.total_equity += holding['market_value']
        return self.total_equity

    def calculate_position_ratios(self):
        """计算各持仓占比"""
        ratios = {}
        for code, holding in self.holdings.items():
            ratio = (holding['market_value'] / self.total_equity * 100) if self.total_equity > 0 else 0
            ratios[code] = ratio
        return ratios

    def simulate_sell(self, code, sell_quantity, price=None, reason=""):
        """模拟卖出操作"""
        if code not in self.holdings:
            return False, "持仓不存在"

        holding = self.holdings[code]
        current_quantity = holding['quantity']

        if sell_quantity > current_quantity:
            return False, f"卖出数量{sell_quantity}超过持仓{current_quantity}"

        # 使用当前价或指定价
        sell_price = price if price is not None else holding['current_price']

        # 计算卖出金额
        sell_amount = sell_quantity * sell_price

        # 计算交易成本（印花税+佣金）
        commission = sell_amount * ETF_PARAMS['commission_rate']
        stamp_tax = sell_amount * ETF_PARAMS['stamp_tax_rate']  # 卖出时印花税
        total_cost = commission + stamp_tax
        net_proceeds = sell_amount - total_cost

        # 更新持仓
        holding['quantity'] -= sell_quantity

        # 如果全部卖出，更新成本价逻辑
        if holding['quantity'] == 0:
            holding['cost_price'] = 0
        else:
            # 部分卖出，成本价不变（简化处理）
            pass

        holding['market_value'] = holding['quantity'] * holding['current_price']

        # 更新现金
        self.cash += net_proceeds

        # 记录交易
        self.transactions.append({
            'type': 'sell',
            'code': code,
            'name': holding['name'],
            'quantity': sell_quantity,
            'price': sell_price,
            'amount': sell_amount,
            'cost': total_cost,
            'net': net_proceeds,
            'reason': reason,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })

        # 更新总资产
        self.update_total_assets()

        return True, f"成功卖出{sell_quantity}股，净收入{net_proceeds:.2f}元"

    def simulate_buy(self, code, buy_amount, price=None, reason=""):
        """模拟买入操作（按金额买入）"""
        if code not in self.holdings:
            # 如果是新买入的ETF，先创建持仓记录
            for h_code, h_name, _, _, _ in holdings:
                if h_code == code:
                    self.holdings[code] = {
                        'name': h_name,
                        'quantity': 0,
                        'cost_price': price if price is not None else 0,
                        'current_price': price if price is not None else 0,
                        'market_value': 0,
                        'type': 'etf' if code != '601857' else 'stock'
                    }
                    break
            else:
                return False, "ETF代码不存在"

        holding = self.holdings[code]

        # 使用当前价或指定价
        buy_price = price if price is not None else holding['current_price']

        if buy_price <= 0:
            return False, "买入价格必须大于0"

        # 计算可买数量（考虑最小交易单位）
        raw_quantity = buy_amount / buy_price
        quantity = int(raw_quantity // ETF_PARAMS['min_trade_unit']) * ETF_PARAMS['min_trade_unit']

        if quantity < ETF_PARAMS['min_trade_unit']:
            return False, f"买入金额{buy_amount:.2f}元不足最小交易单位"

        # 计算实际买入金额
        actual_amount = quantity * buy_price

        # 计算交易成本（佣金）
        commission = actual_amount * ETF_PARAMS['commission_rate']
        total_cost = actual_amount + commission

        # 检查现金是否充足
        if total_cost > self.cash:
            return False, f"现金不足，需要{total_cost:.2f}元，仅有{self.cash:.2f}元"

        # 更新持仓
        old_quantity = holding['quantity']
        old_cost = holding['cost_price'] * old_quantity if old_quantity > 0 else 0

        # 计算新的平均成本
        if old_quantity + quantity > 0:
            new_cost_price = (old_cost + actual_amount) / (old_quantity + quantity)
        else:
            new_cost_price = buy_price

        holding['quantity'] = old_quantity + quantity
        holding['cost_price'] = new_cost_price
        holding['current_price'] = buy_price
        holding['market_value'] = holding['quantity'] * buy_price

        # 更新现金
        self.cash -= total_cost

        # 记录交易
        self.transactions.append({
            'type': 'buy',
            'code': code,
            'name': holding['name'],
            'quantity': quantity,
            'price': buy_price,
            'amount': actual_amount,
            'cost': commission,
            'net': -total_cost,
            'reason': reason,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })

        # 更新总资产
        self.update_total_assets()

        return True, f"成功买入{quantity}股，花费{total_cost:.2f}元"

    def get_portfolio_summary(self):
        """获取投资组合摘要"""
        ratios = self.calculate_position_ratios()

        summary = {
            'total_equity': self.total_equity,
            'cash': self.cash,
            'cash_ratio': (self.cash / self.total_equity * 100) if self.total_equity > 0 else 0,
            'holdings': {},
            'transactions': self.transactions.copy()
        }

        for code, ratio in ratios.items():
            holding = self.holdings[code]
            summary['holdings'][code] = {
                'name': holding['name'],
                'quantity': holding['quantity'],
                'cost_price': holding['cost_price'],
                'current_price': holding['current_price'],
                'market_value': holding['market_value'],
                'ratio': ratio,
                'profit_pct': ((holding['current_price'] / holding['cost_price'] - 1) * 100)
                              if holding['cost_price'] > 0 else 0
            }

        return summary

    def generate_trade_plan(self, signals, prices):
        """根据买卖信号生成交易计划"""
        trade_plan = []

        # 计算当前仓位比例
        current_ratios = self.calculate_position_ratios()

        for code, signal_info in signals.items():
            if code not in self.holdings:
                continue

            holding = self.holdings[code]
            signal_type = signal_info.get('signal', 'hold')
            position_pct = signal_info.get('position_pct', 50)
            current_ratio = current_ratios.get(code, 0)

            # 根据信号类型生成交易建议
            if signal_type == 'sell':
                # 卖出逻辑
                if position_pct > 90:  # 严重高估
                    target_ratio = 0  # 全部卖出
                elif position_pct > 75:  # 高估
                    target_ratio = current_ratio / 2  # 减半
                else:
                    continue

                # 计算卖出数量
                target_market_value = (target_ratio / 100) * self.total_equity
                current_market_value = holding['market_value']

                if target_market_value < current_market_value:
                    sell_value = current_market_value - target_market_value
                    sell_quantity = int(sell_value / holding['current_price'])

                    # 调整到最小交易单位
                    sell_quantity = (sell_quantity // ETF_PARAMS['min_trade_unit']) * ETF_PARAMS['min_trade_unit']

                    if sell_quantity > 0:
                        trade_plan.append({
                            'code': code,
                            'name': holding['name'],
                            'action': 'sell',
                            'quantity': sell_quantity,
                            'price': holding['current_price'],
                            'amount': sell_quantity * holding['current_price'],
                            'reason': f'位置{position_pct:.1f}%>75%，卖出至{target_ratio:.1f}%'
                        })

            elif signal_type == 'buy':
                # 买入逻辑
                if position_pct < 10:  # 严重低估
                    target_ratio = ETF_PARAMS['max_single_position']  # 加满至20%
                elif position_pct < 25:  # 低估
                    target_ratio = min(ETF_PARAMS['max_single_position'], current_ratio * 1.5)  # 适度加仓
                else:
                    continue

                # 计算买入金额
                current_ratio = current_ratios.get(code, 0)

                if target_ratio > current_ratio:
                    # 检查现金是否充足（考虑现金预留）
                    available_cash = self.cash - (self.total_equity * ETF_PARAMS['cash_reserve_pct'] / 100)

                    if available_cash > 0:
                        # 计算需要增加的市值
                        target_increase = (target_ratio - current_ratio) / 100 * self.total_equity
                        buy_amount = min(target_increase, available_cash)

                        if buy_amount > 100:  # 最小买入金额
                            trade_plan.append({
                                'code': code,
                                'name': holding['name'],
                                'action': 'buy',
                                'amount': buy_amount,
                                'price': holding['current_price'],
                                'estimated_quantity': int(buy_amount / holding['current_price']),
                                'reason': f'位置{position_pct:.1f}%<25%，加仓至{target_ratio:.1f}%'
                            })

            elif signal_type == 'adjust':
                # 仓位调整（超限减仓）
                if current_ratio > ETF_PARAMS['max_single_position']:
                    target_ratio = ETF_PARAMS['max_single_position']
                    reduce_value = (current_ratio - target_ratio) / 100 * self.total_equity
                    reduce_quantity = int(reduce_value / holding['current_price'])

                    # 调整到最小交易单位
                    reduce_quantity = (reduce_quantity // ETF_PARAMS['min_trade_unit']) * ETF_PARAMS['min_trade_unit']

                    if reduce_quantity > 0:
                        trade_plan.append({
                            'code': code,
                            'name': holding['name'],
                            'action': 'sell',
                            'quantity': reduce_quantity,
                            'price': holding['current_price'],
                            'amount': reduce_quantity * holding['current_price'],
                            'reason': f'仓位{current_ratio:.1f}%>20%限制，减仓至{target_ratio:.1f}%'
                        })

        return trade_plan

# ==================== 数据加载函数 ====================

def load_etf_history(etf_code):
    """从ETF数据文件加载历史数据"""
    try:
        # 读取CSV文件
        df = pd.read_csv(etf_data_file, encoding='utf-8-sig', low_memory=False)

        # 精确匹配ETF代码
        etf_df = df[df['ETF代码'].astype(str) == str(etf_code)].copy()

        if len(etf_df) == 0:
            return None

        # 重命名列
        column_mapping = {
            '交易日期': 'date',
            '开盘价(元)': 'open',
            '最高价(元)': 'high',
            '最低价(元)': 'low',
            '收盘价(元)': 'close',
            '成交量(手)': 'volume',
            '成交额(千元)': 'amount'
        }

        for old_col, new_col in column_mapping.items():
            if old_col in etf_df.columns:
                etf_df[new_col] = etf_df[old_col]

        # 确保必要列存在
        required_cols = ['date', 'open', 'high', 'low', 'close']
        for col in required_cols:
            if col not in etf_df.columns:
                return None

        # 转换日期格式和数值类型
        etf_df['date'] = pd.to_datetime(etf_df['date'], errors='coerce')

        numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'amount']
        for col in numeric_cols:
            if col in etf_df.columns:
                etf_df[col] = pd.to_numeric(etf_df[col], errors='coerce')

        # 按日期排序
        etf_df = etf_df.sort_values('date').reset_index(drop=True)

        return etf_df

    except Exception as e:
        print(f"  加载数据出错: {e}")
        return None

# ==================== 核心分析函数 ====================

def calculate_60day_position(df_security, current_price):
    """计算60日区间位置"""
    if df_security is None or len(df_security) < 60:
        return None, None, None

    recent_data = df_security.tail(60).copy()
    high_60 = recent_data['high'].max()
    low_60 = recent_data['low'].min()

    if high_60 != low_60:
        position_pct = (current_price - low_60) / (high_60 - low_60) * 100
    else:
        position_pct = 50

    # 位置状态
    if position_pct <= ETF_PARAMS['buy_threshold']:
        position_status = "买入区间"
    elif position_pct >= ETF_PARAMS['sell_threshold']:
        position_status = "卖出区间"
    else:
        position_status = "观望区间"

    return position_pct, position_status, {'high_60': high_60, 'low_60': low_60}

def analyze_all_etfs(holdings):
    """分析所有ETF"""
    results = {}

    for etf_code, etf_name, quantity, cost_price, current_price in holdings:
        # 跳过个股
        if etf_code == '601857':
            results[etf_code] = {
                'name': etf_name,
                'position_pct': None,
                'position_status': '数据不足',
                'signal': 'hold',
                'current_price': current_price,
                'cost_price': cost_price,
                'quantity': quantity
            }
            continue

        # 加载数据
        df_etf = load_etf_history(etf_code)

        if df_etf is None or len(df_etf) < 60:
            results[etf_code] = {
                'name': etf_name,
                'position_pct': None,
                'position_status': '数据不足',
                'signal': 'hold',
                'current_price': current_price,
                'cost_price': cost_price,
                'quantity': quantity
            }
            continue

        # 计算60日位置
        position_pct, position_status, _ = calculate_60day_position(df_etf, current_price)

        # 确定信号
        if position_pct is not None:
            if position_status == "买入区间":
                signal = 'buy'
            elif position_status == "卖出区间":
                signal = 'sell'
            else:
                signal = 'hold'
        else:
            signal = 'hold'

        results[etf_code] = {
            'name': etf_name,
            'position_pct': position_pct,
            'position_status': position_status,
            'signal': signal,
            'current_price': current_price,
            'cost_price': cost_price,
            'quantity': quantity
        }

    return results

# ==================== 主流程 ====================

print("\n🔍 开始ETF综合技术分析（增强版）...")
print("="*80)

# 初始化投资组合模拟器
portfolio = PortfolioSimulator(holdings, INITIAL_CASH)

# 分析所有ETF
print("📊 分析ETF技术面...")
signals = analyze_all_etfs(holdings)

# 显示分析结果
print("\n📈 ETF技术分析结果:")
print("-"*80)

for code, info in signals.items():
    if info['position_pct'] is not None:
        signal_symbol = "🟢买入" if info['signal'] == 'buy' else "🔴卖出" if info['signal'] == 'sell' else "🟡持有"
        print(f"{code} {info['name']:8s}: {signal_symbol} | 位置:{info['position_pct']:.1f}% ({info['position_status']})")
    else:
        print(f"{code} {info['name']:8s}: ⚪数据不足")

# 生成交易计划
print("\n🎯 生成交易计划...")
trade_plan = portfolio.generate_trade_plan(signals, {})

# 显示初始状态
initial_summary = portfolio.get_portfolio_summary()
print(f"\n💰 初始状态:")
print(f"  总资产: {initial_summary['total_equity']:,.0f}元")
print(f"  现金: {initial_summary['cash']:,.0f}元 ({initial_summary['cash_ratio']:.1f}%)")
print(f"  持仓市值: {initial_summary['total_equity'] - initial_summary['cash']:,.0f}元")

print("\n📊 初始持仓分布:")
for code, holding in initial_summary['holdings'].items():
    if holding['quantity'] > 0:
        print(f"  {code} {holding['name']:8s}: {holding['quantity']:,}股, 市值{holding['market_value']:,.0f}元 ({holding['ratio']:.1f}%)")

# 执行交易计划（模拟）
print("\n🔄 执行交易计划（模拟）:")
print("-"*80)

if trade_plan:
    for i, trade in enumerate(trade_plan, 1):
        if trade['action'] == 'sell':
            success, message = portfolio.simulate_sell(
                trade['code'],
                trade['quantity'],
                trade['price'],
                trade['reason']
            )
            if success:
                print(f"{i}. 🔴 卖出 {trade['code']} {trade['name']}: {trade['quantity']:,}股 @ {trade['price']:.3f}")
                print(f"   金额: {trade['amount']:,.0f}元 | 理由: {trade['reason']}")
            else:
                print(f"{i}. ❌ 卖出失败: {message}")

        elif trade['action'] == 'buy':
            success, message = portfolio.simulate_buy(
                trade['code'],
                trade['amount'],
                trade['price'],
                trade['reason']
            )
            if success:
                print(f"{i}. 🟢 买入 {trade['code']} {trade['name']}: {trade['amount']:,.0f}元 @ {trade['price']:.3f}")
                print(f"   预估: {trade['estimated_quantity']:,}股 | 理由: {trade['reason']}")
            else:
                print(f"{i}. ❌ 买入失败: {message}")
else:
    print("暂无交易建议")

# 显示最终状态
print("\n✅ 交易完成后的投资组合:")
print("-"*80)

final_summary = portfolio.get_portfolio_summary()
print(f"  总资产: {final_summary['total_equity']:,.0f}元")
print(f"  现金: {final_summary['cash']:,.0f}元 ({final_summary['cash_ratio']:.1f}%)")

print("\n📊 最终持仓分布:")
for code, holding in final_summary['holdings'].items():
    if holding['quantity'] > 0:
        profit_symbol = "🟢" if holding['profit_pct'] >= 0 else "🔴"
        print(f"  {code} {holding['name']:8s}: {holding['quantity']:,}股, 市值{holding['market_value']:,.0f}元 ({holding['ratio']:.1f}%)")
        print(f"    成本:{holding['cost_price']:.3f}, 当前:{holding['current_price']:.3f}, 盈亏:{profit_symbol}{holding['profit_pct']:.1f}%")

# 统计交易情况
print("\n📈 交易统计:")
print("-"*80)
total_buy = sum(t['net'] for t in portfolio.transactions if t['type'] == 'buy')
total_sell = sum(t['net'] for t in portfolio.transactions if t['type'] == 'sell')
print(f"  买入总额: {-total_buy:,.0f}元")
print(f"  卖出总额: {total_sell:,.0f}元")
print(f"  净现金流: {total_sell + total_buy:,.0f}元")
print(f"  交易次数: {len(portfolio.transactions)}笔")

# 检查规则遵守情况
print("\n🔍 规则遵守检查:")
print("-"*80)

# 检查单只ETF仓位限制
final_ratios = portfolio.calculate_position_ratios()
overweight_etfs = []
for code, ratio in final_ratios.items():
    if portfolio.holdings[code]['type'] == 'etf' and ratio > ETF_PARAMS['max_single_position']:
        overweight_etfs.append((code, portfolio.holdings[code]['name'], ratio))

if overweight_etfs:
    print("⚠️  超限持仓:")
    for code, name, ratio in overweight_etfs:
        print(f"  {code} {name}: {ratio:.1f}% > {ETF_PARAMS['max_single_position']}%")
else:
    print("✅ 所有ETF仓位均在限制范围内")

# 检查现金比例
cash_ratio = (portfolio.cash / portfolio.total_equity * 100) if portfolio.total_equity > 0 else 0
if cash_ratio >= ETF_PARAMS['cash_reserve_pct'] - 5:  # 允许5%偏差
    print(f"✅ 现金比例: {cash_ratio:.1f}% (目标:{ETF_PARAMS['cash_reserve_pct']}%)")
else:
    print(f"⚠️  现金不足: {cash_ratio:.1f}% < {ETF_PARAMS['cash_reserve_pct']}%")

# 生成具体操作清单
print("\n📋 具体操作清单（供执行参考）:")
print("-"*80)

if portfolio.transactions:
    for i, txn in enumerate(portfolio.transactions, 1):
        action_symbol = "🟢买入" if txn['type'] == 'buy' else "🔴卖出"
        print(f"{i}. {action_symbol} {txn['code']} {txn['name']}")
        print(f"   数量: {txn['quantity']:,}股 @ {txn['price']:.3f}元")
        print(f"   金额: {txn['amount']:,.0f}元 (成本:{txn['cost']:.1f}元)")
        print(f"   理由: {txn['reason']}")
        print(f"   时间: {txn['timestamp']}")
        print()
else:
    print("无交易操作")

# 保存结果
output_data = {
    '初始状态': initial_summary,
    '交易计划': trade_plan,
    '执行结果': final_summary,
    '交易记录': portfolio.transactions
}

print(f"\n💾 分析完成，结果已保存到内存")
print("="*80)
print("🎯 核心改进总结:")
print("-"*80)
print("1. ✅ 动态仓位计算：实时更新买卖后的仓位比例")
print("2. ✅ 具体数量建议：提供精确的买卖股数和金额")
print("3. ✅ 现金管理：考虑20%现金预留规则")
print("4. ✅ 交易成本：计入佣金和印花税")
print("5. ✅ 最小交易单位：考虑100股整数倍限制")
print("6. ✅ 规则检查：自动验证仓位和现金比例")
print("\n📊 下次分析建议:")
print("1. 定期（每周）运行分析，更新持仓数据")
print("2. 根据实际成交价调整模拟参数")
print("3. 监控规则遵守情况，及时调整")
print("="*80)