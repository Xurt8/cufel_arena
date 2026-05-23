# QMT API 参考手册

> 基于迅投知识库，对照 CUFEL Arena 策略的实际用法整理。2026-05-22

## 一、策略框架

### 编码声明
```python
#coding:gbk  # QMT 必须 GBK
#coding:utf-8  # 或 UTF-8（需和文件实际编码一致）
```

### 生命周期
```
init(C) → after_init(C) → handlebar(C) 循环 → stop(C)
```

### 上下文对象 ContextInfo (C)
- 不可添加自定义属性（会被重置）
- 用 `class G` + `g = G()` 全局变量存状态 ✓

### 运行模式
| 模式 | 启动方式 | account | 说明 |
|------|---------|:------:|------|
| 调试运行 | 编辑器"运行" | 无 | 回测用 |
| 模拟信号 | 模型交易→模拟 | 有 | 信号不成交 |
| **实盘交易** | 模型交易→实盘 | **有** | 实际下单 |

---

## 二、行情

### C.get_full_tick(code_list)
```python
tick = C.get_full_tick(['510300.SH'])
# {code: {lastPrice, open, high, low, lastClose, amount, volume,
#         askPrice[10], bidPrice[10], askVol[10], bidVol[10],
#         openInt, stockStatus, ...}}
```
- `openInt`: 0/10=正常, 1=停牌, 11=开盘前, 13=连续交易, 14=休市, 15=闭市
- 只能取最新分笔，不能取历史

### C.get_market_data_ex(fields, stock_list, period, start, end, count, dividend, subscribe)
```python
data = C.get_market_data_ex(['close','open','high','low','volume'],
    ['510300.SH'], '1d', '20260101', '', count=120)
# 返回 {code: DataFrame(index=time, columns=fields)}
```
- 回测: `subscribe=False` 读本地数据
- 实盘: `subscribe=True` 实时订阅（限500只）
- period: tick, 1m, 5m, 15m, 30m, 1h, 1d, 1w, 1mon, 1q, 1y

### C.subscribe_quote(stock, period, callback)
```python
def on_data(data):
    for s in data:
        print(s, data[s])
sub_id = C.subscribe_quote('510050.SH', '1d', callback=on_data)
```

### C.set_universe(codes)
设置股票池，用于 get_history_data（已弃用API）

---

## 三、交易

### passorder(opType, orderType, account, code, prType, price, volume, strategy, quickTrade, remark, C)

**股票买卖**:
```python
# 买入100股，对手价
passorder(23, 1101, account, '510300.SH', 14, -1, 100, '策略名', 2, '投资备注', C)
# 卖出100股，最新价（prType=0时price填0）
passorder(24, 1101, account, '510300.SH', 0, 0, 100, '策略名', 2, '投资备注', C)
```

**关键参数**:
- opType: 23=股票买入, 24=股票卖出
- orderType: 1101=按股, 1102=按金额
- prType: 0=卖5价, 5=最新价, 11=指定价, 14=对手价, 42-48=市价
- quickTrade: 0=K线走完, 1=最新bar立即, **2=任何时候立即** ← 我们用2

### cancel(orderId, accountId, accountType, C)
```python
cancel('委托号', account, 'STOCK', C)  # 返回 bool
```

### 委托状态码
| 码 | 状态 | 码 | 状态 |
|:--|------|:--|------|
| 49 | 待报 | 54 | 已撤 |
| 50 | 已报 | 55 | 部成 |
| 51 | 已报待撤 | 56 | **已成** |
| 52 | 部成待撤 | 57 | **废单** |
| 53 | 部撤 | | |

---

## 四、数据查询

### get_trade_detail_data(account, type, dataType)
```python
# 持仓
pos = get_trade_detail_data(account, 'STOCK', 'position')
r.m_strInstrumentID  # 代码
r.m_nVolume          # 总持仓
r.m_nCanUseVolume    # 可用数量
r.m_dOpenPrice       # 成本价
r.m_dPositionProfit  # 浮动盈亏
r.m_dMarketValue     # 市值
r.m_dInstrumentValue # 合约价值

# 账户
acct = get_trade_detail_data(account, 'STOCK', 'account')
acct.m_dBalance       # 总资产
acct.m_dAvailable     # 可用金额
acct.m_dPositionProfit # 持仓盈亏

# 委托
orders = get_trade_detail_data(account, 'STOCK', 'order')
o.m_strOrderSysID   # 委托号
o.m_strRemark       # 投资备注 ← 用于精确匹配
o.m_nOrderStatus    # 状态
o.m_nVolumeTraded   # 已成交
o.m_nVolumeTotalOriginal # 总委托量

# 成交
deals = get_trade_detail_data(account, 'STOCK', 'deal')
d.m_dPrice      # 成交价
d.m_nVolume     # 成交量
d.m_strRemark   # 投资备注
```

### C.get_trading_dates(code, start, end, count, period)
```python
# 获取真实交易日，自动跳过节假日
days = C.get_trading_dates('', '20260501', '20260601', 5, '1d')
# ['20260504', '20260506', '20260508', ...]
```

---

## 五、定时器

### C.run_time(funcName, period, startTime)
```python
C.run_time("on_stoploss", "5nSecond", "2020-01-01 09:31:00")  # 每5秒
C.run_time("on_monthly", "1nDay", "2020-01-01 00:01:00")      # 每天
```
- period: "NnSecond", "NnMilliSecond", "NnDay"
- funcName: 全局函数名字符串

### C.schedule_run(func, time_point, repeat, interval, name)
新版定时器，支持任务分组和取消。

---

## 六、回调（主推）

需先在 `init` 中调用 `C.set_account(account)` 启用：

| 回调 | 触发时机 |
|------|---------|
| `deal_callback(C, dealInfo)` | 成交状态变化 |
| `order_callback(C, orderInfo)` | 委托状态变化 |
| `position_callback(C, positionInfo)` | 持仓变化 |
| `account_callback(C, accountInfo)` | 账户状态变化 |
| `orderError_callback(C, orderArgs, errMsg)` | 下单异常 |

---

## 七、板块/代码

### C.get_stock_list_in_sector(name)
```python
C.get_stock_list_in_sector('沪深ETF')     # 全量ETF
C.get_stock_list_in_sector('ETF股票型')   # 股票ETF
C.get_stock_list_in_sector('ETF债券型')   # 债券ETF
C.get_stock_list_in_sector('ETF商品型')   # 商品ETF
C.get_stock_list_in_sector('ETF货币型')   # 货币ETF
C.get_stock_list_in_sector('ETF跨境型')   # 跨境ETF
C.get_stock_list_in_sector('沪深300')     # 沪深300成分股
C.get_stock_list_in_sector('SW1汽车')     # 申万行业
```

---

## 八、账户/代码类型

```python
account = '200xxxx'  # 股票账号
accountType = 'STOCK'  # 'STOCK', 'FUTURE', 'CREDIT', 'STOCK_OPTION'等

code_to_qmt: '510300' → '510300.SH'  # 5/6开头=上交所
code_to_qmt: '159915' → '159915.SZ'  # 其他=深交所
```

---

## 九、常见错误

| 错误 | 原因 | 解决 |
|------|------|------|
| `name 'account' is not defined` | 不在模型交易模式 | 切换到模型交易 |
| UTF-8 decode error | 文件编码不一致 | `#coding:gbk` + GBK编码 |
| 价格无效跳过 | tick为空(非交易时段) | 用 parquet 补充 |
| 废单 | 涨跌停限制/数量不对 | 检查 price/volume |
