"""
xtdata 统一数据接口 — 替代 ClickHouse
=======================================
全程使用 QMT xtdata 本地数据，MiniQMT 需在后台运行。
"""
import os, time, requests
import numpy as np
import pandas as pd

# QMT xtquant 路径（需 Python ≤ 3.11）
_QMT_LIB = r'D:/长城策略交易系统/bin.x64/Lib/site-packages'
import sys
if _QMT_LIB not in sys.path:
    sys.path.insert(0, _QMT_LIB)

try:
    from xtquant import xtdata
    _XTDATA_OK = True
except ImportError:
    _XTDATA_OK = False
    xtdata = None

_NAME_CACHE = {}

# ── ETF 宇宙 ────────────────────────────────────────────
def get_etf_universe() -> dict:
    """从 xtdata 获取沪深ETF列表，按名称关键字自动分类

    Returns: {"Stock": [(code, name), ...], "Bond": [...], "Commodity": [...]}
    """
    codes_raw = xtdata.get_stock_list_in_sector('沪深ETF')
    codes = [c.split('.')[0] for c in codes_raw if c.endswith(('.SH', '.SZ'))]
    if not codes:
        return {}
    names = _batch_names(codes)
    return _classify_universe(codes, names)


def _batch_names(codes: list) -> dict:
    """新浪批量获取ETF名称"""
    global _NAME_CACHE
    uncached = [c for c in codes if c not in _NAME_CACHE]
    if not uncached:
        return {c: _NAME_CACHE.get(c, c) for c in codes}

    for i in range(0, len(uncached), 40):
        batch = uncached[i:i + 40]
        symbols = ",".join(f"{'sh' if c.startswith(('5','6','51','56','58','59')) else 'sz'}{c}" for c in batch)
        try:
            resp = requests.get(f"https://hq.sinajs.cn/list={symbols}",
                headers={"Referer": "https://finance.sina.com.cn"}, timeout=10)
            resp.encoding = "gbk"
            for line in resp.text.strip().split("\n"):
                if '="' not in line: continue
                raw_code = line.split("=")[0].replace("var hq_str_", "")
                _, data = line.split('="', 1)
                parts = data.rstrip('";').split(",")
                if len(parts) >= 1 and parts[0]:
                    _NAME_CACHE[raw_code[2:]] = parts[0]
        except Exception:
            pass
        time.sleep(0.3)
    return {c: _NAME_CACHE.get(c, c) for c in codes}


def _classify_universe(codes: list, names: dict) -> dict:
    """用 xtdata 板块归属分类 ETF，比名称关键词更准确"""
    EXCLUDE_KW = ["港股", "HK", "恒生", "纳指", "纳斯达克", "标普", "道指",
                  "日经", "德国", "法国", "一倍", "两倍", "做空", "反向"]

    # ── 优先用本地板块缓存，其次 xtdata API ──
    stock_set, bond_set, money_set, commodity_set, cross_set = set(), set(), set(), set(), set()
    try:
        from src.data.local_store import get_sector_map
        cached = get_sector_map()
        if cached:
            stock_set, bond_set = cached.get("stock", set()), cached.get("bond", set())
            money_set, commodity_set = cached.get("money", set()), cached.get("commodity", set())
            cross_set = cached.get("cross", set())
    except Exception:
        pass

    if not stock_set and _XTDATA_OK:
        try:
            stock_set   = set(xtdata.get_stock_list_in_sector('ETF股票型'))
            bond_set    = set(xtdata.get_stock_list_in_sector('ETF债券型'))
            money_set   = set(xtdata.get_stock_list_in_sector('ETF货币型'))
            commodity_set = set(xtdata.get_stock_list_in_sector('ETF商品型'))
            cross_set   = set(xtdata.get_stock_list_in_sector('ETF跨境型'))
        except Exception:
            pass  # 回退到关键词

    use_sector = bool(stock_set)  # 板块数据加载成功时使用

    universe = {"Stock": [], "Bond": [], "Commodity": []}
    for code in codes:
        name = names.get(code, "")
        if not name: continue
        qmt_code = _to_qmt(code)

        if use_sector:
            # ── 板块分类 ──
            if qmt_code in cross_set:
                continue  # 跨境ETF排除
            if qmt_code in commodity_set:
                # 商品型中只保留黄金/贵金属
                if any(kw in name for kw in ["黄金","上海金","金ETF"]):
                    universe["Commodity"].append((code, name))
            elif qmt_code in bond_set or qmt_code in money_set:
                universe["Bond"].append((code, name))
            elif qmt_code in stock_set:
                universe["Stock"].append((code, name))
            # 未命中任何板块：跳过(排除)
        else:
            # ── 关键词回退 ──
            if any(kw in name for kw in EXCLUDE_KW): continue
            if any(kw in name for kw in ["黄金", "上海金"]):
                universe["Commodity"].append((code, name))
            elif any(kw in name for kw in ["国债","债","转债","城投债","利率债","信用债",
                    "短融","日利","货币","理财","现金","添益","快线","利添","财富"]):
                universe["Bond"].append((code, name))
            else:
                universe["Stock"].append((code, name))
    return universe


