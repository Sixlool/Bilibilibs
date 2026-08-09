# -*- coding: utf-8 -*-
"""
清空番剧相关表数据，便于重新爬取/同步。
不删除用户表(user)、用户收藏(user_favorite)，仅清空番剧与标签数据。
使用项目 config 连接 MySQL，执行前会确认。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config

# 按依赖顺序清空（先清关联表，再清主表）
TABLES = [
    "bangumi_episode",
    "bangumi_tag",
    "bangumi_daily_snapshot",
    "tag_info",
    "bangumi_info",
    "bangumi_season",
]


def main():
    try:
        import pymysql
    except ImportError:
        print("请先安装 PyMySQL: pip install PyMySQL")
        sys.exit(1)

    cfg = config.MYSQL_CONFIG
    print("即将清空以下表的数据（不涉及 user / user_favorite）：")
    for t in TABLES:
        print("  -", t)
    do_it = "--yes" in sys.argv or "-y" in sys.argv
    if not do_it:
        try:
            confirm = input("确认执行？输入 y 或 yes 继续: ").strip().lower()
        except Exception:
            confirm = ""
        if confirm not in ("y", "yes"):
            print("已取消。")
            return

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
            for table in TABLES:
                cur.execute(f"TRUNCATE TABLE `{table}`")
                conn.commit()
                print("已清空:", table)
        print("完成。可以重新通过「爬取数据」或「同步追番到本地」获取数据。")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
