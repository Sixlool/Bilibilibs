# -*- coding: utf-8 -*-
"""
B 站网页端二维码登录：生成二维码、轮询状态、解析 Cookie。
不依赖 bilibili_api 的异步，仅用 requests 调用 B 站公开接口。
"""

import base64
import io
import logging
from typing import Optional, Tuple, Any, Dict
from urllib.parse import parse_qs, urlparse

import requests

logger = logging.getLogger(__name__)

# B 站二维码登录接口（与 bilibili-api-python 一致）
GENERATE_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
POLL_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"

# 状态码：0 成功，86038 过期，86090 已扫未确认，86101 未扫
CODE_SUCCESS = 0
CODE_NOT_SCAN = 86101
CODE_SCANNED = 86090
CODE_EXPIRED = 86038

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com/",
}


def generate_qrcode() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    请求 B 站生成登录二维码。
    Returns:
        (qrcode_key, url, qrcode_image_base64) 成功时均非空；失败时 (None, None, None)。
    """
    try:
        r = requests.get(
            GENERATE_URL,
            params={"source": "main-fe-header"},
            headers=DEFAULT_HEADERS,
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("code") != 0:
            logger.warning("bilibili qrcode generate code=%s", data.get("code"))
            return None, None, None
        inner = data.get("data") or {}
        url = inner.get("url") or ""
        qrcode_key = inner.get("qrcode_key") or ""
        if not url or not qrcode_key:
            return None, None, None

        # 用 qrcode 库生成二维码图片（bilibili-api-python 已依赖 qrcode）
        try:
            import qrcode
            qr = qrcode.QRCode(version=1, box_size=6, border=2)
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)
            b64 = base64.b64encode(buf.read()).decode("ascii")
            return qrcode_key, url, b64
        except Exception as e:
            logger.warning("qrcode image gen fail: %s", e)
            # 无图片也返回 key 和 url，前端可用 url 自行生成
            return qrcode_key, url, None
    except Exception as e:
        logger.exception("bilibili qrcode generate error: %s", e)
        return None, None, None


def poll_qrcode(qrcode_key: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    轮询二维码登录状态。
    Returns:
        (status, cookies_dict)
        status: "scan" | "confirm" | "timeout" | "done"
        cookies_dict: 仅当 status=="done" 时非空。
    只有 B 站明确返回 86038（二维码过期）时才返回 "timeout"，其余异常或未知状态返回 "scan" 避免误提示过期。
    """
    if not qrcode_key:
        return "scan", None
    try:
        r = requests.get(
            POLL_URL,
            params={"qrcode_key": qrcode_key, "source": "main-fe-header"},
            headers={**DEFAULT_HEADERS, "Accept": "application/json"},
            timeout=10,
        )
        if r.status_code != 200:
            logger.debug("bilibili qrcode poll http %s", r.status_code)
            return "scan", None
        try:
            data = r.json()
        except ValueError:
            return "scan", None
        code = data.get("code", -1)
        if isinstance(data.get("data"), dict):
            code = data["data"].get("code", code)

        if code == CODE_SUCCESS:
            # 成功：data 中有 url，query 里带 SESSDATA、bili_jct、DedeUserID 等（可能被编码）
            inner = data.get("data") or {}
            cred_url = inner.get("url") or ""
            if not cred_url:
                return "timeout", None
            parsed = urlparse(cred_url)
            query_str = parsed.query or (parsed.fragment if "#" in cred_url else "")
            if not query_str and "?" in cred_url:
                query_str = cred_url.split("?", 1)[1].split("#")[0]
            if not query_str:
                return "timeout", None
            cookies = {}
            try:
                params = parse_qs(query_str, keep_blank_values=True)
                for k, v_list in params.items():
                    v = (v_list[0] or "").strip() if v_list else ""
                    k_upper = k.upper()
                    if k_upper == "SESSDATA":
                        cookies["sessdata"] = v
                    elif k_upper == "BILI_JCT":
                        cookies["bili_jct"] = v
                    elif k_upper == "DEDEUSERID":
                        try:
                            cookies["bilibili_uid"] = int(v)
                        except (ValueError, TypeError):
                            if v:
                                cookies["bilibili_uid"] = v
            except Exception:
                # 回退：按 & 分割
                for part in query_str.split("&"):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        k = k.strip().upper()
                        v = v.strip()
                        if k == "SESSDATA":
                            cookies["sessdata"] = v
                        elif k == "BILI_JCT":
                            cookies["bili_jct"] = v
                        elif k == "DEDEUSERID":
                            try:
                                cookies["bilibili_uid"] = int(v)
                            except (ValueError, TypeError):
                                if v:
                                    cookies["bilibili_uid"] = v
            if cookies.get("sessdata") and cookies.get("bili_jct"):
                return "done", cookies
            return "scan", None

        if code == CODE_NOT_SCAN:
            return "scan", None
        if code == CODE_SCANNED:
            return "confirm", None
        if code == CODE_EXPIRED:
            return "timeout", None
        return "scan", None
    except Exception as e:
        logger.warning("bilibili qrcode poll error: %s", e)
        return "scan", None
