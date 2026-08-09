# -*- coding: utf-8 -*-
"""标签表及番剧-标签关联"""

from datetime import datetime
from .db import db


class TagInfo(db.Model):
    """标签表"""
    __tablename__ = "tag_info"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tag_name = db.Column(db.String(64), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class BangumiTag(db.Model):
    """番剧-标签关联表"""
    __tablename__ = "bangumi_tag"
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    media_id = db.Column(db.Integer, nullable=False, index=True)
    tag_id = db.Column(db.Integer, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("media_id", "tag_id", name="uk_media_tag"),)
