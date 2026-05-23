"""回测引擎 — 唯一回测入口，严格按 VibeCodingPrompts 06 课程规范实现
铁律：禁止在其他任何文件写回测逻辑"""
import os, json, warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

_PROJECT = Path(__file__).parent.parent.parent


class BacktestEngine:
    """ETF 组合回测引擎 — 按课程规范 API，用自定义 NAV 计算"""

    def __init__(self, agent,
                 transaction_cost: float = 0.001,
                 rebalance_threshold: float = 0.005,
                 slippage: float = 0.0005,
                 freq: str = "M"):
        """
        Args:
            agent: MacroDrivenETFAgent 实例
            transaction_cost: 交易成本（默认万分之十=0.001，含买卖双向）
            rebalance_threshold: 调仓阈值（0.5%=0.005，低于此不交易）
            slippage: 滑点（0.05%=0.0005）
            freq: 调仓频率 "M"=月末 "Q"=季末
        """
        self.agent = agent
        self.transaction_cost = transaction_cost
        self.rebalance_threshold = rebalance_threshold
        self.slippage = slippage
        self.freq = freq

    # ═══════════════════════════════════════════════════════
    #  调仓日期
    # ═══════════════════════════════════════════════════════

    def generate_rebalance_dates(self, start: datetime, end: datetime) -> List[datetime]:
        """生成调仓日期列表 (M=月末, Q=季末)"""
        dates = []
        current = start
        while current <= end:
            if current.month == 12:
                month_end = datetime(current.year + 1, 1, 1) - timedelta(days=1)
            else:
                month_end = datetime(current.year, current.month + 1, 1) - timedelta(days=1)
            if month_end <= end:
                if self.freq == "Q" and month_end.month not in (3, 6, 9, 12):
                    pass  # skip non-quarter-end months
                else:
                    dates.append(month_end)
            if current.month == 12:
                current = datetime(current.year + 1, 1, 1)
            else:
                current = datetime(current.year, current.month + 1, 1)
        return dates

    # ═══════════════════════════════════════════════════════
    #  价格数据
    # ═══════════════════════════════════════════════════════

    def _load_price_data(self, codes: list, start: str, end: str) -> pd.DataFrame:
        """从本地 parquet 加载价格数据"""
        pdf = pd.read_parquet(_PROJECT / "data" / "etf_daily.parquet")
        sub = pdf[(pdf["date"] >= start) & (pdf["date"] <= end) & (pdf["code"].isin(codes))]
        if sub.empty:
            return sub
        sub = sub[["date", "code", "close"]].copy()
        sub["close_adj"] = sub["close"]
        sub["date"] = pd.to_datetime(sub["date"])
        return sub

    # ═══════════════════════════════════════════════════════
    #  收集权重
    # ═══════════════════════════════════════════════════════

    def collect_weights(self, start: datetime, end: datetime) -> pd.DataFrame:
        """收集所有调仓日期的目标权重，返回 [date, code, weight] DataFrame"""
        dates = self.generate_rebalance_dates(start, end)
        records = []
        for dt in dates:
            ds = dt.strftime("%Y-%m-%d")
            try:
                h = self.agent.get_current_holdings(ds, theta=1.0)
                w = h.get(ds, {})
            except Exception:
                w = {}
            if w:
                for code, weight in w.items():
                    records.append({"date": dt, "code": code, "weight": weight})
        return pd.DataFrame(records)

    # ═══════════════════════════════════════════════════════
    #  运行回测（核心）
    # ═══════════════════════════════════════════════════════

    def run(self, start: datetime, end: datetime) -> Tuple[pd.DataFrame, dict, pd.Series]:
        """执行回测，返回 (weights_data, performance, nav_series)"""
        # 1. 收集权重
        weights_data = self.collect_weights(start, end)
        if weights_data.empty:
            raise ValueError("没有收集到有效的权重数据")

        # 2. 转换为 pivot 格式
        ws = weights_data.pivot_table(index="date", columns="code", values="weight",
                                       aggfunc="last").fillna(0)
        ws.index = pd.to_datetime(ws.index)
        all_codes = list(ws.columns)

        # 3. 加载价格
        start_s = start.strftime("%Y-%m-%d")
        end_s = end.strftime("%Y-%m-%d")
        prices = self._load_price_data(all_codes, start_s, end_s)
        pivot = prices.pivot_table(index="date", columns="code", values="close_adj",
                                    aggfunc="last").ffill()
        if pivot.empty:
            raise ValueError("价格数据为空")

        # 4. 逐日计算 NAV，调仓日按换手比例扣费
        nav = pd.Series(1.0, index=pivot.index)
        current_weights = pd.Series(0, index=all_codes)
        total_cost = 0.0

        for i, today in enumerate(pivot.index):
            if i == 0:
                continue
            yesterday = pivot.index[i - 1]
            daily_ret = pivot.loc[today] / pivot.loc[yesterday] - 1
            daily_ret = daily_ret.fillna(0)

            # 检查是否调仓日
            rebalance_dates = {d.strftime("%Y-%m-%d"): d for d in ws.index}
            today_s = today.strftime("%Y-%m-%d")

            if today_s in rebalance_dates:
                target_w = ws.loc[rebalance_dates[today_s]]
                target_w = target_w.reindex(all_codes).fillna(0)

                # 计算换手
                w_diff = target_w - current_weights
                turnover = w_diff.abs().sum() / 2

                # rebalance_threshold: 应用阈值后的实际交易量
                tiny_mask = w_diff.abs() < self.rebalance_threshold
                actual_diff = w_diff.copy()
                actual_diff[tiny_mask] = 0
                actual_turnover = actual_diff.abs().sum() / 2

                # 比例扣费: turnover × (buy_cost + sell_cost + 2 × slippage)
                cost = actual_turnover * (self.transaction_cost + self.transaction_cost + 2 * self.slippage)
                total_cost += cost

                # 应用成本和新的权重
                portfolio_ret = (current_weights * daily_ret).sum()
                portfolio_ret -= cost
                nav.loc[today] = nav.loc[yesterday] * (1 + portfolio_ret)
                current_weights = target_w.copy()
            else:
                portfolio_ret = (current_weights * daily_ret).sum()
                nav.loc[today] = nav.loc[yesterday] * (1 + portfolio_ret)

        # 5. 提取绩效
        performance = self._extract_metrics(nav, ws)
        performance["total_cost"] = round(total_cost * 100, 2)
        performance["cost_pct"] = f"{total_cost * 100:.2f}%"
        return weights_data, performance, nav

    def _extract_metrics(self, nav: pd.Series, weights_df: pd.DataFrame) -> dict:
        """从 NAV 序列提取绩效指标"""
        daily = nav.pct_change().dropna()
        n_days = len(daily) + 1
        total_ret = float(nav.iloc[-1] / nav.iloc[0] - 1)
        ann_ret = float((1 + total_ret) ** (252 / max(n_days, 1)) - 1)
        ann_vol = float(daily.std() * np.sqrt(252)) if len(daily) > 5 else 0
        sharpe = float(ann_ret / ann_vol) if ann_vol > 0 else 0
        max_dd = float((nav / nav.cummax() - 1).min())
        turnover = float(weights_df.diff().abs().sum(axis=1).mean()) if len(weights_df) > 1 else 0
        return {
            "total_return": round(total_ret * 100, 1),
            "annual_return": round(ann_ret * 100, 1),
            "annual_volatility": round(ann_vol * 100, 1),
            "sharpe_ratio": round(sharpe, 2),
            "max_drawdown": round(max_dd * 100, 1),
            "turnover": round(turnover, 2),
        }

    # ═══════════════════════════════════════════════════════
    #  可视化
    # ═══════════════════════════════════════════════════════

    def plot_results(self, nav: pd.Series, save_path: str = "backtest_results.png"):
        """生成可视化报告"""
        fig = plt.figure(figsize=(16, 10))

        # 1. 净值曲线
        ax1 = plt.subplot(2, 2, 1)
        ax1.plot(nav.index, nav.values, color="#2196F3", linewidth=1.5)
        ax1.set_title("Net Value Curve")
        ax1.grid(True, alpha=0.3)

        # 2. 回撤曲线
        ax2 = plt.subplot(2, 2, 2)
        dd = (nav / nav.cummax() - 1) * 100
        ax2.fill_between(dd.index, dd.values, 0, color="#FF5722", alpha=0.3)
        ax2.set_title("Drawdown")
        ax2.grid(True, alpha=0.3)

        # 3. 月度收益热力图
        ax3 = plt.subplot(2, 2, 3)
        monthly = nav.resample("ME").last().pct_change().dropna()
        monthly_ret = monthly.values * 100
        colors = ["#26a69a" if x >= 0 else "#ef5350" for x in monthly_ret]
        ax3.bar(range(len(monthly_ret)), monthly_ret, color=colors, alpha=0.8)
        ax3.set_title("Monthly Returns (%)")
        ax3.axhline(y=0, color="black", linewidth=0.5)
        ax3.grid(True, alpha=0.3)

        # 4. 绩效指标表
        ax4 = plt.subplot(2, 2, 4)
        ax4.axis("off")
        perf = self._extract_metrics(nav, pd.DataFrame())
        metrics_text = f"""Total Return: {perf['total_return']}%
Annual Return: {perf['annual_return']}%
Annual Vol: {perf['annual_volatility']}%
Sharpe Ratio: {perf['sharpe_ratio']}
Max Drawdown: {perf['max_drawdown']}%
Turnover: {perf['turnover']}"""
        ax4.text(0.1, 0.5, metrics_text, fontsize=14, fontfamily="monospace",
                 verticalalignment="center")
        ax4.set_title("Performance Metrics")

        plt.tight_layout()
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"Chart saved: {save_path}")


