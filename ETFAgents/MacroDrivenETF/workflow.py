"""
Workflow - LangGraph 工作流模块
用 LangGraph 将三个 Agent 串联成有状态的 Agentic 工作流
"""

import os
import sys
from typing import TypedDict, Optional, Any
from datetime import datetime

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 尝试导入 LangGraph
try:
    from langgraph.graph import StateGraph, END
    from langgraph.checkpoint.memory import MemorySaver
    _LANGGRAPH_AVAILABLE = True
except ImportError:
    _LANGGRAPH_AVAILABLE = False
    print("[WARN] LangGraph 未安装，工作流将使用简化模式")

# 导入三个 Agent
from data_agent import DataAgent, MacroData
from macro_agent import MacroAgent
from portfolio_agent import PortfolioAgent


# ==================== WorkflowState 定义 ====================

class WorkflowState(TypedDict):
    """工作流状态定义"""
    decision_date: datetime
    macro_data: Optional[MacroData]     # 完整宏观数据对象
    macro_analysis: Optional[dict]      # 宏观分析结果
    portfolio_decision: Optional[dict]  # 组合决策结果
    error: Optional[str]                # 错误信息


# ==================== 节点函数工厂 ====================

def create_data_node(data_agent: DataAgent):
    """创建数据节点"""
    def data_node(state: WorkflowState) -> dict:
        print("[INFO] [Node 1/3] DataAgent: 获取宏观数据...")
        try:
            macro_data = data_agent.get_macro_for_decision(state["decision_date"])
            print(f"  [OK] PMI: {macro_data.pmi} (数据时点: {macro_data.pmi_date.strftime('%Y-%m-%d')})")
            print(f"  [OK] CPI同比: {macro_data.cpi_yoy}%")
            print(f"  [OK] PPI同比: {macro_data.ppi_yoy}%")
            print(f"  [OK] M2同比: {macro_data.m2_yoy}%")
            return {**state, "macro_data": macro_data, "error": None}
        except Exception as e:
            print(f"  [ERROR] 错误: {e}")
            return {**state, "error": str(e)}
    return data_node


def create_macro_node(macro_agent: MacroAgent):
    """创建宏观分析节点"""
    def macro_node(state: WorkflowState) -> dict:
        if state.get("error"):
            print("[INFO] [Node 2/3] MacroAgent: 跳过（前置错误）")
            return state

        print("[INFO] [Node 2/3] MacroAgent: 宏观分析...")
        try:
            result = macro_agent.analyze(state["macro_data"])
            print(f"  [OK] 周期判断: {result['cycle_phase']} (置信度: {result['confidence']:.0%})")
            return {**state, "macro_analysis": result, "error": None}
        except Exception as e:
            print(f"  [ERROR] 错误: {e}")
            return {**state, "error": str(e)}
    return macro_node


def create_portfolio_node(portfolio_agent: PortfolioAgent):
    """创建组合决策节点"""
    def portfolio_node(state: WorkflowState) -> dict:
        if state.get("error"):
            print("[INFO] [Node 3/3] PortfolioAgent: 跳过（前置错误）")
            return state

        print("[INFO] [Node 3/3] PortfolioAgent: 生成组合...")
        try:
            result = portfolio_agent.decide(state["macro_analysis"])
            print("  [OK] 组合配置:")
            for item in result["portfolio_summary"]:
                print(f"     {item['code']}: {item['weight']}")
            return {**state, "portfolio_decision": result, "error": None}
        except Exception as e:
            print(f"  [ERROR] 错误: {e}")
            return {**state, "error": str(e)}
    return portfolio_node


# ==================== AgenticPortfolioWorkflow 类 ====================

class AgenticPortfolioWorkflow:
    """Agentic Portfolio 工作流"""

    def __init__(self, data_agent: DataAgent, macro_agent: MacroAgent, portfolio_agent: PortfolioAgent):
        self.data_agent = data_agent
        self.macro_agent = macro_agent
        self.portfolio_agent = portfolio_agent
        self.workflow = None
        self.app = None

        if _LANGGRAPH_AVAILABLE:
            self.workflow = self._build_workflow()
            self.app = self._compile()
            print("[OK] LangGraph 工作流初始化完成")
        else:
            print("[OK] 使用简化模式（无 LangGraph）")

    def _build_workflow(self) -> StateGraph:
        """构建工作流图"""
        workflow = StateGraph(WorkflowState)

        # 添加节点
        workflow.add_node("data_node", create_data_node(self.data_agent))
        workflow.add_node("macro_node", create_macro_node(self.macro_agent))
        workflow.add_node("portfolio_node", create_portfolio_node(self.portfolio_agent))

        # 设置入口点
        workflow.set_entry_point("data_node")

        # 添加边（顺序执行）
        workflow.add_edge("data_node", "macro_node")
        workflow.add_edge("macro_node", "portfolio_node")
        workflow.add_edge("portfolio_node", END)

        return workflow

    def _compile(self):
        """编译工作流"""
        memory = MemorySaver()
        return self.workflow.compile(checkpointer=memory)

    def run(self, decision_date: datetime) -> dict:
        """运行工作流"""
        print("=" * 60)
        print(f"[OK] 启动工作流 | 决策日期: {decision_date.strftime('%Y-%m-%d')}")
        print("=" * 60)

        # 初始状态
        initial_state = {
            "decision_date": decision_date,
            "macro_data": None,
            "macro_analysis": None,
            "portfolio_decision": None,
            "error": None
        }

        # 使用 LangGraph 或简化模式
        if self.app is not None:
            # 配置（使用日期作为 thread_id，支持缓存）
            config = {"configurable": {"thread_id": decision_date.strftime("%Y%m%d")}}

            # 执行工作流
            result = self.app.invoke(initial_state, config)
        else:
            # 简化模式：顺序执行
            result = self._run_simple(initial_state)

        # 输出结果
        if result.get("error"):
            print(f"\n[ERROR] 工作流失败: {result['error']}")
        else:
            print("\n" + "=" * 60)
            print("[OK] 工作流完成")
            print("=" * 60)

        return result

    def _run_simple(self, state: WorkflowState) -> dict:
        """简化模式：顺序执行各节点"""
        # Node 1: DataAgent
        data_node_fn = create_data_node(self.data_agent)
        state = data_node_fn(state)
        if state.get("error"):
            return state

        # Node 2: MacroAgent
        macro_node_fn = create_macro_node(self.macro_agent)
        state = macro_node_fn(state)
        if state.get("error"):
            return state

        # Node 3: PortfolioAgent
        portfolio_node_fn = create_portfolio_node(self.portfolio_agent)
        state = portfolio_node_fn(state)

        return state


# ==================== 测试代码 ====================

if __name__ == "__main__":
    # 初始化 Agents
    print("[INFO] 初始化 Agents...")

    # 获取数据路径
    data_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    data_agent = DataAgent(data_path)
    data_agent.load_all_data()

    macro_agent = MacroAgent(use_llm=False)  # 使用 fallback 模式测试
    portfolio_agent = PortfolioAgent()

    # 创建工作流并运行
    workflow = AgenticPortfolioWorkflow(data_agent, macro_agent, portfolio_agent)
    result = workflow.run(datetime(2024, 3, 31))

    # 打印决策理由
    if result.get("portfolio_decision"):
        print("\n决策理由:")
        print(result["portfolio_decision"]["reasoning"])
