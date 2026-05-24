"""
Macro Driven ETF Agent - 宏观驱动ETF策略
继承 ETFAgentBase，实现 cufel_arena 竞赛接口
"""

import os
import json
import math
import warnings
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import numpy as np
from dotenv import load_dotenv
try:
    from pydantic import BaseModel
except ImportError:
    BaseModel = object

# 路径配置 - 使用 __file__ 计算绝对路径
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "macro")
_CACHE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "cache")

# 加载环境变量
load_dotenv(os.path.join(_THIS_DIR, ".env"))

# 尝试导入 cufel_arena_agent
try:
    from cufel_arena_agent import ETFAgentBase
    _CUFEL_AVAILABLE = True
except ImportError:
    _CUFEL_AVAILABLE = False
    # 本地测试用基础类
    class ETFAgentBase:
        def __init__(self, name="MacroDrivenETF", **kwargs):
            self.name = name


# ==================== DataAgent ====================

from dataclasses import dataclass, field

@dataclass
class MacroData:
    """完整宏观数据结构"""
    decision_date: datetime
    pmi: float = float('nan')
    pmi_history: list = field(default_factory=list)
    pmi_date: datetime = None
    cpi_yoy: float = float('nan')
    cpi_history: list = field(default_factory=list)
    cpi_date: datetime = None
    ppi_yoy: float = float('nan')
    ppi_history: list = field(default_factory=list)
    ppi_date: datetime = None
    m2_yoy: float = float('nan')
    m2_history: list = field(default_factory=list)
    m2_date: datetime = None
    sf_month: float = float('nan')
    sf_history: list = field(default_factory=list)
    sf_date: datetime = None
    gdp_yoy: float = float('nan')
    gdp_quarter: str = ''
    shibor_1m: float = float('nan')
    shibor_3m: float = float('nan')
    shibor_date: datetime = None


class DataAgent:
    """数据层Agent"""

    def __init__(self, data_path: str = None):
        self.data_path = Path(data_path) if data_path else Path(_DATA_PATH)
        self.pmi_data: Optional[pd.DataFrame] = None
        self.cpi_data: Optional[pd.DataFrame] = None
        self.ppi_data: Optional[pd.DataFrame] = None
        self.m2_data: Optional[pd.DataFrame] = None
        self.sf_data: Optional[pd.DataFrame] = None
        self.gdp_data: Optional[pd.DataFrame] = None
        self.shibor_data: Optional[pd.DataFrame] = None

    def load_all_data(self) -> None:
        """加载所有宏观数据"""
        self._load_pmi()
        self._load_cpi()
        self._load_ppi()
        self._load_m()
        self._load_sf()
        self._load_gdp()
        self._load_shibor()

    def _load_pmi(self) -> None:
        try:
            file_path = self.data_path / "cn_pmi.csv"
            df = pd.read_csv(file_path)
            df = df.rename(columns={"month": "date_str", "pmi": "pmi"})
            df["date"] = pd.to_datetime(df["date_str"], format="mixed") + pd.offsets.MonthEnd(0)
            df = df[["date", "pmi"]].sort_values("date")
            self.pmi_data = df
        except Exception as e:
            warnings.warn(f"PMI data load failed: {e}")
            self.pmi_data = pd.DataFrame(columns=["date", "pmi"])

    def _load_cpi(self) -> None:
        try:
            file_path = self.data_path / "cn_cpi.csv"
            df = pd.read_csv(file_path)
            df = df.rename(columns={"month": "date_str", "cpi": "cpi_yoy"})
            df["date"] = pd.to_datetime(df["date_str"], format="mixed") + pd.offsets.MonthEnd(0)
            df = df[df["date"] >= "2020-01-01"]
            df = df[["date", "cpi_yoy"]].sort_values("date")
            self.cpi_data = df
        except Exception as e:
            warnings.warn(f"CPI data load failed: {e}")
            self.cpi_data = pd.DataFrame(columns=["date", "cpi_yoy"])

    def _load_ppi(self) -> None:
        try:
            file_path = self.data_path / "cn_ppi.csv"
            df = pd.read_csv(file_path)
            df = df.rename(columns={"month": "date_str", "ppi": "ppi_yoy"})
            df["date"] = pd.to_datetime(df["date_str"], format="mixed") + pd.offsets.MonthEnd(0)
            df = df[["date", "ppi_yoy"]].sort_values("date")
            self.ppi_data = df
        except Exception as e:
            warnings.warn(f"PPI data load failed: {e}")
            self.ppi_data = pd.DataFrame(columns=["date", "ppi_yoy"])

    def _load_m(self) -> None:
        try:
            file_path = self.data_path / "cn_m.csv"
            df = pd.read_csv(file_path)
            df = df.rename(columns={"month": "date_str", "m2": "m2_yoy"})
            df["date"] = pd.to_datetime(df["date_str"], format="mixed") + pd.offsets.MonthEnd(0)
            df = df[["date", "m2_yoy"]].sort_values("date")
            self.m2_data = df
        except Exception as e:
            warnings.warn(f"M2 data load failed: {e}")
            self.m2_data = pd.DataFrame(columns=["date", "m2_yoy"])

    def _load_sf(self) -> None:
        try:
            file_path = self.data_path / "sf_month.csv"
            df = pd.read_csv(file_path)
            df = df.rename(columns={"月份": "date_str", "社融增量当月值": "sf_month"})
            df["date"] = pd.to_datetime(df["date_str"], format="mixed") + pd.offsets.MonthEnd(0)
            df = df[["date", "sf_month"]].sort_values("date")
            self.sf_data = df
        except Exception as e:
            warnings.warn(f"SF data load failed: {e}")
            self.sf_data = pd.DataFrame(columns=["date", "sf_month"])

    def _load_gdp(self) -> None:
        try:
            file_path = self.data_path / "cn_gdp.csv"
            df = pd.read_csv(file_path)
            df = df.rename(columns={"quarter": "quarter_str", "当季同比增速（%）": "gdp_yoy"})

            def quarter_to_end_date(q_str: str) -> pd.Timestamp:
                year = int(q_str[:4])
                q = int(q_str[-1])
                month = q * 3
                return pd.Timestamp(year, month, 1) + pd.offsets.MonthEnd(0)

            df["date"] = df["quarter_str"].apply(quarter_to_end_date)
            df = df[["date", "gdp_yoy", "quarter_str"]].sort_values("date")
            self.gdp_data = df
        except Exception as e:
            warnings.warn(f"GDP data load failed: {e}")
            self.gdp_data = pd.DataFrame(columns=["date", "gdp_yoy", "quarter_str"])

    def _load_shibor(self) -> None:
        try:
            file_path = self.data_path / "shibor.csv"
            df = pd.read_csv(file_path)
            df.columns = df.columns.str.strip()
            df = df.rename(columns={"date": "date_str", "1m": "shibor_1m", "3m": "shibor_3m"})
            df["date"] = pd.to_datetime(df["date_str"].astype(str), format="%Y%m%d")
            df = df[["date", "shibor_1m", "shibor_3m"]].sort_values("date")
            self.shibor_data = df
        except Exception as e:
            warnings.warn(f"SHIBOR data load failed: {e}")
            self.shibor_data = pd.DataFrame(columns=["date", "shibor_1m", "shibor_3m"])

    @staticmethod
    def _publication_cutoff(data_date: pd.Timestamp, indicator: str) -> pd.Timestamp:
        m, y = data_date.month, data_date.year
        next_month_first = pd.Timestamp(y + 1, 1, 1) if m == 12 else pd.Timestamp(y, m + 1, 1)

        if indicator == "pmi":
            return next_month_first
        elif indicator in ("cpi", "ppi"):
            return next_month_first.replace(day=10)
        elif indicator in ("m2", "sf"):
            return next_month_first.replace(day=15)
        elif indicator == "gdp":
            return data_date + pd.Timedelta(days=16)
        else:
            return data_date + pd.Timedelta(days=1)

    def get_macro_for_decision(self, decision_date: datetime, strict_publication_lag: bool = True) -> MacroData:
        """获取决策日期可用的宏观数据"""
        decision_ts = pd.Timestamp(decision_date)

        def get_latest(df, key_col, indicator, n=6):
            if df is None or len(df) == 0:
                raise ValueError(f"No data for {key_col}")

            if strict_publication_lag:
                available = df["date"].apply(
                    lambda d: DataAgent._publication_cutoff(pd.Timestamp(d), indicator) <= decision_ts
                )
                valid = df[available].copy()
            else:
                valid = df[df["date"] < decision_ts].copy()

            if len(valid) == 0:
                raise ValueError(f"No available data for {key_col}")

            latest = valid.iloc[-1]
            history = valid.tail(n)[key_col].tolist()

            return latest, history

        # 各指标逐一获取，缺失时用 NaN 兜底（避免早期数据不足导致整体失败）
        def _safe_get(df, key_col, indicator, n=6, default_val=None):
            try: return get_latest(df, key_col, indicator, n)
            except (ValueError, KeyError, TypeError, IndexError): return (None, []) if default_val is None else default_val

        pmi_latest, pmi_hist = _safe_get(self.pmi_data, "pmi", "pmi")
        cpi_latest, cpi_hist = _safe_get(self.cpi_data, "cpi_yoy", "cpi")
        ppi_latest, ppi_hist = _safe_get(self.ppi_data, "ppi_yoy", "ppi")
        m2_latest, m2_hist = _safe_get(self.m2_data, "m2_yoy", "m2")
        sf_latest, sf_hist = _safe_get(self.sf_data, "sf_month", "sf")
        gdp_latest, _ = _safe_get(self.gdp_data, "gdp_yoy", "gdp", n=4, default_val=(None, []))

        if self.shibor_data is not None and len(self.shibor_data) > 0:
            shibor_valid = self.shibor_data[self.shibor_data["date"] < decision_ts]
            shibor_latest = shibor_valid.iloc[-1] if len(shibor_valid) > 0 else None
        else:
            shibor_latest = None

        sentinel_date = pd.Timestamp('2000-01-01')  # 缺失数据的占位日期
        return MacroData(
            decision_date=decision_date,
            pmi=float(pmi_latest["pmi"]) if pmi_latest is not None else float('nan'),
            pmi_history=pmi_hist if pmi_hist else [],
            pmi_date=pd.Timestamp(pmi_latest["date"]) if pmi_latest is not None else sentinel_date,
            cpi_yoy=float(cpi_latest["cpi_yoy"]) if cpi_latest is not None else float('nan'),
            cpi_history=cpi_hist if cpi_hist else [],
            cpi_date=pd.Timestamp(cpi_latest["date"]) if cpi_latest is not None else sentinel_date,
            ppi_yoy=float(ppi_latest["ppi_yoy"]) if ppi_latest is not None else float('nan'),
            ppi_history=ppi_hist if ppi_hist else [],
            ppi_date=pd.Timestamp(ppi_latest["date"]) if ppi_latest is not None else sentinel_date,
            m2_yoy=float(m2_latest["m2_yoy"]) if m2_latest is not None else float('nan'),
            m2_history=m2_hist if m2_hist else [],
            m2_date=pd.Timestamp(m2_latest["date"]) if m2_latest is not None else sentinel_date,
            sf_month=float(sf_latest["sf_month"]) if sf_latest is not None else float('nan'),
            sf_history=sf_hist if sf_hist else [],
            sf_date=pd.Timestamp(sf_latest["date"]) if sf_latest is not None else sentinel_date,
            gdp_yoy=float(gdp_latest["gdp_yoy"]) if gdp_latest is not None else float('nan'),
            gdp_quarter=str(gdp_latest["quarter_str"]) if gdp_latest is not None else '',
            shibor_1m=float(shibor_latest["shibor_1m"]) if shibor_latest is not None else float('nan'),
            shibor_3m=float(shibor_latest["shibor_3m"]) if shibor_latest is not None else float('nan'),
            shibor_date=pd.Timestamp(shibor_latest["date"]) if shibor_latest is not None else sentinel_date
        )


