#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
股票数据读取模块
从本地Tushare数据中读取股票历史数据
"""
import json
import os

DATA_FILE = os.path.join(os.path.dirname(__file__), 'data', 'stock_daily.json')

def load_stock_data(code=None, start_date=None, end_date=None):
    """
    读取股票数据

    Args:
        code: 股票代码 (如 '600299.SH')
        start_date: 开始日期 (如 '20260319')
        end_date: 结束日期 (如 '20260415')

    Returns:
        dict or list: 指定股票数据或所有股票数据
    """
    if not os.path.exists(DATA_FILE):
        print(f"数据文件不存在: {DATA_FILE}")
        return None

    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if code:
        # 返回指定股票
        result = data.get(code, {})
        if start_date or end_date:
            filtered = {}
            for date, values in result.items():
                if start_date and date < start_date:
                    continue
                if end_date and date > end_date:
                    continue
                filtered[date] = values
            return filtered
        return result

    return data

def get_stock_price(code, date=None):
    """获取指定日期的股票价格"""
    data = load_stock_data(code)
    if not data:
        return None

    if date:
        return data.get(date, {}).get('close')

    # 返回最新价格
    dates = sorted(data.keys())
    if dates:
        return data[dates[-1]].get('close')
    return None

def get_stock_history(code, days=60):
    """获取股票历史走势"""
    data = load_stock_data(code)
    if not data:
        return []

    dates = sorted(data.keys())[-days:]
    return [{'date': d, 'close': data[d]['close']} for d in dates]

if __name__ == '__main__':
    # 测试
    print("=== 股票数据查询测试 ===")

    # 查询安迪苏
    print("\n1. 安迪苏(600299.SH)最新价格:")
    print(f"   {get_stock_price('600299.SH')}")

    print("\n2. 安迪苏60日走势:")
    history = get_stock_history('600299.SH', 60)
    for h in history[-5:]:
        print(f"   {h['date']}: {h['close']}")

    print("\n3. 查询新宝股份(002705.SZ):")
    print(f"   {load_stock_data('002705.SZ', end_date='20260415')}")