#coding:utf-8

"""

QMT  +  T+2

============================================

    

handlebar  ~5s =SH000300=1

"""

import json, os

from datetime import datetime

EXECUTE_REAL = True

BATCH_FILE = "_batch_state.json"

BATCH_RATIOS = [0.5, 0.3, 0.2]

FIRST_CHECK_TIME = "09:31"

LAST_CHECK_TIME = "14:57"

REBALANCE_TIME = "09:45"  # 45

class G:

    stops = {}              # {code: {peak, threshold_pct, trail_profit_pct, qty, name, cost}}

    sold_codes = set()      # 

    last_minute = ""

    batch_day = 0           # : 1=D1() 2=D2() 3=D3() 0=

    holdings = {}            #  {qmt_code: }

    orders = None            #  JSON

    rebalance_done_date = "" # 

    rebalance_phase = ""     # "" | "submitted" | "verified"  

    expected_holdings = {}   # {code: target_shares}

    pending_orders = {}      #  {remark: time}    

    d1_date = ""            # D1

    d2_date = ""            # D2

    d3_date = ""            # D3

    deals = []               #  [{time, code, direction, volume, price, amount, order_id}]

    orders_log = []          #  [{time, code, direction, volume, filled, price, status, order_id}]

g = G()

def get_script_dir():
    try: return os.path.dirname(os.path.abspath(__file__))
    except: pass
    for d in ["D:\u957f\u57ce\u7b56\u7565\u4ea4\u6613\u7cfb\u7edf\python", os.getcwd()]:
        if os.path.isdir(d): return d
    return os.getcwd()

def load_orders_file():
    """Load orders JSON, try multiple paths"""
    import os, json
    candidates = [
        r"D:\qmt_orders_latest.json",
        os.path.join(os.getcwd(), "qmt_orders_latest.json"),
    ]
    for path in candidates:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    print(f"[ERROR] orders file not found, cwd={os.getcwd()}")
    return None

def code_to_qmt(code):

    return f"{code}.SH" if code.startswith(("5","6","51","56","58","59")) else f"{code}.SZ"

def get_month_trade_dates(C, y, m):

    """: D1=1, D2=3, D3=5"""

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

    # : 

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

    """"""

    try:

        rows = get_trade_detail_data(account, "stock", "position")

        if not rows: return {}

        return {str(r.m_strInstrumentID): int(r.m_nCanUseVolume) for r in rows

                if hasattr(r, 'm_strInstrumentID') and hasattr(r, 'm_nCanUseVolume')}

    except:

        return {}

# 

#   order_* 

#   passorder quickTrade=2 

# 

def do_sell(C, qmt_code, qty, label):

    """ qty GWT order_shares """

    avail = g.holdings.get(qmt_code, 0)

    if avail <= 0:

        g.holdings = query_holdings()

        avail = g.holdings.get(qmt_code, 0)

        if avail <= 0:

            print(f"  [SKIP] {qmt_code} ")

            return

    if qty > avail:

        print(f"  [ADJ] {qmt_code} {qty}{avail}")

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

        print(f"  [DONE]  {qmt_code} x{qty} @{price:.3f}")

    else:

        print(f"  [SIM]   {qmt_code} x{qty}")

def do_buy(C, qmt_code, amount_yuan, label):

    """ amount_yuan  passorder(1101) rder_value """

    tick = C.get_full_tick([qmt_code])

    if not tick or qmt_code not in tick: return

    t = tick[qmt_code]

    price = t.get("askPrice", [0])[0] or t.get("lastPrice", 0)

    if price <= 0: return

    price = round(price, 3)

    shares = int(amount_yuan / price / 100) * 100

    if shares < 100:

        print(f"  [SKIP] {qmt_code} {amount_yuan} 1(@{price:.3f})")

        return

    if EXECUTE_REAL:

        passorder(23, 1101, account, qmt_code, 11, price, shares, label, 2, '', C)

        print(f"  [DONE]  {qmt_code} x{shares} @{price:.3f}")

    else:

        print(f"  [SIM]   {qmt_code} x{shares} @{price:.3f}")

# 