# ==================== MacroAgent ====================

class MacroAgent:
    """宏观分析Agent — 七维指标框架(VibeCodingPrompts规范)"""

    LLM_URL = os.getenv("LLM_API_BASE", "https://api.deepseek.com/v1") + "/chat/completions"
    LLM_KEY = os.getenv("LLM_API_KEY", "sk-63010d7a99a245fa992eb68a89d01f97")
    LLM_MODEL = os.getenv("MODEL_NAME", "deepseek-chat")

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
- 社融增速加速 -> 未来增长动能增强

**周期四象限判断：**
1. 复苏期：PMI 回升 + CPI 低位 + 社融改善 + SHIBOR 较低
2. 扩张期：PMI > 50 稳定 + CPI 温和 + M2/社融旺盛
3. 滞胀期：PMI > 50 但下滑 + CPI 高位 + PPI 高位
4. 衰退期：PMI < 50 持续 + CPI/PPI 下行 + 社融萎缩

## 输出要求
请基于提供的多维宏观数据，给出专业的周期判断和资产配置建议。
分析要专业、简洁，像给投资委员会汇报。必须用具体数值支撑判断。"""

    def __init__(self, use_llm: bool = False):
        self.use_llm = use_llm
        self._llm_cache = {}

    def _describe_trend(self, history: list, name: str) -> str:
        """描述指标趋势"""
        if len(history) < 2:
            return f"{name}数据不足"

        recent = history[-3:] if len(history) >= 3 else history
        diff = recent[-1] - recent[0]

        if name == "PMI":
            threshold = 0.3
        elif name in ("CPI", "PPI"):
            threshold = 0.5
        else:
            threshold = 0.2

        if diff > threshold:
            return f"近{len(recent)}月上升趋势（{recent[0]}->{recent[-1]}，+{diff:.1f}）"
        elif diff < -threshold:
            return f"近{len(recent)}月下行趋势（{recent[0]}->{recent[-1]}，{diff:.1f}）"
        else:
            return f"近{len(recent)}月基本持平（{recent[0]}->{recent[-1]}）"

    def _build_macro_summary(self, macro_data) -> str:
        """构建宏观指标摘要"""
        import math
        sf_str = f"{macro_data.sf_month:.0f}" if not math.isnan(macro_data.sf_month) else "N/A"
        sf_hist = [f"{v:.0f}" for v in macro_data.sf_history] if macro_data.sf_history else []
        gdp_str = f"{macro_data.gdp_yoy}%" if not math.isnan(macro_data.gdp_yoy) else "N/A"

        pmi_date_str = macro_data.pmi_date.strftime('%Y-%m') if macro_data.pmi_date else 'N/A'
        cpi_date_str = macro_data.cpi_date.strftime('%Y-%m') if macro_data.cpi_date else 'N/A'
        ppi_date_str = macro_data.ppi_date.strftime('%Y-%m') if macro_data.ppi_date else 'N/A'
        shibor_date_str = macro_data.shibor_date.strftime('%Y-%m-%d') if macro_data.shibor_date else 'N/A'

        return f"""
