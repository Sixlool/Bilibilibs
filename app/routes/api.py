# -*- coding: utf-8 -*-
"""REST API：番剧列表、详情、分析、榜单、收藏等"""

import asyncio
import math
import secrets
import threading
from datetime import datetime
from urllib.parse import unquote

from flask import Blueprint, request, jsonify, current_app, Response
from flask_login import current_user, login_required, login_user
from sqlalchemy import text
from werkzeug.security import generate_password_hash

from models import db
from services import BangumiService, AnalysisService
import config as config_module

api_bp = Blueprint("api", __name__)
bangumi_svc = None
analysis_svc = None


def _sanitize_for_json(obj):
    """递归把 float/NumPy/pandas 的 NaN、NaT 转为 None，避免 JSON 序列化报错"""
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(x) for x in obj]
    if isinstance(obj, float) and math.isnan(obj):
        return None
    try:
        import numpy as np
        if isinstance(obj, np.floating) and np.isnan(obj):
            return None
    except Exception:
        pass
    try:
        import pandas as pd
        if pd.isna(obj):
            return None
    except Exception:
        pass
    return obj


def get_services():
    global bangumi_svc, analysis_svc
    if bangumi_svc is None:
        bangumi_svc = BangumiService(db)
    if analysis_svc is None:
        analysis_svc = AnalysisService(db)
    return bangumi_svc, analysis_svc


def _normalize_cover_url(url):
    """B 站封面常为 //i0.hdslb.com/... 协议相对 URL，补全为 https 以便前端正常显示"""
    if not url or not isinstance(url, str):
        return ""
    u = (url or "").strip()
    if u.startswith("//"):
        return "https:" + u
    return u


def _serialize_bangumi(info):
    """番剧信息转 JSON 友好"""
    return {
        "id": info.id,
        "media_id": info.media_id,
        "season_id": info.season_id,
        "title": info.title,
        "cover": _normalize_cover_url(info.cover),
        "intro": (info.intro or "")[:500],
        "pub_time": info.pub_time.isoformat() if info.pub_time else None,
        "score": float(info.score) if info.score is not None else None,
        "score_count": info.score_count or 0,
        "follow_count": info.follow_count or 0,
        "play_count": info.play_count or 0,
        "danmaku_count": info.danmaku_count or 0,
        "coin_count": info.coin_count or 0,
        "fav_count": info.fav_count or 0,
        "series_count": info.series_count or 0,
        "area": info.area or "",
        "season_type": info.season_type or 1,
    }


def _serialize_episode(ep):
    return {
        "episode_id": ep.episode_id,
        "index_title": ep.index_title or "",
        "long_title": ep.long_title or "",
        "duration": ep.duration or 0,
        "pub_time": ep.pub_time.isoformat() if ep.pub_time else None,
    }


# B 站 CDN 封面域名白名单，代理时只允许这些域名避免被滥用
_COVER_PROXY_ALLOWED_HOSTS = ("i0.hdslb.com", "i.hdslb.com")


