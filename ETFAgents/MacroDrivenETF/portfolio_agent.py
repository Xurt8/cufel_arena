"""
PortfolioAgent - 决策层模块
根据宏观周期判断，输出具体的 ETF 代码与权重，并通过风险控制检查
"""

from pydantic import BaseModel
from typing import Dict, List


# ==================== Pydantic 模型定义 ====================

class ETFPosition(BaseModel):
    """ETF持仓"""
    name: str      # ETF名称
    type: str      # 股票/债券/商品
    weight: float  # 权重 0-1


class PortfolioDecision(BaseModel):
    """组合决策输出"""
    decision_date: str
    cycle_phase: str
    confidence: float
    portfolio: Dict[str, ETFPosition]
    portfolio_summary: List[Dict[str, str]]
    asset_allocation: Dict[str, str]
    total_weight: float
    reasoning: str
    risk_check: str


# ==================== PortfolioAgent ====================

class PortfolioAgent:
    """组合决策Agent"""

    # 周期 → ETF 硬编码映射
    CYCLE_ALLOCATION = {
        "复苏期": {
            "510300": {"name": "沪深300ETF", "type": "股票", "base_weight": 0.40},
            "510500": {"name": "中证500ETF", "type": "股票", "base_weight": 0.20},
            "511010": {"name": "国债ETF",    "type": "债券", "base_weight": 0.25},
            "518880": {"name": "黄金ETF",    "type": "商品", "base_weight": 0.15},
        },
        "扩张期": {
            "510300": {"name": "沪深300ETF", "type": "股票", "base_weight": 0.50},
            "510500": {"name": "中证500ETF", "type": "股票", "base_weight": 0.25},
            "511010": {"name": "国债ETF",    "type": "债券", "base_weight": 0.15},
            "518880": {"name": "黄金ETF",    "type": "商品", "base_weight": 0.10},
        },
        "滞胀期": {
            "510300": {"name": "沪深300ETF", "type": "股票", "base_weight": 0.25},
            "511010": {"name": "国债ETF",    "type": "债券", "base_weight": 0.35},
            "518880": {"name": "黄金ETF",    "type": "商品", "base_weight": 0.40},
        },
        "衰退期": {
            "510300": {"name": "沪深300ETF", "type": "股票", "base_weight": 0.15},
            "511010": {"name": "国债ETF",    "type": "债券", "base_weight": 0.50},
            "511220": {"name": "城投债ETF",  "type": "债券", "base_weight": 0.20},
            "518880": {"name": "黄金ETF",    "type": "商品", "base_weight": 0.15},
        }
    }

    # 风险控制参数
    CONSTRAINTS = {
        "max_single_etf": 0.55,   # 单ETF最大权重
        "max_stock_ratio": 0.75,  # 股票类最大总权重
        "min_stock_ratio": 0.10,  # 股票类最小总权重
        "max_gold_ratio": 0.45,   # 黄金类最大总权重
    }

    def __init__(self):
        """初始化 PortfolioAgent"""
        print("[OK] PortfolioAgent 初始化完成")

    def decide(self, macro_analysis: dict) -> dict:
        """生成ETF组合决策"""
        cycle = macro_analysis["cycle_phase"]
        confidence = macro_analysis["confidence"]

        # 获取周期配置
        base_config = self.CYCLE_ALLOCATION.get(cycle)
        if not base_config:
            raise ValueError(f"未知的周期阶段: {cycle}")

        # 构建组合
        portfolio = self._build_portfolio(base_config, confidence)

        # 应用风险控制
        portfolio, risk_warnings = self._apply_risk_controls(portfolio)

        # 生成报告
        report = self._generate_report(macro_analysis, portfolio, risk_warnings)

        return report

    def _build_portfolio(self, config: dict, confidence: float) -> Dict[str, dict]:
        """
        构建组合，根据置信度微调权重

        逻辑：
        - confidence > 0.7：使用 base_weight（充分信任模型判断）
        - 0.4 < confidence <= 0.7：向平均权重(1/n)靠拢，取(base_weight + 1/n) / 2
        - confidence <= 0.4：直接使用等权重(1/n)（不确定时保守）
        """
        portfolio = {}
        n_etfs = len(config)

        for code, info in config.items():
            if confidence > 0.7:
                weight = info["base_weight"]
            elif confidence > 0.4:
                weight = (info["base_weight"] + 1.0 / n_etfs) / 2
            else:
                weight = 1.0 / n_etfs

            portfolio[code] = {
                "name": info["name"],
                "type": info["type"],
                "weight": weight
            }

        return portfolio

    def _apply_risk_controls(self, portfolio: Dict) -> tuple[Dict, List[str]]:
        """
        应用风险控制规则

        规则：
        1. 若股票总权重 > 75%：等比例缩减所有股票持仓
        2. 若股票总权重 < 10%：从债券中均摊补足至10%
        3. 若黄金总权重 > 45%：等比例缩减黄金持仓
        4. 最后对所有权重做归一化（保证sum=1.0）
        """
        warnings = []

        # 计算各类资产占比
        stock_ratio = sum(p["weight"] for p in portfolio.values() if p["type"] == "股票")
        gold_ratio = sum(p["weight"] for p in portfolio.values() if p["type"] == "商品")

        # 规则1：股票占比上限
        if stock_ratio > self.CONSTRAINTS["max_stock_ratio"]:
            scale = self.CONSTRAINTS["max_stock_ratio"] / stock_ratio
            for p in portfolio.values():
                if p["type"] == "股票":
                    p["weight"] *= scale
            warnings.append(f"股票占比超限({stock_ratio:.1%})，已调整")

        # 规则2：股票占比下限
        elif stock_ratio < self.CONSTRAINTS["min_stock_ratio"]:
            deficit = self.CONSTRAINTS["min_stock_ratio"] - stock_ratio
            bond_codes = [c for c, p in portfolio.items() if p["type"] == "债券"]
            stock_codes = [c for c, p in portfolio.items() if p["type"] == "股票"]

            if bond_codes and stock_codes:
                per_bond = deficit / len(bond_codes)
                per_stock = deficit / len(stock_codes)

                for code in bond_codes:
                    portfolio[code]["weight"] -= per_bond
                for code in stock_codes:
                    portfolio[code]["weight"] += per_stock

            warnings.append(f"股票占比不足({stock_ratio:.1%})，已调整")

        # 规则3：黄金占比上限
        if gold_ratio > self.CONSTRAINTS["max_gold_ratio"]:
            scale = self.CONSTRAINTS["max_gold_ratio"] / gold_ratio
            for p in portfolio.values():
                if p["type"] == "商品":
                    p["weight"] *= scale
            warnings.append(f"黄金占比超限({gold_ratio:.1%})，已调整")

        # 规则4：归一化（确保总和为1.0）
        total = sum(p["weight"] for p in portfolio.values())
        for p in portfolio.values():
            p["weight"] = round(p["weight"] / total, 4)

        return portfolio, warnings

    def _generate_report(self, macro_analysis: dict, portfolio: Dict, warnings: List[str]) -> dict:
        """生成决策报告"""

        # 构建 portfolio_summary
        portfolio_summary = []
        for code, pos in portfolio.items():
            portfolio_summary.append({
                "code": code,
                "name": pos["name"],
                "type": pos["type"],
                "weight": f"{pos['weight']:.2%}"
            })

        # 按类型汇总资产配置
        asset_summary = {}
        for pos in portfolio.values():
            asset_type = pos["type"]
            asset_summary[asset_type] = asset_summary.get(asset_type, 0) + pos["weight"]

        # 风险检查状态
        risk_check = "通过" if not warnings else f"警告: {'; '.join(warnings)}"

        return {
            "decision_date": macro_analysis.get("metadata", {}).get("input_date"),
            "cycle_phase": macro_analysis["cycle_phase"],
            "confidence": macro_analysis["confidence"],
            "portfolio": portfolio,
            "portfolio_summary": portfolio_summary,
            "asset_allocation": {k: f"{v:.2%}" for k, v in asset_summary.items()},
            "total_weight": sum(p["weight"] for p in portfolio.values()),
            "reasoning": self._build_reasoning(macro_analysis, portfolio),
            "risk_check": risk_check
        }

    def _build_reasoning(self, macro_analysis: dict, portfolio: Dict) -> str:
        """构建决策理由文本"""
        lines = []

        # 宏观研判
        lines.append("【宏观研判】")
        lines.append(macro_analysis.get("analysis", ""))
        lines.append("")

        # 周期判断
        lines.append(f"【周期判断】{macro_analysis['cycle_phase']} (置信度: {macro_analysis['confidence']:.0%})")
        lines.append("")

        # 配置逻辑
        lines.append("【配置逻辑】")
        lines.append(macro_analysis.get("investment_implication", ""))
        lines.append("")

        # 风险提示
        lines.append("【风险提示】")
        for risk in macro_analysis.get("risk_factors", []):
            lines.append(f"- {risk}")
        lines.append("")

        # 最终组合
        lines.append("【最终组合】")
        for code, pos in portfolio.items():
            lines.append(f"  {code} ({pos['name']}): {pos['weight']:.2%}")

        return "\n".join(lines)


# ==================== 测试代码 ====================

if __name__ == "__main__":
    import json

    agent = PortfolioAgent()

    # 测试4种周期
    for cycle in ["复苏期", "扩张期", "滞胀期", "衰退期"]:
        print(f"\n{'='*50}")
        print(f"测试周期: {cycle}")
        print('='*50)

        macro_analysis = {
            "cycle_phase": cycle,
            "confidence": 0.78,
            "analysis": f"当前处于{cycle}，PMI为49.1...",
            "investment_implication": f"{cycle}建议适当配置",
            "risk_factors": ["测试风险1", "测试风险2"],
            "metadata": {"input_date": "2024-03-31"}
        }

        result = agent.decide(macro_analysis)

        print(f"\n组合配置:")
        for item in result["portfolio_summary"]:
            print(f"  {item['code']} ({item['name']}): {item['weight']}")

        print(f"\n资产配置: {result['asset_allocation']}")
        print(f"总权重: {result['total_weight']}")
        print(f"风险检查: {result['risk_check']}")
