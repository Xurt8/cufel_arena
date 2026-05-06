import pandas as pd
import sys
sys.stdout.reconfigure(encoding='utf-8')

df = pd.read_csv('data/etf_day_with_basic_2022_2025.csv')
print('所有列名:')
for col in df.columns:
    print(f'  - {col}')