@api_bp.route("/cover-proxy", methods=["GET"])
def cover_proxy():
    """
    代理 B 站 CDN 封面图，请求时带上 Referer 避免 403。
    仅允许 url 参数为 https://i0.hdslb.com/ 或 i.hdslb.com 的地址。
    """
    raw = (request.args.get("url") or "").strip()
    if not raw:
        return Response(status=400)
    url = unquote(raw)
    if not url.startswith(("https://i0.hdslb.com/", "https://i.hdslb.com/", "http://i0.hdslb.com/", "http://i.hdslb.com/")):
        return Response(status=400)
    try:
        import requests
        r = requests.get(
            url,
            timeout=10,
            headers={"Referer": "https://www.bilibili.com/", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
        r.raise_for_status()
        content_type = r.headers.get("Content-Type") or "image/png"
        return Response(r.content, mimetype=content_type)
    except Exception:
        return Response(status=502)


@api_bp.route("/debug/db", methods=["GET"])
def debug_db():
    """调试：当前连接的数据库及 bangumi_info 表记录数，用于排查“有采集但列表为空”"""
    err = None
    try:
        r = db.session.execute(text("SELECT COUNT(*) AS n FROM bangumi_info")).fetchone()
        count = r[0] if r else 0
    except Exception as e:
        count = None
        err = str(e)
    return jsonify({
        "ok": True,
        "database": config_module.MYSQL_CONFIG.get("database"),
        "host": config_module.MYSQL_CONFIG.get("host"),
        "port": config_module.MYSQL_CONFIG.get("port"),
        "bangumi_info_count": count,
        "error": err,
    })


def _safe_int(val, default=None):
    """避免 'undefined' 或空字符串被当作有效参数，只接受可转成整数的值"""
    if val is None or val == "":
        return default
    if isinstance(val, str) and (val == "undefined" or not val.strip() or (val.strip() and not val.strip().lstrip("-").isdigit())):
        return default
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _normalize_crawl_year(raw_year):
    """
    采集年份支持：
    - 单年：2016
    - 区间桶：2014-2010 / 2009-2005 / 2004-2000 / 90年代 / 80年代 / 更早
    """
    if raw_year in (None, "", "undefined"):
        return None
    if isinstance(raw_year, int):
        return raw_year
    s = str(raw_year).strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    allowed = {"2014-2010", "2009-2005", "2004-2000", "90年代", "80年代", "更早"}
    if s in allowed:
        return s
    return None


@api_bp.route("/bangumi", methods=["GET"])
def list_bangumi():
    """番剧列表：支持 keyword, tags, year, season, score_min, score_max, play_min, play_max, order_by, order_desc, page, page_size"""
    svc, _ = get_services()
    keyword = (request.args.get("keyword") or "").strip() or None
    tags_str = request.args.get("tags", "") or ""
    tags = [t.strip() for t in tags_str.split(",") if t.strip()] or None
    year = _safe_int(request.args.get("year"))
    season = _safe_int(request.args.get("season"))
    try:
        score_min = float(request.args.get("score_min")) if request.args.get("score_min") not in (None, "", "undefined") else None
    except (TypeError, ValueError):
        score_min = None
    try:
        score_max = float(request.args.get("score_max")) if request.args.get("score_max") not in (None, "", "undefined") else None
    except (TypeError, ValueError):
        score_max = None
    try:
        score_lt = float(request.args.get("score_lt")) if request.args.get("score_lt") not in (None, "", "undefined") else None
    except (TypeError, ValueError):
        score_lt = None
    play_min = _safe_int(request.args.get("play_min"))
    play_max = _safe_int(request.args.get("play_max"))
    area = (request.args.get("area") or "").strip() or None
    series_min = _safe_int(request.args.get("series_min"))
    series_max = _safe_int(request.args.get("series_max"))
    no_score = (request.args.get("no_score") or "").strip() in ("1", "true", "yes")
    order_by = request.args.get("order_by") or "play_count"
    order_desc = (request.args.get("order_desc") or "true").lower() == "true"
    page = max(1, _safe_int(request.args.get("page"), 1))
    page_size = min(100, max(1, _safe_int(request.args.get("page_size"), 20)))
    result = svc.get_list(
        keyword=keyword,
        tags=tags,
        year=year,
        season=season,
        score_min=score_min,
        score_max=score_max,
        score_lt=score_lt,
        play_min=play_min,
        play_max=play_max,
        area=area,
        series_min=series_min,
        series_max=series_max,
        no_score=no_score,
        order_by=order_by,
        order_desc=order_desc,
        page=page,
        page_size=page_size,
    )
    items = [_serialize_bangumi(r) for r in result["items"]]
    if current_user.is_authenticated and items:
        from models.user import UserFavorite
        media_ids = [it["media_id"] for it in items]
        fav_media_ids = {f.media_id for f in UserFavorite.query.filter(
            UserFavorite.user_id == current_user.id,
            UserFavorite.media_id.in_(media_ids),
        ).all()}
        for it in items:
            it["favorited"] = it["media_id"] in fav_media_ids
    else:
        for it in items:
            it["favorited"] = False
    return jsonify({"ok": True, "total": result["total"], "page": result["page"], "page_size": result["page_size"], "items": items})


@api_bp.route("/bangumi/<int:media_id>", methods=["GET"])
def bangumi_detail(media_id):
    """番剧详情（含分集、标签）"""
    svc, _ = get_services()
    data = svc.get_by_media_id(media_id)
    if not data:
        return jsonify({"ok": False, "error": "not_found"}), 404
    info, episodes, tags = data["info"], data["episodes"], data["tags"]
    ret = _serialize_bangumi(info)
    ret["episodes"] = [_serialize_episode(ep) for ep in episodes]
    ret["tags"] = tags
    # 是否已收藏（登录用户）
    ret["favorited"] = False
    if current_user.is_authenticated:
        from models.user import UserFavorite
        ret["favorited"] = UserFavorite.query.filter_by(user_id=current_user.id, media_id=media_id).first() is not None
    return jsonify({"ok": True, "data": ret})


@api_bp.route("/analysis/trend", methods=["GET"])
def analysis_trend():
    """宏观趋势：年度/季度新番数量"""
    _, svc = get_services()
    data = _sanitize_for_json(svc.macro_trend())
    return jsonify({"ok": True, "data": data})


@api_bp.route("/analysis/tags", methods=["GET"])
def analysis_tags():
    """标签分布"""
    _, svc = get_services()
    data = _sanitize_for_json(svc.tag_distribution())
    return jsonify({"ok": True, "data": data})


@api_bp.route("/analysis/dashboard-charts", methods=["GET"])
def analysis_dashboard_charts():
    """大屏扩展统计：评分/散点/地区/互动/话数/开播热力/快照"""
    _, svc = get_services()
    data = _sanitize_for_json(svc.dashboard_charts())
    return jsonify({"ok": True, "data": data})


@api_bp.route("/analysis/tags-by-media-ids", methods=["GET"])
def analysis_tags_by_media_ids():
    """按 media_id 列表统计标签分布（用于追番列表的标签分布图）"""
    _, svc = get_services()
    raw = (request.args.get("media_ids") or "").strip()
    if not raw:
        return jsonify({"ok": True, "data": [], "matched_count": 0})
    try:
        ids = [int(x) for x in raw.split(",") if x.strip()][:500]
    except ValueError:
        return jsonify({"ok": True, "data": [], "matched_count": 0})
    tag_list, matched_count = svc.tag_distribution_by_media_ids(ids, limit=20)
    return jsonify({
        "ok": True,
        "data": _sanitize_for_json(tag_list),
        "matched_count": matched_count,
        "requested_count": len(ids),
    })


@api_bp.route("/rank", methods=["GET"])
def rank():
    """榜单：order=play_count|follow_count|score|danmaku_count, limit=20, year=, season="""
    _, svc = get_services()
    order = request.args.get("order", "play_count")
    limit = min(100, max(1, request.args.get("limit", type=int) or 20))
    year = request.args.get("year", type=int) or None
    season = request.args.get("season", type=int) or None
    rows = _sanitize_for_json(svc.rank_by(order=order, limit=limit, year=year, season=season))
    return jsonify({"ok": True, "data": rows})


@api_bp.route("/favorite/<int:media_id>", methods=["POST"])
@login_required
def add_favorite(media_id):
    """收藏番剧"""
    from models.user import UserFavorite
    from models.bangumi import BangumiInfo
    if BangumiInfo.query.filter_by(media_id=media_id).first() is None:
        return jsonify({"ok": False, "error": "bangumi not found"}), 404
    if UserFavorite.query.filter_by(user_id=current_user.id, media_id=media_id).first():
        return jsonify({"ok": True, "message": "already favorited"})
    db.session.add(UserFavorite(user_id=current_user.id, media_id=media_id))
    db.session.commit()
    return jsonify({"ok": True, "message": "ok"})


@api_bp.route("/favorite/<int:media_id>", methods=["DELETE"])
@login_required
def remove_favorite(media_id):
    """取消收藏"""
    from models.user import UserFavorite
    UserFavorite.query.filter_by(user_id=current_user.id, media_id=media_id).delete()
    db.session.commit()
    return jsonify({"ok": True, "message": "ok"})


@api_bp.route("/favorites", methods=["GET"])
@login_required
def list_favorites():
    """当前用户收藏列表"""
    from models.user import UserFavorite
    from models.bangumi import BangumiInfo
    favs = UserFavorite.query.filter_by(user_id=current_user.id).all()
    media_ids = [f.media_id for f in favs]
    if not media_ids:
        return jsonify({"ok": True, "items": []})
    infos = BangumiInfo.query.filter(BangumiInfo.media_id.in_(media_ids)).all()
    id2info = {i.media_id: i for i in infos}
    items = [_serialize_bangumi(id2info[mid]) for mid in media_ids if mid in id2info]
    return jsonify({"ok": True, "items": items})


@api_bp.route("/recommendations/by-tags", methods=["GET"])
@login_required
def recommend_by_tags():
    """根据当前用户已收藏番剧的标签，推荐库中未收藏且标签重合的番剧。"""
    from models.user import UserFavorite

    limit = min(50, max(1, request.args.get("limit", type=int) or 20))
    fav_n = UserFavorite.query.filter_by(user_id=current_user.id).count()
    if fav_n == 0:
        return jsonify({
            "ok": True,
            "items": [],
            "message": "请先收藏几部番剧；系统会按这些番的标签在库中为您找相似作品。",
        })
    svc, _ = get_services()
    rows = svc.recommend_by_favorite_tags(current_user.id, limit=limit)
    if not rows:
        return jsonify({
            "ok": True,
            "items": [],
            "message": "收藏暂无标签数据，或库中没有其它同标签番剧。可先「同步 B 站追番」或重新采集以写入标签。",
        })
    items = []
    for row in rows:
        d = _serialize_bangumi(row["info"])
        d["favorited"] = False
        d["tag_score"] = row["tag_score"]
        d["matched_tags"] = row["matched_tags"]
        items.append(d)
    return jsonify({"ok": True, "items": _sanitize_for_json(items), "message": ""})


@api_bp.route("/user/bilibili-subscribed-bangumi", methods=["GET"])
@login_required
def get_bilibili_subscribed_bangumi():
    """获取当前登录用户 B 站账号的追番列表（需已用 B 站扫码登录并保存 Cookie）"""
    from models.user import User
    from bilibili_api.user import User as BiliUser
    from bilibili_api.user import BangumiType, BangumiFollowStatus
    from bilibili_api.utils.network import Credential
    try:
        from bilibili_api.utils.sync import sync as run_async
    except ImportError:
        def run_async(coro):
            return asyncio.run(coro)

    u = User.query.get(current_user.id)
    if not u:
        return jsonify({"ok": False, "error": "user not found"}), 404
    uid = getattr(u, "bilibili_uid", None)
    sessdata = (getattr(u, "bilibili_sessdata", None) or "").strip()
    bili_jct = (getattr(u, "bilibili_bili_jct", None) or "").strip()
    if not uid or not sessdata or not bili_jct:
        return jsonify({
            "ok": False,
            "error": "请先使用 B 站扫码登录（个人中心 → 显示登录二维码），以获取追番列表",
            "items": [],
        }), 400

    try:
        credential = Credential(sessdata=sessdata, bili_jct=bili_jct)
        bili_user = BiliUser(uid=int(uid), credential=credential)
        all_list = []
        pn = 1
        ps = 30
        while pn <= 10:
            res = run_async(
                bili_user.get_subscribed_bangumi(
                    type_=BangumiType.BANGUMI,
                    follow_status=BangumiFollowStatus.ALL,
                    pn=pn,
                    ps=ps,
                )
            )
            if not res or not isinstance(res, dict):
                break
            data = res.get("data") or res.get("result") or res
            lst = data.get("list") if isinstance(data, dict) else []
            if not lst:
                break
            for item in lst:
                if not isinstance(item, dict):
                    continue
                cover = (item.get("cover") or item.get("square_cover") or "").strip()
                if cover.startswith("//"):
                    cover = "https:" + cover
                stat = item.get("stat") or {}
                new_ep = item.get("new_ep") or {}
                all_list.append({
                    "season_id": item.get("season_id"),
                    "media_id": item.get("media_id"),
                    "title": (item.get("title") or "").strip(),
                    "cover": cover,
                    "follow_status": item.get("follow_status"),
                    "is_finish": item.get("is_finish"),
                    "play_count": stat.get("view") or stat.get("play") or 0,
                    "follow_count": stat.get("follow") or 0,
                    "new_ep_index": new_ep.get("index_show") or new_ep.get("title") or "",
                })
            if len(lst) < ps:
                break
            pn += 1
        return jsonify({"ok": True, "items": _sanitize_for_json(all_list)})
    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e),
            "items": [],
        }), 500