def compare_weights(weights_dicts: dict, start="2021-01-01", end="2026-05-22") -> pd.DataFrame:
    """比较不同 SCORE_WEIGHTS 方案的回测结果"""
    from agent.engine import MacroDrivenETFAgent, PortfolioAgent
    from data.local_store import get_sector_map

    # Build universe once
    df = pd.read_parquet(_PROJECT / "data" / "etf_daily.parquet")
    recent = df[df["date"] >= pd.Timestamp.now() - pd.Timedelta(days=60)]
    vol_rank = recent.groupby("code")["vol"].mean().sort_values(ascending=False)
    with open(_PROJECT / "data" / "etf_names.json", "r", encoding="utf-8") as f:
        names = json.load(f)
    c = get_sector_map()
    GOLD_KW = ["黄金", "上海金", "金ETF"]
    uni = {"Stock": [], "Bond": [], "Commodity": []}
    for code in vol_rank.index.tolist():
        name = names.get(code, "")
        qmt = f"{code}.SH" if code.startswith(("5","6","51","56","58","59")) else f"{code}.SZ"
        if not name or qmt in c["cross"]:
            continue
        if qmt in c["commodity"]:
            if any(kw in name for kw in GOLD_KW):
                uni["Commodity"].append((code, name))
        elif qmt in c["bond"] or qmt in c["money"]:
            uni["Bond"].append((code, name))
        elif qmt in c["stock"]:
            uni["Stock"].append((code, name))

    results = []
    for name, weights in weights_dicts.items():
        for f in Path(_PROJECT / "cache").glob("holdings_*.json"):
            f.unlink()
        PortfolioAgent.SCORE_WEIGHTS = weights
        agent = MacroDrivenETFAgent(use_llm=False)
        agent.set_etf_universe(uni)
        engine = BacktestEngine(agent, transaction_cost=0.0003, rebalance_threshold=0.005, slippage=0.0001)
        try:
            _, perf, _ = engine.run(datetime(2021, 1, 31), datetime(2026, 5, 31))
            perf["scheme"] = name
            perf["weights"] = weights
            results.append(perf)
            print(f"  {name}: Ret={perf['total_return']:.1f}% Sharpe={perf['sharpe_ratio']:.2f} DD={perf['max_drawdown']:.1f}% Turnover={perf['turnover']}")
        except Exception as e:
            print(f"  {name}: ERROR {e}")

    if not results:
        return pd.DataFrame()
    df = pd.DataFrame(results).sort_values("sharpe_ratio", ascending=False)
    return df[["scheme", "total_return", "annual_return", "sharpe_ratio", "max_drawdown", "turnover", "weights"]]