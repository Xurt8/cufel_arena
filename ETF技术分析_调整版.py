#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ETF技术分析（调整版）
针对ETF特性调整技术分析参数：
1. 更长的均线周期（120日、250日）
2. 调整MACD参数适应ETF节奏
3. 结合成交量相对分析
4. 支撑压力位分析（考虑ETF特性）
"""
import pandas as pd
import numpy as np
import warnings
import sys
from datetime import datetime, timedelta
warnings.filterwarnings('ignore')

sys.stdout.reconfigure(encoding='utf-8')

print("="*80)
print("📈 ETF技术分析（调整版）")
print("分析日期: 2026年4月18日")
print("="*80)

# 用户持仓ETF列表
etf_list = [
    ('159915', '创业板', '深圳'),
    ('159934', '黄金ETF', '深圳'),
    ('159994', '5GETF', '深圳'),
    ('510880', '红利ETF', '上海'),
    ('512690', '酒ETF', '上海'),
    ('512760', '芯片ETF', '上海'),
    ('512880', '证券ETF', '上海'),
    ('516160', '新能源', '上海'),
    ('601857', '中国石油', '上海')  # 个股，但一并分析
]

# 尝试读取数据文件
data_files = [
    'stock_daily_20260415.csv',
    'ETFAgents/MyETFassistant/4.18.csv'
]

def load_etf_data(etf_code, market):
    """加载ETF历史数据"""
    # 尝试不同格式的代码
    code_formats = []

    # 深圳ETF格式
    if market == '深圳':
        code_formats.append(f"{etf_code}.SZ")
        code_formats.append(f"SZ{etf_code}")
        code_formats.append(f"sz{etf_code}")
    else:  # 上海
        code_formats.append(f"{etf_code}.SH")
        code_formats.append(f"SH{etf_code}")
        code_formats.append(f"sh{etf_code}")

    # 原始代码
    code_formats.append(etf_code)

    # 尝试从不同文件加载
    for data_file in data_files:
        try:
            print(f"  尝试从 {data_file} 加载 {etf_code}...")
            # 先检查文件是否存在
            import os
            if not os.path.exists(data_file):
                print(f"    文件不存在: {data_file}")
                continue

            # 读取文件（只读取前几行检查格式）
            try:
                df_sample = pd.read_csv(data_file, nrows=1000)
                # 检查列名
                if '股票代码' in df_sample.columns:
                    code_col = '股票代码'
                elif 'code' in df_sample.columns:
                    code_col = 'code'
                else:
                    print(f"    找不到代码列")
                    continue

                # 查找匹配的代码
                matched = False
                for code_format in code_formats:
                    matching_rows = df_sample[df_sample[code_col].astype(str).str.contains(code_format, na=False)]
                    if len(matching_rows) > 0:
                        print(f"    找到匹配: {code_format} ({len(matching_rows)}行)")
                        # 加载完整数据
                        df_full = pd.read_csv(data_file, low_memory=False)
                        df_etf = df_full[df_full[code_col].astype(str).str.contains(code_format, na=False)].copy()

                        # 标准化列名
                        column_mapping = {}
                        if '交易日期' in df_etf.columns:
                            column_mapping['交易日期'] = 'date'
                        if '股票代码' in df_etf.columns:
                            column_mapping['股票代码'] = 'code'
                        if '开盘价' in df_etf.columns:
                            column_mapping['开盘价'] = 'open'
                        if '最高价' in df_etf.columns:
                            column_mapping['最高价'] = 'high'
                        if '最低价' in df_etf.columns:
                            column_mapping['最低价'] = 'low'
                        if '收盘价' in df_etf.columns:
                            column_mapping['收盘价'] = 'close'
                        if '成交量' in df_etf.columns:
                            column_mapping['成交量'] = 'volume'
                        if '成交额' in df_etf.columns:
                            column_mapping['成交额'] = 'amount'

                        df_etf.rename(columns=column_mapping, inplace=True)

                        # 确保必要列存在
                        required_cols = ['date', 'open', 'high', 'low', 'close']
                        missing_cols = [col for col in required_cols if col not in df_etf.columns]
                        if missing_cols:
                            print(f"    缺少必要列: {missing_cols}")
                            continue

                        # 转换日期格式
                        try:
                            df_etf['date'] = pd.to_datetime(df_etf['date'], format='%Y%m%d')
                        except:
                            try:
                                df_etf['date'] = pd.to_datetime(df_etf['date'])
                            except:
                                print(f"    日期格式解析失败")
                                continue

                        # 排序
                        df_etf = df_etf.sort_values('date').reset_index(drop=True)

                        # 转换数值类型
                        numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'amount']
                        for col in numeric_cols:
                            if col in df_etf.columns:
                                df_etf[col] = pd.to_numeric(df_etf[col], errors='coerce')

                        print(f"    成功加载 {len(df_etf)} 行数据")
                        return df_etf

                if not matched:
                    print(f"    未找到匹配的代码格式")

            except Exception as e:
                print(f"    读取文件错误: {e}")
                continue

        except Exception as e:
            print(f"  文件加载异常: {e}")
            continue

    print(f"  无法加载 {etf_code} 的历史数据")
    return None

# ==================== ETF优化技术指标 ====================

def calculate_ma_etf(data, periods=[20, 60, 120, 250]):
    """计算ETF移动平均线（使用更长周期）"""
    ma_results = {}
    for period in periods:
        if len(data) >= period:
            ma_results[f'ma{period}'] = data.rolling(window=period, min_periods=1).mean()
        else:
            ma_results[f'ma{period}'] = pd.Series([np.nan] * len(data), index=data.index)
    return ma_results

def calculate_macd_etf(data, fast=15, slow=30, signal=9):
    """计算ETF MACD（调整参数适应ETF节奏）"""
    exp1 = data.ewm(span=fast, adjust=False).mean()
    exp2 = data.ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    histogram = macd - signal_line
    return macd, signal_line, histogram

def analyze_etf_trend(df_etf):
    """分析ETF趋势状态"""
    if len(df_etf) < 60:
        return "数据不足", {}

    recent_data = df_etf.tail(120).copy()

    # 计算ETF优化均线
    ma_results = calculate_ma_etf(recent_data['close'], periods=[20, 60, 120])

    current_price = recent_data.iloc[-1]['close']
    ma20 = ma_results['ma20'].iloc[-1] if 'ma20' in ma_results else np.nan
    ma60 = ma_results['ma60'].iloc[-1] if 'ma60' in ma_results else np.nan
    ma120 = ma_results['ma120'].iloc[-1] if 'ma120' in ma_results else np.nan

    # 趋势判断（ETF更注重中长期）
    if not np.isnan(ma120) and current_price > ma120:
        if ma60 > ma120 and ma20 > ma60:
            trend = "强势上升"
        elif current_price > ma60:
            trend = "上升趋势"
        else:
            trend = "震荡偏强"
    elif not np.isnan(ma120) and current_price < ma120:
        if ma60 < ma120 and ma20 < ma60:
            trend = "强势下降"
        elif current_price < ma60:
            trend = "下降趋势"
        else:
            trend = "震荡偏弱"
    else:
        trend = "横盘震荡"

    # 位置分析
    half_year_high = recent_data['high'].max()
    half_year_low = recent_data['low'].min()
    position = (current_price - half_year_low) / (half_year_high - half_year_low) * 100 if half_year_high != half_year_low else 50

    if position > 80:
        phase = "历史高位"
    elif position > 60:
        phase = "相对高位"
    elif position > 40:
        phase = "中位区域"
    elif position > 20:
        phase = "相对低位"
    else:
        phase = "历史低位"

    # 波动率（ETF通常波动较小）
    volatility = recent_data['close'].pct_change().std() * np.sqrt(252) * 100  # 年化波动率

    return trend, {
        'trend': trend,
        'phase': phase,
        'position': position,
        'volatility': volatility,
        'current_price': current_price,
        'ma20': ma20,
        'ma60': ma60,
        'ma120': ma120,
        'half_year_high': half_year_high,
        'half_year_low': half_year_low
    }

def calculate_etf_support_resistance(df_etf):
    """计算ETF支撑位和压力位"""
    if len(df_etf) < 60:
        return {}, {}

    recent_data = df_etf.tail(180).copy()  # ETF使用更长周期

    supports = {}
    resistances = {}

    # 1. 均线支撑（ETF更重视中长期均线）
    ma_results = calculate_ma_etf(recent_data['close'], periods=[60, 120, 250])
    for period in [60, 120]:
        key = f'ma{period}'
        if key in ma_results:
            supports[f'{period}日均线'] = ma_results[key].iloc[-1]

    # 2. 近期低点支撑
    recent_lows = recent_data.tail(40)['low'].sort_values().head(3).values
    for i, low in enumerate(recent_lows[:2], 1):
        supports[f'近期低点{i}'] = low

    # 3. 前期平台支撑（简化）
    # 查找成交密集区
    price_bins = pd.cut(recent_data['close'], bins=8)
    if 'volume' in recent_data.columns:
        volume_by_price = recent_data.groupby(price_bins)['volume'].sum()
        if len(volume_by_price) > 0:
            max_volume_bin = volume_by_price.idxmax()
            if hasattr(max_volume_bin, 'mid'):
                supports['成交密集区'] = max_volume_bin.mid

    # 压力位
    # 1. 近期高点压力
    recent_highs = recent_data.tail(40)['high'].sort_values(ascending=False).head(3).values
    for i, high in enumerate(recent_highs[:2], 1):
        resistances[f'近期高点{i}'] = high

    # 2. 前期高点压力
    for i in range(len(recent_data)-60, len(recent_data)-20, 10):
        window = recent_data.iloc[i-10:i+10]
        if recent_data.iloc[i]['high'] == window['high'].max():
            resistances[f'前期高点{i}'] = recent_data.iloc[i]['high']
            break

    # 3. 整数关口压力（ETF常见）
    current_price = recent_data.iloc[-1]['close']
    for level in [round(current_price) + 0.1, round(current_price) + 0.2, round(current_price) + 0.5]:
        if level > current_price:
            resistances[f'整数关口{level}'] = level
            break

    return supports, resistances

def generate_etf_recommendation(df_etf, etf_name, current_price):
    """生成ETF投资建议"""
    if df_etf is None or len(df_etf) < 60:
        return "数据不足，无法分析", {}

    # 分析趋势
    trend, trend_info = analyze_etf_trend(df_etf)

    # 计算支撑压力
    supports, resistances = calculate_etf_support_resistance(df_etf)

    # 技术评分
    score = 0
    reasons = []

    # 1. 趋势评分
    if trend in ["强势上升", "上升趋势"]:
        score += 30
        reasons.append("上升趋势")
    elif trend == "震荡偏强":
        score += 20
        reasons.append("震荡偏强")
    elif trend == "横盘震荡":
        score += 10
        reasons.append("横盘震荡")

    # 2. 位置评分（ETF适合在相对低位买入）
    position = trend_info.get('position', 50)
    if position < 30:
        score += 25
        reasons.append("历史低位")
    elif position < 50:
        score += 20
        reasons.append("相对低位")
    elif position < 70:
        score += 10
        reasons.append("中位区域")

    # 3. 均线排列评分
    ma20 = trend_info.get('ma20', np.nan)
    ma60 = trend_info.get('ma60', np.nan)
    ma120 = trend_info.get('ma120', np.nan)

    if not np.isnan(ma120) and current_price > ma120:
        score += 20
        reasons.append("站上120日线")
    elif not np.isnan(ma60) and current_price > ma60:
        score += 15
        reasons.append("站上60日线")
    elif not np.isnan(ma20) and current_price > ma20:
        score += 10
        reasons.append("站上20日线")

    # 4. 支撑位数量
    support_count = len(supports)
    if support_count >= 3:
        score += 15
        reasons.append("多重支撑")
    elif support_count >= 2:
        score += 10
        reasons.append("支撑较强")

    # 5. 波动率评分（ETF偏好低波动）
    volatility = trend_info.get('volatility', 30)
    if volatility < 20:
        score += 10
        reasons.append("低波动")
    elif volatility < 30:
        score += 5
        reasons.append("适中波动")

    # 总体评价
    if score >= 70:
        rating = "强烈推荐"
        action = "买入"
    elif score >= 50:
        rating = "推荐"
        action = "买入或持有"
    elif score >= 30:
        rating = "中性"
        action = "持有或观望"
    else:
        rating = "谨慎"
        action = "观望或卖出"

    # 止损建议（ETF止损幅度较小）
    stop_loss = None
    if supports:
        important_support = min(supports.values())
        stop_loss_pct = (current_price - important_support) / current_price * 100
        if stop_loss_pct <= 10:  # ETF止损建议5-10%
            stop_loss = important_support

    # 目标价位
    target = None
    if resistances:
        nearest_resistance = min(resistances.values(), key=lambda x: abs(x - current_price) if x > current_price else float('inf'))
        if nearest_resistance > current_price:
            target = nearest_resistance

    recommendation = {
        'rating': rating,
        'action': action,
        'score': score,
        'trend': trend,
        'phase': trend_info.get('phase', '未知'),
        'position': position,
        'stop_loss': stop_loss,
        'target': target,
        'reasons': reasons,
        'support_count': len(supports),
        'resistance_count': len(resistances)
    }

    return recommendation

# ==================== 主分析流程 ====================

print("\n🔍 开始ETF技术分析...")
print("="*80)

results = []

for etf_code, etf_name, market in etf_list:
    print(f"\n{'='*60}")
    print(f"📊 分析: {etf_name} ({etf_code})")
    print(f"{'='*60}")

    # 加载数据
    df_etf = load_etf_data(etf_code, market)

    if df_etf is None or len(df_etf) < 60:
        print(f"  ⚠️ 数据不足，跳过深度分析")
        results.append({
            '代码': etf_code,
            '名称': etf_name,
            '状态': '数据不足',
            '评分': 0,
            '评级': '无法分析'
        })
        continue

    print(f"  数据天数: {len(df_etf)}")
    print(f"  日期范围: {df_etf['date'].min().date()} 到 {df_etf['date'].max().date()}")

    # 当前价格
    current_price = df_etf.iloc[-1]['close']
    print(f"  当前价格: {current_price:.3f}")

    # 生成投资建议
    recommendation = generate_etf_recommendation(df_etf, etf_name, current_price)

    print(f"\n  📈 技术分析结果:")
    print(f"    趋势: {recommendation['trend']}")
    print(f"    位置: {recommendation['phase']} ({recommendation['position']:.1f}%)")
    print(f"    评分: {recommendation['score']}/100")
    print(f"    评级: {recommendation['rating']}")
    print(f"    建议: {recommendation['action']}")

    if recommendation['stop_loss']:
        stop_loss_pct = (current_price - recommendation['stop_loss']) / current_price * 100
        print(f"    止损: {recommendation['stop_loss']:.3f} (-{stop_loss_pct:.1f}%)")

    if recommendation['target']:
        target_return = (recommendation['target'] - current_price) / current_price * 100
        print(f"    目标: {recommendation['target']:.3f} (+{target_return:.1f}%)")

    print(f"    理由: {', '.join(recommendation['reasons'])}")

    # 存储结果
    results.append({
        '代码': etf_code,
        '名称': etf_name,
        '当前价': current_price,
        '趋势': recommendation['trend'],
        '位置': recommendation['phase'],
        '位置百分比': recommendation['position'],
        '评分': recommendation['score'],
        '评级': recommendation['rating'],
        '建议': recommendation['action'],
        '止损价': recommendation.get('stop_loss', np.nan),
        '目标价': recommendation.get('target', np.nan),
        '支撑位数量': recommendation['support_count'],
        '压力位数量': recommendation['resistance_count'],
        '状态': '分析完成'
    })

# 输出总结报告
print("\n" + "="*80)
print("📊 ETF技术分析总结报告")
print("="*80)

if len(results) > 0:
    results_df = pd.DataFrame(results)

    print("\n所有ETF分析结果:")
    print("-"*80)

    # 按评分排序
    analyzed_results = [r for r in results if r['状态'] == '分析完成']
    if len(analyzed_results) > 0:
        analyzed_results.sort(key=lambda x: x['评分'], reverse=True)

        print("推荐顺序（按评分从高到低）:")
        print("-"*80)
        for i, result in enumerate(analyzed_results, 1):
            rating_symbol = "🟢" if result['评分'] >= 70 else "🟡" if result['评分'] >= 50 else "🔴"
            print(f"{i:2d}. {rating_symbol} {result['代码']} {result['名称']:8s}")
            print(f"     评分: {result['评分']} | 趋势: {result['趋势']:10s} | 位置: {result['位置']:8s}")
            print(f"     建议: {result['建议']} | 当前价: {result['当前价']:.3f}")
            if not np.isnan(result['止损价']):
                print(f"     止损: {result['止损价']:.3f}")

    # 数据不足的ETF
    insufficient_results = [r for r in results if r['状态'] == '数据不足']
    if len(insufficient_results) > 0:
        print("\n⚠️ 数据不足无法分析的ETF:")
        print("-"*80)
        for result in insufficient_results:
            print(f"  {result['代码']} {result['名称']:8s}: 需要更多历史数据")

    # 保存结果
    output_file = "ETF技术分析结果.csv"
    results_df.to_csv(output_file, index=False, encoding='utf-8-sig')
    print(f"\n📁 分析结果已保存到: {output_file}")

else:
    print("❌ 没有ETF可以分析")

print("\n" + "="*80)
print("💡 ETF投资建议总结:")
print("-"*80)
print("1. ETF技术分析注重中长期趋势和位置")
print("2. 建议在相对低位、多重支撑时买入")
print("3. ETF止损幅度建议5-10%，比个股更严格")
print("4. 关注行业ETF与对应板块的关联性")
print("5. 宽基ETF适合长期持有，行业ETF适合波段操作")

print("\n" + "="*80)
print("分析完成")