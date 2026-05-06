import pandas as pd
import requests
import json
import time

# 读取技术分析数据
tech = pd.read_csv('4.18/技术分析.csv')

# 读取放量增长分析
vol = pd.read_csv('4.18/放量增长分析.csv')

# 合并
merged = pd.merge(tech, vol, on='代码')

# DeepSeek API配置
API_KEY = "sk-cc367460e51b422bbdd8a05dfdd3a0e8"
API_URL = "https://api.deepseek.com/v1/chat/completions"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# 对前10只股票进行深度分析
print("调用DeepSeek进行深度分析...")
print("=" * 80)

for idx, (_, row) in enumerate(merged.head(10).iterrows()):
    code = row['代码']
    name = row['名称']
    current = row['current']
    support = row['support']
    resistance = row['resistance']
    position = row['position']
    vol_growth = row['10日量增%']

    # 构建分析提示
    prompt = f"""请分析这只股票的技术面和投资建议:
股票代码: {code}
股票名称: {name}
当前价格: {current:.2f}元
支撑位: {support:.2f}元
压力位: {resistance:.2f}元
60日位置: {position:.1f}%
10日量增: {vol_growth}%

请给出:
1. 技术分析
2. 基本面要点
3. 买入建议价格区间
4. 止损位
5. 投资建议

请用JSON格式输出。"""

    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7
    }

    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
        result = response.json()
        if 'choices' in result:
            analysis = result['choices'][0]['message']['content']
            print(f"\n{code} {name}")
            print(analysis[:500])
        time.sleep(1)
    except Exception as e:
        print(f"{code} 分析失败: {e}")

print("\n分析完成!")