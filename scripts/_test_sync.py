import sys, os
sys.path.insert(0, r'D:\长城策略交易系统\bin.x64\Lib\site-packages')
from xtquant import xtdata
from datetime import datetime, timedelta

log_path = r'D:\sync_log.txt'
with open(log_path, 'w', encoding='utf-8') as log:
    try:
        xtdata.download_sector_data()
        log.write("download_sector_data OK\n")
    except Exception as e:
        log.write(f"download_sector_data FAIL: {e}\n")
        log.flush()

    codes = ['510300', '518880', '511010', '563220']
    end = datetime.now().strftime('%Y%m%d')
    start = (datetime.now() - timedelta(days=3)).strftime('%Y%m%d')
    log.write(f"Range: {start} ~ {end}\n")
    log.flush()

    qmt_codes = [f'{c}.SH' if c.startswith(('5','6','51','56','58','59')) else f'{c}.SZ' for c in codes]
    try:
        xtdata.download_history_data2(qmt_codes, '1d', start, end)
        raw = xtdata.get_market_data_ex(['close'], qmt_codes, '1d', start, end)
        for qc in qmt_codes:
            if qc in raw and raw[qc] is not None:
                dates = [str(d)[:10] for d in raw[qc].index]
                log.write(f"  {qc}: {len(dates)} days: {dates}\n")
            else:
                log.write(f"  {qc}: NO DATA\n")
    except Exception as e:
        log.write(f"download_history FAIL: {e}\n")
    log.flush()
    log.write("DONE\n")
