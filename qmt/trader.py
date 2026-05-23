#coding:gbk
"""
QMT 统一交易脚本：止损监控 + 月度调仓 T+2
============================================
单一进程：先查持仓 → 检查止损 → 执行调仓
handlebar 每 ~5s 触发（默认品种=SH000300，周期=1分钟）
"""
import json, os
from datetime import datetime

EXECUTE_REAL = True
BATCH_FILE = "_batch_state.json"
BATCH_RATIOS = [0.5, 0.3, 0.2]
FIRST_CHECK_TIME = "09:31"
LAST_CHECK_TIME = "14:57"
REBALANCE_TIME = "09:45"  # 调仓延迟到开盘45分钟后，避开开盘剧烈波动

class G:
    stops = {}              # {code: {peak, threshold_pct, qty, name, cost}}
    sold_codes = set()      # 已触发止损的代码
    last_minute = ""
    batch_day = 0           # 当天批次: 1=D1(周一) 2=D2(周三) 3=D3(周五) 0=非交易日
    holdings = {}            # 实际持仓 {qmt_code: 可用股数}
    orders = None            # 调仓指令 JSON
    rebalance_done_date = "" # 当天调仓是否已执行（日期字符串）
    rebalance_phase = ""     # "" | "submitted" | "verified" — 验证状态机
    expected_holdings = {}   # {code: target_shares}
    pending_orders = {}      # 待确认委托 {remark: time}  防重复下单 — 当天目标用于验证
    d1_date = ""            # 本月D1日期（第一周周一）
    d2_date = ""            # 本月D2日期（第一周周三）
    d3_date = ""            # 本月D3日期（第一周周五）
    deals = []               # 成交记录 [{time, code, direction, volume, price, amount, order_id}]
    orders_log = []          # 委托记录 [{time, code, direction, volume, filled, price, status, order_id}]
g = G()

def get_script_dir():
    try: return os.path.dirname(os.path.abspath(__file__))
    except: pass
    for d in [r"D:\长城策略交易系统\python", os.getcwd()]:
        if os.path.isdir(d): return d
    return os.getcwd()

def load_orders_file():
    # 只读这一份，不扫描不猜测
    path = r"D:\长城策略交易系统\python\qmt_orders_latest.json"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    print(f"[ERROR] 未找到指令文件: {path}")
    return None

def code_to_qmt(code):
    return f"{code}.SH" if code.startswith(("5","6","51","56","58","59")) else f"{code}.SZ"

def get_month_trade_dates(C, y, m):
    """用真实交易日计算: D1=第1个交易日, D2=第3个, D3=第5个（自动跳过节假日）"""
    start = "%04d%02d01" % (y, m)
    if m == 12:
        end = "%04d0101" % (y + 1)
    else:
        end = "%04d%02d01" % (y, m + 1)
    try:
        days = C.get_trading_dates('', start, end, 5, '1d')
        if days and len(days) >= 5:
            d1 = days[0][:4] + "-" + days[0][4:6] + "-" + days[0][6:8]
            d2 = days[2][:4] + "-" + days[2][4:6] + "-" + days[2][6:8]
            d3 = days[4][:4] + "-" + days[4][4:6] + "-" + days[4][6:8]
            return d1, d2, d3
    except:
        pass
    # 回退: 自然日计算
    def first_weekday(w):
        for d in range(1, 8):
            if __import__('datetime').datetime(y, m, d).weekday() == w:
                return __import__('datetime').datetime(y, m, d)
        return None
    d1 = first_weekday(0)
    if d1 is None:
        return "", "", ""
    d2 = d1 + __import__('datetime').timedelta(days=2)
    d3 = d1 + __import__('datetime').timedelta(days=4)
    return d1.strftime("%Y-%m-%d"), d2.strftime("%Y-%m-%d"), d3.strftime("%Y-%m-%d")
def query_holdings():
    """查询实际持仓"""
    try:
        rows = get_trade_detail_data(account, "stock", "position")
        if not rows: return {}
        return {str(r.m_strInstrumentID): int(r.m_nCanUseVolume) for r in rows
                if hasattr(r, 'm_strInstrumentID') and hasattr(r, 'm_nCanUseVolume')}
    except:
        return {}

