# -*- coding: utf-8 -*-
"""数据库连接与 Flask-SQLAlchemy 初始化"""

from flask_sqlalchemy import SQLAlchemy
from flask import Flask

db = SQLAlchemy()


def init_db(app: Flask):
    """在 Flask 应用上初始化数据库"""
    app.config["SQLALCHEMY_DATABASE_URI"] = app.config.get(
        "SQLALCHEMY_DATABASE_URI",
        "mysql+pymysql://root:123456@127.0.0.1:3306/bilibili_bangumi?charset=utf8mb4",
    )
    app.config.setdefault("SQLALCHEMY_TRACK_MODIFICATIONS", False)
    db.init_app(app)
    return db
