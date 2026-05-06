"""
MacroAgent - 宏观分析层模块
使用 LangChain + LLM 分析七维宏观数据，输出结构化投资建议
支持规则兜底模式（无需 API Key）
"""

import os
import math
from typing import Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field

# 尝试导入 LangChain（仅在 use_llm=True 时需要）
try:
    from langchain_openai import ChatOpenAI
    from langchain_core.output_parsers import PydanticOutputParser
    from langchain_core.prompts import ChatPromptTemplate
    _LANGCHAIN_AVAILABLE = True
except ImportError:
    _LANGCHAIN_AVAILABLE = False


# ==================== Pydantic 输出模型 ====================

class MacroAnalysis(BaseModel):
    """宏观分析输出结构"""
    cycle_phase: str = Field(description="经济周期阶段：复苏期/扩张期/滞胀期/衰退期")
    confidence: float = Field(ge=0, le=1, description="置信度 0-1")
    analysis: str = Field(description="综合分析，300字内，必须引用具体数值")
    cpi_signal: str = Field(description="价格信号摘要")
    liquidity_signal: str = Field(description="流动性信号摘要")
    credit_signal: str = Field(description="信用信号摘要")
    investment_implication: str = Field(description="资产配置建议")
    risk_factors: List[str] = Field(description="2-4个风险点")
    key_signals: List[str] = Field(description="3-5个关键信号，含具体数值")


# ==================== MacroAgent ====================