# ═══════════════════════════════════════════════════════════
#  调仓用 order_* 系列（自动算价格、方向、取整）
#  止损用 passorder（需要 quickTrade=2 立即执行）
# ═══════════════════════════════════════════════════════════

def do_sell(C, qmt_code, qty, label):
    """卖出 qty 股。GWT order_shares 自动取对手价、整手"""
    avail = g.holdings.get(qmt_code, 0)
    if avail <= 0:
        g.holdings = query_holdings()
        avail = g.holdings.get(qmt_code, 0)
        if avail <= 0:
            print(f"  [SKIP] {qmt_code} 无持仓")
            return
    if qty > avail:
        print(f"  [ADJ] {qmt_code} 指令{qty}股→{avail}股")
        qty = avail
    qty = int(qty / 100) * 100
    if qty <= 0: return
    tick = C.get_full_tick([qmt_code])
    if not tick or qmt_code not in tick: return
    t = tick[qmt_code]
    price = t.get("bidPrice", [0])[0] or t.get("lastPrice", 0)
    if price <= 0: return
    price = round(price, 3)
    if EXECUTE_REAL:
        passorder(24, 1101, account, qmt_code, 11, price, qty, label, 2, '', C)
        print(f"  [DONE] 卖 {qmt_code} x{qty} @{price:.3f}")
    else:
        print(f"  [SIM]  卖 {qmt_code} x{qty}")

def do_buy(C, qmt_code, amount_yuan, label):
    """买入 amount_yuan 元。用 passorder(1101) 手工算股数——order_value 实盘不生效"""
    tick = C.get_full_tick([qmt_code])
    if not tick or qmt_code not in tick: return
    t = tick[qmt_code]
    price = t.get("askPrice", [0])[0] or t.get("lastPrice", 0)
    if price <= 0: return
    price = round(price, 3)
    shares = int(amount_yuan / price / 100) * 100
    if shares < 100:
        print(f"  [SKIP] {qmt_code} {amount_yuan}元 不足1手(@{price:.3f})")
        return
    if EXECUTE_REAL:
        passorder(23, 1101, account, qmt_code, 11, price, shares, label, 2, '', C)
        print(f"  [DONE] 买 {qmt_code} x{shares} @{price:.3f}")
    else:
        print(f"  [SIM]  买 {qmt_code} x{shares} @{price:.3f}")

# ═══════════════════════════════════════════════════════════
def run_stoploss(C):
    """检查止损条件，触发则下单卖出"""
    now = datetime.now()
    time_str = now.strftime("%H:%M")
    if time_str < FIRST_CHECK_TIME or time_str > LAST_CHECK_TIME: return
    if time_str == g.last_minute: return
    g.last_minute = time_str
    if not g.stops: return

    for code, info in list(g.stops.items()):
        if code in g.sold_codes: continue
        qmt_code = code_to_qmt(code)
        try:
            tick = C.get_full_tick([qmt_code])
            if not tick or qmt_code not in tick: continue
            t = tick[qmt_code]
            current = t.get("lastPrice", 0)
            if current <= 0: continue
            oi = t.get("openInt", 0)
            if oi not in (0, 10, 13, 14, 15): continue
            peak = max(info["peak"], t.get("high", current))
            threshold = info.get("threshold_pct", 8)
            drawdown = (current - peak) / peak * 100
            if drawdown <= -threshold:
                print(f"\n[STOP] {time_str} {code} {info.get('name',code)}")
                print(f"  现价={current:.3f} 回撤={drawdown:.1f}% 阈值={threshold:.0f}%")
                bid = t.get("bidPrice", [current])[0] if t.get("bidPrice") else current
                order_price = round(bid, 3)
                try:
                    passorder(24, 1101, account, qmt_code, 11, order_price, info['qty'], '止损', 2, '', C)
                    print(f"  [DONE] {qmt_code} x{info['qty']} @{order_price:.3f}")
                    g.sold_codes.add(code)
                    g.holdings.pop(qmt_code, None)  # 从持仓缓存移除
                except Exception as e:
                    print(f"  [FAIL] {qmt_code}: {e}")
        except Exception as e:
            pass  # 静默跳过单只错误

    active = len(g.stops) - len(g.sold_codes)
    if now.minute % 5 == 0:
        print(f"[{time_str}] 监控{active}只 | 已触发{len(g.sold_codes)}只")