@api_bp.route("/user/bilibili-cookie", methods=["GET"])
@login_required
def get_bilibili_cookie_status():
    """是否已绑定 B 站账号 / 已设置 B 站 Cookie（不返回 Cookie 具体值，仅返回 UID）"""
    from models.user import User
    u = User.query.get(current_user.id)
    has = bool(u and (u.bilibili_sessdata or "").strip() and (u.bilibili_bili_jct or "").strip())
    return jsonify({
        "ok": True,
        "has_cookie": has,
        "bilibili_uid": u.bilibili_uid if u else None,
        "has_bind": bool(u and u.bilibili_uid is not None),
    })


@api_bp.route("/user/bilibili-cookie", methods=["POST"])
@login_required
def save_bilibili_cookie():
    """保存当前用户的 B 站 Cookie，采集时用该账号请求以降低 412"""
    from models.user import User
    data = request.get_json() or {}
    sessdata = (data.get("sessdata") or "").strip()
    bili_jct = (data.get("bili_jct") or "").strip()
    u = User.query.get(current_user.id)
    if not u:
        return jsonify({"ok": False, "error": "user not found"}), 404
    u.bilibili_sessdata = sessdata
    u.bilibili_bili_jct = bili_jct
    db.session.commit()
    return jsonify({"ok": True, "message": "已保存"})