# ── 日线数据 ────────────────────────────────────────────
def get_daily_bars(codes: list, days: int = 130, batch_size: int = 50) -> dict:
    """批量获取日线OHLCV。分批次下载，返回 {code: DataFrame(index=date)}"""
    if not codes: return {}
    end = pd.Timestamp.now().strftime('%Y%m%d')
    start = (pd.Timestamp.now() - pd.Timedelta(days=days + 10)).strftime('%Y%m%d')

    result = {}
    for i in range(0, len(codes), batch_size):
        batch = codes[i:i + batch_size]
        qmt_codes = [_to_qmt(c) for c in batch]
        try:
            xtdata.download_history_data2(qmt_codes, '1d', start, end)
        except: pass
    # 批量读取（可一次拉全量）
    all_qmt = [_to_qmt(c) for c in codes]
    try:
        raw = xtdata.get_market_data_ex(['close','high','low','open','volume'],
            all_qmt, '1d', '', '', count=days)
    except:
        return {}
    for qc in all_qmt:
        if qc in raw and raw[qc] is not None and len(raw[qc]) >= 10:
            df = raw[qc].copy()
            df.index = pd.to_datetime(df.index)
            result[qc.split('.')[0]] = df
    return result


def get_realtime_quotes(codes: list) -> dict:
    """实时行情"""
    try:
        qmt_codes = [_to_qmt(c) for c in codes]
        tick = xtdata.get_full_tick(qmt_codes)
        return {qc.split('.')[0]: {"最新价": t.get("lastPrice", 0)}
                for qc, t in tick.items() if qc in qmt_codes and t}
    except: return {}


# ── 技术指标 ────────────────────────────────────────────
def batch_calc_metrics(codes: list, days: int = 130) -> dict:
    """批量计算 pos60/pos120/mom21d/ann_vol/latest_close

    pos60/pos120 为 0-100 范围（与旧 batch_calc_all_metrics 兼容）
    ann_vol 为 百分比（如 30 = 30%）
    mom_21d 为 小数（如 0.05 = +5%）
    """
    if not codes: return {}
    bars = get_daily_bars(codes, days=days)
    return _compute_metrics(codes, bars)


def _compute_metrics(codes: list, bars: dict) -> dict:
    result = {}
    for code in codes:
        df = bars.get(code)
        if df is None or len(df) < 10:
            result[code] = {"60日位置": 50, "120日位置": 50, "年化波动率": 0, "21日动量": 0, "latest_close": 0}
            continue

        c = df['close'].values; h = df['high'].values; l = df['low'].values
        latest_close = float(c[-1])

        # 60日位置
        n60 = min(60, len(c))
        s60_c, s60_h, s60_l = c[-n60:], h[-n60:], l[-n60:]
        hh60, ll60 = s60_h.max(), s60_l.min()
        pos60 = (latest_close - ll60) / (hh60 - ll60) * 100 if hh60 > ll60 else 50

        # 120日位置
        n120 = min(120, len(c))
        s120_c, s120_h, s120_l = c[-n120:], h[-n120:], l[-n120:]
        hh120, ll120 = s120_h.max(), s120_l.min()
        pos120 = (latest_close - ll120) / (hh120 - ll120) * 100 if hh120 > ll120 else 50

        # 年化波动率
        nv = min(60, len(c))
        s = pd.Series(c[-nv:])
        lr = np.log(s / s.shift(1)).dropna()
        ann_vol = float(lr.std() * np.sqrt(252)) * 100 if len(lr) > 5 else 0

        # 21日动量
        mom = float(c[-1] / c[-22] - 1) if len(c) >= 22 else 0

        result[code] = {"60日位置": round(pos60, 1), "120日位置": round(pos120, 1),
                        "年化波动率": round(ann_vol, 1), "21日动量": round(mom, 4),
                        "latest_close": round(latest_close, 4)}
    return result


def get_kline(codes: list, days: int = 500) -> dict:
    """获取K线用于止损计算"""
    return get_daily_bars(codes, days=days)


# ── 辅助 ────────────────────────────────────────────────
def _to_qmt(code: str) -> str:
    if code.startswith(('5', '6', '51', '56', '58', '59')):
        return f"{code}.SH"
    return f"{code}.SZ"