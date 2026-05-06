#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
DataAgent - 宏观 ETF 配置系统的数据层
负责读取所有宏观 CSV 数据、处理字段映射、做 T-1 时序对齐
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import pandas as pd
import os
from datetime import datetime
from typing import List, Dict, Optional
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
    """数据层 Agent"""

    def __init__(self, data_path: str = "../../../PracticeData/"):
        self.data_path = data_path
        self.pmi_data = None
        self.cpi_data = None
        self.ppi_data = None
        self.m2_data = None
        self.sf_data = None
        self.gdp_data = None
        self.shibor_data = None
        self.etf_data = None

    def load_all_data(self) -> None:
        """加载所有数据文件"""
        print("=" * 60)
        print("开始加载数据...")
        print("=" * 60)

        self._load_pmi()
        self._load_cpi()
        self._load_ppi()
        self._load_m()
        self._load_sf()
        self._load_gdp()
        self._load_shibor()
        self._load_etf_prices()

        print("\n✅ 数据加载完成")
        self._print_data_summary()

    def _print_data_summary(self):
        """打印数据摘要"""
        if self.pmi_data is not None and len(self.pmi_data) > 0:
            pmi_range = f"{self.pmi_data['date'].min().strftime('%Y-%m')} ~ {self.pmi_data['date'].max().strftime('%Y-%m')}"
            print(f"  📊 PMI数据: {len(self.pmi_data)}条 ({pmi_range})")

        if self.cpi_data is not None and len(self.cpi_data) > 0:
            cpi_range = f"{self.cpi_data['date'].min().strftime('%Y-%m')} ~ {self.cpi_data['date'].max().strftime('%Y-%m')}"
            print(f"  📊 CPI数据: {len(self.cpi_data)}条 ({cpi_range})")

        if self.ppi_data is not None and len(self.ppi_data) > 0:
            ppi_range = f"{self.ppi_data['date'].min().strftime('%Y-%m')} ~ {self.ppi_data['date'].max().strftime('%Y-%m')}"
            print(f"  📊 PPI数据: {len(self.ppi_data)}条 ({ppi_range})")

        if self.m2_data is not None and len(self.m2_data) > 0:
            m2_range = f"{self.m2_data['date'].min().strftime('%Y-%m')} ~ {self.m2_data['date'].max().strftime('%Y-%m')}"
            print(f"  📊 M2数据: {len(self.m2_data)}条 ({m2_range})")

        if self.sf_data is not None and len(self.sf_data) > 0:
            sf_range = f"{self.sf_data['date'].min().strftime('%Y-%m')} ~ {self.sf_data['date'].max().strftime('%Y-%m')}"
            print(f"  📊 社融数据: {len(self.sf_data)}条 ({sf_range})")

        if self.gdp_data is not None and len(self.gdp_data) > 0:
            gdp_range = f"{self.gdp_data['date'].min().strftime('%YQ')} ~ {self.gdp_data['date'].max().strftime('%YQ')}"
            print(f"  📊 GDP数据: {len(self.gdp_data)}条 ({gdp_range})")

        if self.shibor_data is not None and len(self.shibor_data) > 0:
            shibor_range = f"{self.shibor_data['date'].min().strftime('%Y-%m-%d')} ~ {self.shibor_data['date'].max().strftime('%Y-%m-%d')}"
            print(f"  📊 SHIBOR数据: {len(self.shibor_data)}条 ({shibor_range})")

        if self.etf_data is not None and len(self.etf_data) > 0:
            etf_range = f"{self.etf_data['date'].min().strftime('%Y-%m-%d')} ~ {self.etf_data['date'].max().strftime('%Y-%m-%d')}"
            print(f"  📈 ETF价格: {len(self.etf_data)}条 ({etf_range})")

    def _load_pmi(self) -> None:
        """加载PMI数据"""
        file_path = os.path.join(self.data_path, "采购经理指数cn_pmi.csv")
        try:
            df = pd.read_csv(file_path, encoding='utf-8')
            df.columns = ['month', 'pmi']
            # 转换月份为日期 (月末)
            df['date'] = pd.to_datetime(df['month'].astype(str), format='%Y%m') + pd.offsets.MonthEnd(0)
            df = df.sort_values('date').reset_index(drop=True)
            self.pmi_data = df
        except FileNotFoundError:
            print(f"⚠️ 警告: PMI文件不存在 ({file_path})")
            self.pmi_data = pd.DataFrame(columns=['date', 'pmi'])
        except Exception as e:
            print(f"⚠️ 警告: PMI数据加载失败: {e}")
            self.pmi_data = pd.DataFrame(columns=['date', 'pmi'])

    def _load_cpi(self) -> None:
        """加载CPI数据"""
        file_path = os.path.join(self.data_path, "居民消费价格指数cn_cpi.csv")
        try:
            df = pd.read_csv(file_path, encoding='utf-8')
            df.columns = ['date_str', 'cpi_value', 'cpi_yoy']
            # 过滤2020年之后的数据
            df['date'] = pd.to_datetime(df['date_str'].astype(str), format='%Y%m') + pd.offsets.MonthEnd(0)
            df = df[df['date'] >= '2020-01-01']
            df = df.sort_values('date').reset_index(drop=True)
            self.cpi_data = df[['date', 'cpi_yoy']]
        except FileNotFoundError:
            print(f"⚠️ 警告: CPI文件不存在 ({file_path})")
            self.cpi_data = pd.DataFrame(columns=['date', 'cpi_yoy'])
        except Exception as e:
            print(f"⚠️ 警告: CPI数据加载失败: {e}")
            self.cpi_data = pd.DataFrame(columns=['date', 'cpi_yoy'])

    def _load_ppi(self) -> None:
        """加载PPI数据"""
        file_path = os.path.join(self.data_path, "工业生产者出厂价格指数cn_ppi.csv")
        try:
            df = pd.read_csv(file_path, encoding='utf-8')
            # 找到PPI同比列
            ppi_col = [c for c in df.columns if '同比' in c and '累计' not in c][0]
            df = df[['日期', ppi_col]].copy()
            df.columns = ['date_str', 'ppi_yoy']
            df['date'] = pd.to_datetime(df['date_str'].astype(str), format='%Y%m') + pd.offsets.MonthEnd(0)
            df = df.sort_values('date').reset_index(drop=True)
            self.ppi_data = df[['date', 'ppi_yoy']]
        except FileNotFoundError:
            print(f"⚠️ 警告: PPI文件不存在 ({file_path})")
            self.ppi_data = pd.DataFrame(columns=['date', 'ppi_yoy'])
        except Exception as e:
            print(f"⚠️ 警告: PPI数据加载失败: {e}")
            self.ppi_data = pd.DataFrame(columns=['date', 'ppi_yoy'])

    def _load_m(self) -> None:
        """加载M2数据"""
        file_path = os.path.join(self.data_path, "货币供应量cn_m.csv")
        try:
            df = pd.read_csv(file_path, encoding='utf-8')
            m2_col = [c for c in df.columns if '同比' in c][0]
            df = df[['month', m2_col]]
            df.columns = ['month', 'm2_yoy']
            df['date'] = pd.to_datetime(df['month'].astype(str), format='%Y%m') + pd.offsets.MonthEnd(0)
            df = df.sort_values('date').reset_index(drop=True)
            self.m2_data = df[['date', 'm2_yoy']]
        except FileNotFoundError:
            print(f"⚠️ 警告: M2文件不存在 ({file_path})")
            self.m2_data = pd.DataFrame(columns=['date', 'm2_yoy'])
        except Exception as e:
            print(f"⚠️ 警告: M2数据加载失败: {e}")
            self.m2_data = pd.DataFrame(columns=['date', 'm2_yoy'])

    def _load_sf(self) -> None:
        """加载社融数据"""
        file_path = os.path.join(self.data_path, "社融数据sf_month.csv")
        try:
            df = pd.read_csv(file_path, encoding='utf-8')
            sf_col = [c for c in df.columns if '当月值' in c][0]
            df = df[['month', sf_col]]
            df.columns = ['month', 'sf_month']
            df['date'] = pd.to_datetime(df['month'].astype(str), format='%Y%m') + pd.offsets.MonthEnd(0)
            df = df.sort_values('date').reset_index(drop=True)
            self.sf_data = df[['date', 'sf_month']]
        except FileNotFoundError:
            print(f"⚠️ 警告: 社融文件不存在 ({file_path})")
            self.sf_data = pd.DataFrame(columns=['date', 'sf_month'])
        except Exception as e:
            print(f"⚠️ 警告: 社融数据加载失败: {e}")
            self.sf_data = pd.DataFrame(columns=['date', 'sf_month'])

    def _load_gdp(self) -> None:
        """加载GDP数据"""
        file_path = os.path.join(self.data_path, "国内生产总值cn_gdp.csv")
        try:
            df = pd.read_csv(file_path, encoding='utf-8')
            # 解析季度格式: 2025Q4
            def parse_quarter(q_str):
                year = int(q_str[:4])
                quarter = int(q_str[-1])
                month = quarter * 3  # Q1->3, Q2->6, Q3->9, Q4->12
                return pd.Timestamp(year, month, 1) + pd.offsets.MonthEnd(0)

            gdp_col = [c for c in df.columns if '同比' in c][0]
            df = df[['quarter', gdp_col]]
            df.columns = ['quarter_str', 'gdp_yoy']
            df['date'] = df['quarter_str'].apply(parse_quarter)
            df = df.sort_values('date').reset_index(drop=True)
            self.gdp_data = df[['date', 'gdp_yoy', 'quarter_str']]
        except FileNotFoundError:
            print(f"⚠️ 警告: GDP文件不存在 ({file_path})")
            self.gdp_data = pd.DataFrame(columns=['date', 'gdp_yoy', 'quarter_str'])
        except Exception as e:
            print(f"⚠️ 警告: GDP数据加载失败: {e}")
            self.gdp_data = pd.DataFrame(columns=['date', 'gdp_yoy', 'quarter_str'])

    def _load_shibor(self) -> None:
        """加载SHIBOR数据"""
        file_path = os.path.join(self.data_path, "shibor利率.csv")
        try:
            df = pd.read_csv(file_path, encoding='utf-8')
            # 找到对应列
            date_col = [c for c in df.columns if '日期' in c][0] if '日期' in str(df.columns) else 'date'
            df = df.rename(columns={date_col: 'date_str'})
            # 转换日期
            df['date'] = pd.to_datetime(df['date_str'].astype(str), format='%Y%m%d')
            # 找到1m和3m列
            cols = df.columns.tolist()
            m1_col = [c for c in cols if '1m' in c.lower()][0]
            m3_col = [c for c in cols if '3m' in c.lower()][0]
            df = df[['date', m1_col, m3_col]]
            df.columns = ['date', 'shibor_1m', 'shibor_3m']
            df = df.sort_values('date').reset_index(drop=True)
            self.shibor_data = df
        except FileNotFoundError:
            print(f"⚠️ 警告: SHIBOR文件不存在 ({file_path})")
            self.shibor_data = pd.DataFrame(columns=['date', 'shibor_1m', 'shibor_3m'])
        except Exception as e:
            print(f"⚠️ 警告: SHIBOR数据加载失败: {e}")
            self.shibor_data = pd.DataFrame(columns=['date', 'shibor_1m', 'shibor_3m'])

    def _load_etf_prices(self) -> None:
        """加载ETF价格数据"""
        file_path = os.path.join(self.data_path, "etf_day_with_basic_2022_2025.csv")
        try:
            # 使用 utf-8-sig 读取含 BOM 的文件
            df = pd.read_csv(file_path, encoding='utf-8-sig', low_memory=False)
            # 重命名列
            df = df.rename(columns={
                'ETF代码': 'code',
                '交易日期': 'date',
                '收盘价(元)': 'close'
            })
            # 去掉 code 的 .SH/.SZ 后缀
            df['code'] = df['code'].astype(str).str.replace(r'\.(SH|SZ)', '', regex=True)
            df['date'] = pd.to_datetime(df['date'])
            self.etf_data = df[['code', 'date', 'close']]
        except FileNotFoundError:
            print(f"⚠️ 警告: ETF价格文件不存在 ({file_path})")
            self.etf_data = pd.DataFrame(columns=['code', 'date', 'close'])
        except Exception as e:
            print(f"⚠️ 警告: ETF价格数据加载失败: {e}")
            self.etf_data = pd.DataFrame(columns=['code', 'date', 'close'])

    @staticmethod
    def _publication_cutoff(data_date: pd.Timestamp, indicator: str) -> pd.Timestamp:
        """计算各指标的发布滞后日期"""
        m, y = data_date.month, data_date.year
        # 下月第一天
        if m == 12:
            next_month_first = pd.Timestamp(y + 1, 1, 1)
        else:
            next_month_first = pd.Timestamp(y, m + 1, 1)

        if indicator == "pmi":
            return next_month_first  # 次月1日
        elif indicator in ("cpi", "ppi"):
            return next_month_first.replace(day=10)  # 次月10日
        elif indicator in ("m2", "sf"):
            return next_month_first.replace(day=15)  # 次月15日
        elif indicator == "gdp":
            return data_date + pd.Timedelta(days=16)  # 季末+16日
        else:  # shibor
            return data_date + pd.Timedelta(days=1)  # T+1日

    def get_macro_for_decision(self, decision_date: datetime, strict_publication_lag: bool = True) -> MacroData:
        """获取决策日的宏观数据"""
        decision_ts = pd.Timestamp(decision_date)

        def get_latest(df, key_col, indicator, n=6):
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
                print(f"⚠️ 警告: {key_col} 无可用数据")
                # 返回最后一条
                if len(df) > 0:
                    return df.iloc[-1], df.tail(n)[key_col].tolist()
                return None, []

            latest = valid.iloc[-1]
            history = valid.tail(n)[key_col].tolist()

            # 断言保护：确保不使用未来数据
            if pd.Timestamp(latest["date"]) >= decision_ts:
                print(f"⚠️ 警告: {key_col} 使用了未来数据 {latest['date']}")

            return latest, history

        # 获取各指标数据
        pmi_latest, pmi_hist = get_latest(self.pmi_data, "pmi", "pmi")
        cpi_latest, cpi_hist = get_latest(self.cpi_data, "cpi_yoy", "cpi")
        ppi_latest, ppi_hist = get_latest(self.ppi_data, "ppi_yoy", "ppi")
        m2_latest, m2_hist = get_latest(self.m2_data, "m2_yoy", "m2")
        sf_latest, sf_hist = get_latest(self.sf_data, "sf_month", "sf")
        gdp_latest, _ = get_latest(self.gdp_data, "gdp_yoy", "gdp", n=4)

        # SHIBOR 单独处理（日频）
        shibor_valid = self.shibor_data[self.shibor_data["date"] < decision_ts]
        if len(shibor_valid) > 0:
            shibor_latest = shibor_valid.iloc[-1]
        else:
            # 如果没有可用数据，使用最后一条（保守处理）
            if len(self.shibor_data) > 0:
                shibor_latest = self.shibor_data.iloc[-1]
            else:
                # 返回空数据
                shibor_latest = pd.Series({'date': decision_ts, 'shibor_1m': float('nan'), 'shibor_3m': float('nan')})

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
        """获取指定ETF在指定日期的价格"""
        if self.etf_data is None or len(self.etf_data) == 0:
            return None

        date_ts = pd.Timestamp(date)
        result = self.etf_data[
            (self.etf_data['code'] == str(etf_code)) &
            (self.etf_data['date'] <= date_ts)
        ]

        if len(result) > 0:
            return float(result.iloc[-1]['close'])
        return None

    def get_etf_prices_on_date(self, date: datetime) -> Dict[str, float]:
        """获取指定日期所有ETF的价格"""
        if self.etf_data is None or len(self.etf_data) == 0:
            return {}

        date_ts = pd.Timestamp(date)
        result = self.etf_data[self.etf_data['date'] == date_ts]

        return {row['code']: float(row['close']) for _, row in result.iterrows()}


if __name__ == "__main__":
    # 初始化并加载数据 (使用默认路径 ../../../PracticeData/)
    agent = DataAgent()  # 使用默认路径
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

    # 测试获取ETF价格
    print(f"\n测试ETF价格获取:")
    price = agent.get_etf_price('159915', datetime(2024, 3, 31))
    print(f"  159915 在 2024-03-31: {price}")