## 宏观指标快照

### 景气指数
- 制造业PMI：{macro_data.pmi}（数据时点：{pmi_date_str}）
  近6月走势：{macro_data.pmi_history}
  趋势：{self._describe_trend(macro_data.pmi_history, 'PMI')}

### 价格指标
- CPI同比：{macro_data.cpi_yoy}%（数据时点：{cpi_date_str}）
  近6月：{macro_data.cpi_history}
- PPI同比：{macro_data.ppi_yoy}%（数据时点：{ppi_date_str}）
  近6月：{macro_data.ppi_history}

### 流动性
- M2同比：{macro_data.m2_yoy}%（近6月：{macro_data.m2_history}）
- SHIBOR 1m：{macro_data.shibor_1m}%，3m：{macro_data.shibor_3m}%
  （数据时点：{shibor_date_str}）

### 信用与增长
- 社融增量当月：{sf_str}亿元
  近6月：{sf_hist}亿元
- GDP当季同比：{gdp_str}（{macro_data.gdp_quarter}）
"""

    def _analyze_llm(self, macro_data) -> Dict:
        """调用 LLM 判断经济周期，失败时返回 None"""
        import requests, math

        dt = getattr(macro_data, 'decision_date', None)
        date_str = dt.strftime("%Y-%m-%d") if dt else ''
        if date_str and date_str in self._llm_cache:
            return self._llm_cache[date_str]

        macro_summary = self._build_macro_summary(macro_data)

        prompt = f"""决策日期：{date_str}

{macro_summary}

请判断当前经济周期阶段（复苏期/扩张期/滞胀期/衰退期）并给出投资建议。

