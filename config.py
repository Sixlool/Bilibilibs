# -*- coding: utf-8 -*-
"""
系统配置文件
- 数据库、Redis、Flask 等配置
- MySQL 账号：root，密码：123456（可按需修改）
"""

import os
from dotenv import load_dotenv

load_dotenv()

# 基础路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# MySQL 配置（任务书要求：MySQL 8.0）
MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", "123456"),
    "database": os.getenv("MYSQL_DATABASE", "bilibili_bangumi"),
    "charset": "utf8mb4",
}

# SQLAlchemy 连接字符串
SQLALCHEMY_DATABASE_URI = (
    f"mysql+pymysql://{MYSQL_CONFIG['user']}:{MYSQL_CONFIG['password']}"
    f"@{MYSQL_CONFIG['host']}:{MYSQL_CONFIG['port']}/{MYSQL_CONFIG['database']}"
    f"?charset={MYSQL_CONFIG['charset']}"
)
SQLALCHEMY_TRACK_MODIFICATIONS = False
SQLALCHEMY_ECHO = False  # 生产环境设为 False

# Redis 配置（可选，用于缓存首页、排行榜等）
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
REDIS_ENABLED = os.getenv("REDIS_ENABLED", "0").strip().lower() in ("1", "true", "yes")

# Flask 配置
SECRET_KEY = os.getenv("SECRET_KEY", "bilibili-bangumi-secret-key-change-in-production")
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

# 数据采集配置（请求间隔、重试等）
CRAWL_DELAY_SECONDS = 1.5  # 每次请求间隔，避免触发风控
CRAWL_MAX_RETRIES = 3
CRAWL_TIMEOUT = 15

# 分页默认值
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