def run_rebalance(C):
    """执行月度调仓——D1五步：计算目标→查持仓→卖出→买入→验证"""
    if g.batch_day == 0: return
    if not g.orders: return

    target_weights = g.orders.get("target_weights", {})
    if not target_weights: return

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")

    # ── 重启保护：检查 batch_state 中是否已完成今日调仓 ──
    d = get_script_dir()
    batch_path = os.path.join(d, BATCH_FILE)
    batch_state = {}
    if os.path.exists(batch_path):
        try:
            with open(batch_path, "r", encoding="utf-8") as f:
                batch_state = json.load(f)
        except: pass
    if batch_state.get("rebalance_done_date") == today:
        print(f"  [SKIP] 今日调仓已完成({today})，跳过")
        g.batch_day = 0
        g.rebalance_phase = "verified"
        return

    # ── 验证阶段（第二次 handlebar 触发）──
    if g.rebalance_phase == "submitted":
        _verify_rebalance(C, target_weights, today, batch_path, batch_state)
        return

    if g.rebalance_phase == "verified" and g.rebalance_done_date == today:
        return  # 今日已完成，不再执行

    # ═══════════════════════════════════════════
    # 首次执行：Step 1-4
    # ═══════════════════════════════════════════

    # 刷新持仓
    g.holdings = query_holdings()

    # ── 获取行情 ──
    all_codes = list(g.holdings.keys()) + [code_to_qmt(c) for c in target_weights]
    all_tick = {}
    for qc in all_codes:
        bt = C.get_full_tick([qc])
        if bt and qc in bt: all_tick[qc] = bt[qc]

    # ── 获取账户真实总资产 ──
    total_value = 0.0
    try:
        acct_rows = get_trade_detail_data(g.acct, g.acct_type, 'account')
        if acct_rows:
            total_value = float(acct_rows[0].m_dBalance)
    except: pass
    for qc, vol in g.holdings.items():
        t = all_tick.get(qc, {})
        p = t.get("lastPrice", 0) if t else 0
        if p > 0: total_value += vol * p
    if total_value <= 0:
        total_value = 100000
        print(f"  [估值] 非交易时段，用固定总资产{total_value/10000:.0f}万")

    # ═══════════════════════════════════════════
    # Step 1: 当天目标 + 最终目标（D3=100%）持仓数量
    # ═══════════════════════════════════════════
    cum_ratio = sum(BATCH_RATIOS[:g.batch_day])
    print(f"\n{'='*50}")
    print(f"  D{g.batch_day} 调仓 | 总资产≈{total_value/10000:.1f}万 | 目标{cum_ratio*100:.0f}%")
    print(f"{'='*50}")
    print(f"\n  [Step1] 当天目标 (累计{cum_ratio*100:.0f}%) / 最终目标 (100%):")
    target_quantities = {}
    final_quantities = {}  # D3=100%目标，用于判断是否真正超配
    for code, target_w in target_weights.items():
        qmt_code = code_to_qmt(code)
        t = all_tick.get(qmt_code, {})
        price = t.get("lastPrice", 0) if t else 0
        if price <= 0:
            print(f"    {code}: 无实时价，跳过")
            continue
        # 当天目标
        target_mv = total_value * target_w * cum_ratio
        target_shares = int(target_mv / price / 100) * 100
        if target_shares >= 100:
            target_quantities[code] = target_shares
        else:
            target_shares = 0
        # 最终目标（100%）
        final_mv = total_value * target_w * 1.0
        final_shares = int(final_mv / price / 100) * 100
        final_quantities[code] = final_shares
        print(f"    {code}: 当天{target_shares}股 / 最终{final_shares}股 ({target_mv/10000:.2f}万 @{price:.3f})")

    # ═══════════════════════════════════════════
    # Step 2: 检查当前持仓
    # ═══════════════════════════════════════════
    print(f"\n  [Step2] 当前持仓:")
    if g.holdings:
        for qc, vol in g.holdings.items():
            code = qc.split(".")[0]
            tag = "目标内" if code in target_weights else "需清仓"
            print(f"    {code}: {vol}股 ({tag})")
    else:
        print(f"    (空仓)")

    # ═══════════════════════════════════════════
    # Step 3: 卖出（非目标清仓 + 目标超配减持，以最终目标=100%为基准）
    # ═══════════════════════════════════════════
    sell_list = []
    for qc, vol in g.holdings.items():
        code = qc.split(".")[0]
        if code not in target_weights:
            # 非目标：全部清仓
            v = int(vol / 100) * 100
            if v >= 100:
                sell_list.append((qc, code, v, "清仓"))
        elif code in final_quantities:
            # 目标ETF：超出最终目标(100%)的部分才卖出
            final_v = final_quantities[code]
            if vol > final_v:
                excess = int((vol - final_v) / 100) * 100
                if excess >= 100:
                    sell_list.append((qc, code, excess, f"超配减持(>{final_v}股)"))
    if sell_list:
        print(f"\n  [Step3] 卖出 ({len(sell_list)}笔):")
        for qc, code, vol, reason in sell_list:
            try:
                passorder(24, 1101, account, qc, 0, 0, vol, "月度调仓", 2, '', C)
                print(f"    [DONE] 卖 {qc} x{vol} ({reason})")
            except Exception as e:
                print(f"    [FAIL] 卖 {qc} x{vol}: {e}")
    else:
        print(f"\n  [Step3] 无需卖出")

    # ═══════════════════════════════════════════
    # Step 4: 对比→买入（差额 = 当天目标 - 当前持仓）
    # ═══════════════════════════════════════════
    buy_list = []
    for code, target_shares in target_quantities.items():
        qmt_code = code_to_qmt(code)
        cur_shares = g.holdings.get(qmt_code, 0)
        delta = target_shares - cur_shares
        if delta >= 100:
            t = all_tick.get(qmt_code, {})
            price = t.get("askPrice", [0])[0] or t.get("lastPrice", 0)
            if price <= 0: continue
            price = round(price, 3)
            buy_list.append((qmt_code, code, delta, price))
        elif delta > 0:
            print(f"  [Step4] {code} 差额{delta}股不足1手，跳过")

    if buy_list:
        print(f"\n  [Step4] 买入目标ETF ({len(buy_list)}笔):")
        for qmt_code, code, delta, price in buy_list:
            try:
                passorder(23, 1101, account, qmt_code, 11, price, delta, "月度调仓", 2, '', C)
                print(f"    [DONE] 买 {qmt_code} x{delta} @{price:.3f}")
            except Exception as e:
                print(f"    [FAIL] 买 {qmt_code} x{delta}: {e}")
    else:
        print(f"\n  [Step4] 无需买入")

    # ── 每天进入验证等待 ──
    g.expected_holdings = target_quantities
    g.rebalance_phase = "submitted"
    print(f"\n  → 委托已提交，等待下次bar执行Step5验证...")


