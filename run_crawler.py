# -*- coding: utf-8 -*-
"""
番剧数据采集脚本（命令行）
- 全量/按年季采集并写入 MySQL，需先执行 init_db.sql 并配置 config
- 示例：python run_crawler.py --year 2024 --season 4 --pages 2
"""

import argparse
from app import create_app
from crawler import BangumiCollector
from services.bangumi_service import save_bangumi_list

def main():
    parser = argparse.ArgumentParser(description="B站番剧数据采集")
    parser.add_argument("--year", type=int, default=None, help="年份，如 2024")
    parser.add_argument("--season", type=int, default=None, help="季度 1冬 4春 7夏 10秋")
    parser.add_argument("--pages", type=int, default=2, help="索引拉取页数")
    parser.add_argument("--page-size", type=int, default=20, help="每页条数")
    parser.add_argument("--delay", type=float, default=3.0, help="每次请求间隔秒数，防 412 风控，建议 3~5")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        from models import db
        collector = BangumiCollector(delay=args.delay, max_retries=3)
        details = collector.run_index_and_collect(
            year=args.year,
            season_month=args.season,
            max_pages=args.pages,
            page_size=args.page_size,
        )
        save_bangumi_list(db, details)
        print(f"已采集并写入 {len(details)} 条番剧数据。")


if __name__ == "__main__":
    main()
