# -*- coding: utf-8 -*-
"""用户注册、登录、登出。登录入口为 B 站扫码（见 /api/bilibili-qr）。"""

from flask import Blueprint, request, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from models import db
from models.user import User

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/register", methods=["POST"])
def register():
    """注册：JSON body { username, password, email? }（本系统独立账号，非 B 站）"""
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    email = (data.get("email") or "").strip()
    if not username or not password:
        return jsonify({"ok": False, "error": "username and password required"}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"ok": False, "error": "username exists"}), 400
    user = User(
        username=username,
        password_hash=generate_password_hash(password, method="pbkdf2:sha256"),
        email=email,
    )
    # 首个管理员引导：若库中尚无任何管理员，且环境变量 ADMIN_USERNAME 与注册用户名一致，
    # 则该用户自动成为管理员（部署时在 .env 设置 ADMIN_USERNAME 即可）。
    import os
    admin_username = (os.getenv("ADMIN_USERNAME") or "").strip()
    if admin_username and username == admin_username:
        admin_exists = User.query.filter(User.is_admin == True).first()  # noqa: E712
        if not admin_exists:
            user.is_admin = True
    db.session.add(user)
    db.session.commit()
    login_user(user)
    return jsonify({"ok": True, "user": {"id": user.id, "username": user.username, "is_admin": bool(user.is_admin)}})  # noqa: E501


@auth_bp.route("/login", methods=["POST"])
def login():
    """登录：JSON body { username, password }（本系统独立账号，仅内部用）。入口请用 B 站扫码。"""
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        return jsonify({"ok": False, "error": "username and password required"}), 400
    user = User.query.filter_by(username=username).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"ok": False, "error": "invalid username or password"}), 401
    login_user(user)
    return jsonify({"ok": True, "user": {"id": user.id, "username": user.username, "is_admin": bool(user.is_admin)}})  # noqa: E501


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return jsonify({"ok": True})


@auth_bp.route("/bind", methods=["POST"])
def bind():
    """绑定 B 站账号到本系统账号。

    扫码成功未绑定时，前端拿到 bind_token 后调用本接口，两种模式：
    - mode=bind_existing: { bind_token, username, password } 绑定已有账号
    - mode=register:      { bind_token, username, password, email? } 注册新账号并绑定
    成功后 B 站身份（bilibili_uid + Cookie）挂到该账号，以后可用账号密码直接登录。
    """
    from app.routes.api import _consume_bind_token
    data = request.get_json() or {}
    token = (data.get("bind_token") or "").strip()
    mode = (data.get("mode") or "bind_existing").strip()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    email = (data.get("email") or "").strip()

    if not token:
        return jsonify({"ok": False, "error": "缺少 bind_token"}), 400
    if not username or not password:
        return jsonify({"ok": False, "error": "username and password required"}), 400
    if mode not in ("bind_existing", "register"):
        return jsonify({"ok": False, "error": "mode 仅支持 bind_existing / register"}), 400

    rec = _consume_bind_token(token)
    if rec is None:
        return jsonify({"ok": False, "error": "绑定凭证已过期或无效，请重新扫码登录"}), 410
    sessdata = rec.get("sessdata") or ""
    bili_jct = rec.get("bili_jct") or ""
    bilibili_uid = rec.get("bilibili_uid")

    # 该 B 站账号若已绑定其他用户，拒绝重复绑定
    if bilibili_uid is not None:
        try:
            bilibili_uid = int(bilibili_uid)
        except (TypeError, ValueError):
            bilibili_uid = None
        if bilibili_uid is not None:
            exist = User.query.filter_by(bilibili_uid=bilibili_uid).first()
            if exist:
                return jsonify({"ok": False, "error": f"该 B 站账号已绑定用户「{exist.username}」，请直接用该账号登录"}), 409

    if mode == "register":
        if User.query.filter_by(username=username).first():
            return jsonify({"ok": False, "error": "username exists"}), 400
        user = User(
            username=username,
            password_hash=generate_password_hash(password, method="pbkdf2:sha256"),
            email=email,
            bilibili_uid=bilibili_uid,
            bilibili_sessdata=sessdata,
            bilibili_bili_jct=bili_jct,
        )
        # 首个管理员引导
        import os
        admin_username = (os.getenv("ADMIN_USERNAME") or "").strip()
        if admin_username and username == admin_username:
            admin_exists = User.query.filter(User.is_admin == True).first()  # noqa: E712
            if not admin_exists:
                user.is_admin = True
        db.session.add(user)
        db.session.commit()
    else:
        # 绑定已有账号：校验账号密码
        user = User.query.filter_by(username=username).first()
        if not user or not check_password_hash(user.password_hash, password):
            return jsonify({"ok": False, "error": "invalid username or password"}), 401
        if user.bilibili_uid is not None and user.bilibili_uid != bilibili_uid:
            return jsonify({"ok": False, "error": "该账号已绑定其他 B 站账号"}), 409
        user.bilibili_uid = bilibili_uid
        user.bilibili_sessdata = sessdata
        user.bilibili_bili_jct = bili_jct
        db.session.commit()

    login_user(user)
    return jsonify({"ok": True, "message": "绑定成功", "user": {"id": user.id, "username": user.username, "is_admin": bool(user.is_admin)}})  # noqa: E501


@auth_bp.route("/me", methods=["GET"])
def me():
    """当前登录用户信息"""
    if not current_user.is_authenticated:
        return jsonify({"ok": True, "user": None})
    return jsonify({"ok": True, "user": {
        "id": current_user.id,
        "username": current_user.username,
        "is_admin": bool(getattr(current_user, "is_admin", False)),
    }})
