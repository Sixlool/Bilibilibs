# -*- coding: utf-8 -*-
"""Flask 应用工厂"""

import os
from flask import Flask
from flask_cors import CORS
from flask_login import LoginManager

# 项目根目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def create_app(config_overrides=None):
    app = Flask(__name__, static_folder=os.path.join(BASE_DIR, "static"), static_url_path="")
    # 加载 config 中的 SQLALCHEMY_*、SECRET_KEY 等
    import config as config_module
    app.config.from_object(config_module)
    if config_overrides:
        app.config.update(config_overrides)

    # 数据库
    from models import db, init_db
    init_db(app)

    # 跨域
    CORS(app, supports_credentials=True, origins=["http://127.0.0.1:5000", "http://localhost:5000"])

    # 登录
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    from models.user import User
    @login_manager.user_loader
    def load_user(uid):
        return User.query.get(int(uid)) if uid else None

    # 注册蓝图
    from app.routes.api import api_bp
    from app.routes.auth import auth_bp
    from app.routes.pages import pages_bp
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(pages_bp, url_prefix="/")

    return app
