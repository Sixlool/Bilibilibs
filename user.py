# -*- coding: utf-8 -*-
"""用户表与收藏表"""

from datetime import datetime
from flask_login import UserMixin
from .db import db


class User(UserMixin, db.Model):
    """用户表"""
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(64), nullable=False, unique=True)
    password_hash = db.Column(db.String(256), nullable=False)
    email = db.Column(db.String(128), default="")
    # B 站扫码登录：关联的 B 站用户 mid（DedeUserID），唯一，用于扫码登录时创建/绑定本系统账号
    bilibili_uid = db.Column(db.BigInteger, unique=True, nullable=True, index=True)
    # 可选：用户填写的 B 站 Cookie，采集时用该账号请求以降低 412 风控
    bilibili_sessdata = db.Column(db.String(512), default="")
    bilibili_bili_jct = db.Column(db.String(256), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    favorites = db.relationship("UserFavorite", backref="user", lazy="dynamic")


class UserFavorite(db.Model):
    """用户收藏番剧表"""
    __tablename__ = "user_favorite"
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    media_id = db.Column(db.Integer, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("user_id", "media_id", name="uk_user_media"),)