# ---------- B 站扫码登录（免登录可调：用于入口扫码登录本系统；已登录时则仅更新 Cookie） ----------
@api_bp.route("/bilibili-qr/generate", methods=["GET"])
def bilibili_qr_generate():
    """生成 B 站登录二维码（无需本系统登录）"""
    from services.bilibili_qr_login import generate_qrcode
    qrcode_key, url, qrcode_image_base64 = generate_qrcode()
    if not qrcode_key:
        return jsonify({"ok": False, "error": "获取二维码失败"}), 500
    return jsonify({
        "ok": True,
        "qrcode_key": qrcode_key,
        "url": url,
        "qrcode_image_base64": qrcode_image_base64,
    })


@api_bp.route("/bilibili-qr/poll", methods=["GET"])
def bilibili_qr_poll():
    """轮询二维码状态。未登录时：扫码成功则按 B 站 UID 创建/绑定本系统账号并登录；已登录时：仅更新当前用户的 B 站 Cookie。"""
    from services.bilibili_qr_login import poll_qrcode
    from models.user import User
    qrcode_key = (request.args.get("qrcode_key") or "").strip()
    if not qrcode_key:
        return jsonify({"ok": False, "error": "缺少 qrcode_key"}), 400
    status, cookies = poll_qrcode(qrcode_key)
    if status == "done" and cookies:
        try:
            sessdata = cookies.get("sessdata") or ""
            bili_jct = cookies.get("bili_jct") or ""
            bilibili_uid = cookies.get("bilibili_uid")
            if current_user.is_authenticated:
                u = User.query.get(current_user.id)
                if u:
                    # 已登录用户扫码绑定：先检查该 B 站 UID 是否已被其他用户绑定
                    if bilibili_uid is not None:
                        try:
                            bilibili_uid = int(bilibili_uid)
                        except (TypeError, ValueError):
                            bilibili_uid = None
                        if bilibili_uid is not None:
                            owner = User.query.filter_by(bilibili_uid=bilibili_uid).first()
                            if owner and owner.id != u.id and not getattr(owner, "is_auto_created", False):
                                return jsonify({
                                    "ok": False,
                                    "status": "error",
                                    "error": f"该 B 站账号已绑定用户「{owner.username}」，无法重复绑定",
                                }), 409
                            if owner and owner.id != u.id and getattr(owner, "is_auto_created", False):
                                # 接管自动创建账号：收藏迁移 + 删除，UID 归当前用户
                                from models.user import UserFavorite
                                favs = UserFavorite.query.filter_by(user_id=owner.id).all()
                                for f in favs:
                                    if not UserFavorite.query.filter_by(user_id=u.id, media_id=f.media_id).first():
                                        f.user_id = u.id
                                        db.session.add(f)
                                db.session.delete(owner)
                            u.bilibili_uid = bilibili_uid
                    u.bilibili_sessdata = sessdata
                    u.bilibili_bili_jct = bili_jct
                    db.session.commit()
                return jsonify({"ok": True, "status": "done", "message": "B 站登录成功，已绑定账号"})
            # 未登录：扫码成功 → 按 B 站 UID 查找已绑定账号
            # 有绑定 → 直接登录；无绑定 → 返回 bind_token 引导绑定（不自动建号）
            u = None
            if bilibili_uid is not None:
                try:
                    bilibili_uid = int(bilibili_uid)
                except (TypeError, ValueError):
                    bilibili_uid = None
            if bilibili_uid is not None:
                u = User.query.filter_by(bilibili_uid=bilibili_uid).first()
            if u is not None and not getattr(u, "is_auto_created", False):
                # 已绑定（真实账号）：更新 Cookie 并登录
                u.bilibili_sessdata = sessdata
                u.bilibili_bili_jct = bili_jct
                db.session.commit()
                login_user(u)
                return jsonify({"ok": True, "status": "done", "message": "登录成功", "user": {"id": u.id, "username": u.username}})
            # 未绑定（含自动创建的历史账号）：暂存凭据，返回绑定 token 引导注册/绑定
            bind_token = _create_bind_token(sessdata, bili_jct, bilibili_uid)
            return jsonify({
                "ok": True,
                "status": "done",
                "needs_bind": True,
                "bind_token": bind_token,
                "bilibili_uid": bilibili_uid,
                "message": "该 B 站账号尚未绑定系统账号，请完成绑定",
            })
        except Exception as e:
            emsg = str(e)
            if "cryptography" in emsg and "caching_sha2_password" in emsg:
                emsg = "数据库驱动缺少 cryptography 依赖，无法保存扫码登录结果"
            return jsonify({"ok": False, "status": "error", "error": emsg}), 500
    if status == "error":
        # B 站已确认登录但未拿到完整凭据（新版接口可能变更），给出准确提示而非「二维码已过期」
        return jsonify({"ok": False, "status": "error", "error": "已确认登录，但获取登录凭据失败，请点击「显示登录二维码」重试"}), 502
    return jsonify({"ok": True, "status": status})


