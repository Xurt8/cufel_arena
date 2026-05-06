#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
每日股票数据更新脚本
从长城证券本地数据更新到SQLite数据库
建议运行时间: 每天15:30之后
"""

import struct
import sqlite3
import os
from datetime import datetime

# 配置
DB_PATH = os.path.join(os.path.dirname(__file__), 'stocks.db')
DATA_DIR = r'C:\zd_cczq\vipdoc'

def get_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 创建表(如果不存在)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stock_daily (
            code TEXT,
            date INTEGER,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL,
            amount REAL,
            updated_at TEXT,
            PRIMARY KEY (code, date)
        )
    ''')
    conn.commit()
    return conn, cursor

def parse_day_file(filepath, code):
    """解析通达信.day文件"""
    records = []

    with open(filepath, 'rb') as f:
        data = f.read()

    if len(data) < 32:
        return records

    record_size = 32
    updated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    for i in range(len(data) // record_size):
        pos = i * record_size
        rec = data[pos:pos+record_size]

        try:
            date_val = struct.unpack('<I', rec[0:4])[0]
            if date_val < 19900101 or date_val > 20301231:
                continue

            # 价格除以100
            open_p = struct.unpack('<I', rec[4:8])[0] / 100.0
            high = struct.unpack('<I', rec[8:12])[0] / 100.0
            low = struct.unpack('<I', rec[12:16])[0] / 100.0
            close = struct.unpack('<I', rec[16:20])[0] / 100.0
            volume = float(struct.unpack('<I', rec[20:24])[0])
            amount = float(struct.unpack('<Q', rec[24:32])[0])

            records.append((code, date_val, open_p, high, low, close, volume, amount, updated_at))
        except:
            continue

    return records

def update_all():
    """更新所有数据"""
    print(f'开始更新: {datetime.now()}')

    conn, cursor = get_connection()

    total_count = 0
    dirs = [
        os.path.join(DATA_DIR, 'vipdoc/sz/lday'),
        os.path.join(DATA_DIR, 'vipdoc/sh/lday'),
        os.path.join(DATA_DIR, 'vipdoc/bj/lday'),
    ]

    for lday_dir in dirs:
        if not os.path.exists(lday_dir):
            print(f'跳过: {lday_dir} 不存在')
            continue

        day_files = [f for f in os.listdir(lday_dir) if f.endswith('.day')]
        print(f'处理 {lday_dir}: {len(day_files)} 个文件')

        count = 0
        for day_file in day_files:
            code = day_file.replace('.day', '').upper()
            filepath = os.path.join(lday_dir, day_file)

            records = parse_day_file(filepath, code)

            if records:
                cursor.executemany('''
                    INSERT OR REPLACE INTO stock_daily
                    (code, date, open, high, low, close, volume, amount, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', records)
                count += len(records)

        print(f'  导入 {count} 条')
        total_count += count

    conn.commit()

    # 统计
    cursor.execute('SELECT COUNT(*) FROM stock_daily')
    total = cursor.fetchone()[0]

    cursor.execute('SELECT code, COUNT(*) FROM stock_daily GROUP BY code ORDER BY COUNT(*) DESC LIMIT 5')
    top_stocks = cursor.fetchall()

    cursor.execute('SELECT MIN(date), MAX(date) FROM stock_daily')
    date_range = cursor.fetchone()

    print(f'\\n===== 更新完成 =====')
    print(f'总记录: {total}')
    print(f'日期范围: {date_range[0]} ~ {date_range[1]}')
    print(f'数据目录: {DB_PATH}')

    conn.close()
    print(f'完成: {datetime.now()}')

if __name__ == '__main__':
    update_all()