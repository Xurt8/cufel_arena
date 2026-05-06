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
from dotenv import load_dotenv
from pydantic import BaseModel

# 路径配置 - 使用 __file__ 计算绝对路径
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_PATH = os.path.join(_THIS_DIR, "data/")
_CACHE_PATH = os.path.join(_THIS_DIR, "cache/")

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

class MacroData(BaseModel):
    """完整宏观数据结构"""
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

        pmi_latest, pmi_hist = get_latest(self.pmi_data, "pmi", "pmi")
        cpi_latest, cpi_hist = get_latest(self.cpi_data, "cpi_yoy", "cpi")
        ppi_latest, ppi_hist = get_latest(self.ppi_data, "ppi_yoy", "ppi")
        m2_latest, m2_hist = get_latest(self.m2_data, "m2_yoy", "m2")
        sf_latest, sf_hist = get_latest(self.sf_data, "sf_month", "sf")
        gdp_latest, _ = get_latest(self.gdp_data, "gdp_yoy", "gdp", n=4)

        if self.shibor_data is not None and len(self.shibor_data) > 0:
            shibor_valid = self.shibor_data[self.shibor_data["date"] < decision_ts]
            shibor_latest = shibor_valid.iloc[-1] if len(shibor_valid) > 0 else None
        else:
            shibor_latest = None

        if shibor_latest is None:
            raise ValueError("No SHIBOR data available")

        return MacroData(
            decision_date=decision_date,
            pmi=float(pmi_latest["pmi"]),
            pmi_history=pmi_hist,
            pmi_date=pmi_latest["date"],
            cpi_yoy=float(cpi_latest["cpi_yoy"]),
            cpi_history=cpi_hist,
            cpi_date=cpi_latest["date"],
            ppi_yoy=float(ppi_latest["ppi_yoy"]),
            ppi_history=ppi_hist,
            ppi_date=ppi_latest["date"],
            m2_yoy=float(m2_latest["m2_yoy"]),
            m2_history=m2_hist,
            m2_date=m2_latest["date"],
            sf_month=float(sf_latest["sf_month"]),
            sf_history=sf_hist,
            sf_date=sf_latest["date"],
            gdp_yoy=float(gdp_latest["gdp_yoy"]),
            gdp_quarter=str(gdp_latest["quarter_str"]),
            shibor_1m=float(shibor_latest["shibor_1m"]),
            shibor_3m=float(shibor_latest["shibor_3m"]),
            shibor_date=shibor_latest["date"]
        )


# ==================== MacroAgent ====================

class MacroAgent:
    """宏观分析Agent - 规则兜底版本"""

    def __init__(self, use_llm: bool = False):
        self.use_llm = use_llm

    def analyze(self, macro_data) -> Dict:
        """分析宏观数据，返回规则兜底结果"""
        score = 0

        # PMI信号
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
            implication = "经济繁荣，建议重仓股票"
        elif score >= 1:
            cycle, conf = "复苏期", 0.60
            implication = "经济回暖，建议增配股票"
        elif score >= -2:
            cycle, conf = "滞胀期", 0.55
            implication = "经济放缓，建议平衡配置"
        else:
            cycle, conf = "衰退期", 0.70
            implication = "经济收缩，建议防御配置"

        return {
            "cycle_phase": cycle,
            "confidence": conf,
            "analysis": f"PMI={macro_data.pmi}, CPI={macro_data.cpi_yoy}%, M2={macro_data.m2_yoy}%, 规则打分({score}分)",
            "investment_implication": implication,
            "risk_factors": [],
            "metadata": {"input_pmi": macro_data.pmi, "source": "fallback", "score": score}
        }


# ==================== PortfolioAgent ====================