class MacroAgent:
    """宏观分析Agent - 支持 LLM 分析和规则兜底"""

    SYSTEM_PROMPT = """你是一位拥有20年经验的资深宏观经济学家，曾任央行货币政策委员会委员、主权基金首席投资官。

专业领域：
- 中国制造业PMI指标体系及经济周期研究
- CPI/PPI价格体系与通胀传导机制
- M2货币供应与信用扩张的资产定价影响
- 社融数据解读与未来需求预测
- 基于多维宏观数据的资产配置策略

## 数据时效性说明（重要）

各宏观指标的发布时间存在差异，因此同一决策日期下不同指标的数据时点可能相差1-2个月：
- PMI：次月1日可用，数据时效最新
- CPI/PPI：次月10日可用
- M2/社融：次月15日可用，滞后最长
- GDP：季末后第16日可用（季度数据，更新最慢）

分析时请注意各指标的"数据时点"标注，优先参考时效最新的指标（PMI）作为当前景气锚点。

## 宏观分析框架

**景气信号（PMI）：**
- PMI > 50：制造业扩张，经济景气
- PMI < 50：制造业收缩，经济承压
- 趋势比绝对值更重要：连续3月上行是强复苏信号

**价格信号（CPI/PPI）：**
- CPI > 3%：通胀过热，警惕滞胀
- PPI > CPI：上游涨价无法传导，企业利润受压
- PPI 通缩（< 0）+ CPI 低位：需求不足，衰退风险

**流动性信号（M2/SHIBOR）：**
- M2 增速 > 10%：货币宽松，利好资产价格
- SHIBOR 持续下行：央行宽松，流动性充裕

**信用信号（社融/GDP）：**
- 社融增量领先实体经济 3-6 个月
- 社融增速加速 → 未来增长动能增强

**周期四象限判断：**
1. 复苏期：PMI 回升 + CPI 低位 + 社融改善 + SHIBOR 较低
2. 扩张期：PMI > 50 稳定 + CPI 温和 + M2/社融旺盛
3. 滞胀期：PMI > 50 但下滑 + CPI 高位 + PPI 高位
4. 衰退期：PMI < 50 持续 + CPI/PPI 下行 + 社融萎缩

## 输出要求
请基于提供的多维宏观数据，给出专业的周期判断和资产配置建议。
分析要专业、简洁，像给投资委员会汇报。必须用具体数值支撑判断。"""

    def __init__(self, model_name: str = None, use_llm: bool = False):
        """
        初始化 MacroAgent

        Args:
            model_name: 模型名称，None 时从环境变量读取
            use_llm: 是否使用 LLM，False 时使用规则兜底
        """
        self.use_llm = use_llm and _LANGCHAIN_AVAILABLE
        self.llm = None
        self.parser = None

        if self.use_llm:
            try:
                # 从环境变量读取配置
                api_key = os.getenv("LLM_API_KEY")
                api_base = os.getenv("LLM_API_BASE")
                model = model_name or os.getenv("MODEL_NAME", "gpt-4o-mini")

                if not api_key or api_key == "your_api_key":
                    print("[INFO] LLM API Key 未配置，使用规则兜底模式")
                    self.use_llm = False
                    return

                self.llm = ChatOpenAI(
                    model=model,
                    api_key=api_key,
                    base_url=api_base,
                    temperature=0.2,
                    max_tokens=1500,
                )
                self.parser = PydanticOutputParser(pydantic_object=MacroAnalysis)
                print(f"[OK] MacroAgent 初始化完成，使用 LLM 模式: {model}")
            except Exception as e:
                print(f"[WARN] LLM初始化失败，使用规则兜底: {e}")
                self.use_llm = False
        else:
            print("[OK] MacroAgent 初始化完成，使用规则兜底模式")

    def analyze(self, macro_data) -> Dict[str, Any]:
        """主分析方法"""
        if not self.use_llm:
            return self._fallback_analyze(macro_data)
        try:
            return self._llm_analyze(macro_data)
        except Exception as e:
            print(f"[WARN] LLM分析失败，使用兜底逻辑: {e}")
            return self._fallback_analyze(macro_data)

    def _build_macro_summary(self, macro_data) -> str:
        """构建宏观指标摘要"""
        return f"""
## 宏观指标快照（决策日期：{macro_data.decision_date.strftime('%Y-%m-%d')}）

### 景气指数
- 制造业PMI：{macro_data.pmi}（数据时点：{macro_data.pmi_date.strftime('%Y-%m')}）
  近6月走势：{macro_data.pmi_history}
  趋势：{self._describe_trend(macro_data.pmi_history, 'PMI')}

### 价格指标
- CPI同比：{macro_data.cpi_yoy}%（数据时点：{macro_data.cpi_date.strftime('%Y-%m')}）
  近6月：{macro_data.cpi_history}
- PPI同比：{macro_data.ppi_yoy}%（数据时点：{macro_data.ppi_date.strftime('%Y-%m')}）
  近6月：{macro_data.ppi_history}

### 流动性
- M2同比：{macro_data.m2_yoy}%（近6月：{macro_data.m2_history}）
- SHIBOR 1m：{macro_data.shibor_1m}%，3m：{macro_data.shibor_3m}%
  （数据时点：{macro_data.shibor_date.strftime('%Y-%m-%d')}）

### 信用与增长
- 社融增量当月：{macro_data.sf_month:.0f}亿元
  近6月：{[f'{v:.0f}' for v in macro_data.sf_history]}亿元
- GDP当季同比：{macro_data.gdp_yoy}%（{macro_data.gdp_quarter}）
"""

    def _describe_trend(self, history: List[float], name: str) -> str:
        """描述指标趋势"""
        if len(history) < 2:
            return f"{name}数据不足"

        recent = history[-3:] if len(history) >= 3 else history
        diff = recent[-1] - recent[0]

        # 不同指标的阈值
        if name == "PMI":
            threshold = 0.3
        elif name in ("CPI", "PPI"):
            threshold = 0.5
        else:
            threshold = 0.2

        if diff > threshold:
            return f"近{len(recent)}月上升趋势（{recent[0]}→{recent[-1]}，+{diff:.1f}）"
        elif diff < -threshold:
            return f"近{len(recent)}月下行趋势（{recent[0]}→{recent[-1]}，{diff:.1f}）"
        else:
            return f"近{len(recent)}月基本持平（{recent[0]}→{recent[-1]}）"

    def _llm_analyze(self, macro_data) -> Dict[str, Any]:
        """使用 LLM 进行分析"""
        # 构建提示
        macro_summary = self._build_macro_summary(macro_data)
        user_prompt = f"""决策日期：{macro_data.decision_date.strftime('%Y-%m-%d')}

{macro_summary}

请判断当前经济周期阶段并给出投资建议。

{self.parser.get_format_instructions()}"""

        prompt = ChatPromptTemplate.from_messages([
            ("system", self.SYSTEM_PROMPT),
            ("human", user_prompt)
        ])

        # LCEL 链式调用
        chain = prompt | self.llm | self.parser
        result = chain.invoke({})

        # 添加元数据
        output = result.model_dump()
        output["metadata"] = {
            "input_pmi": macro_data.pmi,
            "input_date": macro_data.pmi_date.strftime("%Y-%m-%d"),
            "source": "llm"
        }
        return output

    def _fallback_analyze(self, macro_data) -> Dict[str, Any]:
        """规则兜底分析（当 LLM 不可用时）"""
        score = 0

        # PMI信号（权重最高，计2分）
        if macro_data.pmi > 51:
            score += 2
        elif macro_data.pmi > 50:
            score += 1
        elif macro_data.pmi > 48:
            score -= 1
        else:
            score -= 2

        # PMI趋势
        if len(macro_data.pmi_history) >= 2:
            score += 1 if macro_data.pmi_history[-1] > macro_data.pmi_history[0] else -1

        # CPI/PPI信号
        if not math.isnan(macro_data.cpi_yoy):
            if macro_data.cpi_yoy > 3.0:
                score += 1
            elif macro_data.cpi_yoy < 0:
                score -= 1

        # M2信号
        if not math.isnan(macro_data.m2_yoy):
            if macro_data.m2_yoy > 10:
                score += 1
            elif macro_data.m2_yoy < 7:
                score -= 1

        # 社融信号
        if macro_data.sf_history:
            sf_avg = sum(macro_data.sf_history) / len(macro_data.sf_history)
            score += 1 if macro_data.sf_month > sf_avg * 1.1 else -1

        # 周期判断
        if score >= 4:
            cycle, conf = "扩张期", 0.75
            implication = "经济繁荣，建议重仓股票资产，适当减少债券"
        elif score >= 1:
            cycle, conf = "复苏期", 0.60
            implication = "经济回暖，建议增配股票，保留部分债券防御"
        elif score >= -2:
            cycle, conf = "滞胀期", 0.55
            implication = "经济放缓，建议平衡配置，增持黄金对冲通胀"
        else:
            cycle, conf = "衰退期", 0.70
            implication = "经济收缩，建议防御配置，重仓债券和黄金"

        return {
            "cycle_phase": cycle,
            "confidence": conf,
            "analysis": f"PMI={macro_data.pmi}, CPI同比={macro_data.cpi_yoy}%, PPI同比={macro_data.ppi_yoy}%, M2增速={macro_data.m2_yoy}%，基于规则打分({score}分)判断为{cycle}",
            "cpi_signal": f"CPI同比{macro_data.cpi_yoy}%, PPI同比{macro_data.ppi_yoy}%",
            "liquidity_signal": f"M2增速{macro_data.m2_yoy}%, SHIBOR-1m {macro_data.shibor_1m}%",
            "credit_signal": f"社融当月{macro_data.sf_month:.0f}亿, GDP增速{macro_data.gdp_yoy}%",
            "investment_implication": implication,
            "risk_factors": ["LLM调用异常，使用规则兜底"],
            "key_signals": [
                f"PMI={macro_data.pmi}",
                f"CPI同比={macro_data.cpi_yoy}%",
                f"PPI同比={macro_data.ppi_yoy}%",
                f"M2增速={macro_data.m2_yoy}%"
            ],
            "metadata": {
                "input_pmi": macro_data.pmi,
                "input_date": macro_data.pmi_date.strftime("%Y-%m-%d"),
                "source": "fallback",
                "score": score
            }
        }


