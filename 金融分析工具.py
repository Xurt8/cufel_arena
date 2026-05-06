#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
金融分析工具 - 基于akshare免费数据源
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import pandas as pd
import os
from datetime import datetime, timedelta

# 本地数据库路径
DB_PATH = 'ETFAgents/MacroDrivenETF/data/etf_day_with_basic_2022_2025.csv'

class FinanceTools:
    """金融分析工具集"""

    def __init__(self):
        self.db_path = DB_PATH

    def load_etf_db(self):
        """加载本地ETF数据库"""
        if os.path.exists(self.db_path):
            return pd.read_csv(self.db_path, encoding='utf-8', low_memory=False)
        return None

    def get_latest_price(self, symbol):
        """获取最新价格"""
        try:
            import akshare as ak
            df = ak.stock_zh_a_hist(symbol=symbol, period='daily',
                                   start_date=(datetime.now()-timedelta(days=7)).strftime('%Y%m%d'),
                                   end_date=datetime.now().strftime('%Y%m%d'))
            if len(df) > 0:
                return df.iloc[-1]
        except Exception as e:
            print(f"获取{symbol}失败: {e}")
        return None

    def get_realtime_quote(self, symbol):
        """获取实时行情"""
        try:
            import akshare as ak
            df = ak.stock_zh_a_spot_em()
            return df[df['代码'] == symbol]
        except:
            return None

    def get_etf_spot(self):
        """获取ETF实时行情"""
        try:
            import akshare as ak
            return ak.fund_etf_spot_em()
        except Exception as e:
            print(f"获取ETF行情失败: {e}")
            return None

    def get_fund_flow(self, symbol):
        """获取主力资金流向"""
        try:
            import akshare as ak
            return ak.stock_individual_fund_flow(stock=symbol, market='sh')
        except:
            return None

    def get_index_components(self, index_code):
        """获取指数成分股"""
        try:
            import akshare as ak
            if index_code == '000300':  # 沪深300
                return ak.index_stock_cons_csindex(symbol='000300')
            elif index_code == '399006':  # 创业板
                return ak.index_stock_cons_zh(index_code)
        except:
            return None

    def get_market_heatmap(self):
        """获取行业热点"""
        try:
            import akshare as ak
            return ak.stock_board_industry_name_em()
        except:
            return None


def main():
    tools = FinanceTools()

    print("="*60)
    print("金融分析工具")
    print("="*60)
    print("""
功能:
  1. 查看ETF实时行情
  2. 获取个股最新价格
  3. 查询主力资金流向
  4. 查看市场热点板块
  5. 分析持仓ETF状态
  0. 退出
    """)

    while True:
        choice = input("选择功能: ").strip()

        if choice == "1":
            print("\n获取ETF实时行情...")
            df = tools.get_etf_spot()
            if df is not None:
                print(df.head(10)[['代码', '名称', '最新价', '涨跌幅']].to_string())

        elif choice == "2":
            symbol = input("输入股票/ETF代码: ").strip()
            price = tools.get_latest_price(symbol)
            if price is not None:
                print(f"日期: {price['日期']}, 收盘: {price['收盘']}, 涨跌幅: {price['涨跌幅']}%")

        elif choice == "3":
            symbol = input("输入股票代码: ").strip()
            flow = tools.get_fund_flow(symbol)
            if flow is not None:
                print(flow.to_string())

        elif choice == "4":
            print("\n市场热点板块:")
            heat = tools.get_market_heatmap()
            if heat is not None:
                print(heat.head(20).to_string())

        elif choice == "5":
            print("\n分析本地数据库持仓...")
            df = tools.load_etf_db()
            if df is not None:
                latest_date = df['交易日期'].max()
                print(f"最新日期: {latest_date}")
                print(f"总记录: {len(df)}")

        elif choice == "0":
            break


if __name__ == "__main__":
    main()