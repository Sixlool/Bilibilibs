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
    db.session.add(user)
    db.session.commit()
    login_user(user)
    return jsonify({"ok": True, "user": {"id": user.id, "username": user.username}})


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
    return jsonify({"ok": True, "user": {"id": user.id, "username": user.username}})


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return jsonify({"ok": True})


@auth_bp.route("/me", methods=["GET"])
def me():
    """当前登录用户信息"""
    if not current_user.is_authenticated:
        return jsonify({"ok": True, "user": None})
    return jsonify({"ok": True, "user": {"id": current_user.id, "username": current_user.username}})