def _verify_rebalance(C, target_weights, today, batch_path, batch_state):
    """Step 5: 验证调仓结果，持久化完成状态"""
    g.holdings = query_holdings()

    print(f"\n{'='*50}")
    print(f"  [Step5] 调仓后持仓验证")
    print(f"{'='*50}")

    all_ok = True
    discrepancies = []

    # 检查目标ETF是否到位
    for code, expected in g.expected_holdings.items():
        qmt_code = code_to_qmt(code)
        actual = g.holdings.get(qmt_code, 0)
        diff = expected - actual
        if diff > 0:
            all_ok = False
            msg = f"缺{code}: 应有{expected}股 实有{actual}股 缺{diff}股"
            discrepancies.append(msg)
            print(f"  [缺] {msg}")
        elif diff < 0:
            all_ok = False
            msg = f"多{code}: 应有{expected}股 实有{actual}股 多{-diff}股"
            discrepancies.append(msg)
            print(f"  [多] {msg}")
        else:
            print(f"  [OK] {code}: {actual}股 OK")

    # 检查非目标是否已清仓
    for qc, vol in g.holdings.items():
        code = qc.split(".")[0]
        if code not in target_weights and vol > 0:
            all_ok = False
            msg = f"残留{code}: 应清仓但仍有{vol}股"
            discrepancies.append(msg)
            print(f"  [残留] {msg}")

    if all_ok:
        print(f"\n  [完成] 持仓与D{g.batch_day}目标一致 OK")
    else:
        print(f"\n  [注意] 存在{len(discrepancies)}项差异:")
        for d_msg in discrepancies:
            print(f"    - {d_msg}")
        print(f"  可能原因: 委托未成交/部分成交/提交失败")

    # ── 持久化完成状态 ──
    batch_state["rebalance_done_date"] = today
    batch_state["cycle"] = datetime.now().strftime("%Y%m")
    batch_state["d1_date"] = g.d1_date
    batch_state["d2_date"] = g.d2_date
    batch_state["d3_date"] = g.d3_date
    with open(batch_path, "w", encoding="utf-8") as f:
        json.dump(batch_state, f)

    g.rebalance_done_date = today
    g.rebalance_phase = "verified"

    if g.batch_day >= 3:
        print(f"\n  T+2 完成 — 本月调仓结束")
    else:
        next_date = [None, g.d2_date, g.d3_date][g.batch_day]
        print(f"\n  [NEXT] D{g.batch_day+1} → {next_date} ({BATCH_RATIOS[g.batch_day]*100:.0f}%)")
    print(f"  [持久化] rebalance_done_date={today} → 重启不再交易\n")

