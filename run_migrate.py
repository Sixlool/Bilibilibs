# -*- coding: utf-8 -*-
"""
执行数据库迁移脚本（按顺序）：user 表 B 站字段、番剧计数字段 BIGINT。
无需安装 mysql 命令行，使用项目配置与 PyMySQL 执行。
"""
import sys
import os

# 项目根目录
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config

MIGRATIONS = [
    "migrate_user_bilibili_cookie.sql",
    "migrate_bangumi_bigint.sql",
]

def run_sql_file(cfg, sql_file):
    import pymysql
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, sql_file)
    if not os.path.isfile(path):
        print("跳过（文件不存在）:", sql_file)
        return
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # 去掉 USE；按分号拆成单条语句，忽略空行和注释
    statements = []
    for line in content.split("\n"):
        line = line.strip()
        if not line or line.startswith("--"):
            continue
        statements.append(line)
    full_sql = " ".join(statements)
    for stmt in full_sql.split(";"):
        stmt = stmt.strip()
        if not stmt or stmt.upper().startswith("USE "):
            continue
        try:
            conn = pymysql.connect(
                host=cfg["host"],
                port=cfg["port"],
                user=cfg["user"],
                password=cfg["password"],
                database=cfg["database"],
                charset=cfg.get("charset", "utf8mb4"),
            )
            try:
                with conn.cursor() as cur:
                    cur.execute(stmt)
                conn.commit()
                print("OK:", stmt[:60] + "..." if len(stmt) > 60 else stmt)
            finally:
                conn.close()
        except pymysql.err.OperationalError as e:
            err = str(e).lower()
            if "1060" in err or "duplicate column" in err or "列已存在" in err:
                print("跳过（列已存在）:", stmt[:50] + "...")
            elif "1061" in err or "duplicate key" in err or "索引已存在" in err:
                print("跳过（索引已存在）:", stmt[:50] + "...")
            else:
                print("执行失败:", stmt[:50] + "...", file=sys.stderr)
                print(e, file=sys.stderr)
                sys.exit(1)

def main():
    try:
        import pymysql
    except ImportError:
        print("请先安装 PyMySQL: pip install PyMySQL")
        sys.exit(1)

    cfg = config.MYSQL_CONFIG
    for sql_file in MIGRATIONS:
        print("\n---", sql_file, "---")
        run_sql_file(cfg, sql_file)
    print("\n迁移完成。")


if __name__ == "__main__":
    main()
