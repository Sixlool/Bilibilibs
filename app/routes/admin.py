# -*- coding: utf-8 -*-
"""后台管理蓝图：管理员鉴权、数据统计概览、用户管理、数据采集（收口到后台）"""

from functools import wraps

from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from sqlalchemy import func

from models import db
from models.user import User
from models.bangumi import BangumiInfo, BangumiEpisode, BangumiDailySnapshot
from models.tag import TagInfo
from models.user import UserFavorite

# 复用 api.py 中的采集状态读写（数据库持久化，多 worker 共享）与后台线程函数
from app.routes.api import (
    _status_get,
    _status_set,
    _run_crawl_in_thread,
    _run_refresh_all_in_db_thread,
    _run_sync_subscribed_in_thread,
)

admin_bp = Blueprint("admin", __name__)


def admin_required(view):
    """仅管理员可访问的装饰器（需已登录）"""

    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not getattr(current_user, "is_admin", False):
            return jsonify({"ok": False, "error": "需要管理员权限"}), 403
        return view(*args, **kwargs)

    return wrapped


def _get_current_user_cookie():
    """取当前登录用户（管理员）已保存的 B 站 Cookie，用于采集时带登录态降低 412"""
    sessdata = (current_user.bilibili_sessdata or "").strip()
    bili_jct = (current_user.bilibili_bili_jct or "").strip()
    return sessdata, bili_jct


@admin_bp.route("/overview", methods=["GET"])
@admin_required
def overview():
    """数据统计概览：库内番剧/分集/标签/用户/收藏/快照数量，以及最近一次采集状态"""
    bangumi_count = db.session.query(func.count(BangumiInfo.id)).scalar() or 0
    episode_count = db.session.query(func.count(BangumiEpisode.id)).scalar() or 0
    tag_count = db.session.query(func.count(TagInfo.id)).scalar() or 0
    user_count = db.session.query(func.count(User.id)).scalar() or 0
    favorite_count = db.session.query(func.count(UserFavorite.id)).scalar() or 0
    snapshot_count = db.session.query(func.count(BangumiDailySnapshot.id)).scalar() or 0
    admin_count = db.session.query(func.count(User.id)).filter(User.is_admin == True).scalar() or 0  # noqa: E712

    status = _status_get(current_user.id)
    return jsonify({
        "ok": True,
        "stats": {
            "bangumi_count": bangumi_count,
            "episode_count": episode_count,
            "tag_count": tag_count,
            "user_count": user_count,
            "admin_count": admin_count,
            "favorite_count": favorite_count,
            "snapshot_count": snapshot_count,
        },
        "crawl": {
            "running": bool(status.get("running")),
            "job": status.get("job") or "",
            "page": status.get("page", 0),
            "pages": status.get("pages", 0),
            "items": status.get("items", 0),
            "message": status.get("message", ""),
        },
    })


@admin_bp.route("/crawl/status", methods=["GET"])
@admin_required
def crawl_status():
    """管理员最近一次采集进度（与前台 /api/crawl/status 共享同一进程内状态）"""
    s = _status_get(current_user.id)
    return jsonify({
        "ok": True,
        "running": bool(s.get("running")),
        "job": s.get("job") or "",
        "detail_media_id": s.get("detail_media_id"),
        "page": s.get("page", 0),
        "pages": s.get("pages", 0),
        "items": s.get("items", 0),
        "message": s.get("message", ""),
    })


def _safe_int(val, default=None):
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


@admin_bp.route("/crawl/start", methods=["POST"])
@admin_required
def crawl_start():
    """后台触发番剧采集（后台线程），使用管理员已保存的 B 站 Cookie"""
    data = request.get_json() or {}
    year = data.get("year")
    season = _safe_int(data.get("season"))
    pages = _safe_int(data.get("pages"), 2) or 2
    page_size = _safe_int(data.get("page_size"), 20) or 20
    delay = float(data.get("delay") or 3.0)
    delay = max(2.0, min(10.0, delay))

    s = _status_get(current_user.id)
    if s and s.get("running"):
        return jsonify({"ok": False, "error": "已有采集任务进行中，请等待结束后再试"}), 409

    sessdata, bili_jct = _get_current_user_cookie()
    app = current_app._get_current_object()
    thread = __import__("threading").Thread(
        target=_run_crawl_in_thread,
        args=(app, current_user.id, year, season, pages, page_size, delay, sessdata, bili_jct),
    )
    thread.daemon = True
    thread.start()
    return jsonify({
        "ok": True,
        "message": "后台采集已启动（年份：%s，季度：%s）" % (str(year) if year else "不限", str(season) if season else "不限"),
        "using_bilibili_cookie": bool(sessdata and bili_jct),
    }), 202


