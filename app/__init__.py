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

    # 跨域（来源白名单由 config.CORS_ORIGINS 控制；同域部署时为空列表即可）
    CORS(app, supports_credentials=True, origins=app.config.get("CORS_ORIGINS") or [])

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
    from app.routes.admin import admin_bp
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(pages_bp, url_prefix="/")
    app.register_blueprint(admin_bp, url_prefix="/admin")

    # ── 访问统计（PV/UV）──
    # 页面请求计数；排除 /api /auth 和静态资源，避免统计接口自身与脚本/样式请求
    @app.before_request
    def record_visit():
        from flask import request as _req
        from datetime import date as _date
        path = _req.path or ""
        if not path or path.startswith(("/api/", "/auth/")) or path == "/api" or path == "/auth":
            return
        # 静态资源 / 无扩展名页面之外的扩展名请求跳过
        ext = path.rsplit(".", 1)[-1] if "." in path.rsplit("/", 1)[-1] else ""
        if ext in ("js", "css", "png", "jpg", "jpeg", "gif", "ico", "svg", "woff", "woff2", "ttf"):
            return
        try:
            from models import db
            from models.user import VisitStat, VisitUv
            today = _date.today()
            # PV
            rec = VisitStat.query.filter_by(stat_date=today).first()
            if rec is None:
                rec = VisitStat(stat_date=today, pv=0, uv=0)
                db.session.add(rec)
            rec.pv += 1
            # UV：按 IP 去重（每天每 IP 仅计一次）
            ip = (_req.headers.get("X-Forwarded-For") or _req.remote_addr or "").split(",")[0].strip()
            if ip:
                duv = VisitUv.query.filter_by(stat_date=today, ip=ip).first()
                if duv is None:
                    db.session.add(VisitUv(stat_date=today, ip=ip))
                    rec.uv += 1
            db.session.commit()
        except Exception:
            try:
                db.session.rollback()
            except Exception:
                pass

    return app