class PortfolioAgent:
    """组合决策Agent"""

    CYCLE_ALLOCATION = {
        "复苏期": {
            "510300": {"name": "沪深300ETF", "type": "Stock", "base_weight": 0.40},
            "510500": {"name": "中证500ETF", "type": "Stock", "base_weight": 0.20},
            "511010": {"name": "国债ETF", "type": "Bond", "base_weight": 0.25},
            "518880": {"name": "黄金ETF", "type": "Commodity", "base_weight": 0.15},
        },
        "扩张期": {
            "510300": {"name": "沪深300ETF", "type": "Stock", "base_weight": 0.50},
            "510500": {"name": "中证500ETF", "type": "Stock", "base_weight": 0.25},
            "511010": {"name": "国债ETF", "type": "Bond", "base_weight": 0.15},
            "518880": {"name": "黄金ETF", "type": "Commodity", "base_weight": 0.10},
        },
        "滞胀期": {
            "510300": {"name": "沪深300ETF", "type": "Stock", "base_weight": 0.25},
            "511010": {"name": "国债ETF", "type": "Bond", "base_weight": 0.35},
            "518880": {"name": "黄金ETF", "type": "Commodity", "base_weight": 0.40},
        },
        "衰退期": {
            "510300": {"name": "沪深300ETF", "type": "Stock", "base_weight": 0.15},
            "511010": {"name": "国债ETF", "type": "Bond", "base_weight": 0.50},
            "511220": {"name": "城投债ETF", "type": "Bond", "base_weight": 0.20},
            "518880": {"name": "黄金ETF", "type": "Commodity", "base_weight": 0.15},
        }
    }

    CONSTRAINTS = {
        "max_single_etf": 0.55,
        "max_stock_ratio": 0.75,
        "min_stock_ratio": 0.10,
        "max_gold_ratio": 0.45,
    }

    def decide(self, macro_analysis: dict) -> dict:
        """生成ETF组合决策"""
        cycle = macro_analysis["cycle_phase"]
        confidence = macro_analysis["confidence"]

        base_config = self.CYCLE_ALLOCATION.get(cycle)
        if not base_config:
            raise ValueError(f"Unknown cycle: {cycle}")

        # 构建组合
        portfolio = {}
        n_etfs = len(base_config)
        for code, info in base_config.items():
            if confidence > 0.7:
                weight = info["base_weight"]
            elif confidence > 0.4:
                weight = (info["base_weight"] + 1.0 / n_etfs) / 2
            else:
                weight = 1.0 / n_etfs
            portfolio[code] = {"name": info["name"], "type": info["type"], "weight": weight}

        # 风险控制
        portfolio, _ = self._apply_risk_controls(portfolio)

        return {
            "cycle_phase": cycle,
            "confidence": confidence,
            "portfolio": portfolio,
            "decision_date": macro_analysis.get("metadata", {}).get("input_date", "")
        }

    def _apply_risk_controls(self, portfolio: Dict) -> tuple:
        """应用风险控制"""
        warnings = []
        stock_ratio = sum(p["weight"] for p in portfolio.values() if p["type"] == "Stock")
        gold_ratio = sum(p["weight"] for p in portfolio.values() if p["type"] == "Commodity")

        if stock_ratio > self.CONSTRAINTS["max_stock_ratio"]:
            scale = self.CONSTRAINTS["max_stock_ratio"] / stock_ratio
            for p in portfolio.values():
                if p["type"] == "Stock":
                    p["weight"] *= scale

        if gold_ratio > self.CONSTRAINTS["max_gold_ratio"]:
            scale = self.CONSTRAINTS["max_gold_ratio"] / gold_ratio
            for p in portfolio.values():
                if p["type"] == "Commodity":
                    p["weight"] *= scale

        # 归一化
        total = sum(p["weight"] for p in portfolio.values())
        for p in portfolio.values():
            p["weight"] = round(p["weight"] / total, 4)

        return portfolio, warnings


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
                        # 应用风险偏好调整
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

    def _adjust_holdings_theta(self, holdings: dict, theta: float) -> dict:
        """根据风险偏好调整持仓"""
        curr_date = list(holdings.keys())[0]
        weights = holdings[curr_date]

        # theta 越低越保守，减少股票仓位
        if theta < 1.0:
            # 降低股票占比，增加债券
            stock_codes = ["510300", "510500"]
            bond_codes = ["511010", "511220"]

            stock_total = sum(weights.get(c, 0) for c in stock_codes)
            bond_total = sum(weights.get(c, 0) for c in bond_codes)

            # 调整系数
            adjust_factor = theta

            new_weights = {}
            for code, weight in weights.items():
                if code in stock_codes:
                    new_weights[code] = round(weight * adjust_factor, 4)
                elif code in bond_codes:
                    # 增加债券比例
                    new_weights[code] = round(weight + stock_total * (1 - adjust_factor) / len(bond_codes), 4)
                else:
                    new_weights[code] = weight

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
