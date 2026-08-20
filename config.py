# -*- coding: utf-8 -*-
"""
系统配置文件
- 数据库、Redis、Flask 等配置
- 所有敏感配置（数据库密码、SECRET_KEY 等）通过环境变量 / .env 注入，
  生产环境（FLASK_ENV=production）强制要求显式配置，不提供默认弱口令。
"""

import os
from dotenv import load_dotenv

load_dotenv()

# 运行环境：development / production（默认 development，保持原行为；部署时设 production）
FLASK_ENV = os.getenv("FLASK_ENV", "development").strip().lower()
IS_PRODUCTION = FLASK_ENV == "production"

# 基础路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# MySQL 配置（任务书要求：MySQL 8.0）
# 生产环境（FLASK_ENV=production）强制要求显式配置，避免默认弱口令 root/123456 上线
if IS_PRODUCTION and not os.getenv("MYSQL_PASSWORD"):
    raise RuntimeError(
        "生产环境必须通过环境变量 MYSQL_PASSWORD 显式配置数据库密码（见 .env.example）"
    )
if IS_PRODUCTION and not os.getenv("SECRET_KEY"):
    raise RuntimeError(
        "生产环境必须通过环境变量 SECRET_KEY 显式配置（生成方法：python -c \"import secrets; print(secrets.token_hex(32))\"）"
    )
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
# HTTPS 下生产环境强制 Secure Cookie，避免会话被浏览器拒绝
SESSION_COOKIE_SECURE = IS_PRODUCTION
# 生产环境关闭 debug
DEBUG = not IS_PRODUCTION

# CORS 允许来源：生产环境用环境变量 CORS_ORIGINS 配置（逗号分隔），
# 默认同域部署时仅允许本机回环（部署时请设为你的域名，如 https://example.com）
if IS_PRODUCTION:
    _cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
    if not _cors_origins:
        # 同域部署（nginx 反代）时浏览器请求同源，无需跨域；仅保留空列表即可
        CORS_ORIGINS = ["https://localhost"]
    else:
        CORS_ORIGINS = _cors_origins
else:
    CORS_ORIGINS = ["http://127.0.0.1:5000", "http://localhost:5000"]

# 首个管理员用户名（注册该用户名且库中无管理员时自动成为管理员）
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "").strip()

# 数据采集配置（请求间隔、重试等）
CRAWL_DELAY_SECONDS = 1.5  # 每次请求间隔，避免触发风控
CRAWL_MAX_RETRIES = 3
CRAWL_TIMEOUT = 15

# 分页默认值
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