# ==================== 测试代码 ====================

if __name__ == "__main__":
    from pydantic import BaseModel
    from typing import List

    # 定义测试用 MacroData（与 data_agent.py 中的 MacroData 兼容）
    class TestMacroData(BaseModel):
        decision_date: datetime
        pmi: float
        pmi_history: List[float]
        pmi_date: datetime
        cpi_yoy: float
        cpi_history: List[float]
        cpi_date: datetime
        ppi_yoy: float
        ppi_history: List[float]
        ppi_date: datetime
        m2_yoy: float
        m2_history: List[float]
        m2_date: datetime
        sf_month: float
        sf_history: List[float]
        sf_date: datetime
        gdp_yoy: float
        gdp_quarter: str
        shibor_1m: float
        shibor_3m: float
        shibor_date: datetime

    # 构造测试数据
    test_data = TestMacroData(
        decision_date=datetime(2024, 3, 31),
        pmi=49.1,
        pmi_history=[49.5, 49.8, 50.1, 49.9, 49.3, 49.1],
        pmi_date=datetime(2024, 2, 29),
        cpi_yoy=0.7,
        cpi_history=[0.5, 0.7, 0.2, 0.1, 0.7, 0.7],
        cpi_date=datetime(2024, 2, 29),
        ppi_yoy=-2.7,
        ppi_history=[-2.5, -2.4, -2.5, -2.6, -2.5, -2.7],
        ppi_date=datetime(2024, 2, 29),
        m2_yoy=8.7,
        m2_history=[9.5, 9.3, 9.1, 8.9, 8.7, 8.7],
        m2_date=datetime(2024, 2, 29),
        sf_month=15623.0,
        sf_history=[19109.0, 34581.0, 16158.0, 6274.0, 9046.0, 15623.0],
        sf_date=datetime(2024, 2, 29),
        gdp_yoy=5.2,
        gdp_quarter="2023Q4",
        shibor_1m=1.85,
        shibor_3m=1.91,
        shibor_date=datetime(2024, 3, 29)
    )

    # 测试 fallback 模式（无需 API Key）
    agent = MacroAgent(use_llm=False)
    result = agent.analyze(test_data)

    import json
    print(json.dumps(result, ensure_ascii=False, indent=2))
