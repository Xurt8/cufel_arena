"""轻量数据同步 — 纯 xtdata，无 pandas 依赖，用 QMT Python 3.6 执行"""
import sys, os, json, traceback
from datetime import datetime, timedelta

sys.path.insert(0, r'D:\长城策略交易系统\bin.x64\Lib\site-packages')
from xtquant import xtdata

# QMT exec() 环境没有 __file__，用 os.getcwd() 回退
try:
    DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
except NameError:
    DATA_DIR = os.path.join(os.getcwd(), "data")

def sync_sectors():
    """同步板块分类"""
    sectors = {}
    for label, name in [('stock','ETF股票型'),('bond','ETF债券型'),
                        ('money','ETF货币型'),('commodity','ETF商品型'),
                        ('cross','ETF跨境型')]:
        codes = xtdata.get_stock_list_in_sector(name)
        sectors[label] = codes
        print(f'  {name}: {len(codes)}')
    sectors['updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(os.path.join(DATA_DIR, 'etf_sectors.json'), 'w', encoding='utf-8') as f:
        json.dump(sectors, f, ensure_ascii=False)
    return True

def sync_names():
    """同步ETF名称"""
    all_raw = xtdata.get_stock_list_in_sector('沪深ETF')
    names = {}
    for qc in all_raw:
        try:
            detail = xtdata.get_instrument_detail(qc)
            name = detail.get('InstrumentName', '')
            code = qc.split('.')[0]
            if name and name != code:
                names[code] = name
        except: pass
    with open(os.path.join(DATA_DIR, 'etf_names.json'), 'w', encoding='utf-8') as f:
        json.dump(names, f, ensure_ascii=False, indent=2)
    print(f'  Names: {len(names)}')
    return True

def sync_etf_daily():
    """增量同步ETF日线 → CSV"""
    names_path = os.path.join(DATA_DIR, 'etf_names.json')
    with open(names_path, 'r', encoding='utf-8') as f:
        names = json.load(f)
    codes = list(names.keys())
    print(f'  ETFs: {len(codes)}')

    # Download last 10 trading days
    now = datetime.now()
    end = now.strftime('%Y%m%d')
    start = (now - timedelta(days=10)).strftime('%Y%m%d')
    print(f'  Range: {start} ~ {end}')

    rows = []
    seen_dates = set()
    for i in range(0, len(codes), 50):
        batch = codes[i:i+50]
        qb = [f'{c}.SH' if c.startswith(('5','6','51','56','58','59')) else f'{c}.SZ' for c in batch]
        try:
            xtdata.download_history_data2(qb, '1d', start, end)
            raw = xtdata.get_market_data_ex(['close','high','low','open','volume','amount'],
                                            qb, '1d', start, end)
            for qc in qb:
                if qc in raw and raw[qc] is not None and len(raw[qc]) >= 1:
                    df = raw[qc]; c = qc.split('.')[0]
                    for idx in df.index:
                        d = str(idx)[:10].replace('-','')
                        seen_dates.add(d)
                        rows.append(f"{c},{d},{df.loc[idx,'close']},{df.loc[idx,'high']},{df.loc[idx,'low']},{df.loc[idx,'open']},{df.loc[idx,'volume']}")
        except Exception as e:
            print(f'    batch {i}: {e}')
        if i % 500 == 0:
            print(f'    {min(i+50,len(codes))}/{len(codes)}: {len(rows)} rows, dates={sorted(seen_dates)}')

    csv_path = os.path.join(DATA_DIR, '_sync_pending.csv')
    with open(csv_path, 'w') as f:
        f.write("code,date,close,high,low,open,volume\n")
        f.write("\n".join(rows))
    print(f'  Saved: {len(rows)} rows, dates={sorted(seen_dates)}')
    return True

if __name__ == '__main__':
    try:
        # Download sector data first (required before get_stock_list_in_sector)
        xtdata.download_sector_data()
        log_path = os.path.join(DATA_DIR, '..', 'cache', 'sync_log.txt')
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, 'w', encoding='utf-8') as log:
            log.write(f"Sync start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            try:
                sync_sectors()
                log.write("sectors OK\n")
            except Exception as e:
                log.write(f"sectors FAIL: {e}\n{traceback.format_exc()}\n")
            try:
                sync_names()
                log.write("names OK\n")
            except Exception as e:
                log.write(f"names FAIL: {e}\n{traceback.format_exc()}\n")
            try:
                sync_etf_daily()
                log.write("etf_daily OK\n")
            except Exception as e:
                log.write(f"etf_daily FAIL: {e}\n{traceback.format_exc()}\n")
            log.write(f"Sync done: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    except Exception as e:
        pass