# -*- coding: utf-8 -*-
"""番剧相关数据表模型"""

from datetime import datetime, date
from .db import db


class BangumiSeason(db.Model):
    """番剧季度表"""
    __tablename__ = "bangumi_season"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    year = db.Column(db.SmallInteger, nullable=False)
    season = db.Column(db.SmallInteger, nullable=False)  # 1冬 4春 7夏 10秋
    label = db.Column(db.String(32), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("year", "season", name="uk_year_season"),)


class BangumiInfo(db.Model):
    """番剧基本信息表"""
    __tablename__ = "bangumi_info"
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    media_id = db.Column(db.Integer, nullable=False, unique=True)
    season_id = db.Column(db.Integer, nullable=False, index=True)
    title = db.Column(db.String(256), nullable=False, default="")
    cover = db.Column(db.String(512), default="")
    intro = db.Column(db.Text)
    pub_time = db.Column(db.DateTime)
    score = db.Column(db.Numeric(3, 2))
    score_count = db.Column(db.BigInteger, default=0)
    follow_count = db.Column(db.BigInteger, default=0)
    play_count = db.Column(db.BigInteger, default=0)
    danmaku_count = db.Column(db.BigInteger, default=0)
    coin_count = db.Column(db.BigInteger, default=0)
    fav_count = db.Column(db.BigInteger, default=0)
    series_count = db.Column(db.SmallInteger, default=0)
    area = db.Column(db.String(64), default="")
    season_type = db.Column(db.SmallInteger, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 分集通过 season_id 在业务层查询，此处不建 relationship 避免无 FK 的复杂配置


class BangumiEpisode(db.Model):
    """番剧分集表"""
    __tablename__ = "bangumi_episode"
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    season_id = db.Column(db.Integer, nullable=False, index=True)
    episode_id = db.Column(db.Integer, nullable=False)
    index_title = db.Column(db.String(128), default="")
    long_title = db.Column(db.String(512), default="")
    duration = db.Column(db.Integer, default=0)
    pub_time = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("season_id", "episode_id", name="uk_season_ep"),)


class BangumiDailySnapshot(db.Model):
    """番剧每日统计快照表"""
    __tablename__ = "bangumi_daily_snapshot"
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    media_id = db.Column(db.Integer, nullable=False, index=True)
    snapshot_date = db.Column(db.Date, nullable=False)
    play_count = db.Column(db.BigInteger, default=0)
    follow_count = db.Column(db.BigInteger, default=0)
    danmaku_count = db.Column(db.BigInteger, default=0)
    coin_count = db.Column(db.BigInteger, default=0)
    fav_count = db.Column(db.BigInteger, default=0)
    score = db.Column(db.Numeric(3, 2))
    score_count = db.Column(db.BigInteger, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("media_id", "snapshot_date", name="uk_media_date"),)