# ── 扫码登录绑定暂存 ─────────────────────────────────────────────────────────
# 扫码成功但 B 站账号未绑定系统账号时，暂存凭据生成一次性 bind_token（内存态，
# 进程内有效，10 分钟过期），前端凭 token 走绑定流程。多 worker 部署下建议换 Redis，
# 单进程/开发环境内存即可。
import time as _time

_BIND_TOKENS = {}  # token -> { sessdata, bili_jct, bilibili_uid, created_at }
BIND_TOKEN_TTL = 600  # 10 分钟


def _create_bind_token(sessdata, bili_jct, bilibili_uid):
    """生成一次性绑定 token 并暂存 B 站凭据"""
    global _BIND_TOKENS
    token = secrets.token_hex(24)
    _BIND_TOKENS[token] = {
        "sessdata": sessdata,
        "bili_jct": bili_jct,
        "bilibili_uid": bilibili_uid,
        "created_at": _time.time(),
    }
    # 顺手清理过期 token
    _BIND_TOKENS = {k: v for k, v in _BIND_TOKENS.items() if _time.time() - v["created_at"] < BIND_TOKEN_TTL}
    return token


def _consume_bind_token(token):
    """取出并销毁绑定 token；不存在或过期返回 None"""
    global _BIND_TOKENS
    rec = _BIND_TOKENS.pop(token, None)
    if not rec:
        return None
    if _time.time() - rec["created_at"] > BIND_TOKEN_TTL:
        return None
    return rec


# 当前用户采集进度（存数据库，多 worker 共享；前端轮询 /crawl/status 或 /admin/crawl/status）


def _status_get(user_id):
    """读取采集进度（数据库）；无记录返回空 dict"""
    from models.user import CrawlStatus
    try:
        s = CrawlStatus.query.filter_by(user_id=user_id).first()
        if s is None:
            return {}
        return {
            "running": bool(s.running),
            "job": s.job or "",
            "detail_media_id": s.detail_media_id,
            "page": s.page or 0,
            "pages": s.pages or 0,
            "items": s.items or 0,
            "message": s.message or "",
        }
    except Exception:
        return {}


def _status_set(user_id, running=None, job=None, detail_media_id=None,
                page=None, pages=None, items=None, message=None):
    """写入采集进度（数据库 upsert）"""
    from models.user import CrawlStatus
    try:
        s = CrawlStatus.query.filter_by(user_id=user_id).first()
        if s is None:
            s = CrawlStatus(user_id=user_id)
            db.session.add(s)
        if running is not None:
            s.running = bool(running)
        if job is not None:
            s.job = job or ""
        if detail_media_id is not None:
            s.detail_media_id = detail_media_id
        if page is not None:
            s.page = page or 0
        if pages is not None:
            s.pages = pages or 0
        if items is not None:
            s.items = items or 0
        if message is not None:
            s.message = (message or "")[:500]
        db.session.commit()
    except Exception:
        db.session.rollback()


