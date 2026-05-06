"""
Backtest - 回测引擎模块
使用 GeneralBacktest 包对 AgenticPortfolio 策略进行专业回测
"""

import os
import sys
from typing import Tuple

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import matplotlib
matplotlib.use('Agg')   # 无GUI环境兼容
import matplotlib.pyplot as plt

from GeneralBacktest import GeneralBacktest
from workflow import AgenticPortfolioWorkflow
from data_agent import DataAgent
from macro_agent import MacroAgent
from portfolio_agent import PortfolioAgent


# ==================== BacktestEngine 类 ====================

class BacktestEngine:
    """回测引擎"""

    def __init__(
        self,
        workflow: AgenticPortfolioWorkflow,
        transaction_cost: float = 0.001,
        rebalance_threshold: float = 0.005,
        slippage: float = 0.0005,
        db_config: dict = None
    ):
        """
        初始化回测引擎

        Args:
            workflow: AgenticPortfolioWorkflow 实例
            transaction_cost: 交易成本（双边万分之十 = 0.001）
            rebalance_threshold: 调仓阈值（0.5% = 0.005）
            slippage: 滑点（0.05% = 0.0005）
            db_config: 数据库配置 dict，若提供则使用数据库回测
        """
        self.workflow = workflow
        self.transaction_cost = transaction_cost
        self.rebalance_threshold = rebalance_threshold
        self.slippage = slippage
        self.db_config = db_config

    def generate_rebalance_dates(self, start: datetime, end: datetime) -> list:
        """
        生成月末调仓日期列表

        例如：2022-01-31, 2022-02-28, 2022-03-31, ..., 2024-12-31
        """
        dates = []
        current = start

        while current <= end:
            # 计算当月最后一天
            if current.month == 12:
                month_end = datetime(current.year + 1, 1, 1) - timedelta(days=1)
            else:
                month_end = datetime(current.year, current.month + 1, 1) - timedelta(days=1)

            if month_end <= end:
                dates.append(month_end)

            # 移动到下月
            if current.month == 12:
                current = datetime(current.year + 1, 1, 1)
            else:
                current = datetime(current.year, current.month + 1, 1)

        return dates

    def collect_weights(self, start: datetime, end: datetime, data_path: str) -> pd.DataFrame:
        """
        收集所有调仓日期的目标权重

        Returns:
            weights_data: DataFrame with columns [date, code, weight, cycle_phase, confidence]
        """
        print("=" * 60)
        print(f"[INFO] 开始收集权重数据: {start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}")
        print("=" * 60)

        # 生成调仓日期
        rebalance_dates = self.generate_rebalance_dates(start, end)
        print(f"调仓次数: {len(rebalance_dates)}次\n")

        weights_list = []

        for i, date in enumerate(rebalance_dates, 1):
            print(f"{'-'*60}")
            print(f"调仓 {i}/{len(rebalance_dates)}: {date.strftime('%Y-%m-%d')}")
            print(f"{'-'*60}")

            # 运行工作流获取决策
            result = self.workflow.run(date)

            if result.get("error") or not result.get("portfolio_decision"):
                print(f"[WARN] 警告: {date.strftime('%Y-%m-%d')} 无有效决策，跳过")
                continue

            portfolio_decision = result["portfolio_decision"]
            portfolio = portfolio_decision["portfolio"]
            cycle_phase = portfolio_decision["cycle_phase"]
            confidence = portfolio_decision["confidence"]

            # 记录权重
            for code, info in portfolio.items():
                weights_list.append({
                    "date": date,
                    "code": code,
                    "weight": info["weight"],
                    "cycle_phase": cycle_phase,
                    "confidence": confidence
                })

        print("\n" + "=" * 60)
        print("[OK] 权重收集完成")
        print("=" * 60)

        return pd.DataFrame(weights_list)

    # ETF 代码映射：策略代码 -> CSV中的代码
    ETF_CODE_MAPPING = {
        "510300": "159300",  # 沪深300ETF
        "511010": "511010",  # 国债ETF (直接匹配)
        "511220": "511220",  # 城投债ETF (直接匹配)
        "518880": "518880",  # 黄金ETF (直接匹配)
    }

    def _load_price_data(self, data_path: str) -> pd.DataFrame:
        """
        从本地文件加载价格数据

        重要：etf_day.csv 含 UTF-8 BOM，必须用 encoding="utf-8-sig" 读取
        """
        # 尝试多个可能的文件名
        possible_names = [
            "etf_day_with_basic_2022_2025.csv",
            "etf_day.csv",
            "etf_day_with_basic.csv"
        ]

        etf_file = None
        for name in possible_names:
            file_path = os.path.join(data_path, name)
            if os.path.exists(file_path):
                etf_file = file_path
                break

        if etf_file is None:
            raise FileNotFoundError(f"未找到 ETF 价格数据文件，尝试的文件: {possible_names}")

        print(f"[INFO] 加载价格数据: {etf_file}")

        # 读取数据（注意 encoding="utf-8-sig"）
        df = pd.read_csv(etf_file, encoding="utf-8-sig")

        # 列名映射（根据实际文件调整）
        column_mapping = {
            "ETF代码": "code",
            "交易日期": "date",
            "开盘价(元)": "open",
            "收盘价(元)": "close",
            "基金复权因子": "adj_factor"
        }

        df = df.rename(columns=column_mapping)

        # 数据处理
        df["date"] = pd.to_datetime(df["date"])
        # 将 code 转为字符串（CSV 中是整数）
        df["code"] = df["code"].astype(str)

        # 获取策略需要的 ETF 代码列表
        needed_codes = list(self.ETF_CODE_MAPPING.keys())
        csv_codes = list(self.ETF_CODE_MAPPING.values())

        # 筛选需要的 ETF
        df = df[df["code"].isin(csv_codes)]

        # 将 CSV 中的代码映射回策略代码
        reverse_mapping = {v: k for k, v in self.ETF_CODE_MAPPING.items()}
        df["code"] = df["code"].map(reverse_mapping)

        # 确保必要列存在
        required_cols = ["code", "date", "open", "close", "adj_factor"]
        for col in required_cols:
            if col not in df.columns:
                print(f"[WARN] 警告: 缺少列 {col}")

        print(f"  价格数据: {len(df)} 条记录")
        print(f"  ETF映射: {self.ETF_CODE_MAPPING}")

        return df

    def run(self, start: datetime, end: datetime, data_path: str) -> Tuple[pd.DataFrame, dict, GeneralBacktest]:
        """
        执行回测

        Returns:
            weights_data: 权重数据 DataFrame
            performance: 绩效指标字典
            bt: GeneralBacktest 实例（用于后续可视化）
        """
        # 1. 收集权重
        weights_data = self.collect_weights(start, end, data_path)

        if weights_data.empty:
            raise ValueError("没有收集到有效的权重数据")

        # 3. 创建回测实例
        bt = GeneralBacktest(
            start_date=start.strftime("%Y-%m-%d"),
            end_date=end.strftime("%Y-%m-%d")
        )

        # 4. 运行回测
        print("\n" + "=" * 60)
        print("[INFO] 开始回测...")
        print("=" * 60)

        # 根据是否提供数据库配置选择回测方式
        if self.db_config:
            # 使用数据库回测（与 cufel_arena 部署一致）
            print("[INFO] 使用数据库回测模式")
            print(f"[INFO] 数据库: {self.db_config['host']}:{self.db_config['port']}")
            try:
                results = bt.run_backtest_ETF(
                    etf_db_config=self.db_config,
                    weights_data=weights_data,
                    buy_price='open',
                    sell_price='open',
                    transaction_cost=[self.transaction_cost, self.transaction_cost],
                    rebalance_threshold=self.rebalance_threshold,
                    slippage=self.slippage
                )
            except Exception as e:
                print(f"[WARN] 数据库连接失败: {e}")
                print("[INFO] 回退到本地 CSV 回测模式")
                price_data = self._load_price_data(data_path)
                results = bt.run_backtest(
                    weights_data=weights_data,
                    price_data=price_data,
                    buy_price='open',
                    sell_price='open',
                    adj_factor_col="adj_factor",
                    close_price_col="close",
                    transaction_cost=[self.transaction_cost, self.transaction_cost],
                    rebalance_threshold=self.rebalance_threshold,
                    slippage=self.slippage
                )
        else:
            # 使用本地 CSV 回测
            print("[INFO] 使用本地 CSV 回测模式")
            price_data = self._load_price_data(data_path)
            results = bt.run_backtest(
                weights_data=weights_data,
                price_data=price_data,
                buy_price='open',
                sell_price='open',
                adj_factor_col="adj_factor",
                close_price_col="close",
                transaction_cost=[self.transaction_cost, self.transaction_cost],
                rebalance_threshold=self.rebalance_threshold,
                slippage=self.slippage
            )

        # 5. 提取绩效指标
        metrics_df = bt.get_metrics()

        # 辅助函数：安全获取指标
        def _get(key, default=float("nan")):
            if key in metrics_df.index:
                return float(metrics_df.loc[key, "值"])
            return default

        # 6. 构建绩效字典
        performance = {
            "initial_capital": 1_000_000.0,
            "total_return": _get("累计收益率"),
            "annual_return": _get("年化收益率"),
            "annual_volatility": _get("年化波动率"),
            "sharpe_ratio": _get("夏普比率"),
            "sortino_ratio": _get("索提诺比率"),
            "calmar_ratio": _get("卡玛比率"),
            "max_drawdown": _get("最大回撤"),
            "max_drawdown_duration": _get("最大回撤持续天数"),
            "var_95": _get("VaR (95%)"),
            "cvar_95": _get("CVaR (95%)"),
            "turnover": _get("累计换手率"),
            "win_rate": _get("胜率"),
            "total_trades": len(weights_data["date"].unique())
        }

        # 7. 打印绩效指标
        print("\n" + "=" * 60)
        print("[INFO] 回测绩效指标")
        print("=" * 60)
        print(f"\n收益指标:")
        print(f"  累计收益率:     {performance['total_return']:.2%}")
        print(f"  年化收益率:     {performance['annual_return']:.2%}")
        print(f"\n风险指标:")
        print(f"  年化波动率:     {performance['annual_volatility']:.2%}")
        print(f"  最大回撤:       {performance['max_drawdown']:.2%}")
        print(f"  最大回撤持续期: {performance['max_drawdown_duration']:.0f}天")
        print(f"\n风险调整指标:")
        print(f"  夏普比率:       {performance['sharpe_ratio']:.2f}")
        print(f"  索提诺比率:     {performance['sortino_ratio']:.2f}")
        print(f"  卡玛比率:       {performance['calmar_ratio']:.2f}")
        print(f"\n尾部风险:")
        print(f"  VaR (95%):      {performance['var_95']:.2%}")
        print(f"  CVaR (95%):     {performance['cvar_95']:.2%}")
        print(f"\n交易指标:")
        print(f"  换手率:         {performance['turnover']:.2%}")
        print(f"  调仓次数:       {performance['total_trades']}次")
        print(f"  胜率:           {performance['win_rate']:.2%}")

        return weights_data, performance, bt

    def plot_results(self, bt: GeneralBacktest, save_path: str = "backtest_results.png"):
        """
        生成可视化报告

        Args:
            bt: GeneralBacktest 实例
            save_path: 保存路径
        """
        print(f"\n[INFO] 生成可视化报告: {save_path}")

        try:
            # 尝试使用内置方法生成图表
            bt.plot_all(save_path=save_path)
            print(f"[OK] 图表已保存: {save_path}")
        except Exception as e:
            print(f"[WARN] 内置可视化失败，尝试手动生成: {e}")

            # 创建图表
            fig = plt.figure(figsize=(16, 12))

            # 1. 净值曲线
            try:
                ax1 = plt.subplot(2, 2, 1)
                nav = bt.get_nav()
                if 'nav' in nav.columns:
                    ax1.plot(nav.index, nav['nav'])
                    ax1.set_title("净值曲线")
            except Exception as ex:
                print(f"[WARN] 净值曲线生成失败: {ex}")

            plt.tight_layout()
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            print(f"[OK] 图表已保存: {save_path}")


