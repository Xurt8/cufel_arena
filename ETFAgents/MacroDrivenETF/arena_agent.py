"""
Arena Agent - cufel_arena_agent 封装
将 MacroDrivenETF 策略封装为 ETFAgentBase 子类
"""

import os
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from dotenv import load_dotenv
from pydantic import BaseModel

# 尝试导入 cufel_arena_agent
try:
    from cufel_arena_agent import ETFAgentBase
    _CUFEL_AVAILABLE = True
except ImportError:
    _CUFEL_AVAILABLE = False
    # 本地测试用基础类
    class ETFAgentBase:
        def __init__(self, name="ETFAgent", **kwargs):
            self.name = name


# 导入三个 Agent
from data_agent import DataAgent, MacroData
from macro_agent import MacroAgent
from portfolio_agent import PortfolioAgent


# ==================== ArenaETFAgent ====================

class MacroDrivenETFAgent(ETFAgentBase):
    """
    宏观驱动ETF策略 Agent
    继承 ETFAgentBase，实现 cufel_arena 竞赛接口
    """

    def __init__(self, use_llm: bool = False, **kwargs):
        """
        初始化 MacroDrivenETFAgent

        Args:
            use_llm: 是否使用 LLM 分析，False 时使用规则兜底
            data_path: 数据目录路径
            cache_path: 缓存目录路径
        """
        # 获取路径配置
        _THIS_DIR = os.path.dirname(os.path.abspath(__file__))

        # 加载环境变量
        load_dotenv(os.path.join(_THIS_DIR, ".env"))

        # 数据库配置
        db_config = {
            'host': os.getenv('CHDB_HOST'),
            'port': int(os.getenv('CHDB_PORT', 20108)),
            'user': os.getenv('CHDB_USER'),
            'password': os.getenv('CHDB_PASSWORD'),
            'database': os.getenv('CHDB_DATABASE', 'etf')
        }

        # 调用父类初始化
        super().__init__(name="MacroDrivenETFStrategy", db_config=db_config, **kwargs)

        # 数据路径
        data_path = kwargs.get('data_path', os.path.join(_THIS_DIR, "data"))
        cache_path = kwargs.get('cache_path', os.path.join(_THIS_DIR, "cache"))

        # 初始化 Agents
        print("[INFO] Initializing DataAgent...")
        self.data_agent = DataAgent(data_path)
        self.data_agent.load_all_data()

        print("[INFO] Initializing MacroAgent...")
        self.macro_agent = MacroAgent(use_llm=use_llm)

        print("[INFO] Initializing PortfolioAgent...")
        self.portfolio_agent = PortfolioAgent()

        # 缓存路径
        self.cache_path = Path(cache_path)

        print("[OK] MacroDrivenETFAgent initialized")

    def load_current_data(self, curr_date: str) -> dict:
        """
        加载当前日期所需要的数据
        cufel_arena 接口
        """
        try:
            # 尝试从数据库加载ETF数据
            if _CUFEL_AVAILABLE:
                from quantchdb import ClickHouseDatabase
                db = ClickHouseDatabase(config=self.db_config, terminal_log=False)
                sql = f'''
                    SELECT code
                    FROM etf.etf_day
                    WHERE date = '{curr_date}'
                    ORDER BY date DESC
                    LIMIT 20
                '''
                df = db.fetch(sql)
                available_codes = df['code'].tolist() if len(df) > 0 else []
            else:
                available_codes = []

            return {
                "data_available": True,
                "date": curr_date,
                "available_codes": available_codes
            }
        except Exception as e:
            return {
                "data_available": False,
                "date": curr_date,
                "error": str(e)
            }

    def get_current_holdings(self, curr_date: str, feedback: str = None, theta: float = None) -> dict:
        """
        获取当前日期的持仓
        cufel_arena 接口

        Parameters
        ----------
        curr_date : str
            当前日期，格式为 'YYYY-MM-DD'
        feedback : str, optional
            来自 FOF Agent 的反馈信息
        theta : float, optional
            风险偏好系数

        Returns
        -------
        dict
            持仓字典 {curr_date: {code: weight, ...}}
        """
        # 检查缓存
        cache_file = self.cache_path / f"holdings_{curr_date}.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    cached = json.load(f)
                    if theta is not None and theta != 1.0:
                        return self._adjust_holdings_theta(cached, theta)
                    return cached
            except:
                pass

        # 解析日期
        try:
            date_obj = datetime.strptime(curr_date, "%Y-%m-%d")
        except:
            date_obj = datetime.strptime(curr_date, "%Y%m%d")

        # 获取宏观数据
        macro_data = self.data_agent.get_macro_for_decision(date_obj)

        # 宏观分析
        macro_analysis = self.macro_agent.analyze(macro_data)
        macro_analysis["metadata"]["input_date"] = curr_date

        # 组合决策
        decision = self.portfolio_agent.decide(macro_analysis)

        # 转换为持仓格式
        portfolio = decision["portfolio"]
        holdings = {curr_date: {}}

        for code, info in portfolio.items():
            holdings[curr_date][code] = info["weight"]

        # 验证权重
        total = sum(holdings[curr_date].values())
        if abs(total - 1.0) > 1e-6:
            print(f"[WARNING] Holdings weight sum = {total}, normalizing...")
            holdings[curr_date] = {k: round(v / total, 4) for k, v in holdings[curr_date].items()}

        # 保存缓存
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_file, 'w') as f:
                json.dump(holdings, f)
        except:
            pass

        # 应用风险偏好调整
        if theta is not None and theta != 1.0:
            holdings = self._adjust_holdings_theta(holdings, theta)

        return holdings

    def get_current_holdings_intraday(self, curr_datetime: str, feedback: str = None, theta: float = None) -> dict:
        """
        获取当前时间点的盘中持仓
        cufel_arena 接口
        """
        # 提取日期部分，使用日频持仓
        date_str = curr_datetime.split(" ")[0]
        return self.get_current_holdings(date_str, feedback=feedback, theta=theta)

    def _adjust_holdings_theta(self, holdings: dict, theta: float) -> dict:
        """根据风险偏好调整持仓"""
        curr_date = list(holdings.keys())[0]
        weights = holdings[curr_date]

        # theta 越低越保守，减少股票仓位
        if theta < 1.0:
            stock_codes = ["510300", "510500"]
            bond_codes = ["511010", "511220"]

            stock_total = sum(weights.get(c, 0) for c in stock_codes)
            bond_total = sum(weights.get(c, 0) for c in bond_codes)

            adjust_factor = theta

            new_weights = {}
            for code, weight in weights.items():
                if code in stock_codes:
                    new_weights[code] = round(weight * adjust_factor, 4)
                elif code in bond_codes:
                    new_weights[code] = round(weight + stock_total * (1 - adjust_factor) / len(bond_codes), 4)
                else:
                    new_weights[code] = weight

            # 归一化
            total = sum(new_weights.values())
            new_weights = {k: round(v / total, 4) for k, v in new_weights.items()}

            holdings[curr_date] = new_weights

        return holdings

    def run_backtest(self, start_date: str, end_date: str, price_data=None):
        """
        运行回测

        Args:
            start_date: 开始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD
            price_data: 价格数据 DataFrame，可选
        """
        from datetime import datetime as dt
        from backtest import BacktestEngine
        from workflow import AgenticPortfolioWorkflow

        # 创建工作流
        workflow = AgenticPortfolioWorkflow(
            self.data_agent,
            self.macro_agent,
            self.portfolio_agent
        )

        # 创建回测引擎
        engine = BacktestEngine(workflow)

        # 运行回测
        start = dt.strptime(start_date, "%Y-%m-%d")
        end = dt.strptime(end_date, "%Y-%m-%d")

        data_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        return engine.run(start, end, data_path)


# ==================== 测试代码 ====================

if __name__ == "__main__":
    # 测试 Agent
    print("[TEST] Testing MacroDrivenETFAgent...")

    agent = MacroDrivenETFAgent(use_llm=False)

    # 测试数据加载
    data_info = agent.load_current_data('2024-03-31')
    print("Data available:", data_info.get('data_available'))

    # 测试持仓获取
    holdings = agent.get_current_holdings('2024-03-31')
    print("Holdings:", holdings)

    # 测试风险偏好调整
    holdings_adj = agent.get_current_holdings('2024-03-31', theta=0.7)
    print("Adjusted holdings (theta=0.7):", holdings_adj)
