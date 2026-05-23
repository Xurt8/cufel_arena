"""
Xu-ETFplan — Arena 竞赛策略
============================
基于 MacroDrivenETFAgent 完整版，包含：
- DeepSeek LLM 宏观分析（规则兜底）
- 统一4因子评分（60日位35% + 动量25% + 120日位20% + 低波20%）
- 残差相关性去重（22日滚动，阈值0.95）
- 波动率自适应仓位
- 动态ETF候选池
- Theta风险偏好调节
"""
import os, sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

# 加载 .env（LLM_API_KEY 等）
try:
    from dotenv import load_dotenv
    # 优先 config/arena.env，回退同目录 .env
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(_THIS_DIR))), "config", "arena.env")
    if os.path.exists(env_path):
        load_dotenv(env_path)
    else:
        load_dotenv(os.path.join(_THIS_DIR, ".env"))
except ImportError:
    pass

from .engine import MacroDrivenETFAgent


class XuETFplan(MacroDrivenETFAgent):
    """Arena 竞赛策略 — 继承 MacroDrivenETFAgent 全部改进"""

    def __init__(self, **kwargs):
        kwargs.setdefault("use_llm", True)
        super().__init__(**kwargs)
        self.name = "Xu-ETFplan"
        print(f"[Xu-ETFplan] LLM={'启用' if self.macro_agent.use_llm else '规则兜底'} | {self.name}")
