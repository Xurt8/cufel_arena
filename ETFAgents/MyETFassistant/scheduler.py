# 每日15:30自动更新股票数据
# 使用方法:
# 1. 打开任务计划程序 (Taskschd.msc)
# 2. 创建基本任务 -> 命名为 "stock_data_update"
# 3. 触发器: 每天 15:30
# 4. 操作: 启动程序 -> 选择此.bat文件

# 或者使用Python调度 (需要安装schedule库):
# pip install schedule
# 然后运行: python scheduler.py

import schedule
import time
from datetime import datetime
import subprocess

def run_update():
    print(f"[{datetime.now()}] 开始更新股票数据...")
    subprocess.run([r'C:\Users\xrt85\Desktop\3月22日课程资料\cufel_arena\ETFAgents\MyETFassistant\update_stocks.py'])
    print(f"[{datetime.now()}] 更新完成")

# 每天15:30执行
schedule.every().day.at("15:30").do(run_update)

print("股票数据自动更新服务已启动")
print("每天15:30自动更新")
print("按Ctrl+C停止")

while True:
    schedule.run_pending()
    time.sleep(60)