# Bilibilibs · B站动漫番剧数据分析与可视化系统

> 基于 **Python + Flask + MySQL** 的番剧数据采集、存储、分析与可视化系统。
> 支持 B 站扫码登录、追番自动同步入库（含国产番剧）、后台管理、访问统计、账号绑定。

---

## ✨ 功能特性

| 模块 | 说明 |
|---|---|
| 🕷️ 番剧采集 | 基于 bilibili-api-python 的索引/详情采集，支持年份分桶、请求间隔与 412 风控重试 |
| 🎬 追番自动入库 | 点击「我的追番」自动同步 B 站追番（**含索引缺失的国产番剧**），按 media_id 去重入库 |
| 📊 数据分析 | 年度/季度趋势、标签分布、多维度榜单（Pandas/NumPy），ECharts 可视化大屏 |
| 🔐 用户系统 | 账号密码注册/登录 + **B 站扫码登录**；扫码未绑定账号自动引导绑定 |
| 👑 后台管理 | 数据统计概览、访问统计折线图（PV/UV）、数据采集、用户管理（仅管理员） |
| 📈 访问统计 | 每日 PV/UV 自动统计，后台 14 天折线图展示 |

---

## 🚀 快速开始（本地开发）

### 1. 环境要求

- Python 3.8+（推荐 3.10）
- MySQL 8.0
- （可选）Redis —— 缓存加速
- （可选）Docker + Docker Compose —— 正式部署

### 2. 创建虚拟环境并安装依赖

```bash
git clone https://github.com/<你的用户名>/Bilibilibs.git
cd Bilibilibs
python -m venv .venv
source .venv/bin/activate        # Linux/macOS；Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. 初始化数据库

```bash
# 创建数据库
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS bilibili_bangumi DEFAULT CHARSET utf8mb4;"
# 导入建表脚本（含全部表结构与字段）
mysql -u root -p bilibili_bangumi < init_db.sql
```

> 若已有旧库，可执行 `migrate_*.sql` 迁移脚本完成增量升级（见 `migrate_` 前缀文件）。

### 4. 配置环境变量

复制 `.env.example` 为 `.env` 并修改：

```bash
cp .env.example .env
```

```ini
# .env（生产环境务必修改密码与密钥！）
FLASK_ENV=development          # 生产环境设为 production
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=你的数据库密码
MYSQL_DATABASE=bilibili_bangumi
SECRET_KEY=你的随机密钥         # 生成：python -c "import secrets; print(secrets.token_hex(32))"
ADMIN_USERNAME=admin            # 注册该用户名且库中无管理员时自动成为管理员
```

### 5. 启动 Web 服务

```bash
python run.py
```

浏览器访问 **http://127.0.0.1:5000**

**登录流程**：
1. 打开登录页 → 左侧**账号密码注册/登录**，右侧**B 站扫码登录**
2. 首次扫码且未绑定 → 进入**绑定页面**：绑定已有账号 或 注册新账号并绑定
3. 绑定后可用**账号密码直接登录**，也可扫码直接进

**使用路径**：
- 番剧列表 → 数据大屏 → 我的追番 → 个人中心 → 后台管理（管理员）
- 「我的追番」点开即自动同步入库；未绑定账号提示前往个人中心绑定

---

## 🐳 正式部署（Docker Compose，推荐）

```bash
# 1) 准备环境变量（必须设置强密码与随机密钥）
cp .env.example .env
#    编辑 .env：FLASK_ENV=production、强密码、SECRET_KEY、ADMIN_USERNAME

# 2) 一键启动（MySQL 8 + 应用 + Nginx 反代，首次自动建表）
docker compose up -d --build