def _run_crawl_in_thread(app, user_id, year, season, pages, page_size, delay, sessdata, bili_jct):
    """在后台线程中执行采集并写入 DB；需同时有 app 与 request 上下文，否则 db.session.commit 可能未持久化到 MySQL"""
    import logging
    log = logging.getLogger(__name__)
    with app.app_context():
        with app.test_request_context():
            from models import db
            from models.user import User
            from models.bangumi import BangumiInfo
            from crawler import BangumiCollector
            from services.bangumi_service import save_bangumi_list_safe
            credential = None
            if sessdata and bili_jct:
                try:
                    from bilibili_api.utils.network import Credential
                    credential = Credential(sessdata=sessdata, bili_jct=bili_jct)
                except Exception:
                    pass
            status = _status_get(user_id)
            _status_set(user_id, running=True, job="index", detail_media_id=None,
                        page=0, pages=pages or 2, items=0,
                        message=f"正在启动…（年份：{str(year) if year is not None else '不限'}，季度：{str(season) if season in (1, 4, 7, 10) else '不限'}）")

            def progress_cb(current_page, max_pages, items_count, message):
                _status_set(user_id, page=current_page, pages=max_pages,
                            items=items_count, message=message)

            details = []
            try:
                collector = BangumiCollector(delay=delay or 3.0, max_retries=3)
                details = collector.run_index_and_collect(
                    year=year,
                    season_month=season,
                    max_pages=pages or 2,
                    page_size=page_size or 20,
                    credential=credential,
                    progress_callback=progress_cb,
                )
                n = len(details)
                if n == 0:
                    _status_set(user_id, message="采集完成，共 0 条（可能触发了风控，请调大间隔或减少页数后重试）")
                else:
                    inserted, updated = save_bangumi_list_safe(db, details)
                    db.session.commit()
                    total = db.session.query(BangumiInfo).count()
                    _status_set(user_id, message=f"采集完成：本次新增 {inserted} 条、更新 {updated} 条，库中共 {total} 条。请点击「番剧列表」查看。（若想库中条数变多，请爬取不同年份/季度或更多页）")
            except Exception as e:
                log.exception("采集或写入数据库失败")
                _status_set(user_id, message=f"写入数据库失败：{e!s}")
            finally:
                _status_set(user_id, running=False, items=len(details))
                try:
                    db.session.remove()
                except Exception:
                    pass


def _run_sync_subscribed_in_thread(app, user_id, sessdata, bili_jct, bilibili_uid):
    """后台线程：拉取当前用户 B 站追番列表的详情并写入 DB"""
    import logging
    log = logging.getLogger(__name__)
    with app.app_context():
        with app.test_request_context():
            from models import db
            from models.bangumi import BangumiInfo
            from crawler.collector import run_sync_subscribed
            from services.bangumi_service import save_bangumi_list_safe
            from bilibili_api.utils.network import Credential

            credential = None
            if sessdata and bili_jct:
                try:
                    credential = Credential(sessdata=sessdata, bili_jct=bili_jct)
                except Exception:
                    pass
            _status_set(user_id, running=True, job="sync_subscribed", detail_media_id=None,
                        page=0, pages=1, items=0, message="正在拉取追番列表…")

            def progress_cb(_page, _pages, count, message):
                _status_set(user_id, items=count, message=message)

            details = []
            try:
                details = run_sync_subscribed(
                    credential=credential,
                    bilibili_uid=bilibili_uid,
                    progress_callback=progress_cb,
                    delay=6.0,
                )
                if details:
                    inserted, updated = save_bangumi_list_safe(db, details)
                    db.session.commit()
                    total = db.session.query(BangumiInfo).count()
                    _status_set(user_id, message=f"同步完成：本次新增 {inserted} 条、更新 {updated} 条，库中共 {total} 条。追番标签分布等图表将更全面。")
                else:
                    _status_set(user_id, message="同步完成，共 0 条（请确认已用 B 站扫码登录且账号有追番）")
            except Exception as e:
                log.exception("同步追番失败")
                _status_set(user_id, message=f"同步失败：{e!s}")
            finally:
                _status_set(user_id, running=False, items=len(details))
                try:
                    db.session.remove()
                except Exception:
                    pass


def _run_refresh_one_detail_in_thread(app, user_id, media_id, sessdata, bili_jct):
    """后台线程：仅重新拉取单部番剧的详情并写入 DB"""
    import logging
    log = logging.getLogger(__name__)
    with app.app_context():
        with app.test_request_context():
            from models import db
            from models.bangumi import BangumiInfo
            from crawler.collector import run_async, _fetch_one_bangumi_detail
            from services.bangumi_service import save_bangumi_list_safe

            credential = None
            if sessdata and bili_jct:
                try:
                    from bilibili_api.utils.network import Credential
                    credential = Credential(sessdata=sessdata, bili_jct=bili_jct)
                except Exception:
                    pass

            _status_set(user_id, running=True, job="detail", detail_media_id=media_id,
                        page=0, pages=1, items=1,
                        message=f"正在重新拉取该番详情（media_id={media_id}）…")

            try:
                info = BangumiInfo.query.filter_by(media_id=media_id).first()
                if not info:
                    _status_set(user_id, message="库中未找到该番剧")
                    return
                detail = run_async(_fetch_one_bangumi_detail(info.season_id, media_id, credential))
                if not detail:
                    _status_set(user_id, message="拉取失败（网络或风控），请稍后重试；登录 B 站后再试可提高成功率")
                else:
                    save_bangumi_list_safe(db, [detail])
                    db.session.commit()
                    _status_set(user_id, message="详情已更新")
            except Exception as e:
                log.exception("单番详情刷新失败 media_id=%s", media_id)
                _status_set(user_id, message=f"写入失败：{e!s}")
            finally:
                _status_set(user_id, running=False, job="", detail_media_id=None)
                try:
                    db.session.remove()
                except Exception:
                    pass


