"""
Main - 主程序入口
宏观驱动ETF配置系统的命令行入口，支持单次决策和回测两种模式
"""

import os
import sys
import argparse
import json
import math
from datetime import datetime

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_agent import DataAgent
from macro_agent import MacroAgent
from portfolio_agent import PortfolioAgent
from workflow import AgenticPortfolioWorkflow
from backtest import BacktestEngine


# ==================== 配置类 ====================

class Config:
    """配置类"""

    def __init__(self):
        from dotenv import load_dotenv

        # 加载环境变量
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        load_dotenv(env_path)

        # 路径配置
        self.DATA_PATH = os.getenv("DATA_PATH", "./data/")
        self.CACHE_PATH = os.getenv("CACHE_PATH", "./cache/")
        self.OUTPUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

        # 交易参数
        self.TRANSACTION_COST = 0.001  # 双边万分之十
        self.REBALANCE_THRESHOLD = 0.005  # 0.5%
        self.SLIPPAGE = 0.0005  # 0.05%

        # 数据库配置（用于回测）
        self.DB_CONFIG = None
        chdb_host = os.getenv("CHDB_HOST")
        if chdb_host:
            self.DB_CONFIG = {
                'host': chdb_host,
                'port': int(os.getenv("CHDB_PORT", 20108)),
                'user': os.getenv("CHDB_USER"),
                'password': os.getenv("CHDB_PASSWORD"),
                'database': os.getenv("CHDB_DATABASE", "etf")
            }


# ==================== 核心函数 ====================

def setup_agents(config: Config, use_llm: bool = True):
    """初始化所有 Agent，返回 (data_agent, macro_agent, portfolio_agent)"""
    print("[INFO] 初始化 Agents...")

    # 数据 Agent
    data_agent = DataAgent(config.DATA_PATH)
    data_agent.load_all_data()

    # 宏观分析 Agent
    macro_agent = MacroAgent(use_llm=use_llm)

    # 组合决策 Agent
    portfolio_agent = PortfolioAgent()

    return data_agent, macro_agent, portfolio_agent


def run_single_decision(date: datetime, config: Config, use_llm: bool = True):
    """单次决策模式"""
    print("=" * 60)
    print(f"[INFO] 单次决策模式 | 日期: {date.strftime('%Y-%m-%d')}")
    print("=" * 60)

    # 初始化 Agents
    data_agent, macro_agent, portfolio_agent = setup_agents(config, use_llm)

    # 创建工作流
    workflow = AgenticPortfolioWorkflow(data_agent, macro_agent, portfolio_agent)

    # 运行工作流
    result = workflow.run(date)

    if result.get("error"):
        print(f"\n[ERROR] 决策失败: {result['error']}")
        return

    decision = result["portfolio_decision"]

    # 打印决策结果
    print("\n" + "=" * 60)
    print("[INFO] 决策结果")
    print("=" * 60)
    print(f"\n周期判断: {decision['cycle_phase']}")
    print(f"置信度: {decision['confidence']:.0%}")

    print("\n组合配置:")
    for item in decision["portfolio_summary"]:
        print(f"  {item['code']} ({item['name']}): {item['weight']}")

    print("\n资产分配:")
    for asset, weight in decision["asset_allocation"].items():
        print(f"  {asset}: {weight}")

    print(f"\n风险检查: {decision['risk_check']}")

    print("\n" + "=" * 60)
    print("决策理由:")
    print("=" * 60)
    print(decision["reasoning"])

    # 保存 JSON（处理 datetime 序列化）
    os.makedirs(config.OUTPUT_PATH, exist_ok=True)
    output_file = os.path.join(config.OUTPUT_PATH, f"decision_{date.strftime('%Y%m%d')}.json")

    def _make_serializable(obj):
        """递归处理 datetime 对象"""
        if isinstance(obj, dict):
            return {k: _make_serializable(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_make_serializable(i) for i in obj]
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        return obj

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(_make_serializable(decision), f, ensure_ascii=False, indent=2)

    print(f"\n[OK] 结果已保存: {output_file}")


def run_backtest(start: datetime, end: datetime, config: Config, use_llm: bool = True):
    """回测模式"""
    print("=" * 60)
    print(f"[INFO] 回测模式 | {start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}")
    print("=" * 60)

    # 初始化 Agents
    data_agent, macro_agent, portfolio_agent = setup_agents(config, use_llm)

    # 创建工作流
    workflow = AgenticPortfolioWorkflow(data_agent, macro_agent, portfolio_agent)

    # 创建回测引擎
    engine = BacktestEngine(
        workflow,
        transaction_cost=config.TRANSACTION_COST,
        rebalance_threshold=config.REBALANCE_THRESHOLD,
        slippage=config.SLIPPAGE,
        db_config=config.DB_CONFIG
    )

    # 运行回测
    weights_df, performance, bt = engine.run(start, end, config.DATA_PATH)

    # 保存结果
    os.makedirs(config.OUTPUT_PATH, exist_ok=True)

    # 保存权重数据
    weights_file = os.path.join(config.OUTPUT_PATH, "weights_data.csv")
    weights_df.to_csv(weights_file, index=False, encoding="utf-8")
    print(f"\n[OK] 权重数据已保存: {weights_file}")

    # 保存绩效数据（处理 NaN）
    if performance:
        def _clean(v):
            if isinstance(v, float) and math.isnan(v):
                return None
            return v

        perf_file = os.path.join(config.OUTPUT_PATH, "performance.json")
        with open(perf_file, "w", encoding="utf-8") as f:
            json.dump({k: _clean(v) for k, v in performance.items()}, f, ensure_ascii=False, indent=2)
        print(f"[OK] 绩效数据已保存: {perf_file}")

    # 保存可视化
    if bt:
        plot_path = os.path.join(config.OUTPUT_PATH, "backtest_results.png")
        engine.plot_results(bt, plot_path)


# ==================== 主入口 ====================

def main():
    """主入口"""
    # 设置输出编码
    if sys.platform == "win32":
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

    parser = argparse.ArgumentParser(
        description="MacroDrivenETF - 宏观驱动ETF配置系统"
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=["single", "backtest"],
        help="运行模式: single=单次决策, backtest=历史回测"
    )
    parser.add_argument(
        "--date",
        help="单次决策日期 (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--start",
        help="回测开始日期 (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--end",
        help="回测结束日期 (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="禁用LLM，使用规则兜底（无需API Key）"
    )

    args = parser.parse_args()

    # 加载配置
    config = Config()
    use_llm = not args.no_llm

    # 根据模式执行
    if args.mode == "single":
        if not args.date:
            print("[ERROR] 错误: single模式需要 --date 参数")
            sys.exit(1)
        try:
            date = datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            print("[ERROR] 错误: 日期格式应为 YYYY-MM-DD")
            sys.exit(1)
        run_single_decision(date, config, use_llm)

    elif args.mode == "backtest":
        if not args.start or not args.end:
            print("[ERROR] 错误: backtest模式需要 --start 和 --end 参数")
            sys.exit(1)
        try:
            start = datetime.strptime(args.start, "%Y-%m-%d")
            end = datetime.strptime(args.end, "%Y-%m-%d")
        except ValueError:
            print("[ERROR] 错误: 日期格式应为 YYYY-MM-DD")
            sys.exit(1)
        run_backtest(start, end, config, use_llm)


if __name__ == "__main__":
    main()
