"""Compare factor weight schemes on full framework"""
import subprocess, sys, os
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

schemes = [
    ("F-原始(20/45/20/15)", "0.20,0.45,0.20,0.15"),
    ("均衡(30/30/25/15)", "0.30,0.30,0.25,0.15"),
    ("进攻(35/20/25/20)", "0.35,0.20,0.25,0.20"),
]

for label, weights in schemes:
    print(f"\n{'='*60}")
    print(f"  {label}: weights=[{weights}]")
    print(f"{'='*60}")
    code = open("scripts/_framework.py", "r", encoding="utf-8").read()
    code = code.replace(
        "SCHEME_WEIGHTS = [0.30, 0.30, 0.25, 0.15]",
        f"SCHEME_WEIGHTS = [{weights}]"
    )
    # Write and run
    with open("scripts/_tmp_framework.py", "w", encoding="utf-8") as f:
        f.write(code)
    result = subprocess.run([sys.executable, "scripts/_tmp_framework.py"],
                            capture_output=True, text=True, timeout=600)
    # Print key metrics
    for line in result.stdout.split("\n"):
        if any(k in line for k in ["Return", "Sharpe", "Drawdown", "Turnover", "Win",
                                     "vs", "周期", "==="]):
            print(line)
    if result.stderr:
        print(f"ERR: {result.stderr[:200]}")
    os.remove("scripts/_tmp_framework.py")