# ==================== 测试代码 ====================

if __name__ == "__main__":
    # 初始化 Agents
    print("[INFO] 初始化 Agents...")

    # 数据路径
    data_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    practice_data_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "PracticeData")

    # 初始化 DataAgent
    data_agent = DataAgent(data_path)
    data_agent.load_all_data()

    # 初始化其他 Agents
    macro_agent = MacroAgent(use_llm=False)
    portfolio_agent = PortfolioAgent()

    # 创建工作流
    workflow = AgenticPortfolioWorkflow(data_agent, macro_agent, portfolio_agent)

    # 创建回测引擎
    engine = BacktestEngine(
        workflow,
        transaction_cost=0.001,
        rebalance_threshold=0.005,
        slippage=0.0005
    )

    # 运行回测（使用较短的时间范围进行快速测试）
    start = datetime(2022, 1, 31)
    end = datetime(2023, 12, 31)

    # 使用 data 目录（包含 ETF 价格数据）
    data_path_for_backtest = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

    try:
        weights_df, performance, bt = engine.run(start, end, data_path_for_backtest)

        # 保存权重数据
        weights_df.to_csv("weights_data.csv", index=False)
        print(f"\n权重数据已保存: weights_data.csv")

        # 生成可视化
        engine.plot_results(bt, "backtest_results.png")
    except Exception as e:
        print(f"[ERROR] 回测失败: {e}")
        import traceback
        traceback.print_exc()