def _run_refresh_all_in_db_thread(app, user_id, sessdata, bili_jct, delay: float):
    """后台线程：依次重新拉取库内每条 BangumiInfo 的详情并写回数据库"""
    import logging
    import time
    log = logging.getLogger(__name__)
    with app.app_context():
        with app.test_request_context():
            from models import db
            from models.bangumi import BangumiInfo
            from crawler.collector import run_async, _fetch_one_bangumi_detail
            from services.bangumi_service import save_bangumi_list_safe

            credential = None
            if sessdata and bili_jct:
                try:
                    from bilibili_api.utils.network import Credential
                    credential = Credential(sessdata=sessdata, bili_jct=bili_jct)
                except Exception:
                    pass

            rows = BangumiInfo.query.order_by(BangumiInfo.media_id.asc()).all()
            total = len(rows)
            _status_set(user_id, running=True, job="refresh_db", detail_media_id=None,
                        page=0, pages=max(1, total) if total else 1, items=0,
                        message=f"准备更新库内番剧详情，共 {total} 条…")

            ok = 0
            fail = 0
            try:
                if total == 0:
                    _status_set(user_id, message="库中暂无番剧记录")
                    return
                for i, info in enumerate(rows):
                    short_title = (info.title or "")[:28]
                    _status_set(user_id, page=i + 1, pages=total,
                                message=f"更新中 {i + 1}/{total}：{short_title or '(无标题)'}")
                    try:
                        detail = run_async(_fetch_one_bangumi_detail(info.season_id, info.media_id, credential))
                        if detail:
                            save_bangumi_list_safe(db, [detail])
                            db.session.commit()
                            ok += 1
                        else:
                            fail += 1
                    except Exception as e:
                        log.warning("批量刷新单条失败 media_id=%s: %s", info.media_id, e)
                        fail += 1
                        try:
                            db.session.rollback()
                        except Exception:
                            pass
                    _status_set(user_id, items=ok)
                    if i + 1 < total:
                        time.sleep(delay)
                _status_set(user_id, message=f"库内番剧详情更新结束：成功 {ok} 条，失败或未拉到 {fail} 条。")
            except Exception as e:
                log.exception("批量刷新库内番剧失败")
                _status_set(user_id, message=f"批量更新中断：{e!s}")
            finally:
                _status_set(user_id, running=False, job="",
                            pages=total if total else 1, page=total if total else 0)
                try:
                    db.session.remove()
                except Exception:
                    pass


@api_bp.route("/crawl/sync-subscribed", methods=["POST"])
@login_required
def crawl_sync_subscribed():
    """同步当前用户 B 站追番到本地数据库（后台执行），便于追番标签分布等图表更全"""
    from models.user import User
    u = User.query.get(current_user.id)
    if not u:
        return jsonify({"ok": False, "error": "user not found"}), 404
    uid = getattr(u, "bilibili_uid", None)
    sessdata = (getattr(u, "bilibili_sessdata", None) or "").strip()
    bili_jct = (getattr(u, "bilibili_bili_jct", None) or "").strip()
    if not uid:
        return jsonify({"ok": False, "error": "请先使用 B 站扫码登录（个人中心 → 显示登录二维码）"}), 400
    if not sessdata or not bili_jct:
        return jsonify({"ok": False, "error": "请先使用 B 站扫码登录以保存 Cookie"}), 400
    # 并发保护：已有任务运行中则拒绝
    s = _status_get(current_user.id)
    if s and s.get("running"):
        return jsonify({"ok": False, "error": "已有同步任务进行中，请等待结束后再试"}), 409
    app = current_app._get_current_object()
    thread = threading.Thread(
        target=_run_sync_subscribed_in_thread,
        args=(app, current_user.id, sessdata, bili_jct, int(uid)),
    )
    thread.daemon = True
    thread.start()
    return jsonify({"ok": True, "message": "已开始同步追番，请查看下方进度"}), 202


