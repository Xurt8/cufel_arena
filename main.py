#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
cufel_arena 主程序入口
运行宏观驱动ETF策略
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

from ETFAgents.MacroDrivenETF.macro_driven_etf_agent import MacroDrivenETFAgent

if __name__ == "__main__":
    # 初始化策略 (use_llm=False 使用规则引擎)
    print("初始化宏观驱动ETF策略...")
    agent = MacroDrivenETFAgent(use_llm=False)

    # 测试数据加载
    print("\n[1] 测试数据加载...")
    data_info = agent.load_current_data('2024-03-31')
    print(f"数据可用: {data_info.get('data_available')}")
    print(f"日期: {data_info.get('date')}")

    # 测试持仓获取
    print("\n[2] 测试持仓获取...")
    holdings = agent.get_current_holdings('2024-03-31')
    print(f"持仓: {holdings}")

    # 测试风险偏好调整
    print("\n[3] 测试风险偏好调整 (theta=0.7)...")
    holdings_adj = agent.get_current_holdings('2024-03-31', theta=0.7)
    print(f"调整后持仓: {holdings_adj}")

    print("\n✅ 策略测试完成!")