@admin_bp.route("/crawl/refresh-in-db", methods=["POST"])
@admin_required
def crawl_refresh_in_db():
    """后台依次刷新库内已有番剧的详情"""
    s = _status_get(current_user.id)
    if s and s.get("running"):
        return jsonify({"ok": False, "error": "已有采集任务进行中，请等待结束后再试"}), 409

    data = request.get_json() or {}
    delay = float(data.get("delay") or 4.0)
    delay = max(2.0, min(10.0, delay))
    total = db.session.query(func.count(BangumiInfo.id)).scalar() or 0

    sessdata, bili_jct = _get_current_user_cookie()
    app = current_app._get_current_object()
    thread = __import__("threading").Thread(
        target=_run_refresh_all_in_db_thread,
        args=(app, current_user.id, sessdata, bili_jct, delay),
    )
    thread.daemon = True
    thread.start()
    return jsonify({
        "ok": True,
        "message": "已开始更新库内番剧详情（约 %d 条）" % total,
        "total": total,
        "using_bilibili_cookie": bool(sessdata and bili_jct),
    }), 202


@admin_bp.route("/crawl/sync-subscribed", methods=["POST"])
@admin_required
def crawl_sync_subscribed():
    """后台同步管理员 B 站追番到本地数据库（需管理员已扫码登录并保存 Cookie）"""
    uid = getattr(current_user, "bilibili_uid", None)
    sessdata, bili_jct = _get_current_user_cookie()
    if not uid:
        return jsonify({"ok": False, "error": "管理员尚未绑定 B 站账号，请在个人中心使用 B 站扫码登录"}), 400
    if not sessdata or not bili_jct:
        return jsonify({"ok": False, "error": "管理员尚未保存 B 站 Cookie，请在个人中心设置"}), 400

    s = _status_get(current_user.id)
    if s and s.get("running"):
        return jsonify({"ok": False, "error": "已有采集任务进行中，请等待结束后再试"}), 409

    app = current_app._get_current_object()
    thread = __import__("threading").Thread(
        target=_run_sync_subscribed_in_thread,
        args=(app, current_user.id, sessdata, bili_jct, int(uid)),
    )
    thread.daemon = True
    thread.start()
    return jsonify({"ok": True, "message": "已开始同步追番，请查看下方进度"}), 202


@admin_bp.route("/users", methods=["GET"])
@admin_required
def list_users():
    """用户列表（含管理员标记、B 站绑定状态、注册时间）"""
    users = User.query.order_by(User.id).all()
    return jsonify({
        "ok": True,
        "users": [{
            "id": u.id,
            "username": u.username,
            "email": u.email or "",
            "is_admin": bool(u.is_admin),
            "bilibili_uid": u.bilibili_uid,
            "has_cookie": bool((u.bilibili_sessdata or "").strip() and (u.bilibili_bili_jct or "").strip()),
            "created_at": u.created_at.isoformat() if u.created_at else None,
        } for u in users],
    })


@admin_bp.route("/users/<int:user_id>/toggle-admin", methods=["POST"])
@admin_required
def toggle_admin(user_id):
    """提升/取消某用户的管理员权限（不能撤销自己的管理员权限，避免锁死）"""
    target = User.query.get(user_id)
    if not target:
        return jsonify({"ok": False, "error": "用户不存在"}), 404
    if target.id == current_user.id:
        return jsonify({"ok": False, "error": "不能修改自己的管理员权限"}), 400
    target.is_admin = not target.is_admin
    db.session.commit()
    return jsonify({"ok": True, "is_admin": bool(target.is_admin), "username": target.username})


@admin_bp.route("/users/<int:user_id>", methods=["DELETE"])
@admin_required
def delete_user(user_id):
    """删除用户（不能删除自己；仅删除用户与其收藏，不删除番剧数据）"""
    target = User.query.get(user_id)
    if not target:
        return jsonify({"ok": False, "error": "用户不存在"}), 404
    if target.id == current_user.id:
        return jsonify({"ok": False, "error": "不能删除自己"}), 400
    UserFavorite.query.filter_by(user_id=target.id).delete()
    db.session.delete(target)
    db.session.commit()
    return jsonify({"ok": True})
