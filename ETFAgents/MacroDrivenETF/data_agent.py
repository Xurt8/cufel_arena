"""
DataAgent - 数据层模块
负责读取所有宏观CSV数据、处理字段映射、做T-1时序对齐
"""

import os
import warnings
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from pydantic import BaseModel


class MacroData(BaseModel):
    """完整宏观数据结构"""
    decision_date: datetime

    # PMI 数据
    pmi: float
    pmi_history: List[float]
    pmi_date: datetime

    # CPI 数据
    cpi_yoy: float
    cpi_history: List[float]
    cpi_date: datetime

    # PPI 数据
    ppi_yoy: float
    ppi_history: List[float]
    ppi_date: datetime

    # M2 数据
    m2_yoy: float
    m2_history: List[float]
    m2_date: datetime

    # 社融数据
    sf_month: float
    sf_history: List[float]
    sf_date: datetime

    # GDP 数据
    gdp_yoy: float
    gdp_quarter: str

    # SHIBOR 数据
    shibor_1m: float
    shibor_3m: float
    shibor_date: datetime


class DataAgent:
    """数据层Agent - 负责加载和预处理宏观数据"""

    def __init__(self, data_path: str = "./data/"):
        self.data_path = Path(data_path)
        self.pmi_data: Optional[pd.DataFrame] = None
        self.cpi_data: Optional[pd.DataFrame] = None
        self.ppi_data: Optional[pd.DataFrame] = None
        self.m2_data: Optional[pd.DataFrame] = None
        self.sf_data: Optional[pd.DataFrame] = None
        self.gdp_data: Optional[pd.DataFrame] = None
        self.shibor_data: Optional[pd.DataFrame] = None
        self.etf_data: Optional[pd.DataFrame] = None

    def load_all_data(self) -> None:
        """加载所有宏观数据"""
        print("[INFO] Loading data...")

        self._load_pmi()
        self._load_cpi()
        self._load_ppi()
        self._load_m()
        self._load_sf()
        self._load_gdp()
        self._load_shibor()
        self._load_etf_prices()

        self._print_summary()

    def _load_pmi(self) -> None:
        """加载PMI数据"""
        try:
            file_path = self.data_path / "cn_pmi.csv"
            df = pd.read_csv(file_path)
            # 列名映射
            df = df.rename(columns={"month": "date_str", "制造业PMI": "pmi"})
            # 转换日期：YYYYMM -> 月末日期
            df["date"] = pd.to_datetime(df["date_str"], format="%Y%m") + pd.offsets.MonthEnd(0)
            df = df[["date", "pmi"]].sort_values("date")
            self.pmi_data = df
            print(f"  [OK] PMI data: {len(df)} records")
        except Exception as e:
            warnings.warn(f"PMI data load failed: {e}")
            self.pmi_data = pd.DataFrame(columns=["date", "pmi"])

    def _load_cpi(self) -> None:
        """加载CPI数据"""
        try:
            file_path = self.data_path / "cn_cpi.csv"
            df = pd.read_csv(file_path)
            # 列名映射
            df = df.rename(columns={"日期": "date_str", "全国同比（%）": "cpi_yoy"})
            # 转换日期：YYYYMM -> 月末日期
            df["date"] = pd.to_datetime(df["date_str"], format="%Y%m") + pd.offsets.MonthEnd(0)
            # 过滤2020年之后的数据（原始数据从1953年开始）
            df = df[df["date"] >= "2020-01-01"]
            df = df[["date", "cpi_yoy"]].sort_values("date")
            self.cpi_data = df
            print(f"  [OK] CPI data: {len(df)} records")
        except Exception as e:
            warnings.warn(f"CPI data load failed: {e}")
            self.cpi_data = pd.DataFrame(columns=["date", "cpi_yoy"])

    def _load_ppi(self) -> None:
        """加载PPI数据"""
        try:
            file_path = self.data_path / "cn_ppi.csv"
            df = pd.read_csv(file_path)
            # 列名映射
            df = df.rename(columns={"日期": "date_str", "PPI：全部工业品：当月同比": "ppi_yoy"})
            # 转换日期：YYYYMM -> 月末日期
            df["date"] = pd.to_datetime(df["date_str"], format="%Y%m") + pd.offsets.MonthEnd(0)
            df = df[["date", "ppi_yoy"]].sort_values("date")
            self.ppi_data = df
            print(f"  [OK] PPI data: {len(df)} records")
        except Exception as e:
            warnings.warn(f"PPI data load failed: {e}")
            self.ppi_data = pd.DataFrame(columns=["date", "ppi_yoy"])

    def _load_m(self) -> None:
        """加载M2数据"""
        try:
            file_path = self.data_path / "cn_m.csv"
            df = pd.read_csv(file_path)
            # 列名映射
            df = df.rename(columns={"month": "date_str", "M2同比（%）": "m2_yoy"})
            # 转换日期：YYYYMM -> 月末日期
            df["date"] = pd.to_datetime(df["date_str"], format="%Y%m") + pd.offsets.MonthEnd(0)
            df = df[["date", "m2_yoy"]].sort_values("date")
            self.m2_data = df
            print(f"  [OK] M2 data: {len(df)} records")
        except Exception as e:
            warnings.warn(f"M2 data load failed: {e}")
            self.m2_data = pd.DataFrame(columns=["date", "m2_yoy"])

    def _load_sf(self) -> None:
        """加载社融数据"""
        try:
            file_path = self.data_path / "sf_month.csv"
            df = pd.read_csv(file_path)
            # 列名映射
            df = df.rename(columns={"month": "date_str", "社融增量当月值（亿元）": "sf_month"})
            # 转换日期：YYYYMM -> 月末日期
            df["date"] = pd.to_datetime(df["date_str"], format="%Y%m") + pd.offsets.MonthEnd(0)
            df = df[["date", "sf_month"]].sort_values("date")
            self.sf_data = df
            print(f"  [OK] SF data: {len(df)} records")
        except Exception as e:
            warnings.warn(f"SF data load failed: {e}")
            self.sf_data = pd.DataFrame(columns=["date", "sf_month"])

    def _load_gdp(self) -> None:
        """加载GDP数据"""
        try:
            file_path = self.data_path / "cn_gdp.csv"
            df = pd.read_csv(file_path)
            # 列名映射
            df = df.rename(columns={"quarter": "quarter_str", "当季同比增速（%）": "gdp_yoy"})

            def quarter_to_end_date(q_str: str) -> pd.Timestamp:
                """季度字符串转换为季末日期"""
                year = int(q_str[:4])
                q = int(q_str[-1])
                month = q * 3  # Q1=3, Q2=6, Q3=9, Q4=12
                return pd.Timestamp(year, month, 1) + pd.offsets.MonthEnd(0)

            df["date"] = df["quarter_str"].apply(quarter_to_end_date)
            df = df[["date", "gdp_yoy", "quarter_str"]].sort_values("date")
            self.gdp_data = df
            print(f"  [OK] GDP data: {len(df)} records")
        except Exception as e:
            warnings.warn(f"GDP data load failed: {e}")
            self.gdp_data = pd.DataFrame(columns=["date", "gdp_yoy", "quarter_str"])

    def _load_shibor(self) -> None:
        """加载SHIBOR数据"""
        try:
            file_path = self.data_path / "shibor.csv"
            df = pd.read_csv(file_path)
            # 列名映射 - 处理可能的空格
            df.columns = df.columns.str.strip()
            df = df.rename(columns={
                "date": "date_str",
                "1m": "shibor_1m",
                "3m": "shibor_3m"
            })
            # 转换日期：YYYYMMDD -> 日期
            df["date"] = pd.to_datetime(df["date_str"].astype(str), format="%Y%m%d")
            df = df[["date", "shibor_1m", "shibor_3m"]].sort_values("date")
            self.shibor_data = df
            print(f"  [OK] SHIBOR data: {len(df)} records")
        except Exception as e:
            warnings.warn(f"SHIBOR data load failed: {e}")
            self.shibor_data = pd.DataFrame(columns=["date", "shibor_1m", "shibor_3m"])

    def _load_etf_prices(self) -> None:
        """加载ETF价格数据"""
        try:
            # 尝试多个可能的文件名
            possible_names = [
                "etf_day_with_basic_2022_2025.csv",
                "etf_day.csv",
                "etf_day_with_basic.csv"
            ]
            file_path = None
            for name in possible_names:
                if (self.data_path / name).exists():
                    file_path = self.data_path / name
                    break

            if file_path is None:
                warnings.warn("ETF price data file not found")
                self.etf_data = pd.DataFrame()
                return

            # 重要：UTF-8 BOM处理
            df = pd.read_csv(file_path, encoding="utf-8-sig")
            # 列名映射
            df = df.rename(columns={
                "ETF代码": "code",
                "交易日期": "date_str",
                "收盘价(元)": "close"
            })
            # 清理code列，去掉.SH/.SZ后缀
            df["code"] = df["code"].astype(str).str.replace(r"\.(SH|SZ)", "", regex=True)
            # 转换日期 - 处理多种格式
            try:
                df["date"] = pd.to_datetime(df["date_str"], format="%Y%m%d")
            except:
                try:
                    df["date"] = pd.to_datetime(df["date_str"])
                except:
                    df["date"] = pd.to_datetime(df["date_str"], format="%Y-%m-%d")
            self.etf_data = df[["code", "date", "close"]].sort_values(["code", "date"])
            print(f"  [OK] ETF prices: {len(df)} records")
        except Exception as e:
            warnings.warn(f"ETF price data load failed: {e}")
            self.etf_data = pd.DataFrame()

    def _print_summary(self) -> None:
        """打印数据加载摘要"""
        print("\n[OK] 数据加载完成")
        if self.pmi_data is not None and len(self.pmi_data) > 0:
            date_range = f"{self.pmi_data['date'].min().strftime('%Y-%m')} ~ {self.pmi_data['date'].max().strftime('%Y-%m')}"
            print(f"  [OK] PMI数据: {len(self.pmi_data)}条 ({date_range})")
        if self.cpi_data is not None and len(self.cpi_data) > 0:
            date_range = f"{self.cpi_data['date'].min().strftime('%Y-%m')} ~ {self.cpi_data['date'].max().strftime('%Y-%m')}"
            print(f"  [OK] CPI数据: {len(self.cpi_data)}条 ({date_range})")
        if self.ppi_data is not None and len(self.ppi_data) > 0:
            date_range = f"{self.ppi_data['date'].min().strftime('%Y-%m')} ~ {self.ppi_data['date'].max().strftime('%Y-%m')}"
            print(f"  [OK] PPI数据: {len(self.ppi_data)}条 ({date_range})")
        if self.m2_data is not None and len(self.m2_data) > 0:
            date_range = f"{self.m2_data['date'].min().strftime('%Y-%m')} ~ {self.m2_data['date'].max().strftime('%Y-%m')}"
            print(f"  [OK] M2数据: {len(self.m2_data)}条 ({date_range})")
        if self.sf_data is not None and len(self.sf_data) > 0:
            date_range = f"{self.sf_data['date'].min().strftime('%Y-%m')} ~ {self.sf_data['date'].max().strftime('%Y-%m')}"
            print(f"  [OK] 社融数据: {len(self.sf_data)}条 ({date_range})")
        if self.gdp_data is not None and len(self.gdp_data) > 0:
            date_range = f"{self.gdp_data['date'].min().strftime('%YQ')} ~ {self.gdp_data['date'].max().strftime('%YQ')}"
            print(f"  [OK] GDP数据: {len(self.gdp_data)}条 ({date_range})")
        if self.shibor_data is not None and len(self.shibor_data) > 0:
            date_range = f"{self.shibor_data['date'].min().strftime('%Y-%m-%d')} ~ {self.shibor_data['date'].max().strftime('%Y-%m-%d')}"
            print(f"  [OK] SHIBOR数据: {len(self.shibor_data)}条 ({date_range})")
        if self.etf_data is not None and len(self.etf_data) > 0:
            print(f"  [OK] ETF价格: {len(self.etf_data)}条")

    @staticmethod
    def _publication_cutoff(data_date: pd.Timestamp, indicator: str) -> pd.Timestamp:
        """计算各指标的发布滞后截止日期"""
        m, y = data_date.month, data_date.year
        next_month_first = pd.Timestamp(y + 1, 1, 1) if m == 12 else pd.Timestamp(y, m + 1, 1)

        if indicator == "pmi":
            return next_month_first  # 次月1日
        elif indicator in ("cpi", "ppi"):
            return next_month_first.replace(day=10)  # 次月10日
        elif indicator in ("m2", "sf"):
            return next_month_first.replace(day=15)  # 次月15日
        elif indicator == "gdp":
            return data_date + pd.Timedelta(days=16)  # 季末+16日
        else:  # shibor
            return data_date + pd.Timedelta(days=1)

    def get_macro_for_decision(self, decision_date: datetime, strict_publication_lag: bool = True) -> MacroData:
        """获取决策日期可用的宏观数据（T-1对齐）"""
        decision_ts = pd.Timestamp(decision_date)

        def get_latest(df, key_col, indicator, n=6):
            if df is None or len(df) == 0:
                raise ValueError(f"No data for {key_col}")

            if strict_publication_lag:
                # 严格模式：只使用已公布的数据
                available = df["date"].apply(
                    lambda d: DataAgent._publication_cutoff(pd.Timestamp(d), indicator) <= decision_ts
                )
                valid = df[available].copy()
            else:
                # 宽松T-1：数据时点 < 决策日
                valid = df[df["date"] < decision_ts].copy()

            if len(valid) == 0:
                raise ValueError(f"No available data for {key_col} (decision date: {decision_ts})")

            latest = valid.iloc[-1]
            history = valid.tail(n)[key_col].tolist()

            # 断言保护：确保不使用未来数据
            assert pd.Timestamp(latest["date"]) < decision_ts, \
                f"Future data error: {key_col} uses future data {latest['date']}"

            return latest, history

        # 获取各指标数据
        pmi_latest, pmi_hist = get_latest(self.pmi_data, "pmi", "pmi")
        cpi_latest, cpi_hist = get_latest(self.cpi_data, "cpi_yoy", "cpi")
        ppi_latest, ppi_hist = get_latest(self.ppi_data, "ppi_yoy", "ppi")
        m2_latest, m2_hist = get_latest(self.m2_data, "m2_yoy", "m2")
        sf_latest, sf_hist = get_latest(self.sf_data, "sf_month", "sf")
        gdp_latest, _ = get_latest(self.gdp_data, "gdp_yoy", "gdp", n=4)

        # SHIBOR 单独处理（日频）
        if self.shibor_data is not None and len(self.shibor_data) > 0:
            shibor_valid = self.shibor_data[self.shibor_data["date"] < decision_ts]
            if len(shibor_valid) > 0:
                shibor_latest = shibor_valid.iloc[-1]
            else:
                raise ValueError("No SHIBOR available data")
        else:
            raise ValueError("No SHIBOR data")

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

    def get_etf_price(self, etf_code: str, date: datetime) -> Optional[float]:
        """获取单个ETF在指定日期的价格"""
        if self.etf_data is None or len(self.etf_data) == 0:
            return None

        date_ts = pd.Timestamp(date)
        result = self.etf_data[
            (self.etf_data["code"] == etf_code) &
            (self.etf_data["date"] <= date_ts)
        ]

        if len(result) == 0:
            return None

        return float(result.iloc[-1]["close"])

    def get_etf_prices_on_date(self, date: datetime) -> Dict[str, float]:
        """获取指定日期所有ETF的价格"""
        if self.etf_data is None or len(self.etf_data) == 0:
            return {}

        date_ts = pd.Timestamp(date)
        result = self.etf_data[self.etf_data["date"] == date_ts]

        return {row["code"]: float(row["close"]) for _, row in result.iterrows()}


if __name__ == "__main__":
    # 初始化并加载数据
    agent = DataAgent("./data/")
    agent.load_all_data()

    # 测试获取宏观数据
    from datetime import datetime
    macro = agent.get_macro_for_decision(datetime(2024, 3, 31))

    print(f"\n测试：2024-03-31 决策")
    print(f"  PMI: {macro.pmi} (数据时点: {macro.pmi_date.strftime('%Y-%m-%d')})")
    print(f"  CPI同比: {macro.cpi_yoy}%")
    print(f"  PPI同比: {macro.ppi_yoy}%")
    print(f"  M2同比: {macro.m2_yoy}%")
    print(f"  社融增量: {macro.sf_month:.0f}亿")
    print(f"  GDP同比: {macro.gdp_yoy}% (季度: {macro.gdp_quarter})")
    print(f"  SHIBOR 1m: {macro.shibor_1m}%, 3m: {macro.shibor_3m}%")
