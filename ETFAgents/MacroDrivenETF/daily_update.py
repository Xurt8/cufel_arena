#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
每日股票数据自动更新脚本
交易日下午3:30自动执行
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import os
os.environ['TUSHARE_TOKEN'] = '1b7d8361af2340efcd7638f97f33c17a3aab9df5c427a968db4c94d8'

import tushare as ts
import pandas as pd
from datetime import datetime, timedelta
import json
import shutil

# 配置
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
CSV_FILE = os.path.join(DATA_DIR, 'stock_daily_all.csv')
JSON_FILE = os.path.join(DATA_DIR, 'stock_daily.json')

def get_latest_trade_date():
    """获取最近交易日期"""
    today = datetime.now()

    # 如果当前时间在15:30之前，今天可能有数据
    if today.hour < 15 or (today.hour == 15 and today.minute < 30):
        # 用昨天
        for i in range(1, 10):
            d = today - timedelta(days=i)
            if d.weekday() < 5:
                return d.strftime('%Y%m%d')

    # 否则用今天
    if today.weekday() < 5:
        return today.strftime('%Y%m%d')

    # 找到下一个交易日
    for i in range(1, 10):
        d = today - timedelta(days=i)
        if d.weekday() < 5:
            return d.strftime('%Y%m%d')

    return datetime.now().strftime('%Y%m%d')

def fetch_daily_data(trade_date):
    """获取单日数据"""
    pro = ts.pro_api()
    df = pro.daily(trade_date=trade_date)
    if df is not None:
        df['trade_date'] = trade_date
    return df

def update_data():
    """更新数据"""
    print(f"=== 每日数据更新 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")

    # 获取最新交易日
    trade_date = get_latest_trade_date()
    print(f"目标日期: {trade_date}")

    # 获取当日数据
    print(f"获取数据...")
    df = fetch_daily_data(trade_date)
    if df is None or len(df) == 0:
        print("未获取到数据，可能还未收盘")
        return False

    print(f"获取 {len(df)} 条数据")

    # 合并现有数据
    existing = {}
    if os.path.exists(JSON_FILE):
        print("合并现有数据...")
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            existing = json.load(f)

    # 合并新数据
    for _, row in df.iterrows():
        code = row['ts_code']
        if code not in existing:
            existing[code] = {}
        existing[code][trade_date] = {
            'open': round(row['open'], 2),
            'high': round(row['high'], 2),
            'low': round(row['low'], 2),
            'close': round(row['close'], 2),
            'vol': round(row['vol'], 2),
            'amount': round(row['amount'], 2)
        }

    # 保存JSON
    print(f"保存JSON...")
    with open(JSON_FILE, 'w', encoding='utf-8') as f:
        json.dump(existing, f, ensure_ascii=False)

    # 保存CSV
    print(f"保存CSV...")
    all_data = []
    for code, dates in existing.items():
        for date, values in dates.items():
            row = {'ts_code': code, 'trade_date': date}
            row.update(values)
            all_data.append(row)

    df_all = pd.DataFrame(all_data)
    df_all = df_all.sort_values(['trade_date', 'ts_code'])
    df_all.to_csv(CSV_FILE, index=False, encoding='utf-8')

    print(f"\n✓ 更新完成!")
    print(f"  股票数量: {len(existing)}")
    print(f"  数据日期: {trade_date}")

    return True

if __name__ == '__main__':
    # 直接运行
    update_data()