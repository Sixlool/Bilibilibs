# B站动漫番剧数据分析与可视化系统

基于任务书要求，使用 Python + Flask + MySQL + bilibili-api-python 实现的番剧数据采集、存储、分析与可视化系统。

## 环境要求

- Python 3.8+
- MySQL 8.0（账号 root，密码 123456，或通过环境变量配置）
- （可选）Redis，用于缓存

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
- **采集**：登录后进入「个人中心」，在「爬取数据」中点击「开始采集」即可在后台拉取番剧（扫码登录后会自动带 B 站 Cookie，有助于降低 412 风控）。
- **B 站 Cookie**：扫码登录后自动保存；也可在个人中心手动粘贴 `sessdata`、`bili_jct` 或再次扫码更新。

仍可通过命令行采集：`python run_crawler.py --year 2024 --pages 2 --delay 5`

## 功能模块概览

| 模块 | 说明 |
|------|------|
| **番剧数据采集** | `crawler/collector.py`：基于 bilibili-api-python 的索引/详情采集，支持年份分桶、请求间隔与重试 |
| **数据存储** | MySQL 表见 `init_db.sql`；写入逻辑在 `services/bangumi_service.py` 的 `save_bangumi_list` |
| **数据分析** | `services/analysis_service.py`：年度/季度趋势、标签分布、多维度榜单（Pandas/NumPy） |
| **REST API** | `app/routes/api.py`：番剧列表/详情、趋势/标签/榜单、用户收藏、采集进度、B 站扫码登录 |
| **用户鉴权** | `app/routes/auth.py` + `services/bilibili_qr_login.py`：账号密码登录与 B 站扫码登录 |
| **前端页面** | `static/index.html` + `static/app.js` + `static/login.html` + `static/login.js`：列表/详情/大屏/个人中心与登录页 |

## 主要接口

- `GET /api/bangumi`：番剧列表（keyword, year, season, order_by, page, page_size）
- `GET /api/bangumi/<media_id>`：番剧详情（含分集、标签、是否已收藏）
- `GET /api/analysis/trend`：年度/季度新番趋势
- `GET /api/analysis/tags`：标签分布
- `GET /api/rank`：榜单（order=play_count|follow_count|score，limit, year, season）
- `POST/DELETE /api/favorite/<media_id>`：收藏/取消收藏（需登录）
- `GET /api/favorites`：当前用户收藏列表（需登录）
- `POST /auth/register`、`POST /auth/login`、`POST /auth/logout`、`GET /auth/me`

## 项目结构

```
Bilibilibs/
├── app/                     # Flask 应用
│   ├── __init__.py          # 应用工厂、数据库与登录初始化
│   └── routes/
│       ├── api.py           # REST API
│       ├── auth.py          # 注册/登录/登出
│       └── pages.py         # 前端页面路由
├── config.py                # 配置（MySQL、Flask、采集参数等）
├── .env.example             # 环境变量示例
├── crawler/
│   ├── __init__.py
│   └── collector.py         # 番剧采集（bilibili-api-python）
├── models/                  # SQLAlchemy 模型
│   ├── db.py
│   ├── bangumi.py
│   ├── tag.py
│   └── user.py
├── services/
│   ├── bangumi_service.py   # 番剧写入与查询
│   ├── analysis_service.py  # 分析与榜单
│   └── bilibili_qr_login.py # B 站扫码登录
├── static/
│   ├── index.html           # 单页前端
│   ├── app.js               # 列表、详情、大屏、用户与收藏
│   ├── login.html           # 登录页
│   └── login.js             # 登录页逻辑
├── init_db.sql             # 数据库建表
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
