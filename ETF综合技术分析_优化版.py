#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ETF综合技术分析 - 优化版（严格遵循用户60日位置规则）
基于用户投资规则优化：
1. 60日位置<25%买入，>75%卖出（核心规则）
2. 单只ETF≤20%仓位管理
3. ETF特性参数调整
分析日期：2026年4月18日
"""
import pandas as pd
import numpy as np
import warnings
import sys
from datetime import datetime, timedelta
warnings.filterwarnings('ignore')

sys.stdout.reconfigure(encoding='utf-8')

print("="*80)
print("📈 ETF综合技术分析 - 优化版（严格遵循用户60日位置规则）")
print("分析日期: 2026年4月18日")
print("="*80)

# 用户持仓数据（从用户输入整理）
holdings = [
    ('159915', '创业板', 200, 3.480, 3.670),
    ('159934', '黄金ETF', 1300, 10.583, 10.480),
    ('159994', '5GETF', 5400, 1.090, 1.178),
    ('510880', '红利ETF', 2900, 3.223, 3.218),
    ('512690', '酒ETF', 24400, 0.494, 0.485),
    ('512760', '芯片ETF', 11400, 0.881, 0.881),
    ('512880', '证券ETF', 20200, 1.071, 1.076),
    ('516160', '新能源', 1000, 3.100, 3.194),
    ('601857', '中国石油', 1000, 11.835, 11.530)
]

# ETF数据文件路径
etf_data_file = 'ETFAgents/MacroDrivenETF/data/etf_day_with_basic_2022_2025.csv'

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
    'cash_reserve': 20          # 现金预留比例
}

# ==================== 数据加载函数（优化版） ====================

def load_etf_history(etf_code):
    """从ETF数据文件加载历史数据（优化匹配）"""
    try:
        print(f"  读取 {etf_code} 历史数据...")
        # 读取CSV文件，注意可能有BOM头
        df = pd.read_csv(etf_data_file, encoding='utf-8-sig', low_memory=False)

        # 先尝试精确匹配ETF代码
        etf_df = df[df['ETF代码'].astype(str) == str(etf_code)].copy()

        if len(etf_df) == 0:
            # 尝试去除可能的空格和特殊字符
            etf_df = df[df['ETF代码'].astype(str).str.strip() == str(etf_code).strip()].copy()

        if len(etf_df) == 0:
            print(f"  未找到精确匹配 {etf_code} 的数据")
            return None

        print(f"  找到 {len(etf_df)} 行数据")

        # 重命名列，标准化格式
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
                print(f"  缺少必要列: {col}")
                return None

        # 转换日期格式
        etf_df['date'] = pd.to_datetime(etf_df['date'], errors='coerce')

        # 转换数值类型
        numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'amount']
        for col in numeric_cols:
            if col in etf_df.columns:
                etf_df[col] = pd.to_numeric(etf_df[col], errors='coerce')

        # 按日期排序
        etf_df = etf_df.sort_values('date').reset_index(drop=True)

        # 检查数据质量
        if etf_df['close'].isna().sum() > len(etf_df) * 0.1:  # 超过10%缺失
            print(f"  数据质量较差，缺失值过多")
            return None

        print(f"  数据日期范围: {etf_df['date'].min().date()} 到 {etf_df['date'].max().date()}")
        return etf_df

    except Exception as e:
        print(f"  加载数据出错: {e}")
        return None

def load_stock_history(stock_code):
    """加载个股历史数据（占位函数，实际需要个股数据源）"""
    print(f"  个股 {stock_code} 需要个股数据源，暂时无法分析")
    return None

def load_security_data(code, security_type='etf'):
    """根据类型加载证券数据"""
    if security_type == 'etf':
        return load_etf_history(code)
    else:
        return load_stock_history(code)

# ==================== 核心规则函数（60日位置） ====================

def calculate_60day_position(df_security, current_price):
    """计算60日区间位置（用户核心规则）"""
    if df_security is None or len(df_security) < ETF_PARAMS['position_period']:
        return None, None, None

    # 获取最近60个交易日数据
    recent_data = df_security.tail(ETF_PARAMS['position_period']).copy()

    # 计算60日最高价和最低价
    high_60 = recent_data['high'].max()
    low_60 = recent_data['low'].min()

    # 计算位置百分比
    if high_60 != low_60:
        position_pct = (current_price - low_60) / (high_60 - low_60) * 100
    else:
        position_pct = 50

    # 位置状态（基于用户规则）
    if position_pct <= ETF_PARAMS['buy_threshold']:
        position_status = "买入区间"
    elif position_pct >= ETF_PARAMS['sell_threshold']:
        position_status = "卖出区间"
    else:
        position_status = "观望区间"

    return position_pct, position_status, {'high_60': high_60, 'low_60': low_60}

def apply_user_position_rule(position_pct, position_status):
    """应用用户60日位置规则生成买卖信号"""
    if position_pct is None:
        return "数据不足", "无法计算60日位置"

    if position_status == "买入区间":
        return "买入信号", f"60日位置{position_pct:.1f}%<{ETF_PARAMS['buy_threshold']}%，符合买入规则"
    elif position_status == "卖出区间":
        return "卖出信号", f"60日位置{position_pct:.1f}%>{ETF_PARAMS['sell_threshold']}%，符合卖出规则"
    else:
        return "持有信号", f"60日位置{position_pct:.1f}%在{ETF_PARAMS['buy_threshold']}%-{ETF_PARAMS['sell_threshold']}%之间，观望"

# ==================== 技术分析函数（ETF优化版） ====================

def calculate_ma_etf(data, periods):
    """计算ETF移动平均线（多周期）"""
    ma_results = {}
    for period in periods:
        ma_results[f'ma{period}'] = data.rolling(window=period, min_periods=1).mean()
    return ma_results

def calculate_macd_etf(data):
    """计算ETF MACD指标（优化参数）"""
    fast = ETF_PARAMS['macd_fast']
    slow = ETF_PARAMS['macd_slow']
    signal = ETF_PARAMS['macd_signal']

    exp1 = data.ewm(span=fast, adjust=False).mean()
    exp2 = data.ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    histogram = macd - signal_line
    return macd, signal_line, histogram

def analyze_trend_etf(df_security, current_price):
    """分析ETF趋势状态"""
    if len(df_security) < 60:
        return "数据不足", {}

    # 计算多周期均线
    ma_results = calculate_ma_etf(df_security['close'], ETF_PARAMS['ma_periods'])

    # 获取当前均线值
    current_ma = {}
    for ma_name, ma_values in ma_results.items():
        if len(ma_values) > 0:
            current_ma[ma_name] = ma_values.iloc[-1]
        else:
            current_ma[ma_name] = np.nan

    # 趋势判断（基于均线排列）
    if 'ma20' in current_ma and 'ma60' in current_ma and 'ma120' in current_ma:
        ma20 = current_ma['ma20']
        ma60 = current_ma['ma60']
        ma120 = current_ma['ma120']

        if not np.isnan(ma20) and not np.isnan(ma60) and not np.isnan(ma120):
            if current_price > ma20 > ma60 > ma120:
                trend = "强势上升趋势"
            elif current_price > ma20 and ma20 > ma60:
                trend = "上升趋势"
            elif current_price < ma20 and ma20 < ma60:
                trend = "下降趋势"
            else:
                trend = "横盘震荡"
        else:
            trend = "数据不足"
    else:
        trend = "数据不足"

    # 站上60日线判断
    above_ma60 = False
    if 'ma60' in current_ma and not np.isnan(current_ma['ma60']):
        above_ma60 = current_price > current_ma['ma60']

    trend_info = {
        'trend': trend,
        'above_ma60': above_ma60,
        'current_ma': current_ma
    }

    return trend, trend_info

def calculate_support_resistance_etf(df_security, current_price):
    """计算ETF支撑位和压力位（考虑ETF特性）"""
    if len(df_security) < 60:
        return {}, {}

    # 使用最近90天数据
    recent_data = df_security.tail(90).copy()

    supports = {}
    resistances = {}

    # 1. 均线支撑（ETF重视中长期）
    ma_results = calculate_ma_etf(recent_data['close'], [20, 60, 120])

    for ma_name, ma_values in ma_results.items():
        if len(ma_values) > 0:
            ma_value = ma_values.iloc[-1]
            if ma_value < current_price:
                supports[f'{ma_name}支撑'] = ma_value

    # 2. 近期低点支撑（60日内）
    if len(recent_data) >= 60:
        low_60 = recent_data.tail(60)['low'].min()
        if low_60 < current_price:
            supports['60日低点'] = low_60

    # 3. 近期低点支撑（20日内）
    low_20 = recent_data.tail(20)['low'].min()
    if low_20 < current_price:
        supports['20日低点'] = low_20

    # 4. 前期平台支撑
    if len(recent_data) > 30:
        earlier_data = recent_data.iloc[:-30]
        if len(earlier_data) > 10:
            # 简化平台识别：成交密集区中位
            price_bins = pd.cut(earlier_data['close'], bins=5)
            if 'volume' in earlier_data.columns:
                volume_by_price = earlier_data.groupby(price_bins)['volume'].sum()
                if len(volume_by_price) > 0:
                    max_volume_bin = volume_by_price.idxmax()
                    if hasattr(max_volume_bin, 'mid'):
                        support_price = max_volume_bin.mid
                        if support_price < current_price:
                            supports['前期平台'] = support_price

    # 压力位
    # 1. 近期高点压力（60日内）
    if len(recent_data) >= 60:
        high_60 = recent_data.tail(60)['high'].max()
        if high_60 > current_price:
            resistances['60日高点'] = high_60

    # 2. 近期高点压力（20日内）
    high_20 = recent_data.tail(20)['high'].max()
    if high_20 > current_price:
        resistances['20日高点'] = high_20

    # 3. 整数关口压力（ETF常见）
    # 根据价格级别调整整数关口
    if current_price < 1:
        integer_level = round(current_price * 100) / 100  # 保留两位小数
    elif current_price < 10:
        integer_level = round(current_price * 10) / 10  # 保留一位小数
    else:
        integer_level = round(current_price)

    if integer_level > current_price:
        resistances['整数关口'] = integer_level

    # 4. 前期高点压力
    if len(recent_data) > 60:
        # 寻找60-90天前的高点
        earlier_high = recent_data.iloc[:30]['high'].max()
        if earlier_high > current_price:
            resistances['前期高点'] = earlier_high

    return supports, resistances

def check_etf_technical_signals(df_security):
    """检查ETF技术信号（基于用户标准调整）"""
    if len(df_security) < 60:
        return {}

    signals = {}

    # 1. 检查放量拉升（ETF调整标准）
    recent_data = df_security.tail(30).copy()
    if 'volume' in recent_data.columns:
        for i in range(1, len(recent_data)):
            vol_today = recent_data.iloc[i]['volume']
            vol_yesterday = recent_data.iloc[i-1]['volume']

            # ETF放量标准：1.5倍（比个股的2倍宽松）
            if vol_yesterday > 0 and vol_today >= vol_yesterday * ETF_PARAMS['volume_ratio']:
                close_today = recent_data.iloc[i]['close']
                close_yesterday = recent_data.iloc[i-1]['close']

                # 需要上涨
                if close_today > close_yesterday:
                    date_str = recent_data.iloc[i]['date'].strftime('%Y-%m-%d')
                    signals['放量拉升'] = {
                        'date': date_str,
                        'volume_ratio': vol_today / vol_yesterday,
                        'price_change': (close_today / close_yesterday - 1) * 100
                    }
                    break

    # 2. 检查山谷形态
    ma5 = df_security['close'].rolling(window=5, min_periods=1).mean()
    ma10 = df_security['close'].rolling(window=10, min_periods=1).mean()
    ma20 = df_security['close'].rolling(window=20, min_periods=1).mean()

    recent_data = df_security.tail(60).copy()
    for i in range(3, len(recent_data)):
        idx = recent_data.index[i]
        ma5_today = ma5.iloc[idx] if idx < len(ma5) else np.nan
        ma5_prev = ma5.iloc[recent_data.index[i-1]] if recent_data.index[i-1] < len(ma5) else np.nan
        ma10_today = ma10.iloc[idx] if idx < len(ma10) else np.nan
        ma10_prev = ma10.iloc[recent_data.index[i-1]] if recent_data.index[i-1] < len(ma10) else np.nan
        ma20_today = ma20.iloc[idx] if idx < len(ma20) else np.nan

        if np.isnan(ma5_today) or np.isnan(ma5_prev) or np.isnan(ma10_today) or np.isnan(ma10_prev) or np.isnan(ma20_today):
            continue

        if ma5_prev <= ma10_prev and ma5_today > ma10_today:
            if ma5_today > ma20_today and ma10_today > ma20_today:
                signals['金山谷'] = recent_data.iloc[i]['date'].strftime('%Y-%m-%d')
                break
            else:
                signals['银山谷'] = recent_data.iloc[i]['date'].strftime('%Y-%m-%d')
                break

    # 3. 检查MACD底背离
    if len(df_security) >= 120:
        recent_data = df_security.tail(120).copy()
        macd, signal, hist = calculate_macd_etf(recent_data['close'])

        # 简化底背离检查：价格新低但MACD不新低
        price_lows = []
        for i in range(20, len(recent_data) - 5):
            if i >= len(macd):
                continue

            # 检查局部低点
            window_start = max(0, i - 10)
            window_end = min(len(recent_data), i + 10)
            price_window = recent_data['close'].iloc[window_start:window_end]

            if recent_data['close'].iloc[i] == price_window.min():
                price_lows.append({
                    'idx': i,
                    'price': recent_data['close'].iloc[i],
                    'macd': macd.iloc[i]
                })

        # 检查底背离
        for i in range(1, len(price_lows)):
            prev_low = price_lows[i-1]
            curr_low = price_lows[i]

            if curr_low['price'] < prev_low['price'] and curr_low['macd'] > prev_low['macd']:
                if curr_low['macd'] < 0:  # 水下
                    signals['MACD底背离'] = '存在'
                    break

    return signals

def suggest_stop_loss_etf(df_security, current_price, cost_price=None, position_pct=None):
    """建议ETF止损价（结合技术位、成本和位置）"""
    if len(df_security) < 60:
        return None, {}

    # 计算支撑位
    supports, _ = calculate_support_resistance_etf(df_security, current_price)

    # 多种止损方案
    stop_loss_options = {}

    # 1. 技术止损：跌破重要支撑位
    if supports:
        important_support = min(supports.values()) if supports else current_price
        loss_pct = (current_price - important_support) / current_price * 100

        # 只考虑合理范围内的止损
        if ETF_PARAMS['stop_loss_range'][0] <= loss_pct <= ETF_PARAMS['stop_loss_range'][1]:
            stop_loss_options['技术止损'] = {
                'price': important_support,
                'loss_pct': loss_pct,
                'reason': f'跌破重要支撑位 {important_support:.3f}'
            }

    # 2. 百分比止损（ETF建议5-8%）
    for pct in range(ETF_PARAMS['stop_loss_range'][0], ETF_PARAMS['stop_loss_range'][1] + 1):
        stop_price = current_price * (1 - pct/100)
        stop_loss_options[f'{pct}%固定止损'] = {
            'price': stop_price,
            'loss_pct': pct,
            'reason': f'固定{pct}%止损'
        }

    # 3. 成本止损（如果提供成本价且亏损）
    if cost_price is not None and current_price < cost_price:
        current_loss = (cost_price - current_price) / cost_price * 100

        # 如果已经亏损，考虑更严格的止损
        for additional_loss in [2, 3, 5]:
            stop_price = current_price * (1 - additional_loss/100)
            total_loss_from_cost = (cost_price - stop_price) / cost_price * 100

            # 总亏损控制在8%以内
            if total_loss_from_cost <= 8:
                stop_loss_options[f'成本追加-{additional_loss}%'] = {
                    'price': stop_price,
                    'loss_pct': (current_price - stop_price) / current_price * 100,
                    'reason': f'基于当前价追加{additional_loss}%止损，总亏损{total_loss_from_cost:.1f}%'
                }

    # 4. 位置止损（高位ETF需要更严格止损）
    if position_pct is not None and position_pct > 70:  # 高位
        strict_stop_pct = ETF_PARAMS['stop_loss_range'][0]  # 取最小值
        stop_price = current_price * (1 - strict_stop_pct/100)
        stop_loss_options['高位严格止损'] = {
            'price': stop_price,
            'loss_pct': strict_stop_pct,
            'reason': f'高位{position_pct:.1f}%，严格{strict_stop_pct}%止损'
        }

    # 选择最佳止损方案
    best_stop = None
    for name, option in stop_loss_options.items():
        # ETF优选：损失在5-8%范围内，有技术依据优先
        if ETF_PARAMS['stop_loss_range'][0] <= option['loss_pct'] <= ETF_PARAMS['stop_loss_range'][1]:
            if '技术' in name:  # 优先技术止损
                best_stop = option.copy()
                best_stop['name'] = name
                break
            elif best_stop is None:
                best_stop = option.copy()
                best_stop['name'] = name

    # 如果没有合适的，选择损失最小的
    if best_stop is None and stop_loss_options:
        best_stop = min(stop_loss_options.values(), key=lambda x: x['loss_pct'])
        best_stop['name'] = '最小损失止损'

    return best_stop, stop_loss_options

# ==================== 综合建议生成（规则优先） ====================

def generate_comprehensive_recommendation_rule_first(etf_info, position_pct, position_status,
                                                    position_signal, trend_info, supports,
                                                    resistances, best_stop, technical_signals):
    """生成综合投资建议（规则优先）"""
    recommendation = {
        '核心信号': position_signal[0],
        '核心理由': position_signal[1],
        '操作建议': '持有',
        '信心等级': '中等',
        '关键理由': [],
        '风险提示': [],
        '仓位建议': '维持'
    }

    current_price = etf_info['current_price']
    cost_price = etf_info['cost_price']
    quantity = etf_info['quantity']
    market_value = etf_info.get('market_value', current_price * quantity)
    total_value = etf_info.get('total_value', market_value)  # 简化处理

    # 1. 核心规则信号（最高优先级）
    if position_signal[0] == "买入信号":
        recommendation['操作建议'] = '买入'
        recommendation['信心等级'] = '高'
        recommendation['关键理由'].append(f'60日位置{position_pct:.1f}%<{ETF_PARAMS["buy_threshold"]}%')
    elif position_signal[0] == "卖出信号":
        recommendation['操作建议'] = '卖出'
        recommendation['信心等级'] = '高'
        recommendation['关键理由'].append(f'60日位置{position_pct:.1f}%>{ETF_PARAMS["sell_threshold"]}%')

    # 2. 盈亏状态（次要考虑）
    if cost_price is not None:
        profit_pct = (current_price / cost_price - 1) * 100

        if position_signal[0] == "卖出信号" and profit_pct > 0:
            recommendation['关键理由'].append(f'盈利{profit_pct:.1f}%，符合止盈条件')
        elif position_signal[0] == "买入信号" and profit_pct < -5:
            recommendation['风险提示'].append(f'当前亏损{abs(profit_pct):.1f}%，谨慎抄底')

    # 3. 趋势判断
    trend = trend_info.get('trend', '未知')
    if trend in ["强势上升趋势", "上升趋势"]:
        recommendation['信心等级'] = '高'
        recommendation['关键理由'].append(f'处于{trend}')
    elif trend == "下降趋势":
        if position_signal[0] == "买入信号":
            recommendation['风险提示'].append('处于下降趋势，左侧交易风险')
        else:
            recommendation['关键理由'].append('处于下降趋势，减仓避险')

    # 4. 技术信号增强
    if technical_signals:
        strong_signals = ['金山谷', '银山谷', 'MACD底背离']
        for signal_name in strong_signals:
            if signal_name in technical_signals:
                recommendation['信心等级'] = '高'
                recommendation['关键理由'].append(f'有{signal_name}信号')
                break

        if '放量拉升' in technical_signals:
            recommendation['关键理由'].append('近期有放量拉升')

    # 5. 支撑压力分析
    support_count = len(supports)
    resistance_count = len(resistances)

    if support_count >= 3:
        recommendation['信心等级'] = '高'
        recommendation['关键理由'].append(f'有{support_count}重技术支撑')
    elif support_count <= 1:
        recommendation['风险提示'].append('技术支撑位较少')

    # 6. 仓位管理建议
    if total_value > 0:
        position_ratio = (market_value / total_value) * 100

        if position_ratio > ETF_PARAMS['max_single_position']:
            recommendation['仓位建议'] = f'减仓至{ETF_PARAMS["max_single_position"]}%以下'
            recommendation['风险提示'].append(f'当前占比{position_ratio:.1f}%超限')
        elif position_signal[0] == "买入信号" and position_ratio < ETF_PARAMS['max_single_position']:
            recommendation['仓位建议'] = f'可加仓至{ETF_PARAMS["max_single_position"]}%'

    # 7. 止损建议
    if best_stop:
        stop_price = best_stop['price']
        loss_pct = best_stop['loss_pct']
        recommendation['止损建议'] = f"{stop_price:.3f} (亏损{loss_pct:.1f}%)"
        recommendation['止损理由'] = best_stop.get('reason', '')

    # 8. 目标价位
    if resistances:
        nearest_resistance = min(resistances.values())
        target_return = (nearest_resistance - current_price) / current_price * 100
        if target_return > 0:
            recommendation['目标价位'] = f"{nearest_resistance:.3f} (+{target_return:.1f}%)"

    return recommendation

# ==================== 主分析流程 ====================

print("\n🔍 开始ETF综合技术分析（优化版）...")
print("="*80)

results = []
total_market_value = 0

# 先计算总市值
for _, _, quantity, _, current_price in holdings:
    total_market_value += quantity * current_price

print(f"📊 账户总市值: {total_market_value:,.0f}元")
print(f"📋 分析持仓数量: {len(holdings)}只")
print(f"🎯 核心规则: 60日位置<{ETF_PARAMS['buy_threshold']}%买入，>{ETF_PARAMS['sell_threshold']}%卖出")
print(f"📈 仓位限制: 单只ETF≤{ETF_PARAMS['max_single_position']}%，现金预留{ETF_PARAMS['cash_reserve']}%")
print("-"*80)

for etf_code, etf_name, quantity, cost_price, current_price in holdings:
    print(f"\n{'='*60}")
    print(f"📊 综合分析: {etf_name} ({etf_code})")
    print(f"{'='*60}")

    # 基础信息
    market_value = quantity * current_price
    position_ratio = (market_value / total_market_value) * 100 if total_market_value > 0 else 0

    print(f"  持仓: {quantity:,}股 | 成本: {cost_price:.3f} | 当前: {current_price:.3f}")
    print(f"  市值: {market_value:,.0f}元 | 占比: {position_ratio:.1f}%")

    profit_pct = (current_price / cost_price - 1) * 100
    profit_symbol = "🟢" if profit_pct >= 0 else "🔴"
    print(f"  盈亏: {profit_symbol} {profit_pct:.2f}%")

    # 判断证券类型（ETF还是个股）
    security_type = 'etf'
    if etf_code == '601857':  # 中国石油
        security_type = 'stock'
        print(f"  ⚠️  {etf_name}为个股，使用个股分析逻辑")

    # 加载历史数据
    df_security = load_security_data(etf_code, security_type)

    if df_security is None:
        print(f"  ❌ 历史数据不足，无法进行技术分析")
        results.append({
            '代码': etf_code,
            '名称': etf_name,
            '类型': security_type,
            '当前价': current_price,
            '成本价': cost_price,
            '盈亏%': profit_pct,
            '市值占比%': position_ratio,
            '60日位置%': None,
            '位置状态': '数据不足',
            '核心信号': '数据不足',
            '操作建议': '数据不足',
            '状态': '数据不足'
        })
        continue

    print(f"  ✅ 数据充足，开始分析...")

    # 1. 计算60日位置（核心规则）
    position_pct, position_status, position_data = calculate_60day_position(df_security, current_price)

    if position_pct is not None:
        position_signal = apply_user_position_rule(position_pct, position_status)
        print(f"  60日位置: {position_pct:.1f}% ({position_status})")
        print(f"  核心信号: {position_signal[0]} - {position_signal[1]}")

        if position_data:
            print(f"  区间范围: {position_data['low_60']:.3f} - {position_data['high_60']:.3f}")
    else:
        position_signal = ("数据不足", "无法计算60日位置")
        print(f"  ⚠️  无法计算60日位置")

    # 2. 分析趋势
    trend, trend_info = analyze_trend_etf(df_security, current_price)
    print(f"  趋势分析: {trend}")
    if trend_info.get('above_ma60'):
        print(f"  站上60日线: 是")

    # 3. 计算支撑压力位
    supports, resistances = calculate_support_resistance_etf(df_security, current_price)

    print(f"  支撑位 ({len(supports)}个):")
    for name, price in sorted(supports.items(), key=lambda x: x[1], reverse=True):
        diff_pct = (current_price - price) / current_price * 100
        print(f"    {name}: {price:.3f} (-{diff_pct:.1f}%)")

    print(f"  压力位 ({len(resistances)}个):")
    for name, price in sorted(resistances.items(), key=lambda x: x[1]):
        diff_pct = (price - current_price) / current_price * 100
        print(f"    {name}: {price:.3f} (+{diff_pct:.1f}%)")

    # 4. 建议止损价
    best_stop, all_stops = suggest_stop_loss_etf(df_security, current_price, cost_price, position_pct)

    if best_stop:
        print(f"  建议止损: {best_stop['name']} - {best_stop['price']:.3f}")
        print(f"    理由: {best_stop['reason']}")
        print(f"    亏损: {best_stop['loss_pct']:.1f}%")

    # 5. 检查技术信号
    technical_signals = check_etf_technical_signals(df_security)
    if technical_signals:
        print(f"  技术信号:")
        for signal_name, signal_info in technical_signals.items():
            if isinstance(signal_info, dict):
                formatted_info = []
                for key, value in signal_info.items():
                    if key == 'date':
                        formatted_info.append(f"日期:{value}")
                    elif key == 'volume_ratio':
                        formatted_info.append(f"量比:{value:.2f}")
                    elif key == 'price_change':
                        formatted_info.append(f"涨幅:{value:.2f}%")
                    else:
                        formatted_info.append(f"{key}:{value}")
                print(f"    ✅ {signal_name}: {', '.join(formatted_info)}")
            else:
                print(f"    ✅ {signal_name}: {signal_info}")

    # 6. 生成综合建议
    etf_info = {
        'current_price': current_price,
        'cost_price': cost_price,
        'quantity': quantity,
        'market_value': market_value,
        'total_value': total_market_value
    }

    recommendation = generate_comprehensive_recommendation_rule_first(
        etf_info, position_pct, position_status, position_signal,
        trend_info, supports, resistances, best_stop, technical_signals
    )

    print(f"\n  💡 综合投资建议:")
    print(f"    核心: {recommendation['核心信号']} - {recommendation['核心理由']}")
    print(f"    操作: {recommendation['操作建议']}")
    print(f"    信心: {recommendation['信心等级']}")

    if recommendation.get('关键理由'):
        print(f"    利好: {', '.join(recommendation['关键理由'])}")

    if recommendation.get('风险提示'):
        print(f"    风险: {', '.join(recommendation['风险提示'])}")

    if recommendation.get('仓位建议'):
        print(f"    仓位: {recommendation['仓位建议']}")

    if recommendation.get('止损建议'):
        print(f"    止损: {recommendation['止损建议']}")

    if recommendation.get('目标价位'):
        print(f"    目标: {recommendation['目标价位']}")

    # 存储结果
    result = {
        '代码': etf_code,
        '名称': etf_name,
        '类型': security_type,
        '当前价': current_price,
        '成本价': cost_price,
        '盈亏%': profit_pct,
        '市值占比%': position_ratio,
        '60日位置%': position_pct if position_pct is not None else np.nan,
        '位置状态': position_status if position_pct is not None else '未知',
        '核心信号': position_signal[0] if position_pct is not None else '未知',
        '趋势': trend,
        '站上60日线': '是' if trend_info.get('above_ma60') else '否',
        '支撑位数量': len(supports),
        '压力位数量': len(resistances),
        '技术信号': ', '.join(technical_signals.keys()) if technical_signals else '无',
        '建议止损价': best_stop['price'] if best_stop else np.nan,
        '止损亏损%': best_stop['loss_pct'] if best_stop else np.nan,
        '操作建议': recommendation['操作建议'],
        '信心等级': recommendation['信心等级'],
        '仓位建议': recommendation.get('仓位建议', '维持'),
        '状态': '分析完成'
    }

    results.append(result)

# 输出总结报告
print("\n" + "="*80)
print("📊 ETF综合技术分析总结报告（优化版）")
print("="*80)

if len(results) > 0:
    # 创建DataFrame
    results_df = pd.DataFrame(results)

    # 按核心信号和60日位置排序
    analyzed_results = [r for r in results if r['状态'] == '分析完成']
    if len(analyzed_results) > 0:
        # 先按信号排序：买入->持有->卖出->数据不足
        signal_order = {'买入信号': 0, '持有信号': 1, '卖出信号': 2, '数据不足': 3, '未知': 4}

        analyzed_results.sort(key=lambda x: (
            signal_order.get(x['核心信号'], 99),
            x['60日位置%'] if not np.isnan(x['60日位置%']) else 999
        ))

        print("\n🎯 基于60日位置规则的操作建议:")
        print("-"*80)

        for i, result in enumerate(analyzed_results, 1):
            # 信号符号
            if result['核心信号'] == '买入信号':
                signal_symbol = "🟢买入"
            elif result['核心信号'] == '卖出信号':
                signal_symbol = "🔴卖出"
            elif result['核心信号'] == '持有信号':
                signal_symbol = "🟡持有"
            else:
                signal_symbol = "⚪未知"

            # 盈亏符号
            profit_symbol = "🟢" if result['盈亏%'] >= 0 else "🔴"

            print(f"{i:2d}. {signal_symbol} {profit_symbol} {result['代码']} {result['名称']:8s}")
            print(f"     位置: {result['60日位置%']:.1f}% ({result['位置状态']})")
            print(f"     操作: {result['操作建议']} | 信心: {result['信心等级']}")
            print(f"     盈亏: {result['盈亏%']:.1f}% | 占比: {result['市值占比%']:.1f}% | 趋势: {result['趋势']:8s}")
            if not np.isnan(result.get('建议止损价', np.nan)):
                print(f"     止损: {result['建议止损价']:.3f} (-{result['止损亏损%']:.1f}%)")

    # 统计信号分布
    print("\n📈 信号分布统计:")
    print("-"*80)

    signal_counts = {}
    for result in results:
        signal = result.get('核心信号', '未知')
        signal_counts[signal] = signal_counts.get(signal, 0) + 1

    for signal, count in signal_counts.items():
        print(f"  {signal}: {count}只")

    # 仓位分析
    print("\n📊 仓位结构分析:")
    print("-"*80)

    # 检查超限持仓
    overweight_etfs = [r for r in results if r['类型'] == 'etf' and r['市值占比%'] > ETF_PARAMS['max_single_position']]
    if overweight_etfs:
        print("⚠️ 超限持仓（需减仓）:")
        for etf in overweight_etfs:
            print(f"  {etf['代码']} {etf['名称']}: {etf['市值占比%']:.1f}% > {ETF_PARAMS['max_single_position']}%")
    else:
        print("✅ 所有ETF仓位均在限制范围内")

    # 买入建议汇总
    buy_signals = [r for r in results if r['核心信号'] == '买入信号' and r['类型'] == 'etf']
    if buy_signals:
        print(f"\n🎯 买入建议（{len(buy_signals)}只）:")
        for etf in buy_signals:
            print(f"  {etf['代码']} {etf['名称']}: 位置{etf['60日位置%']:.1f}%，当前占比{etf['市值占比%']:.1f}%")

    # 卖出建议汇总
    sell_signals = [r for r in results if r['核心信号'] == '卖出信号' and r['类型'] == 'etf']
    if sell_signals:
        print(f"\n⚠️ 卖出建议（{len(sell_signals)}只）:")
        for etf in sell_signals:
            print(f"  {etf['代码']} {etf['名称']}: 位置{etf['60日位置%']:.1f}%，当前占比{etf['市值占比%']:.1f}%")

    # 保存结果
    output_file = "ETF综合技术分析结果_优化版.csv"
    results_df.to_csv(output_file, index=False, encoding='utf-8-sig')
    print(f"\n📁 分析结果已保存到: {output_file}")

else:
    print("❌ 没有持仓可以分析")

print("\n" + "="*80)
print("💡 核心分析逻辑说明（优化版）:")
print("-"*80)
print(f"1. 60日位置规则: <{ETF_PARAMS['buy_threshold']}%买入，>{ETF_PARAMS['sell_threshold']}%卖出（最高优先级）")
print(f"2. 仓位管理: 单只ETF≤{ETF_PARAMS['max_single_position']}%，保持{ETF_PARAMS['cash_reserve']}%现金")
print(f"3. ETF参数优化: MACD({ETF_PARAMS['macd_fast']},{ETF_PARAMS['macd_slow']},{ETF_PARAMS['macd_signal']})")
print(f"4. 止损策略: {ETF_PARAMS['stop_loss_range'][0]}-{ETF_PARAMS['stop_loss_range'][1]}%固定止损")
print(f"5. 放量标准: {ETF_PARAMS['volume_ratio']}倍量比（比个股宽松）")
print("6. 规则优先: 位置规则 > 技术分析 > 盈亏状态")

print("\n" + "="*80)
print("✅ 分析完成（优化版）")