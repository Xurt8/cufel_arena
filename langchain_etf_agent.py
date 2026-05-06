"""
LangChain Agent - ETF 金融助手
使用 Claude Sonnet 4.5 + ClickHouse 数据库
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

from langchain.tools import tool
from langchain.chat_models import init_chat_model
from langgraph.checkpoint.memory import InMemorySaver
from langchain.agents import create_agent
from quantchdb import ClickHouseDatabase


# ========== 工具定义 ==========

@tool
def get_etf_price(code: str) -> str:
    """获取ETF最新收盘价"""
    config = {
        'host': '10.13.66.5',
        'port': 20108,
        'user': 'cufel_arena_etf_reader',
        'password': 'cufel_arena_etf_404',
        'database': 'etf'
    }
    with ClickHouseDatabase(config=config, terminal_log=False, file_log=False) as db:
        df = db.fetch(f"SELECT close, date FROM etf_day WHERE code = '{code}' ORDER BY date DESC LIMIT 1")
        if len(df) > 0:
            return f"ETF {code} 最新收盘价: {df.iloc[0]['close']:.3f} 元 (日期: {df.iloc[0]['date']})"
        return f"未找到ETF {code}的数据"


@tool
def get_etf_60day_change(code: str) -> str:
    """获取ETF的60日涨跌幅"""
    config = {
        'host': '10.13.66.5',
        'port': 20108,
        'user': 'cufel_arena_etf_reader',
        'password': 'cufel_arena_etf_404',
        'database': 'etf'
    }
    with ClickHouseDatabase(config=config, terminal_log=False, file_log=False) as db:
        df = db.fetch(f"""
            SELECT close FROM etf_day
            WHERE code = '{code}'
            ORDER BY date DESC LIMIT 60
        """)
        if len(df) >= 2:
            latest = df.iloc[0]['close']
            oldest = df.iloc[-1]['close']
            change = (latest - oldest) / oldest * 100
            return f"ETF {code} 60日涨跌幅: {change:+.2f}%"
        return f"数据不足"


@tool
def get_etf_ma(code: str) -> str:
    """获取ETF的均线数据 (MA5, MA10, MA20, MA60)"""
    config = {
        'host': '10.13.66.5',
        'port': 20108,
        'user': 'cufel_arena_etf_reader',
        'password': 'cufel_arena_etf_404',
        'database': 'etf'
    }
    with ClickHouseDatabase(config=config, terminal_log=False, file_log=False) as db:
        df = db.fetch(f"""
            SELECT close, date FROM etf_day
            WHERE code = '{code}'
            ORDER BY date DESC LIMIT 60
        """)
        if len(df) >= 20:
            df_sorted = df.sort_values('date')
            ma5 = df_sorted['close'].tail(5).mean()
            ma10 = df_sorted['close'].tail(10).mean()
            ma20 = df_sorted['close'].tail(20).mean()
            ma60 = df_sorted['close'].tail(60).mean()

            # 判断趋势
            if ma5 > ma10 > ma20:
                trend = "上升趋势"
            elif ma5 < ma10 < ma20:
                trend = "下降趋势"
            else:
                trend = "震荡整理"

            return f"ETF {code} 均线: MA5={ma5:.3f}, MA10={ma10:.3f}, MA20={ma20:.3f}, MA60={ma60:.3f} | 趋势: {trend}"
        return f"数据不足"


# ========== 初始化 ==========

# 配置模型
model = init_chat_model(
    'anthropic:claude-sonnet-4-5',
    temperature=0.7,
    max_tokens=1000
)

# 添加记忆
checkpointer = InMemorySaver()

# 系统提示
SYSTEM_PROMPT = """你是一位专业的金融助手，专门回答用户关于ETF的问题。

你可以使用以下工具：
- get_etf_price: 查询ETF最新价格
- get_etf_60day_change: 查询ETF 60日涨跌幅
- get_etf_ma: 查询ETF均线数据

请用简洁友好的方式回答，如果用户没有指明具体ETF代码，可以根据上下文判断。"""

# 创建代理
agent = create_agent(
    model=model,
    system_prompt=SYSTEM_PROMPT,
    tools=[get_etf_price, get_etf_60day_change, get_etf_ma],
    checkpointer=checkpointer
)


# ========== 运行 ==========

def run_chat():
    config = {'configurable': {'thread_id': 'etf-assistant'}}

    print("=" * 60)
    print("ETF 金融助手 (输入 'quit' 退出)")
    print("=" * 60)

    while True:
        user_input = input("\n用户: ").strip()
        if user_input.lower() in ['quit', '退出', 'q']:
            break

        response = agent.invoke(
            {'messages': [{'role': 'user', 'content': user_input}]},
            config=config
        )

        # 打印最终回复
        for msg in response['messages']:
            if hasattr(msg, 'content') and isinstance(msg.content, str):
                # 只打印最后一条AI回复
                pass
            elif hasattr(msg, 'content') and isinstance(msg.content, list):
                for item in msg.content:
                    if item.get('type') == 'text':
                        print(f"\n助手: {item.get('text', '')}")


if __name__ == "__main__":
    # 单次测试
    config = {'configurable': {'thread_id': 'test-1'}}

    # 测试1: 查价格
    print("=== 测试1: 查询价格 ===")
    r1 = agent.invoke(
        {'messages': [{'role': 'user', 'content': '创业板ETF (159915) 现在多少钱？'}]},
        config=config
    )
    for msg in r1['messages']:
        if hasattr(msg, 'content') and isinstance(msg.content, list):
            for item in msg.content:
                if item.get('type') == 'text':
                    print(item.get('text', ''))

    # 测试2: 60日表现
    print("\n=== 测试2: 60日表现 ===")
    r2 = agent.invoke(
        {'messages': [{'role': 'user', 'content': '那它的60日表现怎么样？'}]},
        config=config
    )
    for msg in r2['messages']:
        if hasattr(msg, 'content') and isinstance(msg.content, list):
            for item in msg.content:
                if item.get('type') == 'text':
                    print(item.get('text', ''))

    # 测试3: 均线
    print("\n=== 测试3: 均线分析 ===")
    r3 = agent.invoke(
        {'messages': [{'role': 'user', 'content': '帮我分析一下510880红利的均线'}]},
        config=config
    )
    for msg in r3['messages']:
        if hasattr(msg, 'content') and isinstance(msg.content, list):
            for item in msg.content:
                if item.get('type') == 'text':
                    print(item.get('text', ''))