@api_bp.route("/crawl/refresh-detail", methods=["POST"])
@login_required
def crawl_refresh_detail():
    """仅重新爬取当前番剧的详情（简介、统计、分集等），在个人中心详情页触发"""
    from models.user import User
    data = request.get_json() or {}
    media_id = _safe_int(data.get("media_id"))
    if not media_id:
        return jsonify({"ok": False, "error": "media_id 无效"}), 400

    from models.bangumi import BangumiInfo
    if not BangumiInfo.query.filter_by(media_id=media_id).first():
        return jsonify({"ok": False, "error": "库中未找到该番剧"}), 404

    uid = current_user.id
    s = _status_get(uid)
    if s and s.get("running"):
        return jsonify({"ok": False, "error": "已有采集任务进行中，请等待结束后再试"}), 409

    u = User.query.get(uid)
    sessdata = (u.bilibili_sessdata or "").strip() if u else ""
    bili_jct = (u.bilibili_bili_jct or "").strip() if u else ""
    # 先写入状态，便于前端立刻轮询到 running=true（避免任务过快结束漏检）
    _status_set(uid, running=True, job="detail", detail_media_id=media_id,
                page=0, pages=1, items=1,
                message=f"正在重新拉取该番详情（media_id={media_id}）…")
    app = current_app._get_current_object()
    thread = threading.Thread(
        target=_run_refresh_one_detail_in_thread,
        args=(app, uid, media_id, sessdata, bili_jct),
    )
    thread.daemon = True
    thread.start()
    return jsonify({
        "ok": True,
        "message": "已开始重新拉取详情，完成后请刷新本页或稍候自动更新",
        "media_id": media_id,
        "using_bilibili_cookie": bool(sessdata and bili_jct),
    }), 202


@api_bp.route("/crawl/refresh-in-db", methods=["POST"])
@login_required
def crawl_refresh_in_db():
    """依次重新爬取数据库中已有番剧的详情（简介、统计、分集等），后台执行，耗时与库内条数成正比"""
    from models.user import User
    from models.bangumi import BangumiInfo

    uid = current_user.id
    s = _status_get(uid)
    if s and s.get("running"):
        return jsonify({"ok": False, "error": "已有采集任务进行中，请等待结束后再试"}), 409

    data = request.get_json() or {}
    delay = float(data.get("delay") or 4.0)
    delay = max(2.0, min(10.0, delay))

    total = BangumiInfo.query.count()
    u = User.query.get(uid)
    sessdata = (u.bilibili_sessdata or "").strip() if u else ""
    bili_jct = (u.bilibili_bili_jct or "").strip() if u else ""

    _status_set(uid, running=True, job="refresh_db", detail_media_id=None,
                page=0, pages=max(1, total) if total else 1, items=0,
                message=f"任务已排队：将更新库内共 {total} 条番剧（每条间隔约 {delay:g}s）…")
    app = current_app._get_current_object()
    thread = threading.Thread(
        target=_run_refresh_all_in_db_thread,
        args=(app, uid, sessdata, bili_jct, delay),
    )
    thread.daemon = True
    thread.start()
    return jsonify({
        "ok": True,
        "message": f"已开始更新库内番剧详情（约 {total} 条），请勿重复启动其它采集任务",
        "total": total,
        "delay": delay,
        "using_bilibili_cookie": bool(sessdata and bili_jct),
    }), 202


@api_bp.route("/crawl/start", methods=["POST"])
@login_required
def crawl_start():
    """手动触发采集（后台线程执行），使用当前用户已保存的 B 站 Cookie 若存在"""
    from models.user import User
    data = request.get_json() or {}
    raw_year = data.get("year")
    raw_season = data.get("season")
    year = _normalize_crawl_year(raw_year)
    season = _safe_int(raw_season)
    # 显式校验：避免非法值被静默当成“不过滤”导致“看起来没按年份爬”
    if raw_year not in (None, "", "undefined") and year is None:
        return jsonify({"ok": False, "error": "year 参数无效，请选择年份或区间（如 2016 / 2014-2010）"}), 400
    if raw_season not in (None, "", "undefined") and season is None:
        return jsonify({"ok": False, "error": "season 参数无效，请输入 1/4/7/10"}), 400
    if isinstance(year, int) and (year < 1900 or year > datetime.now().year + 1):
        return jsonify({"ok": False, "error": f"year 超出范围：{year}"}), 400
    if season is not None and season not in (1, 4, 7, 10):
        return jsonify({"ok": False, "error": f"season 仅支持 1/4/7/10，当前为 {season}"}), 400
    pages = int(data.get("pages") or 2)
    page_size = int(data.get("page_size") or 20)
    delay = float(data.get("delay") or 3.0)
    delay = max(2.0, min(10.0, delay))
    u = User.query.get(current_user.id)
    sessdata = (u.bilibili_sessdata or "").strip() if u else ""
    bili_jct = (u.bilibili_bili_jct or "").strip() if u else ""
    app = current_app._get_current_object()
    thread = threading.Thread(
        target=_run_crawl_in_thread,
        args=(app, current_user.id, year, season, pages, page_size, delay, sessdata, bili_jct),
    )
    thread.daemon = True
    thread.start()
    year_text = str(year) if year is not None else "不限"
    season_text = str(season) if season is not None else "不限"
    return jsonify({
        "ok": True,
        "message": f"采集已启动（年份：{year_text}，季度：{season_text}），下方将显示进度",
        "using_bilibili_cookie": bool(sessdata and bili_jct),
        "effective_filters": {"year": year, "season": season},
    }), 202


@api_bp.route("/crawl/status", methods=["GET"])
@login_required
def crawl_status():
    """当前用户最近一次采集进度（供前端轮询）"""
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
