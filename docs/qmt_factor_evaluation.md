# 迅投内置因子 ETF 适用性评估

## 一、可用接口

| 接口 | 调用方式 | 当前使用 | ETF 适用 |
|------|---------|:--:|:--:|
| `get_full_tick` | QMT 运行时 | ✓ 止损取价 | ✓ |
| `get_market_data_ex` | QMT 运行时 | - | ✓ |
| `get_factor_value` | QMT 运行时 | - | ⚠ 部分 |
| `ext_data` | 需预定义扩展数据 | - | △ 需配置 |
| `call_vba` | VBA 模型 | - | △ 需建模 |

## 二、价格类因子（对 ETF 直接可用）

| 因子 | 迅投接口 | 当前自建 | 评估 | 建议 |
|------|---------|:--:|------|------|
| N日动量 | `get_factor_value` 或自算 | ✓ mom_21d/60d | 与自算等价 | 保留自算 |
| 波动率 | 自算对数收益 | ✓ ann_vol | 自算即可 | 保留自算 |
| RSI | `get_factor_value` | - | 拥挤度指标 | **可选加** |
| 布林带位置 | 自算 | - | 与 pos_60 重叠 | 不需要 |
| MA 偏离度 | 自算 | - | 与 trend 类似 | 不需要 |

## 三、量价/资金流因子（QMT 独有，自算不出的）

| 因子 | 数据来源 | 说明 | 对 ETF 意义 | 建议 |
|------|---------|------|-----------|------|
| **换手率** | `get_turnover_rate` | 日内换手 | 反映交投活跃度 | **加** |
| **资金流向** | L2 数据 | 主力/散户资金流 | 机构偏好信号 | △ 需VIP |
| **北向资金** | `get_north_finance_change` | 沪深港通资金 | 仅对港股通ETF | ✗ |
| **成交量比** | 自算 vol/vol_ma | 放量/缩量 | 动量确认 | **加** |
| 振幅比 | 自算 (high-low)/close | 日内波动 | 与 vol_s 重叠 | 不需要 |

## 四、ETF 特有因子（迅投内置）

| 因子 | 接口 | 说明 | 建议 |
|------|------|------|------|
| **IOPV 折溢价** | `get_etf_iopv` | ETF 净值 vs 市价 | **加** — 折价买入有安全边际 |
| **申赎清单** | `get_etf_info` | 成分股构成 | △ VIP权限 |
| 基金规模 | 无法直接获取 | 份额 × 净值 | ✗ 数据不可得 |

## 五、不适用 ETF 的因子（跳过）

| 因子类型 | 原因 |
|---------|------|
| 基本面(P/E, P/B, ROE) | ETF 是组合，成分股加权的基本面不等于ETF的基本面 |
| 一致预期/分析师评级 | 股票因子，ETF 没有 |
| 质押/股东相关 | 股票专属 |
| 龙虎榜 | 股票专属 |
| 限售解禁 | 股票专属 |

## 六、建议采纳因子

基于当前策略架构，建议新增 3 个因子：

```
原有 3 因子: trend_60d(30%) + mom_60d(30%) + vol_s(40%)

新增 3 因子:
  turnover_ratio (换手率): 交投活跃度，放大趋势信号可信度
  volume_surge (量比): 放量突破确认，放量下跌预警  
  iopv_discount (IOPV折溢价): 折价时买入有安全边际

新公式:
  trend × 0.25 + mom_60d × 0.25 + vol_s × 0.25
  + turnover_ratio × 0.10 + volume_surge × 0.10 + iopv_discount × 0.05
```

| 因子 | 计算方式 | 数据来源 | 实现难度 |
|------|---------|---------|:--:|
| turnover_ratio | `volume / volume_ma_20`，高=活跃 | parquet 自算 | 低 |
| volume_surge | `(vol_5d - vol_20d) / vol_20d` | parquet 自算 | 低 |
| iopv_discount | `(IOPV - lastPrice) / IOPV` | QMT `get_etf_iopv` | 中(QMT内) |

## 七、实施建议

1. **turnover_ratio 和 volume_surge** 从 parquet 自算，与现有评分引擎无依赖，可直接加入
2. **iopv_discount** 只能在 QMT 策略内获取（`get_etf_iopv` 是 ContextInfo 方法），Streamlit 评分时不可用——作为盘中择时参考而非选基因子
3. 权重 25/25/25/10/10/5 需要通过回测验证最优性
