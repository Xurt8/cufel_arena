"""宏观数据自动更新 — 从 akshare 抓取 PMI/CPI/M2 写入本地 CSV"""
import sys, os, pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data" / "macro"


def update_pmi():
    """制造业PMI"""
    import akshare as ak
    df = ak.macro_china_pmi()
    months = []
    for _, row in df.iterrows():
        s = str(row.iloc[0])  # col 0 = 月份
        y = s[:4]; m = s.split('年')[1].split('月')[0].zfill(2)
        months.append({'month': f'{y}-{m}', 'pmi': float(row.iloc[1])})  # col 1 = 制造业-指数
    new = pd.DataFrame(months).sort_values('month')
    _merge_csv(DATA_DIR / 'cn_pmi.csv', new, ['month', 'pmi'])
    print(f'PMI: {len(new)} rows')


def update_cpi():
    """CPI同比"""
    import akshare as ak
    df = ak.macro_china_cpi_yearly()
    rows = []
    for _, row in df.iterrows():
        try:
            dt = pd.Timestamp(row.iloc[1])  # col 1 = 日期
            v = row.iloc[2]                  # col 2 = 值
            if pd.notna(v):
                rows.append({'month': dt.strftime('%Y-%m'), 'cpi': float(v)})
        except: pass
    new = pd.DataFrame(rows).sort_values('month')
    _merge_csv(DATA_DIR / 'cn_cpi.csv', new, ['month', 'cpi'])
    print(f'CPI: {len(new)} rows')


def update_m2():
    """M2同比"""
    import akshare as ak
    df = ak.macro_china_money_supply()
    rows = []
    for _, row in df.iterrows():
        s = str(row.iloc[0]); y = s[:4]; m = s.split('年')[1].split('月')[0].zfill(2)
        rows.append({'month': f'{y}-{m}', 'm2': float(row.iloc[2])})  # col 2 = M2同比
    new = pd.DataFrame(rows).sort_values('month')
    _merge_csv(DATA_DIR / 'cn_m.csv', new, ['month', 'm2'])
    print(f'M2: {len(new)} rows')


def _merge_csv(path, new_df, cols):
    """合并：保留已有数据，只追加新月份"""
    if path.exists():
        old = pd.read_csv(path)
        old['month'] = old['month'].astype(str)
    else:
        old = pd.DataFrame(columns=cols)
    new_df['month'] = new_df['month'].astype(str)
    combined = pd.concat([old, new_df]).drop_duplicates(subset=['month'], keep='last')
    combined = combined.sort_values('month')
    combined.to_csv(path, index=False)


if __name__ == '__main__':
    print("Macro update start...")
    try:
        update_pmi()
        update_cpi()
        update_m2()
        print("Done")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
