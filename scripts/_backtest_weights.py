"""回测对比不同评分权重 — 唯一入口 src/backtest/engine.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from backtest.engine import compare_weights

schemes = {
    "A-当前(30/30/25/15)": {"mom": 0.30, "vol": 0.30, "sharpe": 0.25, "flow": 0.15},
    "B-偏动量(40/20/20/20)": {"mom": 0.40, "vol": 0.20, "sharpe": 0.20, "flow": 0.20},
    "C-等权(25/25/25/25)": {"mom": 0.25, "vol": 0.25, "sharpe": 0.25, "flow": 0.25},
    "D-无流量(35/35/30/0)": {"mom": 0.35, "vol": 0.35, "sharpe": 0.30, "flow": 0.00},
    "E-重夏普(20/20/40/20)": {"mom": 0.20, "vol": 0.20, "sharpe": 0.40, "flow": 0.20},
    "F-重低波(20/45/20/15)": {"mom": 0.20, "vol": 0.45, "sharpe": 0.20, "flow": 0.15},
}

print("Scoring Weight Backtest (2021-2026)")
print("=" * 60)
df = compare_weights(schemes)
if not df.empty:
    print("\n===== RANKING =====")
    for i, row in df.iterrows():
        flag = " <<< BEST" if i == df.index[0] else ""
        print(f"{row['scheme']}: Sharpe={row['sharpe_ratio']} Ret={row['total_return']}% DD={row['max_drawdown']}%{flag}")
else:
    print("NO RESULTS")