def run_stoploss(C):

    """"""

    now = datetime.now()

    time_str = now.strftime("%H:%M")

    if time_str < FIRST_CHECK_TIME or time_str > LAST_CHECK_TIME: return

    if time_str == g.last_minute: return

    g.last_minute = time_str

    if not g.stops: return

    for code, info in list(g.stops.items()):

        if code in g.sold_codes: continue

        qmt_code = code_to_qmt(code)

        if qmt_code not in g.holdings and code not in g.holdings: continue 

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

            trail_tp = info.get("trail_profit_pct", 30)

            drawdown = (current - peak) / peak * 100

            triggered = drawdown <= -threshold

            tp_triggered = drawdown <= -trail_tp

            reason = "stop" if triggered else ("trail_profit" if tp_triggered else None)

            if reason:

                label = "STOP" if reason == "stop" else "TPROFIT"

                print(f"\n[{label}] {time_str} {code} {info.get('name',code)}")

                print(f"  price={current:.3f} dd={drawdown:.1f}% limit={threshold:.0f}% tp={trail_tp:.0f}%")

                bid = t.get("bidPrice", [current])[0] if t.get("bidPrice") else current

                order_price = round(bid, 3)

                try:

                    passorder(24, 1101, account, qmt_code, 11, order_price, info['qty'], '', 2, '', C)

                    print(f"  [DONE] {qmt_code} x{info['qty']} @{order_price:.3f}")

                    g.sold_codes.add(code)

                    g.holdings.pop(qmt_code, None)

                    # Log stop loss event
                    g.deals.append({
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "code": code, "name": info.get("name", code),
                        "qty": info['qty'], "price": order_price,
                        "peak": peak, "drawdown": round(drawdown, 1),
                        "threshold": threshold, "reason": reason,
                    })
                    try:
                        d = get_script_dir()
                        with open(os.path.join(d, "stoploss_log.json"), "w", encoding="utf-8") as sf:
                            json.dump({
                                "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "events": g.deals
                            }, sf, ensure_ascii=False)
                    except:
                        pass

                except Exception as e:

                    print(f"  [FAIL] {qmt_code}: {e}")

        except Exception as e:

            pass  # 

    active = sum(1 for c in g.stops if c not in g.sold_codes and code_to_qmt(c) in g.holdings)

    if now.minute % 5 == 0:

        print(f"[{time_str}] monitoring={active} triggered={len(g.sold_codes)}")

