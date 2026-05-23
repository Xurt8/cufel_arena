"""下载 xtquant 因子到 data/factors/ — 用 QMT Python 3.11 执行"""
import sys, os, json
from pathlib import Path
from datetime import datetime

QMT_LIB = r"D:\长城策略交易系统\bin.x64\Lib\site-packages"
if QMT_LIB not in sys.path:
    sys.path.insert(0, QMT_LIB)

from xtquant import xtdata

DATA_DIR = Path(__file__).parent.parent / "data" / "factors"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 要下载的因子列表 — 按类别
FACTORS = {
    "growth": [
        "net_profit_growth_parent",   # 归属净利润增长率
        "total_profit_growth",        # 利润总额增长率
        "revenue_growth",             # 营业收入增长率
    ],
    "quality": [
        "op_cash_flow_growth_rate",   # 经营现金流增长率
        "gross_profit_margin_growth_rate",  # 毛利率增长率
    ],
    "value": [
        "pb_ratio",                   # 市净率
        "pe_ratio",                   # 市盈率
    ],
    "sentiment": [
        "davol20",                    # 20日成交量偏差
        "money_flow_20",              # 20日资金流向
        "arbr",                       # 买卖盘力道比
    ],
    "momentum": [
        "bias60",                     # 60日乖离率
        "price3m",                    # 3月价格动量
    ],
    "risk": [
        "variance60",                 # 60日年化方差
        "sharpe_ratio_60",            # 60日夏普比率
    ],
}
ALL_FACTORS = [f for flist in FACTORS.values() for f in flist]

def get_etf_codes():
    """获取所有 ETF 代码（非跨境）"""
    sectors = json.loads(open(DATA_DIR.parent / "etf_sectors.json", "r", encoding="utf-8").read())
    codes = set()
    for k in ["stock", "bond", "commodity", "money"]:
        for qc in sectors.get(k, []):
            codes.add(qc)
    return list(codes)

def download_factor(factor_name: str, stock_list: list):
    """下载单个因子历史数据"""
    print(f"  {factor_name}...", end=" ")
    try:
        xtdata.download_factor_data([factor_name], stock_list, "20200101", "20260531")
        # 获取数据
        result = {}
        for qc in stock_list:
            data = xtdata.get_factor_data([factor_name], [qc])
            if data and factor_name in data:
                result[qc] = data[factor_name]
        # 存为 JSON（按日期索引的 dict）
        fpath = DATA_DIR / f"{factor_name}.json"
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
        print(f"OK ({len(result)} codes)")
        return True
    except Exception as e:
        print(f"FAIL: {e}")
        return False

if __name__ == "__main__":
    print(f"Factor download: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Target: {DATA_DIR}")
    print()

    codes = get_etf_codes()
    print(f"ETF count: {len(codes)}")
    print()

    for category, factor_list in FACTORS.items():
        print(f"[{category}]")
        for factor in factor_list:
            download_factor(factor, codes)
        print()
    print("Done")