# 3) 访问 http://<服务器IP>，注册 ADMIN_USERNAME 指定的账号即成为管理员
```

- 数据库通过 `init_db.sql` + `migrate_add_admin.sql` 自动初始化
- **HTTPS 证书**（任选其一）：
  - 自动签发：Caddy 配置 `sxklzyb.cn { tls { ca https://acme.zerossl.com/v2/DV90 } }`（需服务器能访问 ACME 服务）
  - 手动证书：阿里云等签发的证书放入 `/etc/caddy/certs/`（fullchain.pem + privkey.key），Caddy 配置 `tls /etc/caddy/certs/xxx.pem /etc/caddy/certs/xxx.key`
- 传统部署（gunicorn + systemd）：见 `run.py` 头部注释与 `deploy/` 目录
- 命令行采集：`python run_crawler.py --year 2024 --pages 2 --delay 5`

---

## 🧱 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python / Flask / Flask-Login / Flask-CORS / Flask-SQLAlchemy |
| 数据库 | MySQL 8（PyMySQL）/ SQLAlchemy ORM |
| 采集 | bilibili-api-python（异步封装为同步）/ requests / aiohttp |
| 数据分析 | Pandas / NumPy |
| 前端 | 原生 HTML/CSS/JS + ECharts |
| 部署 | gunicorn / Docker Compose / Nginx |
| 可选 | Redis（缓存）/ cloudflared（内网穿透公网访问） |

---

## 📦 功能模块

| 模块 | 文件 | 职责 |
|---|---|---|
| 番剧采集 | `crawler/collector.py` | 索引/详情采集、追番同步、412 风控重试 |
| 数据存储 | `models/` | SQLAlchemy 模型（bangumi/tag/user/visit_stat 等） |
| 业务服务 | `services/bangumi_service.py` | 写入去重（含并发安全）、查询、分析 |
| REST API | `app/routes/api.py` | 番剧/分析/收藏/扫码登录/采集/追番 |
| 鉴权 | `app/routes/auth.py` | 注册/登录/登出/扫码绑定 |
| 后台管理 | `app/routes/admin.py` | 统计概览/访问统计/采集管理/用户管理 |
| 页面路由 | `app/routes/pages.py` | 首页/登录页/静态资源 |
| 前端 | `static/` | index.html + app.js（单页应用）+ login 页 |
| 数据库初始化 | `init_db.sql` + `migrate_*.sql` | 建表与迁移 |

---

## 🔌 主要接口

### 公开接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/bangumi` | 番剧列表（keyword/year/season/order_by/page/page_size） |
| GET | `/api/bangumi/<media_id>` | 番剧详情（分集、标签、是否收藏） |
| GET | `/api/analysis/trend` | 年度/季度新番趋势 |
| GET | `/api/analysis/tags` | 标签分布 |
| GET | `/api/analysis/dashboard-charts` | 大屏聚合图表数据 |
| GET | `/api/rank` | 榜单（play_count/follow_count/score） |
| POST | `/auth/register` | 注册账号 |
| POST | `/auth/login` | 账号密码登录 |
| POST | `/auth/logout` | 登出 |
| GET | `/auth/me` | 当前用户信息（含 is_admin） |

### 需登录

| 方法 | 路径 | 说明 |
|---|---|---|
| POST/DELETE | `/api/favorite/<media_id>` | 收藏/取消收藏 |
| GET | `/api/favorites` | 我的收藏 |
| GET | `/api/user/bilibili-subscribed-bangumi` | 拉取 B 站追番列表 |
| GET/POST | `/api/user/bilibili-cookie` | 查询/保存 B 站 Cookie |
| GET | `/api/bilibili-qr/generate` | 生成登录二维码 |
| GET | `/api/bilibili-qr/poll` | 轮询扫码状态（done 时自动登录/绑定） |
| POST | `/api/crawl/start` | 启动采集（年份/季度/页数/间隔） |
| POST | `/api/crawl/sync-subscribed` | 同步追番入库（去重，并发安全） |
| POST | `/api/crawl/refresh-in-db` | 刷新库内番剧详情 |
| GET | `/api/crawl/status` | 采集/同步进度轮询 |
| POST | `/auth/bind` | 扫码后绑定账号（bind_existing/register） |

### 后台管理（需管理员）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/admin/overview` | 数据统计概览 |
| GET | `/admin/stats/visits` | 访问统计（近 N 天 PV/UV，折线图数据） |
| POST | `/admin/crawl/start` | 后台启动采集 |
| POST | `/admin/crawl/refresh-in-db` | 更新库内番剧 |
| POST | `/admin/crawl/sync-subscribed` | 同步管理员追番 |
| GET | `/admin/crawl/status` | 采集进度 |
| GET | `/admin/users` | 用户列表 |
| POST | `/admin/users/<id>/toggle-admin` | 设为/取消管理员 |
| DELETE | `/admin/users/<id>` | 删除用户 |

---

## 📁 项目结构

```
Bilibilibs/
├── app/                        # Flask 应用
│   ├── __init__.py             # 应用工厂（含访问统计钩子）
│   └── routes/
│       ├── api.py              # REST API + 采集/同步线程
│       ├── auth.py             # 注册/登录/扫码绑定
│       ├── admin.py            # 后台管理
│       └── pages.py            # 页面路由
├── crawler/collector.py        # B 站采集（索引/详情/追番同步）
├── models/                     # SQLAlchemy 模型
│   ├── db.py / bangumi.py / tag.py / user.py
├── services/                   # 业务服务
│   ├── bangumi_service.py      # 写入去重（并发安全）、查询、分析
│   ├── analysis_service.py     # 数据分析
│   └── bilibili_qr_login.py    # B 站扫码登录
├── static/                     # 前端（index.html / app.js / login.*）
├── deploy/nginx.conf           # 生产 Nginx 反代配置
├── Dockerfile / docker-compose.yml
├── init_db.sql                 # 建表脚本
├── migrate_*.sql               # 迁移脚本（admin/auto_created/crawl_status/visit_stat）
├── config.py                   # 配置（环境变量注入，生产强制安全）
├── requirements.txt
├── run.py                      # 启动入口
├── run_crawler.py              # 命令行采集
└── start-public.sh             # 一键启动（MySQL+gunicorn+公网隧道）
```

---

## 🔒 安全说明

> **本仓库不包含任何真实凭据。** 所有敏感配置通过环境变量 / `.env` 注入。

- **数据库密码 / SECRET_KEY**：通过 `.env` 配置；生产环境（`FLASK_ENV=production`）**强制要求显式设置**，缺失即启动报错，杜绝默认弱口令上线
- **首个管理员**：`.env` 设置 `ADMIN_USERNAME`，注册该用户名且库中无管理员时自动成为管理员
- **B 站 Cookie**：仅存数据库，接口不返回具体值，仅返回状态
- **扫码绑定**：绑定 token 一次性使用、10 分钟过期；已绑定真实账号的 B 站 UID 拒绝重复绑定
- **部署加固**：`SESSION_COOKIE_SECURE`（HTTPS）、CORS 白名单可配、debug 由环境控制

### 修改配置的位置

| 想改什么 | 位置 |
|---|---|
| 数据库/密钥/管理员 | `.env`（参考 `.env.example`） |
| 采集间隔/重试 | `config.py` 的 `CRAWL_*` |
| 管理员账号 | `.env` 的 `ADMIN_USERNAME`（或后台用户管理） |
| CORS 白名单 | `.env` 的 `CORS_ORIGINS` |
| 分页大小 | `config.py` 的 `DEFAULT_PAGE_SIZE` |

---

## ⚠️ 注意事项

- 数据源为 B 站公开接口，请遵守平台规范，控制请求频率（脚本已内置延迟与重试）
- 本机/服务器 IP 可能触发 B 站 412 风控：管理员先在个人中心**扫码登录保存 Cookie**，采集带登录态可显著降低
- 多用户并发同步追番已做并发安全处理（唯一键冲突兜底 + 死锁自动重试）

## 📄 许可

基于任务书要求开发；数据源为 B 站公开接口，仅供学习研究使用。
