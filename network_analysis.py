#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
长城证券 网络流量分析工具
监控本机与券商服务器的通信
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import socket
import subprocess
import threading
import time
import os

print("="*60)
print("长城证券 网络流量分析")
print("="*60)

# ==================== 方法1: 监控网络连接 ====================

def get_connections():
    """获取当前网络连接"""
    try:
        # Windows网络连接命令
        result = subprocess.run(
            ['netstat', '-an'],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.stdout
    except Exception as e:
        print(f"获取连接失败: {e}")
        return None

def find_securities_connections():
    """查找与证券相关的连接"""
    connections = get_connections()
    if not connections:
        return []

    keywords = [' securities', 'zq', 'jq', 'finance', 'stock', 'cc', 'gw', '9552', '9578']

    found = []
    for line in connections.split('\n'):
        line = line.lower()
        for kw in keywords:
            if kw in line and 'ESTABLISHED' in line:
                found.append(line.strip())

    return found

# ==================== 方法2: hosts文件检查 ====================

def check_hosts():
    """检查hosts文件中的券商相关条目"""
    try:
        with open(r'C:\Windows\System32\drivers\etc\hosts', 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            lines = [l.strip() for l in content.split('\n') if l.strip() and not l.startswith('#')]
            securities = [l for l in lines if any(k in l.lower() for k in ['securities', 'zq', 'stock', 'cc', 'gw'])]
            return securities
    except Exception as e:
        print(f"检查hosts失败: {e}")
        return []

# ==================== 方法3: 抓取进程网络 ====================

def get_process_connections():
    """获取长城证券进程的网络连接"""
    try:
        # 查找长城证券进程
        result = subprocess.run(
            ['tasklist', '/FI', 'IMAGENAME eq *'],
            capture_output=True,
            text=True,
            timeout=10
        )

        processes = []
        for line in result.stdout.split('\n'):
            if 'Great' in line or '长城' in line or 'Securities' in line:
                processes.append(line.strip())

        return processes
    except:
        return []

# ==================== 主程序 ====================

def main():
    print("\n[1] 检查hosts文件...")
    hosts = check_hosts()
    if hosts:
        print("发现相关条目:")
        for h in hosts:
            print(f"  {h}")
    else:
        print("  未发现券商相关条目")

    print("\n[2] 查找长城证券进程...")
    procs = get_process_connections()
    if procs:
        print("找到进程:")
        for p in procs:
            print(f"  {p}")
    else:
        print("  未找到长城证券进程")

    print("\n[3] 监控网络连接 (5秒)...")
    print("  提示: 请确保长城证券正在运行...")

    all_connections = []
    start_time = time.time()

    while time.time() - start_time < 5:
        conns = find_securities_connections()
        for c in conns:
            if c not in all_connections:
                all_connections.append(c)

        if all_connections:
            break
        time.sleep(0.5)

    if all_connections:
        print(f"\n找到 {len(all_connections)} 个相关连接:")
        for c in all_connections[:10]:
            print(f"  {c}")
    else:
        print("  未找到活跃的券商连接")

    print("\n[4] 尝试获取更多连接信息...")
    # 尝试抓取所有80/443端口的连接
    try:
        result = subprocess.run(
            ['netstat', '-ano'],
            capture_output=True,
            text=True,
            timeout=10
        )

        ports_443 = []
        for line in result.stdout.split('\n'):
            if ':443' in line or ':8080' in line or ':80' in line:
                if 'ESTABLISHED' in line:
                    ports_443.append(line.strip())

        if ports_443:
            print(f"\n发现 {len(ports_443)} 个HTTPS连接:")
            for c in ports_443[:5]:
                print(f"  {c}")
    except:
        pass

    print("\n" + "="*60)
    print("分析完成!")
    print("="*60)
    print("""
下一步:
- 如果找到服务器IP,可以尝试抓包分析
- 需要更详细的抓包请安装 Wireshark 或 Charles
- 或联系券商客服获取官方数据接口
""")

if __name__ == "__main__":
    main()