# ═══════════════════════════════════════════════════════════
def init(C):
    print(f"\n{'='*55}")
    print(f"  QMT 统一交易 | {'实盘' if EXECUTE_REAL else '模拟'}")
    print(f"{'='*55}")

    # 1. 查持仓
    g.holdings = query_holdings()
    if g.holdings:
        print(f"  [持仓] {len(g.holdings)}只")
        for c, v in g.holdings.items():
            print(f"    {c}: {v}股")
    else:
        print(f"  [持仓] 查询失败")

    # 导出持仓到本地文件，供 Streamlit 自动读取
    if g.holdings:
        try:
            hold_report = {
                "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "positions": []
            }
            # 获取完整持仓信息（含盈亏）
            pos_rows = get_trade_detail_data(g.acct, g.acct_type, "position")
            pos_map = {}
            if pos_rows:
                for r in pos_rows:
                    c = str(r.m_strInstrumentID).split(".")[0]
                    pos_map[c] = {
                        "shares": int(r.m_nVolume),
                        "can_use": int(r.m_nCanUseVolume),
                        "cost": round(float(r.m_dOpenPrice), 3) if hasattr(r, 'm_dOpenPrice') else 0,
                        "profit": round(float(r.m_dPositionProfit), 2) if hasattr(r, 'm_dPositionProfit') else 0,
                        "mv": round(float(r.m_dMarketValue), 2) if hasattr(r, 'm_dMarketValue') else 0,
                    }
            for qmt_code, shares in g.holdings.items():
                code = qmt_code.split(".")[0]
                tick = C.get_full_tick([qmt_code])
                price = 0
                if tick and qmt_code in tick:
                    t = tick[qmt_code]
                    price = t.get("lastPrice", 0)
                pnl = pos_map.get(code, {})
                hold_report["positions"].append({
                    "code": code, "shares": shares, "price": price,
                    "cost": pnl.get("cost", 0), "profit": pnl.get("profit", 0),
                    "market_value": pnl.get("mv", 0),
                })
            d = get_script_dir()
            with open(os.path.join(d, "qmt_holdings.json"), "w", encoding="utf-8") as f:
                json.dump(hold_report, f, ensure_ascii=False)
            print(f"  [导出] 持仓→qmt_holdings.json")
        except: pass

    # 2. 加载指令文件
    g.sold_codes = set()
    g.orders = load_orders_file()
    if g.orders:
        date = g.orders.get("date", "?")
        stops = g.orders.get("stops", [])
        g.stops = {s["code"]: s for s in stops}
        trades = g.orders.get("trades", {})
        n_sell = len(trades.get("止损卖出", [])) + len([o for o in trades.get("调仓", []) if o.get("方向") == "卖"])
        n_buy = len([o for o in trades.get("调仓", []) if o.get("方向") == "买"])
        print(f"  [指令] {date} | 止损卖{n_sell}笔 买{n_buy}笔 | 监控{len(g.stops)}只")

        # 设置universe保持实盘持续运行
        if g.stops:
            try:
                codes = [code_to_qmt(c) for c in g.stops]
                C.set_universe(codes)
                print(f"  [U] universe已订阅")
            except: pass
    else:
        print(f"  [指令] 无——仅止损监控模式")

    # 3. 月度调仓日期（D1=第一周周一, D2=第一周周三, D3=第一周周五）
    now = datetime.now()
    cycle = now.strftime("%Y%m")
    d1, d2, d3 = get_month_trade_dates(C, now.year, now.month)
    d = get_script_dir()
    batch_path = os.path.join(d, BATCH_FILE)
    state = {}

    if os.path.exists(batch_path):
        with open(batch_path, "r", encoding="utf-8") as f:
            state = json.load(f)
        saved_cycle = state.get("cycle", "")
        if saved_cycle == cycle:
            d1 = state.get("d1_date", d1)
            d2 = state.get("d2_date", d2)
            d3 = state.get("d3_date", d3)
        # else: 新月，用刚计算的日期
        saved_done = state.get("rebalance_done_date", "")
        today_str = now.strftime("%Y-%m-%d")
        if saved_done == today_str:
            g.rebalance_done_date = saved_done
            g.rebalance_phase = "verified"
            print(f"  [分批] 今日调仓已完成({saved_done})，跳过交易")
        else:
            g.rebalance_phase = ""
            g.expected_holdings = {}

    g.d1_date = d1
    g.d2_date = d2
    g.d3_date = d3

    # ==== 节假日手动调整（如遇节假日顺延至下周同一日）====
    # 示例：2026年5月 5/1劳动节→D3顺延至5/8
    # if cycle == "202605":
    #     g.d3_date = "2026-05-08"
    # =================================================

    print(f"  [调仓日] D1={g.d1_date}(周一) D2={g.d2_date}(周三) D3={g.d3_date}(周五)")

    C.run_time("on_stoploss", "5nSecond", "2020-01-01 09:31:00")
    C.run_time("on_rebalance", "60nSecond", "2020-01-01 09:45:00")
    C.run_time("on_monthly", "1nDay", "2020-01-01 00:01:00")
    C.run_time("on_order_check", "30nSecond", "2020-01-01 09:31:00")

    # 保存到文件（新月或首次启动）
    if state.get("cycle", "") != cycle:
        with open(batch_path, "w", encoding="utf-8") as f:
            json.dump({"cycle": cycle, "d1_date": d1, "d2_date": d2, "d3_date": d3}, f)
        print(f"  [分批] 新月周期 {cycle}")

