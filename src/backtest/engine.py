"""
回测引擎 — 基于 GeneralBacktest 包，按 VibeCodingPrompts 06 课程规范实现

接口:
    bt = BacktestEngine(workflow, transaction_cost, rebalance_threshold, slippage)
    weights_df, performance, bt = engine.run(start, end, data_path)
    engine.plot_results(bt, save_path)
"""
import sys, os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from GeneralBacktest import GeneralBacktest

sys.path.insert(0, str(Path(__file__).parent.parent))


class BacktestEngine:
    """ETF 组合回测引擎 — 对接 AgenticPortfolio 策略"""

    def __init__(
        self,
        workflow,              # AgenticPortfolioWorkflow 或 MacroDrivenETFAgent
        transaction_cost: float = 0.001,
        rebalance_threshold: float = 0.005,
        slippage: float = 0.0005
    ):
        self.workflow = workflow
        self.transaction_cost = transaction_cost
        self.rebalance_threshold = rebalance_threshold
        self.slippage = slippage

    # ═══════════════════════════════════════════════════════
    #  调仓日期
    # ═══════════════════════════════════════════════════════

    def generate_rebalance_dates(self, start: datetime, end: datetime) -> List[datetime]:
        """生成月末调仓日期列表"""
        dates = []
        current = start
        while current <= end:
            if current.month == 12:
                month_end = datetime(current.year + 1, 1, 1) - timedelta(days=1)
            else:
                month_end = datetime(current.year, current.month + 1, 1) - timedelta(days=1)
            if month_end <= end:
                dates.append(month_end)
            if current.month == 12:
                current = datetime(current.year + 1, 1, 1)
            else:
                current = datetime(current.year, current.month + 1, 1)
        return dates

    # ═══════════════════════════════════════════════════════
    #  权重收集
    # ═══════════════════════════════════════════════════════

    def collect_weights(self, start: datetime, end: datetime) -> pd.DataFrame:
        """收集所有调仓日期的目标权重"""
        print("=" * 60)
        print(f"收集权重: {start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}")
        print("=" * 60)

        rebalance_dates = self.generate_rebalance_dates(start, end)
        print(f"调仓次数: {len(rebalance_dates)}次\n")

        weights_list = []
        previous_codes = set()
        for i, date in enumerate(rebalance_dates, 1):
            date_str = date.strftime("%Y-%m-%d")
            print(f"{'─'*60}")
            print(f"调仓 {i}/{len(rebalance_dates)}: {date_str}")
            print(f"{'─'*60}")

            try:
                # 设置前月持仓用于惯性加成
                self.workflow._prev_codes = previous_codes
                holdings = self.workflow.get_current_holdings(date_str, theta=1.0)
                portfolio = holdings.get(date_str, {})
                previous_codes = set(portfolio.keys())

                if not portfolio:
                    print(f"  {date_str} 无有效决策，跳过")
                    continue

                for code, weight in portfolio.items():
                    weights_list.append({
                        "date": date,
                        "code": code,
                        "weight": weight,
                    })

                print(f"  {len(portfolio)} ETFs, 权重合计={sum(portfolio.values()):.2%}")

            except Exception as e:
                print(f"  {date_str} 出错: {e}")

        if not weights_list:
            print("无有效权重数据")
            return pd.DataFrame()

        df = pd.DataFrame(weights_list)
        # 添加占位列（GeneralBacktest 可能需要）
        df["cycle_phase"] = "N/A"
        df["confidence"] = 0.5
        return df

    # ═══════════════════════════════════════════════════════
    #  价格数据加载
    # ═══════════════════════════════════════════════════════

    def _load_price_data(self) -> pd.DataFrame:
        """从本地 parquet 加载价格数据，转换为 GeneralBacktest 兼容格式"""
        from src.data.local_store import get_bars, get_names

        # 从权重数据中获取所有代码
        # 如果还没有权重，先加载所有 ETF
        parquet_path = "data/etf_daily.parquet"
        df = pd.read_parquet(parquet_path)
        df["code"] = df["code"].astype(str)
        df["date"] = pd.to_datetime(df["date"])

        # 转换为课程列名格式
        price_df = df.rename(columns={
            "open": "open",
            "close": "close",
        })

        # GeneralBacktest 需要的列: code, date, open, close
        # adj_factor 用 1.0 填充（parquet 数据为前复权，不需要额外复权因子）
        price_df["adj_factor"] = 1.0

        price_df = price_df[["code", "date", "open", "close", "adj_factor"]]
        print(f"  价格数据: {len(price_df)} 条")
        return price_df

    # ═══════════════════════════════════════════════════════
    #  运行回测
    # ═══════════════════════════════════════════════════════

    def run(self, start: datetime, end: datetime) -> Tuple[pd.DataFrame, dict, GeneralBacktest]:
        """执行回测"""
        # 1. 收集权重
        weights_data = self.collect_weights(start, end)
        if weights_data.empty:
            raise ValueError("没有收集到有效的权重数据")

        # 2. 加载价格数据
        price_data = self._load_price_data()

        # 3. 创建回测实例
        bt = GeneralBacktest(
            start_date=start.strftime("%Y-%m-%d"),
            end_date=end.strftime("%Y-%m-%d")
        )

        # 4. 运行回测
        print("\n" + "=" * 60)
        print("执行回测...")
        print("=" * 60)

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

        def _get(key, default=float("nan")):
            if key in metrics_df.index:
                return float(metrics_df.loc[key, "值"])
            return default

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

        # 6. 打印绩效
        print("\n" + "=" * 60)
        print("回测绩效指标")
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

    # ═══════════════════════════════════════════════════════
    #  可视化
    # ═══════════════════════════════════════════════════════

    def plot_results(self, bt: GeneralBacktest, save_path: str = "backtest_results.png"):
        """生成可视化报告"""
        print(f"\n生成可视化: {save_path}")

        fig = plt.figure(figsize=(16, 12))

        # 1. 净值曲线
        ax1 = plt.subplot(2, 2, 1)
        bt.plot_nav_curve(log_scale=False, ax=ax1)
        ax1.set_title("Net Value Curve")

        # 2. 对数坐标净值曲线
        ax2 = plt.subplot(2, 2, 2)
        bt.plot_nav_curve(log_scale=True, ax=ax2)
        ax2.set_title("Net Value Curve (Log)")

        # 3. 月度收益热力图
        ax3 = plt.subplot(2, 2, 3)
        bt.plot_monthly_returns(ax=ax3)
        ax3.set_title("Monthly Returns Heatmap")

        # 4. 换手率分析
        ax4 = plt.subplot(2, 2, 4)
        bt.plot_turnover(ax=ax4)
        ax4.set_title("Turnover Analysis")

        plt.tight_layout()
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"图表已保存: {save_path}")


# ═══════════════════════════════════════════════════════
#  测试入口
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    from datetime import datetime
    from src.agent import init_agent

    print("初始化 Agent...")
    agent = init_agent()

    print("创建回测引擎...")
    engine = BacktestEngine(
        workflow=agent,
        transaction_cost=0.001,
        rebalance_threshold=0.005,
        slippage=0.0005
    )

    start = datetime(2022, 1, 31)
    end = datetime(2024, 12, 31)

    weights_df, performance, bt = engine.run(start, end)

    weights_df.to_csv("weights_data.csv", index=False)
    print(f"\n权重数据已保存: weights_data.csv")

    engine.plot_results(bt, "backtest_results.png")
