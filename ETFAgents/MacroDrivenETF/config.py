"""
配置模块
从 .env 文件读取配置参数
"""

import os
from pathlib import Path
from dotenv import load_dotenv


class Config:
    """全局配置类"""

    # 获取当前文件所在目录
    BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))

    def __init__(self):
        # 加载环境变量
        env_path = self.BASE_DIR / ".env"
        load_dotenv(env_path)

        # ===== 数据路径配置 =====
        self.DATA_PATH = os.path.join(self.BASE_DIR, os.getenv("DATA_PATH", "./data/"))
        self.CACHE_PATH = os.path.join(self.BASE_DIR, os.getenv("CACHE_PATH", "./cache/"))
        self.OUTPUT_PATH = os.path.join(self.BASE_DIR, "output")

        # ===== LLM 配置 =====
        self.LLM_API_KEY = os.getenv("LLM_API_KEY", "")
        self.LLM_API_BASE = os.getenv("LLM_API_BASE", "")
        self.LLM_MODEL = os.getenv("MODEL_NAME", "gpt-4o-mini")

        # ===== 数据库配置 =====
        self.CHDB_HOST = os.getenv("CHDB_HOST", "")
        self.CHDB_PORT = int(os.getenv("CHDB_PORT", 20108))
        self.CHDB_USER = os.getenv("CHDB_USER", "")
        self.CHDB_PASSWORD = os.getenv("CHDB_PASSWORD", "")
        self.CHDB_DATABASE = os.getenv("CHDB_DATABASE", "etf")

        # ===== 交易参数 =====
        self.TRANSACTION_COST = 0.001  # 双边万分之十
        self.REBALANCE_THRESHOLD = 0.005  # 0.5%
        self.SLIPPAGE = 0.0005  # 0.05%

        # ===== 确保目录存在 =====
        os.makedirs(self.DATA_PATH, exist_ok=True)
        os.makedirs(self.CACHE_PATH, exist_ok=True)
        os.makedirs(self.OUTPUT_PATH, exist_ok=True)


# 全局配置实例
config = Config()
