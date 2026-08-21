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
    # 是否管理员（可进入后台管理界面，执行数据采集等管理操作）
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    # 是否扫码自动创建的临时账号（旧版行为，未绑定真实用户名密码）。
    # 此类账号扫码时仍走绑定流程，不算「已绑定」。
    is_auto_created = db.Column(db.Boolean, default=False, nullable=False)
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


class CrawlStatus(db.Model):
    """采集进度（多 worker 共享，存数据库避免进程内存不共享）"""
    __tablename__ = "crawl_status"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, nullable=False, unique=True, index=True)
    running = db.Column(db.Boolean, default=False, nullable=False)
    job = db.Column(db.String(32), default="")
    detail_media_id = db.Column(db.Integer, nullable=True)
    page = db.Column(db.Integer, default=0)
    pages = db.Column(db.Integer, default=0)
    items = db.Column(db.Integer, default=0)
    message = db.Column(db.String(512), default="")
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class VisitStat(db.Model):
    """每日访问统计"""
    __tablename__ = "visit_stat"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    stat_date = db.Column(db.Date, nullable=False, unique=True, index=True)
    pv = db.Column(db.Integer, default=0, nullable=False)
    uv = db.Column(db.Integer, default=0, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class VisitUv(db.Model):
    """独立访客去重（每日每 IP 一条）"""
    __tablename__ = "visit_uv"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    stat_date = db.Column(db.Date, nullable=False, index=True)
    ip = db.Column(db.String(64), nullable=False, default="")
    __table_args__ = (db.UniqueConstraint("stat_date", "ip", name="uk_date_ip"),)


class SubscribedPending(db.Model):
    """追番待同步队列：用户查看追番时未入库的番剧加入，管理员统一同步"""
    __tablename__ = "subscribed_pending"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, nullable=False, index=True)
    media_id = db.Column(db.Integer, nullable=True, index=True)
    season_id = db.Column(db.Integer, nullable=True)
    title = db.Column(db.String(256), nullable=False, default="")
    cover = db.Column(db.String(512), nullable=False, default="")
    status = db.Column(db.SmallInteger, nullable=False, default=0)  # 0待同步 1同步中 2已同步 3失败
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