def on_order_check(C):
    """每30秒检查未成交委托，超时撤单重报"""
    if not g.pending_orders:
        return
    try:
        orders = get_trade_detail_data(g.acct, g.acct_type, "order")
    except:
        return
    now = datetime.now()
    for o in orders:
        st = int(getattr(o, "m_nOrderStatus", 3))
        if st >= 3:
            continue  # 已成/已撤，跳过
        code = str(o.m_strInstrumentID) if hasattr(o, 'm_strInstrumentID') else ""
        vol = int(getattr(o, 'm_nVolumeTotalOriginal', 0))
        ref = str(getattr(o, 'm_strOrderRef', ""))
        # 检查是否是我们提交的委托
        for po in list(g.pending_orders):
            if po["code"] in code and po["qty"] == vol:
                elapsed = (now - po["time"]).total_seconds()
                if elapsed > 30:
                    try:
                        cancel(str(o.m_strOrderSysID), g.acct, g.acct_type, C)
                        print(f"  [撤单] {code} x{vol} 超时{elapsed:.0f}s")
                    except:
                        pass
                    g.pending_orders.remove(po)
                break


def handlebar(C):
    if hasattr(C, 'is_last_bar') and not C.is_last_bar():
        return
    pass


# ======== run_time timers ========

def on_stoploss(C):
    run_stoploss(C)


def on_rebalance(C):
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    if g.d1_date and g.d2_date and g.d3_date:
        if today == g.d1_date: g.batch_day = 1
        elif today == g.d2_date: g.batch_day = 2
        elif today == g.d3_date: g.batch_day = 3
        else: g.batch_day = 0
    if g.batch_day > 0 and g.orders and g.rebalance_done_date != today:
        if now.strftime("%H:%M") >= REBALANCE_TIME:
            run_rebalance(C)