请严格按以下格式回复（不要有任何多余文字）：
周期: [阶段]
置信度: [0.0-1.0的小数]
分析: [200字以内，引用具体数值]
投资建议: [一句话资产配置建议]"""

        try:
            r = requests.post(self.LLM_URL,
                headers={"Authorization": f"Bearer {self.LLM_KEY}", "Content-Type": "application/json"},
                json={"model": self.LLM_MODEL,
                      "messages": [{"role": "system", "content": self.SYSTEM_PROMPT},
                                   {"role": "user", "content": prompt}],
                      "max_tokens": 400, "temperature": 0.2},
                timeout=30)
            if r.status_code != 200:
                return None

            text = r.json()["choices"][0]["message"]["content"]

            cycle = None; conf = 0.7; analysis = ""; implication = ""
            cycle_map = {
                "扩张": "扩张期", "膨胀": "扩张期", "繁荣": "扩张期", "过热": "扩张期",
                "复苏": "复苏期", "回升": "复苏期", "回暖": "复苏期",
                "滞胀": "滞胀期", "滞涨": "滞胀期", "放缓": "滞胀期",
                "衰退": "衰退期", "收缩": "衰退期", "萧条": "衰退期", "低迷": "衰退期",
            }
            for line in text.replace("\uff1a", ":").split("\n"):
                line = line.strip()
                if ("周期" in line or "阶段" in line) and ":" in line:
                    keyword = line.split(":")[-1].strip()
                    for k, v in cycle_map.items():
                        if k in keyword: cycle = v; break
                if ("置信" in line or "conf" in line.lower()) and ":" in line:
                    try:
                        val = line.split(":")[-1].strip().split()[0]
                        conf = float(val)
                    except: pass
                if ("分析" in line or "理由" in line) and ":" in line:
                    analysis = line.split(":", 1)[-1].strip()[:200]
                if ("建议" in line or "投资" in line) and ":" in line:
                    implication = line.split(":", 1)[-1].strip()

            if cycle is None:
                return None

            if not analysis:
                analysis = text.strip()[:200]

            result = {
                "cycle_phase": cycle,
                "confidence": conf,
                "analysis": analysis,
                "investment_implication": implication,
                "risk_factors": [],
                "metadata": {"source": "llm", "score": 0}
            }
            if date_str:
                self._llm_cache[date_str] = result
            return result
        except Exception:
            return None

    def _fallback_analyze(self, macro_data) -> Dict:
        """规则兜底分析（当 LLM 不可用时）"""
        import math

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
        sf_hist = macro_data.sf_history
        if sf_hist and len(sf_hist) >= 2:
            sf_avg = sum(sf_hist[:-1]) / (len(sf_hist) - 1) if len(sf_hist) > 1 else sf_hist[0]
            if not math.isnan(macro_data.sf_month) and sf_avg > 0:
                score += 1 if macro_data.sf_month > sf_avg * 1.1 else (-1 if macro_data.sf_month < sf_avg * 0.9 else 0)

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

        pmi_date_str = macro_data.pmi_date.strftime("%Y-%m-%d") if macro_data.pmi_date else ""

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
                "input_date": pmi_date_str,
                "source": "fallback",
                "score": score
            }
        }

    def analyze(self, macro_data) -> Dict:
        """主分析方法：LLM优先，规则兜底"""
        if not self.use_llm:
            return self._fallback_analyze(macro_data)
        try:
            result = self._analyze_llm(macro_data)
            if result is not None:
                return result
            return self._fallback_analyze(macro_data)
        except Exception as e:
            print(f"LLM分析失败，使用兜底逻辑: {e}")
            return self._fallback_analyze(macro_data)


# ==================== PortfolioAgent ====================

class PortfolioAgent:
    """组合决策Agent — 宏观定类别权重 + 技术面动态选ETF"""

    # 第一层：宏观周期 → 资产类别目标权重（股票/债券/商品）
    CLASS_TARGETS = {
        "复苏期": {"Stock": 0.60, "Bond": 0.25, "Commodity": 0.15},
        "扩张期": {"Stock": 0.75, "Bond": 0.15, "Commodity": 0.10},
        "滞胀期": {"Stock": 0.25, "Bond": 0.35, "Commodity": 0.40},
        "衰退期": {"Stock": 0.15, "Bond": 0.70, "Commodity": 0.15},
    }

    # 第二层：候选ETF池（必须通过 set_etf_universe() 注入动态宇宙）
    ETF_UNIVERSE = {"Stock": [], "Bond": [], "Commodity": []}

    # 每类最多选几只
    TOP_N = {"Stock": 5, "Bond": 2, "Commodity": 2}

    CONSTRAINTS = {
        "max_single_etf": 0.55,
        "max_stock_ratio": 0.75,
        "min_stock_ratio": 0.10,
        "max_gold_ratio": 0.45,
    }

    # 去重关键词（非股票类ETF用，股票类优先SW1行业）
    INDEX_PATTERNS = [
        ("黄金", "黄金"), ("上海金", "黄金"), ("金ETF", "黄金"),
        ("国债", "国债"), ("城投债", "城投债"), ("转债", "可转债"),
        ("信用债", "信用债"), ("短融", "短融"), ("科创债", "科创债"),
        ("公司债", "公司债"),
        ("货币", "货币"), ("添益", "货币"),
        ("科创", "科创"), ("半导体", "芯片"), ("芯片", "芯片"),
        ("消费电子", "消费电子"), ("消电", "消费电子"),
        ("A500", "A500"), ("沪深300", "沪深300"), ("中证500", "中证500"),
        ("创业板", "创业板"), ("双创", "双创"), ("上证50", "上证50"),
        ("红利", "红利"), ("证券", "证券"), ("银行", "银行"),
        ("新能源", "新能源"), ("光伏", "新能源"),
        ("石油ETF", "石油"), ("养殖", "养殖"), ("粮食", "粮食"),
        ("医药", "医药"), ("医疗", "医药"),
        ("军工", "军工"), ("通信", "通信"), ("5G", "通信"),
        ("汽车", "汽车"), ("机器人", "机器人"),
        ("港股", "港股"), ("恒生", "港股"),
    ]
    _sector_map = None

    @classmethod
    def _get_sector_map(cls):
        """懒加载 ETF → SW1行业 映射"""
        if cls._sector_map is not None:
            return cls._sector_map
        cls._sector_map = {}
        try:
            try:
                from data.local_store import get_sector_map
            except ImportError:
                from src.data.local_store import get_sector_map
            cached = get_sector_map()
            stock_set = cached.get("stock", set())
            # 对股票型ETF，进一步按SW1行业分类
            import sys, os
            _qmt_lib = r'D:/长城策略交易系统/bin.x64/Lib/site-packages'
            if _qmt_lib not in sys.path:
                sys.path.insert(0, _qmt_lib)
            from xtquant import xtdata
            sw1_sectors = [s for s in xtdata.get_sector_list() if s.startswith('SW1') and not s.startswith('SW1加权')]
            for sw1 in sw1_sectors:
                stocks = set(xtdata.get_stock_list_in_sector(sw1))
                label = sw1.replace('SW1', '')
                for qc in stocks:
                    if qc in stock_set:
                        cls._sector_map[qc] = label
        except Exception:
            pass
        return cls._sector_map

    @classmethod
    def _extract_index(cls, name: str) -> str:
        """去重标识：按 INDEX_PATTERNS 关键词匹配"""
        for kw, idx in cls.INDEX_PATTERNS:
            if kw in name:
                return idx
        return name

    SCORE_WEIGHTS = {"mom": 0.20, "vol": 0.45, "sharpe": 0.20, "flow": 0.15}  # default (衰退/防御)
    CYCLE_WEIGHTS = {
        "复苏期": {"mom": 0.35, "vol": 0.20, "sharpe": 0.25, "flow": 0.20},
        "扩张期": {"mom": 0.25, "vol": 0.30, "sharpe": 0.25, "flow": 0.20},
        "滞胀期": {"mom": 0.10, "vol": 0.50, "sharpe": 0.20, "flow": 0.20},
        "衰退期": {"mom": 0.15, "vol": 0.45, "sharpe": 0.20, "flow": 0.20},
    }
    LAZY_LAMBDA = 0.0

    @classmethod
    def _score_etf(cls, metrics: dict) -> float:
        """统一因子评分 — 动量+低波+夏普+量比，同类内部排序"""
        w = cls.SCORE_WEIGHTS
        mom = max(-0.5, min(0.5, metrics.get('mom_60d', 0))) + 0.5
        vol = metrics.get('ann_vol', 0.3)
        vol_s = max(0, 1 - vol / 0.6) if vol > 0 else 0.5
        sharpe = max(0, min(1, (metrics.get('sharpe60', 0) + 2) / 6))
        # 量比: 5日均量/20日均量, >1=放量活跃(flow proxy)
        turnover = metrics.get('turnover', 1.0)
        flow_s = min(1.5, max(0.5, turnover)) / 1.5
        return mom * w["mom"] + vol_s * w["vol"] + sharpe * w["sharpe"] + flow_s * w["flow"]

    def _select_etfs(self, class_type: str, target_weight: float,
                     scores: dict, confidence: float,
                     etf_universe: dict = None,
                     current_codes: set = None) -> dict:
        """从候选池中按评分选出最优ETF，同指数只保留得分最高的。
        current_codes: 当前持有的代码集合，持有中的ETF评分加成10%（持仓惯性）
        """
        source = etf_universe if etf_universe is not None else self.ETF_UNIVERSE
        candidates = source.get(class_type, [])
        if not candidates:
            return {}

        hold_bonus = 1.0 + PortfolioAgent.LAZY_LAMBDA  # configurable hold bonus
        current_set = current_codes or set()
        top_n = self.TOP_N.get(class_type, 2)
        ranked = []
        for code, name in candidates:
            metrics = scores.get(code, {})
            sc = self._score_etf(metrics) if metrics else 0.5
            if code in current_set:
                sc *= hold_bonus  # 持仓惯性加分
            ranked.append((code, name, sc))
        ranked.sort(key=lambda x: x[2], reverse=True)

        # 去重：同SW1行业/同指数的ETF只保留得分最高的
        sector_map = self._get_sector_map() if class_type == "Stock" else {}
        selected = []
        seen = set()
        for code, name, sc in ranked:
            qc = f"{code}.SH" if code.startswith(("5","6","51","56","58","59")) else f"{code}.SZ"
            # 优先用SW1行业去重，回退到名称关键词
            sector = sector_map.get(qc, "")
            tag = sector if sector else self._extract_index(name)
            if tag in seen:
                continue
            seen.add(tag)
            selected.append((code, name, sc))
            if len(selected) >= top_n:
                break

        # 如果去重后数量不够，用非去重列表补足
        if len(selected) < min(top_n, 2):
            for code, name, sc in ranked:
                if (code, name, sc) not in selected:
                    selected.append((code, name, sc))
                    if len(selected) >= min(top_n, 2):
                        break

        # 按得分比例分配该类别权重
        total_score = sum(s[2] for s in selected)
        if total_score == 0:
            total_score = len(selected)

        result = {}
        for code, name, sc in selected:
            w = target_weight * sc / total_score
            n = len(selected)
            w = w * confidence + (target_weight / n) * (1 - confidence)
            result[code] = {"name": name, "type": class_type, "weight": round(w, 4)}

        # 单只最低权重 2%，过低则剔除（防过度分散，仅多只ETF类别生效）
        if len(result) > 2:
            to_drop = [c for c, v in result.items() if v["weight"] < 0.02]
            if len(result) - len(to_drop) >= 2:  # 至少保留2只
                for c in to_drop:
                    del result[c]
                # 重新归一化
                total = sum(v["weight"] for v in result.values())
                if total > 0:
                    for v in result.values():
                        v["weight"] = round(v["weight"] / total, 4)

        return result

    def _compute_rotation_speed(self, etf_scores: dict, etf_universe: dict) -> float:
        """行业轮动速度 (0~1). 用股票ETF动量截面离散度做代理"""
        if not etf_universe or not etf_scores:
            return 0.5
        stock_moms = []
        for item in etf_universe.get('Stock', []):
            code = item[0] if isinstance(item, (list, tuple)) else item
            mom = etf_scores.get(code, {}).get('mom_60d', 0)
            if isinstance(mom, (int, float)) and abs(mom) < 2:
                stock_moms.append(float(mom))
        if len(stock_moms) < 10:
            return 0.5
        arr = np.array(stock_moms)
        dispersion = float(np.std(arr) / (np.mean(np.abs(arr)) + 0.001))
        return min(1.0, max(0.0, dispersion / 3))

    CYCLE_ALLOC = {
        "复苏期": {"gold": 0.10, "bond": 0.25, "stock_core": 0.325, "stock_sat": 0.325, "cash": 0.00},
        "扩张期": {"gold": 0.35, "bond": 0.15, "stock_core": 0.175, "stock_sat": 0.175, "cash": 0.15},
        "滞胀期": {"gold": 0.30, "bond": 0.15, "stock_core": 0.10, "stock_sat": 0.10, "cash": 0.35},
        "衰退期": {"gold": 0.10, "bond": 0.50, "stock_core": 0.10, "stock_sat": 0.10, "cash": 0.20},
    }
    CORE_STOCKS = {"563220": "A500ETF"}  # 实盘持仓宽基
    GOLD_ETF = "518860"   # 实盘持仓黄金
    BOND_ETF = "511010"   # 实盘持仓国债
    SATELLITE_N = 4

    def _get_ma200_cache(self, codes: list, target_date: str) -> dict:
        """获取指定日期的200日均线值 {code: (close, ma200)}"""
        import pandas as _pd
        parquet_path = "cache/ma200_cache.parquet"
        df = _pd.read_parquet(parquet_path)
        df["date"] = _pd.to_datetime(df["date"])
        up_to = df[(df["date"] <= target_date) & (df["code"].isin(codes))]
        if up_to.empty: return {}
        latest = up_to.sort_values("date").groupby("code").last()
        return {c: (latest.loc[c, "close"], latest.loc[c, "ma200"])
                for c in codes if c in latest.index}

    def _percentile_score(self, raw: list, cycle: str = None) -> list:
        """截面排名百分位归一化，按宏观周期切换因子权重，返回 [(code, score), ...]"""
        import pandas as _pd
        if not raw: return []
        w = self.CYCLE_WEIGHTS.get(cycle, self.SCORE_WEIGHTS) if cycle else self.SCORE_WEIGHTS
        rf = _pd.DataFrame(raw, columns=["code", "mom_60d", "ann_vol", "sharpe60", "turnover"])
        rf["mom_rank"] = rf["mom_60d"].rank(pct=True)
        rf["vol_rank"] = 1 - rf["ann_vol"].rank(pct=True)
        rf["sh_rank"] = rf["sharpe60"].rank(pct=True)
        rf["flow_rank"] = rf["turnover"].rank(pct=True)
        rf["score"] = (rf["mom_rank"] * w["mom"] + rf["vol_rank"] * w["vol"] +
                       rf["sh_rank"] * w["sharpe"] + rf["flow_rank"] * w["flow"])
        rf = rf.sort_values("score", ascending=False)
        return [(r["code"], r["score"]) for _, r in rf.iterrows()]

    def decide(self, macro_analysis: dict, etf_scores: dict = None,
               etf_universe: dict = None,
               current_codes: set = None, curr_date: str = None) -> dict:
        """完整框架: 核心卫星 + 趋势门控 + 截面排名因子"""
        cycle = macro_analysis["cycle_phase"]
        confidence = macro_analysis.get("confidence", 0.5)
        alloc = dict(self.CYCLE_ALLOC.get(cycle, self.CYCLE_ALLOC["滞胀期"]))
        source = etf_universe if etf_universe is not None else self.ETF_UNIVERSE
        if etf_scores is None: etf_scores = {}

        portfolio = {}

        # --- Gold: fixed ETF ---
        portfolio[self.GOLD_ETF] = {"name": "黄金ETF", "type": "Commodity", "weight": alloc["gold"]}

        # --- Bond: fixed ETF + cash ---
        portfolio[self.BOND_ETF] = {"name": "国债ETF", "type": "Bond",
                                     "weight": alloc["bond"] + alloc.get("cash", 0)}

        # --- Trend gate MA lookup ---
        above_ma = set()
        if curr_date:
            try:
                all_stock_codes = [item[0] for item in source.get("Stock", [])
                                   if isinstance(item, (list, tuple))]
                all_stock_codes += list(self.CORE_STOCKS.keys())
                ma_data = self._get_ma200_cache(all_stock_codes, curr_date)
                above_ma = {c for c, (close, ma) in ma_data.items() if close > ma}
            except Exception: pass

        # --- Stock Core: 沪深300 + 中证500 ---
        core_codes = [c for c in self.CORE_STOCKS if c in above_ma]
        if core_codes:
            per_core = alloc["stock_core"] / len(core_codes)
            for c in core_codes:
                portfolio[c] = {"name": self.CORE_STOCKS[c], "type": "Stock",
                                "weight": per_core}
        elif alloc["stock_core"] > 0:
            portfolio[self.BOND_ETF]["weight"] += alloc["stock_core"]

        # --- Stock Satellite: trend gate + percentile ranking ---
        raw_data = []
        for item in source.get("Stock", []):
            code = item[0] if isinstance(item, (list, tuple)) else item
            if code not in above_ma: continue
            sc = etf_scores.get(code, {})
            if not sc: continue
            raw_data.append((code, sc.get("mom_60d", 0), sc.get("ann_vol", 0.3),
                            sc.get("sharpe60", 0), sc.get("turnover", 1.0)))

        ranked = self._percentile_score(raw_data, cycle)
        # 去重补位: 同tag只选1只, 向下填充
        selected = []
        seen_tags = set()
        for code, score in ranked:
            name = "ETF"
            for item in source.get("Stock", []):
                if item[0] == code:
                    name = item[1]; break
            tag = self._extract_index(name)
            if tag in seen_tags: continue
            seen_tags.add(tag)
            selected.append((code, score, name))
            if len(selected) >= self.SATELLITE_N: break
        if selected:
            total_s = sum(s for _, s, _ in selected)
            for code, score, name in selected:
                w = alloc["stock_sat"] * score / total_s if total_s > 0 else alloc["stock_sat"] / len(selected)
                portfolio[code] = {"name": name, "type": "Stock", "weight": w}
        elif alloc["stock_sat"] > 0:
            # Fallback: satellite allocation to bonds
            portfolio[self.BOND_ETF]["weight"] += alloc["stock_sat"]

        # Merge duplicate codes (BOND_ETF may have multiple entries)
        merged = {}
        for code, info in portfolio.items():
            if code in merged:
                merged[code]["weight"] += info["weight"]
            else:
                merged[code] = dict(info)
        portfolio = merged

        # 风险控制
        portfolio, risk_warnings = self._apply_risk_controls(portfolio, curr_date)

        # Normalize
        total = sum(p["weight"] for p in portfolio.values())
        if total > 0:
            for p in portfolio.values():
                p["weight"] = round(p["weight"] / total, 4)

        self._prev_class_weights = {"Stock": 0, "Bond": 0, "Commodity": 0}
        for code, info in portfolio.items():
            self._prev_class_weights[info["type"]] += info["weight"]

        reasoning = self._build_reasoning(macro_analysis, portfolio)
        risk_check = "通过" if not risk_warnings else "警告: " + "; ".join(risk_warnings)

        return {
            "cycle_phase": cycle, "confidence": confidence,
            "portfolio": portfolio,
            "decision_date": macro_analysis.get("metadata", {}).get("input_date", ""),
            "reasoning": reasoning, "risk_check": risk_check, "risk_warnings": risk_warnings
        }

    def _build_reasoning(self, macro_analysis: dict, portfolio: dict) -> str:
        """构建决策理由文本"""
        lines = []
        lines.append("【宏观研判】")
        lines.append(macro_analysis.get("analysis", ""))
        lines.append("")
        lines.append(f"【周期判断】{macro_analysis['cycle_phase']} (置信度: {macro_analysis['confidence']:.0%})")
        lines.append("")
        lines.append("【配置逻辑】")
        lines.append(macro_analysis.get("investment_implication", ""))
        lines.append("")
        risk_factors = macro_analysis.get("risk_factors", [])
        if risk_factors:
            lines.append("【风险提示】")
            for risk in risk_factors:
                lines.append(f"- {risk}")
            lines.append("")
        lines.append("【最终组合】")
        for code, pos in sorted(portfolio.items(), key=lambda x: x[1]["weight"], reverse=True):
            lines.append(f"  {code} ({pos['name']}): {pos['weight']:.2%}")
        return "\n".join(lines)

    def _dedup_correlation(self, portfolio: dict, curr_date: str) -> dict:
        """残差相关性去重：仅股票类内，22日滚动，阈值0.95，至少保留3只"""
        stock_codes = [c for c, p in portfolio.items() if p.get("type") == "Stock"]
        if len(stock_codes) < 4:
            return portfolio

        codes_to_fetch = list(set(stock_codes + ["510300"]))
        try:
            try:
                from data.local_store import get_bars
            except ImportError:
                from src.data.local_store import get_bars
            bars = get_bars(codes_to_fetch, days=30)
            if not bars:
                return portfolio
            frames = []
            for c, df in bars.items():
                df2 = df[['close']].copy()
                df2['code'] = c
                df2 = df2.reset_index().rename(columns={'index': 'date'})
                frames.append(df2)
            if not frames:
                return portfolio
            raw = pd.concat(frames, ignore_index=True)
            raw["date"] = pd.to_datetime(raw["date"])
        except:
            return portfolio

        mkt = raw[raw["code"] == "510300"]
        if len(mkt) < 22:
            return portfolio
        mkt_ret = mkt["close"].tail(22).pct_change().dropna()
        if len(mkt_ret) < 15:
            return portfolio

        to_remove = set()
        for i in range(len(stock_codes)):
            if stock_codes[i] in to_remove:
                continue
            for j in range(i + 1, len(stock_codes)):
                if stock_codes[j] in to_remove:
                    continue
                s1 = raw[raw["code"] == stock_codes[i]]
                s2 = raw[raw["code"] == stock_codes[j]]
                if len(s1) < 22 or len(s2) < 22:
                    continue
                r1_raw = s1["close"].tail(22).pct_change()
                r2_raw = s2["close"].tail(22).pct_change()
                if r1_raw.count() < 15 or r2_raw.count() < 15:
                    continue
                common = r1_raw.dropna().index.intersection(r2_raw.dropna().index).intersection(mkt_ret.index)
                if len(common) < 15:
                    continue
                r1 = r1_raw[common]
                r2 = r2_raw[common]
                m = mkt_ret[common]
                beta1 = np.cov(r1, m)[0, 1] / np.var(m) if np.var(m) > 0 else 1
                beta2 = np.cov(r2, m)[0, 1] / np.var(m) if np.var(m) > 0 else 1
                resid1 = r1 - beta1 * m
                resid2 = r2 - beta2 * m
                corr = resid1.corr(resid2)
                if corr > 0.95:
                    w1 = portfolio[stock_codes[i]]["weight"]
                    w2 = portfolio[stock_codes[j]]["weight"]
                    loser = stock_codes[j] if w1 >= w2 else stock_codes[i]
                    to_remove.add(loser)

        if to_remove and (len(stock_codes) - len(to_remove)) >= 3:
            for c in to_remove:
                del portfolio[c]
            total = sum(p["weight"] for p in portfolio.values())
            if total > 0:
                for p in portfolio.values():
                    p["weight"] = round(p["weight"] / total, 4)

        return portfolio

    def _apply_risk_controls(self, portfolio: Dict, curr_date: str = None) -> tuple:
        """应用风险控制：关键词去重 + 残差相关性去重 + 比例钳制"""
        warnings_list = []

        # 先归一化（_select_etfs 各分类独立分配，总和可能≠1.0）
        total = sum(p["weight"] for p in portfolio.values())
        if total > 0 and abs(total - 1.0) > 0.001:
            for p in portfolio.values():
                p["weight"] = p["weight"] / total

        # 兜底去重：同指数/同关键词的ETF只保留一个（合并权重到最高分者）
        by_tag = {}
        for code, p in list(portfolio.items()):
            tag = self._extract_index(p["name"])
            if tag not in by_tag:
                by_tag[tag] = []
            by_tag[tag].append((code, p["weight"]))
        for tag, items in by_tag.items():
            if len(items) > 1:
                items.sort(key=lambda x: x[1], reverse=True)
                keeper = items[0][0]
                merged_w = sum(w for _, w in items)
                portfolio[keeper]["weight"] = merged_w
                for code, _ in items[1:]:
                    del portfolio[code]

        # 残差相关性去重（仅股票类内，22日滚动，阈值0.95）
        if curr_date:
            portfolio = self._dedup_correlation(portfolio, curr_date)

        stock_ratio = sum(p["weight"] for p in portfolio.values() if p["type"] == "Stock")
        gold_ratio = sum(p["weight"] for p in portfolio.values() if p["type"] == "Commodity")
        bond_codes = [c for c, p in portfolio.items() if p["type"] == "Bond"]
        stock_codes = [c for c, p in portfolio.items() if p["type"] == "Stock"]

        if stock_ratio > self.CONSTRAINTS["max_stock_ratio"]:
            scale = self.CONSTRAINTS["max_stock_ratio"] / stock_ratio
            for p in portfolio.values():
                if p["type"] == "Stock":
                    p["weight"] *= scale
            warnings_list.append(f"股票占比超限({stock_ratio:.1%})，已缩至{self.CONSTRAINTS['max_stock_ratio']:.0%}")

        elif stock_ratio < self.CONSTRAINTS["min_stock_ratio"] and bond_codes:
            deficit = self.CONSTRAINTS["min_stock_ratio"] - stock_ratio
            per_bond = deficit / len(bond_codes)
            for c in bond_codes:
                portfolio[c]["weight"] = max(0.01, portfolio[c]["weight"] - per_bond)
            for c in stock_codes:
                portfolio[c]["weight"] += deficit / len(stock_codes)
            warnings_list.append(f"股票占比不足({stock_ratio:.1%})，从债券补足至{self.CONSTRAINTS['min_stock_ratio']:.0%}")

        if gold_ratio > self.CONSTRAINTS["max_gold_ratio"]:
            scale = self.CONSTRAINTS["max_gold_ratio"] / gold_ratio
            for p in portfolio.values():
                if p["type"] == "Commodity":
                    p["weight"] *= scale
            warnings_list.append(f"黄金占比超限({gold_ratio:.1%})，已缩至{self.CONSTRAINTS['max_gold_ratio']:.0%}")

        # 归一化
        total = sum(p["weight"] for p in portfolio.values())
        for p in portfolio.values():
            p["weight"] = round(p["weight"] / total, 4)

        return portfolio, warnings_list


# ==================== MacroDrivenETFAgent ====================

class MacroDrivenETFAgent(ETFAgentBase):
    """宏观驱动ETF策略Agent - 继承ETFAgentBase"""

    def __init__(self, use_llm: bool = False, **kwargs):
        # 数据库配置
        db_config = {
            'host': os.getenv('CHDB_HOST'),
            'port': int(os.getenv('CHDB_PORT', 20108)),
            'user': os.getenv('CHDB_USER'),
            'password': os.getenv('CHDB_PASSWORD'),
            'database': os.getenv('CHDB_DATABASE', 'etf')
        }

        super().__init__(name="MacroDrivenETFStrategy", db_config=db_config, **kwargs)

        self.use_llm = use_llm

        # 初始化Agents
        print("[INFO] Initializing DataAgent...")
        self.data_agent = DataAgent(_DATA_PATH)
        self.data_agent.load_all_data()

        print("[INFO] Initializing MacroAgent...")
        self.macro_agent = MacroAgent(use_llm=use_llm)

        self._etf_universe = None  # 动态ETF宇宙，通过set_etf_universe()设置

        print("[INFO] Initializing PortfolioAgent...")
        self.portfolio_agent = PortfolioAgent()

        # 缓存路径
        self.cache_path = Path(_CACHE_PATH)

        print("[SUCCESS] MacroDrivenETFAgent initialized")

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

    def _fetch_etf_scores(self, curr_date: str, etf_universe: dict = None) -> dict:
        """从本地 parquet 获取全量候选ETF的技术评分，结果缓存到文件"""
        import json as _json
        _score_cache = Path(self.cache_path) / f"etf_scores_{curr_date}.json"
        if _score_cache.exists():
            try:
                with open(_score_cache, 'r') as _f:
                    return _json.load(_f)
            except: pass

        all_codes = []
        source = etf_universe if etf_universe is not None else self.portfolio_agent.ETF_UNIVERSE
        for codes in source.values():
            for item in codes:
                code = item[0] if isinstance(item, (list, tuple)) else item
                all_codes.append(code)
        if not all_codes:
            return {}

        try:
            try:
                from data.local_store import get_bars
            except ImportError:
                from src.data.local_store import get_bars
            bars = get_bars(all_codes, days=130)
            if not bars:
                return {}

            import numpy as np
            scores = {}
            for code in all_codes:
                df = bars.get(code)
                if df is None or len(df) < 10:
                    scores[code] = {"pos_60": 0.5, "pos_120": 0.5, "mom_21d": 0.0, "ann_vol": 0.3}
                    continue
                c = df['close'].values; h = df['high'].values; l = df['low'].values
                latest_close = float(c[-1])
                n60 = min(60, len(c))
                pos_60 = (latest_close - l[-n60:].min()) / (h[-n60:].max() - l[-n60:].min()) if h[-n60:].max() > l[-n60:].min() else 0.5
                n120 = min(120, len(c))
                pos_120 = (latest_close - l[-n120:].min()) / (h[-n120:].max() - l[-n120:].min()) if h[-n120:].max() > l[-n120:].min() else 0.5
                s = pd.Series(c[-min(60, len(c)):])
                lr = np.log(s / s.shift(1)).dropna()
                ann_vol = float(lr.std() * np.sqrt(252)) if len(lr) > 5 else 0.3
                mom_21d = float(c[-1] / c[-22] - 1) if len(c) >= 22 else 0
                mom_60d = float(c[-1] / c[-61] - 1) if len(c) >= 61 else mom_21d
                # QMT 等效因子
                # bias60: (close-MA60)/MA60, 替代pos_60
                ma60 = np.mean(c[-60:]) if len(c) >= 60 else c[-1]
                bias60 = float((c[-1] - ma60) / ma60) if ma60 > 0 else 0
                # bull/bear power: 多空力道
                ema13 = pd.Series(c).ewm(span=13).mean().iloc[-1]
                bull = float((h[-1] - ema13) / c[-1]) if c[-1] > 0 else 0
                bear = float((l[-1] - ema13) / c[-1]) if c[-1] > 0 else 0
                net_power = bull + bear  # bear为负，net=多空净值
                # MFI: 资金流量指标 (14日)
                tp = (h[-14:] + l[-14:] + c[-14:]) / 3
                mf = tp * df['volume'].values[-14:].astype(float) if 'volume' in df.columns else tp
                pos_mf = np.sum(mf[tp[-len(mf):] > np.roll(tp[-len(mf):], 1)[:len(mf)]]) if len(mf) >= 2 else 1
                neg_mf = np.sum(mf[tp[-len(mf):] < np.roll(tp[-len(mf):], 1)[:len(mf)]]) if len(mf) >= 2 else 1
                mfi = float(100 - 100 / (1 + pos_mf / (neg_mf + 0.0001)))
                # 换手率
                vol_col = df['volume'] if 'volume' in df.columns else pd.Series([0])
                v = vol_col.values[-20:].astype(float) if len(vol_col) >= 20 else np.ones(20)
                v5 = v[-5:] if len(v) >= 5 else v
                turnover = float(np.mean(v5) / (np.mean(v) + 0.0001))
                # 夏普比率 60日
                rets = np.diff(np.log(c[-60:])) if len(c) >= 60 else [0]
                sharpe60 = float(np.mean(rets) / (np.std(rets) + 0.0001) * np.sqrt(252))
                # 偏度 60日（负偏度=暴跌风险）
                skew60 = float(pd.Series(rets).skew()) if len(rets) > 5 else 0
                # CCI 20：商品通道指数
                tp20 = (h[-20:] + l[-20:] + c[-20:]) / 3
                ma20 = np.mean(tp20)
                md20 = np.mean(np.abs(tp20 - ma20))
                cci20 = float((tp20[-1] - ma20) / (0.015 * md20 + 0.0001))
                # 周期自适应所需附加因子
                price3m = float(c[-1] / c[-61] - 1) if len(c) >= 61 else mom_60d
                ema_12 = pd.Series(c).ewm(span=12).mean().iloc[-1]
                ema_26 = pd.Series(c).ewm(span=26).mean().iloc[-1]
                macdc_val = float((ema_12 - ema_26) / c[-1]) if c[-1] > 0 else 0
                boll_ma = np.mean(c[-20:]) if len(c) >= 20 else c[-1]
                boll_std = np.std(c[-20:]) if len(c) >= 20 else 0
                boll_up_val = float((boll_ma + 2*boll_std) / c[-1] - 1) if c[-1] > 0 else 0
                var20 = float(np.var(rets[-20:]) * 252) if len(rets) >= 20 else ann_vol
                var60 = ann_vol  # already computed as 60-day
                tr_arr = np.maximum(h[-14:]-l[-14:], np.maximum(np.abs(h[-14:]-np.roll(c[-15:-1],1)[-14:]), np.abs(l[-14:]-np.roll(c[-15:-1],1)[-14:]))) if len(c) >= 15 else [0]
                atr_val = float(np.mean(tr_arr) / c[-1]) if c[-1] > 0 else 0
                ema120_val = float(pd.Series(c).ewm(span=120).mean().iloc[-1] / c[-1]) if c[-1] > 0 else 1.0
                scores[code] = {"ann_vol": round(ann_vol, 4),
                                "mom_60d": round(mom_60d, 4),
                                "price3m": round(price3m, 4),
                                "macdc": round(macdc_val, 4),
                                "boll_up": round(boll_up_val, 4),
                                "variance20": round(var20, 4),
                                "variance60": round(var60, 4),
                                "atr14": round(atr_val, 4),
                                "ema120": round(ema120_val, 4),
                                "sharpe60": round(sharpe60, 4)}
            try:
                _score_cache.parent.mkdir(parents=True, exist_ok=True)
                with open(_score_cache, 'w') as _f:
                    _json.dump(scores, _f)
            except: pass
            return scores
        except Exception as e:
            warnings.warn(f"ETF scoring failed: {e}")
            return {}

    def set_etf_universe(self, universe: dict):
        """设置动态ETF宇宙（绕过基类签名检查）"""
        self._etf_universe = universe

    def get_current_holdings(self, curr_date: str, feedback: str = None,
                             theta: float = None) -> dict:
        """
        获取当前日期的持仓。
        如需持仓惯性加成，在调用前设置 self._prev_codes = {'510300', ...}
        """
        etf_universe = getattr(self, '_etf_universe', None)
        # 检查缓存（回测模式有 _prev_codes 时跳过缓存）
        cache_file = self.cache_path / f"holdings_{curr_date}.json"
        if cache_file.exists() and getattr(self, '_prev_codes', None) is None:
            try:
                with open(cache_file, 'r') as f:
                    cached = json.load(f)
                weights = list(cached.values())[0].values()
                if not any(isinstance(w, float) and w != w for w in weights):
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

        # 获取全量ETF技术评分（动态宇宙优先）
        etf_scores = self._fetch_etf_scores(curr_date, etf_universe=etf_universe)

        # 组合决策（传入技术评分 + 动态宇宙用于动态选ETF）
        prev = getattr(self, '_prev_codes', None)
        decision = self.portfolio_agent.decide(macro_analysis, etf_scores=etf_scores,
                                               etf_universe=etf_universe,
                                               current_codes=prev, curr_date=curr_date)

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

    def _adjust_holdings_theta(self, holdings: dict, theta: float) -> dict:
        """根据风险偏好调整持仓 — θ<1 保守（降股票+债券），θ>1 激进（增股票+黄金）"""
        curr_date = list(holdings.keys())[0]
        weights = holdings[curr_date]

        etf_uni = getattr(self, '_etf_universe', None)
        if etf_uni is None:
            etf_uni = self.portfolio_agent.ETF_UNIVERSE
        all_stock = {c for c, _ in etf_uni.get("Stock", [])}
        all_bond = {c for c, _ in etf_uni.get("Bond", [])}
        all_gold = {c for c, _ in etf_uni.get("Commodity", [])}

        stock_codes = [c for c in weights if c in all_stock]
        bond_codes = [c for c in weights if c in all_bond]
        gold_codes = [c for c in weights if c in all_gold]

        if theta == 1.0 or len(stock_codes) == 0:
            return holdings

        stock_total = sum(weights.get(c, 0) for c in stock_codes)
        bond_total = sum(weights.get(c, 0) for c in bond_codes) if bond_codes else 0
        gold_total = sum(weights.get(c, 0) for c in gold_codes) if gold_codes else 0

        new_weights = dict(weights)

        if theta < 1.0:
            # 保守：股票按 θ 打折，差額转给债券
            for c in stock_codes:
                new_weights[c] = round(weights[c] * theta, 4)
            reduced = stock_total * (1 - theta)
            recipients = bond_codes or gold_codes or stock_codes
            for c in recipients:
                new_weights[c] = round(weights.get(c, 0) + reduced / len(recipients), 4)
        else:
            # 激进：θ>1 增持股票(+黄金)，减持债券
            # 债券按 1/θ 打折，差額按2:1分配给股票和黄金
            targets = stock_codes + gold_codes
            if bond_codes and bond_total > 0:
                for c in bond_codes:
                    new_weights[c] = round(weights[c] / theta, 4)
                freed = bond_total * (1 - 1/theta)
                stock_share = freed * 0.67
                gold_share = freed * 0.33
                for c in stock_codes:
                    new_weights[c] = round(weights.get(c, 0) + stock_share / len(stock_codes), 4)
                for c in gold_codes:
                    new_weights[c] = round(weights.get(c, 0) + gold_share / len(gold_codes), 4)
            else:
                # 没债券可减：直接拉升股票
                scale = theta  # theta∈(1,2] → 股票权重×1~2
                for c in stock_codes:
                    new_weights[c] = round(weights[c] * scale, 4)

        # 归一化
        total = sum(new_weights.values())
        new_weights = {k: round(v / total, 4) for k, v in new_weights.items()}

        holdings[curr_date] = new_weights
        return holdings

    def get_current_holdings_intraday(self, curr_datetime: str, feedback: str = None, theta: float = None) -> dict:
        """
        获取当前时间点的盘中持仓
        cufel_arena 接口

        Parameters
        ----------
        curr_datetime : str
            当前时间点，格式为 'YYYY-MM-DD HH:MM:SS'
        feedback : str, optional
            来自 FOF Agent 的反馈信息
        theta : float, optional
            风险偏好系数

        Returns
        -------
        dict
            持仓字典 {curr_datetime: {code: weight, ...}}
        """
        # 提取日期部分，使用日频持仓
        date_str = curr_datetime.split(" ")[0]
        return self.get_current_holdings(date_str, feedback=feedback, theta=theta)


if __name__ == "__main__":
    # 测试代码
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
