import os
with open(r"D:\test_qmt_run.txt", "w") as f:
    f.write(f"cwd={os.getcwd()}\n")
    try:
        import sys
        sys.path.insert(0, r"D:\长城策略交易系统\bin.x64\Lib\site-packages")
        from xtquant import xtdata
        f.write("xtdata OK\n")
        codes = xtdata.get_stock_list_in_sector("沪深ETF")
        f.write(f"codes={len(codes)}\n")
    except Exception as e:
        f.write(f"err={e}\n")