def run_rebalance(C):

    """D1"""

    if g.batch_day == 0: return

    if not g.orders: return

    target_weights = g.orders.get("target_weights", {})

    if not target_weights: return

    now = datetime.now()

    today = now.strftime("%Y-%m-%d")

    #   batch_state  

    d = get_script_dir()

    batch_path = os.path.join(d, BATCH_FILE)

    batch_state = {}

    if os.path.exists(batch_path):

        try:

            with open(batch_path, "r", encoding="utf-8") as f:

                batch_state = json.load(f)

        except: pass

    if batch_state.get("rebalance_done_date") == today:

        print(f"  [SKIP] ({today})")

        g.batch_day = 0

        g.rebalance_phase = "verified"

        return

    #   handlebar 

    if g.rebalance_phase == "submitted":

        _verify_rebalance(C, target_weights, today, batch_path, batch_state)

        return

    if g.rebalance_phase == "verified" and g.rebalance_done_date == today:

        return  # 

    # 

    # Step 1-4

    # 

    # 

    g.holdings = query_holdings()

    #   

    all_codes = list(g.holdings.keys()) + [code_to_qmt(c) for c in target_weights]

    all_tick = {}

    for qc in all_codes:

        bt = C.get_full_tick([qc])

        if bt and qc in bt: all_tick[qc] = bt[qc]

    #   

    total_value = 0.0

    try:

        acct_rows = get_trade_detail_data(account, "stock", 'account')

        if acct_rows:

            total_value = float(acct_rows[0].m_dBalance)

    except: pass

    for qc, vol in g.holdings.items():

        t = all_tick.get(qc, {})

        p = t.get("lastPrice", 0) if t else 0

        if p > 0: total_value += vol * p

    if total_value <= 0:

        total_value = 100000

        print(f"  [] {total_value/10000:.0f}")

    # 

    # Step 1:  + D3=100%

    # 

    cum_ratio = sum(BATCH_RATIOS[:g.batch_day])

    print(f"\n{'='*50}")

    print(f"  D{g.batch_day} total={total_value/10000:.1f}wan cash={cum_ratio*100:.0f}%")

    print(f"{'='*50}")

    print(f"\n  [Step1]  ({cum_ratio*100:.0f}%) /  (100%):")

    target_quantities = {}

    final_quantities = {}  # D3=100%

    for code, target_w in target_weights.items():

        qmt_code = code_to_qmt(code)

        t = all_tick.get(qmt_code, {})

        price = t.get("lastPrice", 0) if t else 0

        if price <= 0:

            print(f"    {code}: ")

            continue

        # 

        target_mv = total_value * target_w * cum_ratio

        target_shares = int(target_mv / price / 100) * 100

        if target_shares >= 100:

            target_quantities[code] = target_shares

        else:

            target_shares = 0

        # 100%

        final_mv = total_value * target_w * 1.0

        final_shares = int(final_mv / price / 100) * 100

        final_quantities[code] = final_shares

        print(f"    {code}: {target_shares} / {final_shares} ({target_mv/10000:.2f} @{price:.3f})")

    # 

    # Step 2: 

    # 

    print(f"\n  [Step2] :")

    if g.holdings:

        for qc, vol in g.holdings.items():

            code = qc.split(".")[0]

            tag = "" if code in target_weights else ""

            print(f"    {code}: {vol} ({tag})")

    else:

        print(f"    ()")

    # 

    # Step 3:  + =100%

    # 

    sell_list = []

    for qc, vol in g.holdings.items():

        code = qc.split(".")[0]

        if code not in target_weights:

            # 

            v = int(vol / 100) * 100

            if v >= 100:

                sell_list.append((qc, code, v, ""))

        elif code in final_quantities:

            # ETF(100%)

            final_v = final_quantities[code]

            if vol > final_v:

                excess = int((vol - final_v) / 100) * 100

                if excess >= 100:

                    sell_list.append((qc, code, excess, f"(>{final_v})"))

    if sell_list:

        print(f"\n  [Step3] Sell ({len(sell_list)} orders):")

        for qc, code, vol, reason in sell_list:

            try:

                passorder(24, 1101, account, qc, 0, 0, vol, "", 2, '', C)

                print(f"    [DONE]  {qc} x{vol} ({reason})")

            except Exception as e:

                print(f"    [FAIL]  {qc} x{vol}: {e}")

    else:

        print(f"\n  [Step3] No sell needed")

    # 

    # Step 4:  =  - 

    # 

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

            print(f"  [Step4] {code} need {delta} shares <1 lot")

    if buy_list:

        print(f"\n  [Step4] Buy ETFs ({len(buy_list)} orders):")

        for qmt_code, code, delta, price in buy_list:

            try:

                passorder(23, 1101, account, qmt_code, 11, price, delta, "", 2, '', C)

                print(f"    [DONE]  {qmt_code} x{delta} @{price:.3f}")

            except Exception as e:

                print(f"    [FAIL]  {qmt_code} x{delta}: {e}")

    else:

        print(f"\n  [Step4] No buy needed")

    #   

    g.expected_holdings = target_quantities

    g.rebalance_phase = "submitted"

    print(f"\n   barStep5...")

def _verify_rebalance(C, target_weights, today, batch_path, batch_state):

    """Step 5: """

    g.holdings = query_holdings()

    print(f"\n{'='*50}")

    print(f"  [Step5] ")

    print(f"{'='*50}")

    all_ok = True

    discrepancies = []

    # TF

    for code, expected in g.expected_holdings.items():

        qmt_code = code_to_qmt(code)

        actual = g.holdings.get(qmt_code, 0)

        diff = expected - actual

        if diff > 0:

            all_ok = False

            msg = f"{code}: {expected} {actual} {diff}"

            discrepancies.append(msg)

            print(f"  [] {msg}")

        elif diff < 0:

            all_ok = False

            msg = f"{code}: {expected} {actual} {-diff}"

            discrepancies.append(msg)

            print(f"  [] {msg}")

        else:

            print(f"  [OK] {code}: {actual} OK")

    # 

    for qc, vol in g.holdings.items():

        code = qc.split(".")[0]

        if code not in target_weights and vol > 0:

            all_ok = False

            msg = f"{code}: {vol}"

            discrepancies.append(msg)

            print(f"  [] {msg}")

    if all_ok:

        print(f"\n  [ D{g.batch_day} OK")

    else:

        print(f"\n  [Result] {len(discrepancies)} discrepancies:")

        for d_msg in discrepancies:

            print(f"    - {d_msg}")

        print(f"  : //")

    #   

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

        print(f"\n  T+2   ")

    else:

        next_date = [None, g.d2_date, g.d3_date][g.batch_day]

        print(f"\n  [NEXT] D{g.batch_day+1}  {next_date} ({BATCH_RATIOS[g.batch_day]*100:.0f}%)")

    print(f"  [] rebalance_done_date={today}  \n")

