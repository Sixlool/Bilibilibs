# B站动漫番剧数据分析与可视化系统

基于任务书要求，使用 Python + Flask + MySQL + bilibili-api-python 实现的番剧数据采集、存储、分析与可视化系统。
包含**后台管理界面**：数据采集（爬虫）等管理操作收口到后台，仅管理员可执行。

## 环境要求

- Python 3.8+
- MySQL 8.0（账号 root，密码 123456，或通过环境变量配置）
- （可选）Redis，用于缓存
- （可选）Docker + Docker Compose（推荐用于正式部署）

## 快速开始

### 1. 创建虚拟环境并安装依赖

```bash
cd Bilibilibs
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # Linux/macOS
pip install -r requirements.txt
```

### 2. 初始化数据库

在 MySQL 中执行：

```sql
CREATE DATABASE IF NOT EXISTS bilibili_bangumi DEFAULT CHARSET utf8mb4;
```

然后在MySQL中执行项目中的建表脚本：

路径文件自行更改
```sql
USE bilibili_bangumi;
SOURCE D:/biyesheji/Bilibilibs/init_db.sql;
```

或在 MySQL 客户端中打开并执行 `init_db.sql`。

若数据库已存在且 `user` 表没有 B 站 Cookie/uid 字段，可执行迁移（任选其一）：  
- **推荐**：在项目根目录运行  
  `python run_migrate.py`  
  （使用当前项目配置与 PyMySQL，无需安装 mysql 命令行）  
- 若已配置 mysql 命令行：PowerShell 用  
  `Get-Content migrate_user_bilibili_cookie.sql | mysql -u root -p123456 bilibili_bangumi`  
  CMD 用  
  `mysql -u root -p123456 bilibili_bangumi < migrate_user_bilibili_cookie.sql`  
- 或在 MySQL 客户端内：  
  `SOURCE D:/biyesheji/Bilibilibs/migrate_user_bilibili_cookie.sql;`  
（列/索引已存在时会自动跳过）

### 3. 配置（可选）

在项目根目录创建 `.env` 可覆盖默认配置，例如：

```
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=123456
MYSQL_DATABASE=bilibili_bangumi
SECRET_KEY=your-secret-key
```

### 4. 启动 Web 服务

```bash
python run.py
```

浏览器访问：http://127.0.0.1:5000

- **入口**：打开后默认使用 **B 站扫码登录**（点击「显示登录二维码」，用 B 站 App 扫码即可登录本系统，无需记住本系统密码）。首次扫码会自动创建本系统账号；也可点击「使用账号密码登录」展开传统注册/登录。
- **后台管理**：在 `.env` 中设置 `ADMIN_USERNAME=admin` 后，用该用户名注册的账号自动成为管理员（仅首个管理员），导航栏出现「后台管理」入口。数据采集、库内更新、追番同步、用户管理等操作全部收口在后台。
- **采集（管理员）**：进入「后台管理 → 数据采集」，选择年份/季度/页数/间隔后点击「开始采集」；也可点击「更新库内番剧信息」「同步我的追番」。
- **B 站 Cookie**：扫码登录后自动保存；也可在个人中心手动粘贴 `sessdata`、`bili_jct` 或再次扫码更新（后台采集会使用管理员账号的 Cookie）。

仍可通过命令行采集：`python run_crawler.py --year 2024 --pages 2 --delay 5`

### 5. 正式部署（Docker Compose，推荐）

```bash
# 1) 准备环境变量
cp .env.example .env
#    编辑 .env：设置强密码 MYSQL_PASSWORD、随机 SECRET_KEY、ADMIN_USERNAME

# 2) 一键启动（MySQL + 应用 + Nginx 反代，首次自动建表）
docker compose up -d --build

# 3) 访问 http://<服务器IP> ，注册 ADMIN_USERNAME 指定的账号即成为管理员
```

- 数据库自动用 `init_db.sql` + `migrate_add_admin.sql` 初始化。
- HTTPS：把证书放到 `deploy/certs/`（fullchain.pem / privkey.pem），按 `deploy/nginx.conf` 注释开启 443。
- 传统部署（gunicorn + systemd）：见 `deploy/` 目录与 `run.py` 头部注释。

## 功能模块概览