def on_monthly(C):
    now = datetime.now()
    cycle = now.strftime("%Y%m")
    if g.d1_date:
        saved_cycle = g.d1_date[:7].replace("-", "")
        if cycle != saved_cycle:
            d1, d2, d3 = get_month_trade_dates(C, now.year, now.month)
            g.d1_date, g.d2_date, g.d3_date = d1, d2, d3
            g.rebalance_done_date = ""
            g.rebalance_phase = ""
            g.expected_holdings = {}
            d = get_script_dir()
            with open(os.path.join(d, BATCH_FILE), "w", encoding="utf-8") as f:
                json.dump({"cycle": cycle, "d1_date": d1, "d2_date": d2, "d3_date": d3}, f)
            print("\n[new month] " + cycle + " D1=" + d1 + " D2=" + d2 + " D3=" + d3)

def save_trade_report():
    """保存成交记录到文件，供 Streamlit 读取"""
    d = get_script_dir()
    path = os.path.join(d, "_trade_report.json")
    report = {
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "deals": g.deals[-500:],    # 最近500笔成交
        "orders": g.orders_log[-200:],  # 最近200笔委托
    }
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False)
    except:
        pass

def deal_callback(C, dealInfo):
    """成交回报：每笔成交时QMT自动调用"""
    try:
        code = str(dealInfo.m_strInstrumentID) if hasattr(dealInfo, 'm_strInstrumentID') else ""
        vol = int(getattr(dealInfo, 'm_nVolume', 0))
        price = round(float(getattr(dealInfo, 'm_dPrice', 0)), 3)
        amount = round(float(getattr(dealInfo, 'm_dAmount', 0)), 2)
        direction = "买" if getattr(dealInfo, 'm_nOrderType', 0) in (23, 27) else "卖"
        d = {"time": datetime.now().strftime("%H:%M:%S"), "code": code,
             "direction": direction, "volume": vol, "price": price,
             "amount": amount, "order_id": str(getattr(dealInfo, 'm_strOrderRef', ''))}
        g.deals.append(d)
        print(f"[成交] {d['time']} {d['direction']} {code} x{vol} @{price:.3f} ={amount:.2f}")
        # 按投资备注移除已成交委托
        remark = str(getattr(dealInfo, 'm_strRemark', ''))
        if remark and remark in g.pending_orders:
            del g.pending_orders[remark]
        save_trade_report()
    except Exception as e:
        print(f"[deal_callback err] {e}")

def order_callback(C, orderInfo):
    """委托回报：委托状态变化时QMT自动调用"""
    try:
        status_map = {0: "未报", 1: "已报", 2: "部成", 3: "全成", 4: "部撤", 5: "全撤", 6: "废单"}
        st = int(getattr(orderInfo, 'm_nOrderStatus', 0))
        o = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "code": str(orderInfo.m_strInstrumentID) if hasattr(orderInfo, 'm_strInstrumentID') else "",
            "direction": "买" if getattr(orderInfo, 'm_nOrderType', 0) in (23, 27) else "卖",
            "volume": int(getattr(orderInfo, 'm_nVolumeTotal', 0)),
            "filled": int(getattr(orderInfo, 'm_nVolumeTraded', 0)),
            "price": round(float(getattr(orderInfo, 'm_dPrice', 0)), 3),
            "status": status_map.get(st, str(st)),
            "order_id": str(getattr(orderInfo, 'm_strOrderRef', '')),
        }
        g.orders_log.append(o)
        if st >= 3:
            print(f"[委托] {o['time']} {o['direction']} {o['code']} {o['volume']}股 {o['status']}")
        save_trade_report()
    except Exception as e:
        print(f"[order_callback err] {e}")

def position_callback(C, positionInfo):
    """持仓变化主推：自动刷新持仓缓存"""
    try:
        code = str(getattr(positionInfo, 'm_strInstrumentID', ''))
        vol = int(getattr(positionInfo, 'm_nVolume', 0))
        if code:
            g.holdings[code] = vol
    except: pass


def account_callback(C, accountInfo):
    """账户状态回调"""
    try:
        status = str(getattr(accountInfo, 'm_strStatus', ''))
        if status:
            print(f"[账户] {datetime.now().strftime('%H:%M:%S')} 状态: {status}")
    except:
        pass


def orderError_callback(C, orderArgs, errMsg):
    """下单异常主推"""
    try:
        code = str(getattr(orderArgs, 'm_strInstrumentID', '')) if hasattr(orderArgs, 'm_strInstrumentID') else ""
        print(f"[下单异常] {code}: {errMsg}")
    except:
        pass