# 

def init(C):

    print(f"\n{'='*55}")
    print(f'  QMT Unified Trader | {"Live" if EXECUTE_REAL else "Sim"}')

    print(f"{'='*55}")

    # 1. Load holdings

    g.holdings = query_holdings()

    if g.holdings:

        print(f"  [Holdings] {len(g.holdings)} positions")

        for c, v in g.holdings.items():

            print(f"    {c}: {v}")

    else:

        print(f"  [Holdings] no positions")

    #  Streamlit 

    if g.holdings:

        try:

            hold_report = {

                "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),

                "positions": []

            }

            # 

            pos_rows = get_trade_detail_data(account, "stock", "position")

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

                pnl = pos_map.get(code, {})

                price = pnl.get("mv", 0) / shares if pnl.get("mv", 0) > 0 and shares > 0 else 0

                hold_report["positions"].append({

                    "code": code, "shares": shares, "price": round(price, 3),

                    "cost": pnl.get("cost", 0), "profit": pnl.get("profit", 0),

                    "market_value": pnl.get("mv", 0),

                })

            # Compute available cash
            total_mv = sum(p.get("market_value", 0) for p in hold_report["positions"])
            hold_report["available_cash"] = round(hold_report["total_balance"] - total_mv, 2)

            d = get_script_dir()
            with open(os.path.join(d, "qmt_holdings.json"), "w", encoding="utf-8") as f:
                json.dump(hold_report, f, ensure_ascii=False)

            # Init stoploss log if not exists
            sl_path = os.path.join(d, "stoploss_log.json")
            if not os.path.exists(sl_path):
                with open(sl_path, "w", encoding="utf-8") as sf:
                    json.dump({"updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "events": []}, sf)

            print(f"  [Export] qmt_holdings.json")

        except: pass

    # 2. Load orders

    g.sold_codes = set()

    g.orders = load_orders_file()

    if g.orders:

        date = g.orders.get("date", "?")

        stops = g.orders.get("stops", [])

        g.stops = {s["code"]: s for s in stops}

        trades = g.orders.get("trades", {})

        n_sell = len(trades.get("", [])) + len([o for o in trades.get("", []) if o.get("") == ""])

        n_sell = len(trades.get("stop_sell", [])) + len([o for o in trades.get("rebalance", []) if o.get("direction") == "sell"])
        n_buy = len([o for o in trades.get("rebalance", []) if o.get("direction") == "buy"])
        print(f"  [Orders] {date} | sell={n_sell} buy={n_buy} | stops={sum(1 for c in g.stops if code_to_qmt(c) in g.holdings or c in g.holdings)}/{len(g.stops)}")

        # universe

        if g.stops:

            try:

                codes = [code_to_qmt(c) for c in g.stops]

                C.set_universe(codes)

                print(f"  [U] universe")

            except: pass

    else:

        print(f"  [Orders] none, stoploss-only mode")

    # 3. D1=, D2=, D3=

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

        # else: 

        saved_done = state.get("rebalance_done_date", "")

        today_str = now.strftime("%Y-%m-%d")

        if saved_done == today_str:

            g.rebalance_done_date = saved_done

            g.rebalance_phase = "verified"

            print(f"  [] ({saved_done})")

        else:

            g.rebalance_phase = ""

            g.expected_holdings = {}

    g.d1_date = d1

    g.d2_date = d2

    g.d3_date = d3

    # ==== ====

    # 20265 5/1D35/8

    # if cycle == "202605":

    #     g.d3_date = "2026-05-08"

    # =================================================

    print(f"  [Rebalance] D1={g.d1_date} D2={g.d2_date} D3={g.d3_date}")

    C.run_time("on_stoploss", "5nSecond", "2020-01-01 09:31:00")

    C.run_time("on_rebalance", "60nSecond", "2020-01-01 09:45:00")

    C.run_time("on_monthly", "1nDay", "2020-01-01 00:01:00")

    C.run_time("on_order_check", "30nSecond", "2020-01-01 09:31:00")

    # 

    if state.get("cycle", "") != cycle:

        with open(batch_path, "w", encoding="utf-8") as f:

            json.dump({"cycle": cycle, "d1_date": d1, "d2_date": d2, "d3_date": d3}, f)

        print(f"  []  {cycle}")

def on_order_check(C):

    """30"""

    if not g.pending_orders:

        return

    try:

        orders = get_trade_detail_data(account, "stock", "order")

    except:

        return

    now = datetime.now()

    for o in orders:

        st = int(getattr(o, "m_nOrderStatus", 3))

        if st >= 3:

            continue  # /

        code = str(o.m_strInstrumentID) if hasattr(o, 'm_strInstrumentID') else ""

        vol = int(getattr(o, 'm_nVolumeTotalOriginal', 0))

        ref = str(getattr(o, 'm_strOrderRef', ""))

        # 

        for po in list(g.pending_orders):

            if po["code"] in code and po["qty"] == vol:

                elapsed = (now - po["time"]).total_seconds()

                if elapsed > 30:

                    try:

                        cancel(str(o.m_strOrderSysID), account, "stock", C)

                        print(f"  [] {code} x{vol} {elapsed:.0f}s")

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

    """ Streamlit """

    d = get_script_dir()

    path = os.path.join(d, "_trade_report.json")

    report = {

        "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),

        "deals": g.deals[-500:],    # 500

        "orders": g.orders_log[-200:],  # 200

    }

    try:

        with open(path, "w", encoding="utf-8") as f:

            json.dump(report, f, ensure_ascii=False)

    except:

        pass

def deal_callback(C, dealInfo):

    """QMT"""

    try:

        code = str(dealInfo.m_strInstrumentID) if hasattr(dealInfo, 'm_strInstrumentID') else ""

        vol = int(getattr(dealInfo, 'm_nVolume', 0))

        price = round(float(getattr(dealInfo, 'm_dPrice', 0)), 3)

        amount = round(float(getattr(dealInfo, 'm_dAmount', 0)), 2)

        direction = "" if getattr(dealInfo, 'm_nOrderType', 0) in (23, 27) else ""

        d = {"time": datetime.now().strftime("%H:%M:%S"), "code": code,

             "direction": direction, "volume": vol, "price": price,

             "amount": amount, "order_id": str(getattr(dealInfo, 'm_strOrderRef', ''))}

        g.deals.append(d)

        print(f"[] {d['time']} {d['direction']} {code} x{vol} @{price:.3f} ={amount:.2f}")

        # 

        remark = str(getattr(dealInfo, 'm_strRemark', ''))

        if remark and remark in g.pending_orders:

            del g.pending_orders[remark]

        save_trade_report()

    except Exception as e:

        print(f"[deal_callback err] {e}")

def order_callback(C, orderInfo):

    """QMT"""

    try:

        status_map = {0: "", 1: "", 2: "", 3: "", 4: "", 5: "", 6: ""}

        st = int(getattr(orderInfo, 'm_nOrderStatus', 0))

        o = {

            "time": datetime.now().strftime("%H:%M:%S"),

            "code": str(orderInfo.m_strInstrumentID) if hasattr(orderInfo, 'm_strInstrumentID') else "",

            "direction": "" if getattr(orderInfo, 'm_nOrderType', 0) in (23, 27) else "",

            "volume": int(getattr(orderInfo, 'm_nVolumeTotal', 0)),

            "filled": int(getattr(orderInfo, 'm_nVolumeTraded', 0)),

            "price": round(float(getattr(orderInfo, 'm_dPrice', 0)), 3),

            "status": status_map.get(st, str(st)),

            "order_id": str(getattr(orderInfo, 'm_strOrderRef', '')),

        }

        g.orders_log.append(o)

        if st >= 3:

            print(f"[] {o['time']} {o['direction']} {o['code']} {o['volume']} {o['status']}")

        save_trade_report()

    except Exception as e:

        print(f"[order_callback err] {e}")

def position_callback(C, positionInfo):

    """"""

    try:

        code = str(getattr(positionInfo, 'm_strInstrumentID', ''))

        vol = int(getattr(positionInfo, 'm_nVolume', 0))

        if code:

            g.holdings[code] = vol

    except: pass

def account_callback(C, accountInfo):

    """"""

    try:

        status = str(getattr(accountInfo, 'm_strStatus', ''))

        if status:

            print(f'[Account] {datetime.now().strftime("%H:%M:%S")} status={status}')

    except:

        pass

def orderError_callback(C, orderArgs, errMsg):

    """"""

    try:

        code = str(getattr(orderArgs, 'm_strInstrumentID', '')) if hasattr(orderArgs, 'm_strInstrumentID') else ""

        print(f"[] {code}: {errMsg}")

    except:

        pass