| 模块 | 说明 |
|------|------|
| **番剧数据采集** | `crawler/collector.py`：基于 bilibili-api-python 的索引/详情采集，支持年份分桶、请求间隔与重试 |
| **数据存储** | MySQL 表见 `init_db.sql`；写入逻辑在 `services/bangumi_service.py` 的 `save_bangumi_list` |
| **数据分析** | `services/analysis_service.py`：年度/季度趋势、标签分布、多维度榜单（Pandas/NumPy） |
| **REST API** | `app/routes/api.py`：番剧列表/详情、趋势/标签/榜单、用户收藏、采集进度、B 站扫码登录 |
| **后台管理** | `app/routes/admin.py`：管理员鉴权、数据统计概览、用户管理、数据采集（开始采集/更新库内/同步追番） |
| **用户鉴权** | `app/routes/auth.py` + `services/bilibili_qr_login.py`：账号密码登录与 B 站扫码登录；首个管理员由 `ADMIN_USERNAME` 引导 |
| **前端页面** | `static/index.html` + `static/app.js` + `static/login.html` + `static/login.js`：列表/详情/大屏/个人中心/后台管理 |

## 主要接口

- `GET /api/bangumi`：番剧列表（keyword, year, season, order_by, page, page_size）
- `GET /api/bangumi/<media_id>`：番剧详情（含分集、标签、是否已收藏）
- `GET /api/analysis/trend`：年度/季度新番趋势
- `GET /api/analysis/tags`：标签分布
- `GET /api/rank`：榜单（order=play_count|follow_count|score，limit, year, season）
- `POST/DELETE /api/favorite/<media_id>`：收藏/取消收藏（需登录）
- `GET /api/favorites`：当前用户收藏列表（需登录）
- `POST /auth/register`、`POST /auth/login`、`POST /auth/logout`、`GET /auth/me`（含 `is_admin`）
- `GET /admin/overview`：数据统计概览（需管理员）
- `POST /admin/crawl/start`、`POST /admin/crawl/refresh-in-db`、`POST /admin/crawl/sync-subscribed`、`GET /admin/crawl/status`：后台采集（需管理员）
- `GET /admin/users`、`POST /admin/users/<id>/toggle-admin`、`DELETE /admin/users/<id>`：用户管理（需管理员）

## 项目结构

```
Bilibilibs/
├── app/                     # Flask 应用
│   ├── __init__.py          # 应用工厂、数据库与登录初始化
│   └── routes/
│       ├── api.py           # REST API
│       ├── auth.py          # 注册/登录/登出
│       ├── admin.py         # 后台管理（管理员鉴权、采集、用户管理）
│       └── pages.py         # 前端页面路由
├── config.py                # 配置（MySQL、Flask、采集参数、生产加固）
├── .env.example             # 环境变量示例（生产必配）
├── crawler/
│   ├── __init__.py
│   └── collector.py         # 番剧采集（bilibili-api-python）
├── models/                  # SQLAlchemy 模型
│   ├── __init__.py
│   ├── db.py
│   ├── bangumi.py
│   ├── tag.py
│   └── user.py              # 含 is_admin 管理员标记
├── services/
│   ├── __init__.py
│   ├── bangumi_service.py   # 番剧写入与查询
│   ├── analysis_service.py  # 分析与榜单
│   └── bilibili_qr_login.py # B 站扫码登录
├── static/
│   ├── index.html           # 单页前端（含后台管理页）
│   ├── app.js               # 列表、详情、大屏、用户与后台管理
│   ├── login.html           # 登录页
│   └── login.js             # 登录页逻辑
├── deploy/
│   └── nginx.conf           # 生产 Nginx 反代配置
├── Dockerfile               # 生产镜像（gunicorn）
├── docker-compose.yml       # 生产编排（MySQL + 应用 + Nginx）
├── init_db.sql              # 数据库建表（含 is_admin）
├── migrate_add_admin.sql    # user 表加 is_admin 迁移（已有库执行）
├── migrate_bangumi_bigint.sql        # bangumi 字段类型迁移
├── migrate_user_bilibili_cookie.sql  # user 表 Cookie/UID 迁移
├── run_migrate.py           # 执行数据库迁移
├── clear_bangumi_data.py    # 清空番剧相关数据
├── requirements.txt
├── run.py                   # 启动 Web
├── run_crawler.py           # 命令行采集
└── README.md
```

## 备注

- 数据源为 B 站公开接口，请遵守平台规范，控制请求频率（脚本内已做延迟与重试）。
- MySQL 默认使用 root/123456，生产环境请修改为独立账号并设置强密码。
- 未安装 Redis 时系统仍可正常运行，仅无缓存加速。
