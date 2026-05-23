"""
本地数据存储 — 统一数据层
==========================
ETF日线: MiniQMT(xtdata) → data/etf_daily.parquet
宏观数据: ClickHouse → data/macro/*.csv
名称映射: MiniQMT(xtdata) → data/etf_names.json
所有读取: 本地 parquet/CSV，无外部依赖
"""
import os, sys, json, time
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime

_PROJECT = Path(__file__).parent.parent.parent
_DATA_DIR = _PROJECT / "data"
_ETF_STORE = _DATA_DIR / "etf_daily.parquet"
_NAME_STORE = _DATA_DIR / "etf_names.json"
_SECTOR_STORE = _DATA_DIR / "etf_sectors.json"
_MACRO_DIR = _PROJECT / "data" / "macro"

# QMT xtquant 路径
_QMT_LIB = r'D:/长城策略交易系统/bin.x64/Lib/site-packages'
_xtdata = None


def _get_xtdata():
    """懒加载 xtdata（需 MiniQMT 运行）"""
    global _xtdata
    if _xtdata is None:
        if _QMT_LIB not in sys.path:
            sys.path.insert(0, _QMT_LIB)
        from xtquant import xtdata
        _xtdata = xtdata
    return _xtdata


# ═══════════════════════════════════════════════════════
#  ETF 数据同步 (MiniQMT → 本地)
# ═══════════════════════════════════════════════════════

