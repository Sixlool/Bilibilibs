# -*- coding: utf-8 -*-
"""前端页面路由：首页、大屏、个人中心等"""

import os
from flask import Blueprint, send_from_directory, Response

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STATIC = os.path.join(BASE_DIR, "static")

pages_bp = Blueprint("pages", __name__)


@pages_bp.route("/favicon.ico")
def favicon():
    """避免浏览器请求 /favicon.ico 时返回 404"""
    return Response(status=204)


@pages_bp.route("/login")
def login_page():
    """登录页（仅图1）"""
    return send_from_directory(STATIC, "login.html")


@pages_bp.route("/")
def index():
    """首页：主应用（仅图2），未登录时前端会跳转到 /login"""
    return send_from_directory(STATIC, "index.html")


@pages_bp.route("/dashboard")
def dashboard():
    """可视化大屏"""
    return send_from_directory(STATIC, "index.html")


@pages_bp.route("/detail/<int:media_id>")
def detail(media_id):
    """番剧详情页（前端路由）"""
    return send_from_directory(STATIC, "index.html")


@pages_bp.route("/<path:path>")
def static_files(path):
    """静态资源"""
    return send_from_directory(STATIC, path)