def sync_etf_full(start_date: str = "2020-01-01") -> int:
    """从 MiniQMT 全量下载ETF日线 → data/etf_daily.parquet"""
    print(f"[sync] MiniQMT 全量下载 {start_date} ~ ...")
    xt = _get_xtdata()

    # 1. 获取全量ETF代码
    all_raw = xt.get_stock_list_in_sector('沪深ETF')
    codes = [c.split('.')[0] for c in all_raw if c.endswith(('.SH', '.SZ'))]
    print(f"  ETFs: {len(codes)}")

    # 2. 分批下载（每批50只）
    end = datetime.now().strftime('%Y%m%d')
    all_data = {}
    batch_size = 50
    for i in range(0, len(codes), batch_size):
        batch = codes[i:i + batch_size]
        qb = [f'{c}.SH' if c.startswith(('5','6','51','56','58','59')) else f'{c}.SZ' for c in batch]
        try:
            xt.download_history_data2(qb, '1d', start_date, end)
            raw = xt.get_market_data_ex(['close','high','low','open','volume','amount'],
                                        qb, '1d', '', '', count=9999)
            for qc in qb:
                if qc in raw and raw[qc] is not None and len(raw[qc]) >= 10:
                    df = raw[qc].copy()
                    df['code'] = qc.split('.')[0]
                    df = df.reset_index().rename(columns={'index': 'date'})
                    all_data[qc.split('.')[0]] = df
        except Exception as e:
            pass
        if (i // batch_size) % 10 == 0:
            print(f"  {min(i + batch_size, len(codes))}/{len(codes)}: {len(all_data)} ok")

    if not all_data:
        print("[sync] 无数据，请检查MiniQMT是否运行")
        return 0

    combined = pd.concat(all_data.values(), ignore_index=True)
    combined["date"] = pd.to_datetime(combined["date"])
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(_ETF_STORE)
    n = combined["code"].nunique()
    print(f"[sync] ETF完成: {n}只, {len(combined)}行, {_ETF_STORE.stat().st_size/1024/1024:.1f}MB")
    return n


def sync_etf_latest(days: int = 7) -> bool:
    """增量同步最近N天ETF数据（从MiniQMT）"""
    if not _ETF_STORE.exists():
        print("[sync] 无本地ETF数据，请先运行 sync_etf_full()")
        return False

    xt = _get_xtdata()
    existing = pd.read_parquet(_ETF_STORE)
    codes = existing["code"].unique().tolist()
    last_date = existing["date"].max().strftime('%Y%m%d')

    # 只更新最近N天
    start = (datetime.now() - pd.Timedelta(days=days + 3)).strftime('%Y%m%d')
    end = datetime.now().strftime('%Y%m%d')
    print(f"[sync] ETF增量 {start}~{end} ({len(codes)}只)")

    new_data = {}
    for i in range(0, len(codes), 50):
        batch = codes[i:i + 50]
        qb = [f'{c}.SH' if c.startswith(('5','6','51','56','58','59')) else f'{c}.SZ' for c in batch]
        try:
            xt.download_history_data2(qb, '1d', start, end)
            raw = xt.get_market_data_ex(['close','high','low','open','volume','amount'],
                                        qb, '1d', start, end)
            for qc in qb:
                if qc in raw and raw[qc] is not None and len(raw[qc]) >= 1:
                    df = raw[qc].copy()
                    df['code'] = qc.split('.')[0]
                    df = df.reset_index().rename(columns={'index': 'date'})
                    new_data[qc.split('.')[0]] = df
        except: pass

    if new_data:
        new_df = pd.concat(new_data.values(), ignore_index=True)
        new_df["date"] = pd.to_datetime(new_df["date"])
        combined = pd.concat([existing, new_df], ignore_index=True)
        combined = combined.drop_duplicates(subset=["code", "date"])
        combined.to_parquet(_ETF_STORE)
        print(f"[sync] ETF增量: +{len(new_df)}行")
    else:
        print("[sync] ETF已是最新")
    return True


# ═══════════════════════════════════════════════════════
#  名称同步 (MiniQMT → 本地)
# ═══════════════════════════════════════════════════════

def sync_names() -> int:
    """从 MiniQMT 同步ETF名称 → data/etf_names.json"""
    xt = _get_xtdata()
    all_raw = xt.get_stock_list_in_sector('沪深ETF')
    print(f"[sync] 名称: {len(all_raw)} ETFs")

    names = {}
    for qc in all_raw:
        try:
            detail = xt.get_instrument_detail(qc)
            name = detail.get('InstrumentName', '')
            code = qc.split('.')[0]
            if name and name != code:
                names[code] = name
        except: pass

    with open(_NAME_STORE, 'w', encoding='utf-8') as f:
        json.dump(names, f, ensure_ascii=False, indent=2)
    print(f"[sync] 名称: {len(names)} 保存")
    return len(names)


def sync_sectors() -> bool:
    """从 MiniQMT 同步ETF板块分类 → data/etf_sectors.json"""
    xt = _get_xtdata()
    print("[sync] 板块分类...")

    sectors = {}
    for label, sector_name in [("stock", "ETF股票型"), ("bond", "ETF债券型"),
                                ("money", "ETF货币型"), ("commodity", "ETF商品型"),
                                ("cross", "ETF跨境型")]:
        try:
            codes = xt.get_stock_list_in_sector(sector_name)
            sectors[label] = codes
            print(f"  {sector_name}: {len(codes)}")
        except Exception as e:
            print(f"  {sector_name}: 失败 {e}")
            sectors[label] = []

    if not any(sectors.values()):
        print("[sync] 板块数据为空，请检查MiniQMT")
        return False

    sectors["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(_SECTOR_STORE, 'w', encoding='utf-8') as f:
        json.dump(sectors, f, ensure_ascii=False)
    print(f"[sync] 板块: 已保存")
    return True


# ═══════════════════════════════════════════════════════
#  宏观数据同步 (ClickHouse → 本地)
# ═══════════════════════════════════════════════════════

def sync_macro() -> bool:
    """从 ClickHouse 同步宏观CSV → data/macro/（仅当CH可用时）"""
    try:
        from quantchdb import ClickHouseDatabase
        from dotenv import load_dotenv
        load_dotenv(_PROJECT / ".env")
        ch = ClickHouseDatabase(config={
            "host": os.getenv("CHDB_HOST", "10.13.66.5"),
            "port": int(os.getenv("CHDB_PORT", "20108")),
            "user": os.getenv("CHDB_USER", "cufel_arena_etf_reader"),
            "password": os.getenv("CHDB_PASSWORD", "cufel_arena_etf_404"),
            "database": os.getenv("CHDB_DATABASE", "etf"),
        }, terminal_log=False)
    except ImportError:
        print("[sync] ClickHouse不可用，跳过宏观同步")
        return False

    print("[sync] 宏观数据无需从CH同步（已有本地CSV）")
    return True


# ═══════════════════════════════════════════════════════
#  统一更新入口
# ═══════════════════════════════════════════════════════

def update_all():
    """每日一键更新所有数据"""
    print("=" * 50)
    print("  数据更新 " + datetime.now().strftime('%Y-%m-%d %H:%M'))
    print("=" * 50)
    sync_names()
    sync_sectors()
    if _ETF_STORE.exists():
        sync_etf_latest()
    else:
        sync_etf_full()
    sync_macro()
    print("=" * 50)
    print("  更新完成")


# ═══════════════════════════════════════════════════════
#  数据读取（纯本地，无外部依赖）
# ═══════════════════════════════════════════════════════

def get_bars(codes: list, days: int = 130) -> dict:
    """读取日线 {code: DataFrame(index=date)}"""
    if not _ETF_STORE.exists():
        return {}
    df = pd.read_parquet(_ETF_STORE)
    result = {}
    for code in codes:
        sub = df[df["code"] == code]
        if len(sub) < 10:
            continue
        sub = sub.sort_values("date").tail(days)
        result[code] = sub.set_index("date")
    return result


def get_latest_close(codes: list) -> dict:
    """最新收盘价"""
    if not _ETF_STORE.exists():
        return {}
    df = pd.read_parquet(_ETF_STORE)
    latest = df[df["code"].isin(codes)].groupby("code").last()
    return {c: float(latest.loc[c, "close"]) for c in codes if c in latest.index}


def get_names() -> dict:
    """读取名称映射"""
    if _NAME_STORE.exists():
        with open(_NAME_STORE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def get_sector_map() -> dict:
    """读取板块分类缓存 {stock: set, bond: set, ...}"""
    if not _SECTOR_STORE.exists():
        return {}
    with open(_SECTOR_STORE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return {k: set(v) for k, v in data.items() if k != "updated"}