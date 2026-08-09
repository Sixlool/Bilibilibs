# -*- coding: utf-8 -*-
"""
番剧数据采集与更新模块
- 基于 bilibili-api-python 的 get_index_info、Bangumi.get_meta/get_stat/get_episode_list
- 支持请求间隔、异常重试；全量/增量更新；数据落库
"""

import asyncio
import time
import logging
import re
from datetime import datetime
from enum import Enum as EnumType
from typing import List, Dict, Any, Optional, Tuple

# 同步执行 bilibili-api 的异步接口
try:
    from bilibili_api.utils.sync import sync as run_async
except ImportError:
    def run_async(coro):
        return asyncio.run(coro)

from bilibili_api import bangumi
from bilibili_api.bangumi import (
    get_index_info,
    Bangumi,
    IndexFilterMeta,
    IndexFilter,
)
try:
    from bilibili_api.exceptions import NetworkException
except ImportError:
    NetworkException = Exception  # 兼容

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 请求间隔（秒），避免触发 B 站风控 412；建议 3~5 秒，被限流后可调大
DEFAULT_DELAY = 3.0
# 触发 412 后等待时长（秒），再继续请求
DELAY_AFTER_412 = 90
MAX_RETRIES = 3


def _delay(seconds: float = DEFAULT_DELAY):
    """请求间隔"""
    time.sleep(seconds)


def _is_412(e: Exception) -> bool:
    """是否因风控返回 412"""
    if getattr(e, "status", None) == 412:
        return True
    return "412" in str(e)


def _parse_pub_time(ts: Any) -> Optional[datetime]:
    """时间戳（秒或毫秒）或日期字符串转 datetime。B 站部分接口返回毫秒需除以 1000。"""
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts
    try:
        if isinstance(ts, str) and len(ts) >= 8:
            # 尝试 "2024-01-01" 或带时间的格式
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d"):
                try:
                    return datetime.strptime(ts.strip()[:19], fmt)
                except ValueError:
                    continue
            return None
        n = int(float(ts))
        # 大于 1e12 视为毫秒
        if n > 1e12:
            n = n // 1000
        return datetime.utcfromtimestamp(n)
    except (TypeError, ValueError, Exception):
        return None


def _normalize_cover(url: Optional[str]) -> str:
    """B 站封面常为 //i0.hdslb.com/...，补全为 https 便于存储与前端显示"""
    if not url or not isinstance(url, str):
        return ""
    u = url.strip()
    if u.startswith("//"):
        return "https:" + u
    return u


def _collect_tags(media: Dict[str, Any], raw: Dict[str, Any]) -> List[str]:
    """从 media/raw 中收集标签（风格），统一为字符串列表，便于入库做标签分布"""
    out = []
    seen = set()

    def add(s: str):
        if not s or not isinstance(s, str):
            return
        t = s.strip()
        if t and t not in seen:
            seen.add(t)
            out.append(t)

    for src in (media.get("styles"), raw.get("styles"), raw.get("label")):
        if not src:
            continue
        if isinstance(src, list):
            for x in src:
                if isinstance(x, str):
                    add(x)
                elif isinstance(x, dict):
                    add(x.get("name") or x.get("title") or "")
        elif isinstance(src, str):
            add(src)
    return out


def _extract_area(media: Dict[str, Any], raw: Dict[str, Any]) -> str:
    """
    地区展示文案：B 站 meta 多为 media.areas=[{id, name}]，未必再有顶层字符串 area；
    collective_info（raw）字段结构类似，做兜底。
    """
    def from_areas_field(val: Any) -> str:
        if val is None:
            return ""
        if isinstance(val, str):
            return val.strip()
        if isinstance(val, list):
            parts: List[str] = []
            for x in val:
                if isinstance(x, dict):
                    n = x.get("name") or x.get("area_name") or ""
                    if n:
                        parts.append(str(n).strip())
                elif isinstance(x, str) and x.strip():
                    parts.append(x.strip())
            return " / ".join(parts) if parts else ""
        return ""

    for block in (media, raw):
        if not isinstance(block, dict):
            continue
        s = from_areas_field(block.get("areas"))
        if s:
            return s
        a = block.get("area")
        if isinstance(a, str) and a.strip():
            return a.strip()
    return ""


def _cover_from_index_item(item: Dict[str, Any]) -> str:
    """
    从索引页单条 item 中提取封面 URL（与 B 站番剧列表页 picture/source 同源）。
    索引接口可能返回 cover / cover_url / pic / season_cover / square_cover 等。
    """
    if not item:
        return ""
    media = item.get("media") if isinstance(item.get("media"), dict) else {}
    for key in ("cover", "cover_url", "pic", "season_cover", "square_cover", "horizontal_cover"):
        val = item.get(key) or (media.get(key) if media else None)
        if val and isinstance(val, str) and val.strip():
            return _normalize_cover(val)
    return ""


def _month_to_season_month(month: int) -> int:
    """自然月映射到季度起始月：1/4/7/10。"""
    if month in (1, 2, 3):
        return 1
    if month in (4, 5, 6):
        return 4
    if month in (7, 8, 9):
        return 7
    return 10


def _year_to_range(year: Any) -> Optional[Tuple[Optional[int], Optional[int]]]:
    """
    将年份筛选转成区间 [start, end) 年份。
    - int: 单年 -> [y, y+1)
    - '2014-2010': 区间 -> [2010, 2015)
    - '2009-2005': 区间 -> [2005, 2010)
    - '2004-2000': 区间 -> [2000, 2005)
    - '90年代': [1990, 2000)
    - '80年代': [1980, 1990)
    - '更早': [None, 1980)
    """
    if year is None or year == "":
        return None
    if isinstance(year, int):
        return int(year), int(year) + 1
    s = str(year).strip()
    if not s:
        return None
    if s.isdigit():
        y = int(s)
        return y, y + 1
    mapping = {
        "2014-2010": (2010, 2015),
        "2009-2005": (2005, 2010),
        "2004-2000": (2000, 2005),
        "90年代": (1990, 2000),
        "80年代": (1980, 1990),
        "更早": (None, 1980),
    }
    if s in mapping:
        return mapping[s]
    if "-" in s:
        try:
            left, right = s.split("-", 1)
            hi = int(left.strip())
            lo = int(right.strip())
            return lo, hi + 1
        except Exception:
            return None
    return None


def _match_year_season(pub_time: Optional[datetime], year: Any, season_month: Optional[int]) -> bool:
    """
    兜底过滤：B 站索引接口偶发忽略 year/season 参数时，按详情开播时间二次过滤。
    只要设置了 year 或 season，且详情无开播时间，则判定为不匹配，避免混入错误年份数据。
    """
    if year is None and season_month is None:
        return True
    if pub_time is None:
        # 详情时间缺失时先放行，后续会按用户筛选条件补默认时间，避免“全被过滤成 0 条”
        return True
    yr = _year_to_range(year)
    if yr is not None:
        start_y, end_y = yr
        if start_y is not None and pub_time.year < start_y:
            return False
        if end_y is not None and pub_time.year >= end_y:
            return False
    if season_month in (1, 4, 7, 10):
        return _month_to_season_month(pub_time.month) == int(season_month)
    return True


def _infer_pub_time_from_index_item(item: Dict[str, Any]) -> Optional[datetime]:
    """
    详情缺少开播时间时，尽量从索引条目中推断，避免误判为不匹配。
    """
    if not isinstance(item, dict):
        return None
    media = item.get("media") if isinstance(item.get("media"), dict) else {}
    for src in (item, media):
        if not isinstance(src, dict):
            continue
        for key in ("pub_time", "pub_date", "release_date"):
            dt = _parse_pub_time(src.get(key))
            if dt is not None:
                return dt
    return None


def _fetch_pub_year_from_bangumi_page(season_id: int) -> Optional[int]:
    """
    访问番剧主页（ss 页面）提取“xxxx年x月x日开播”的年份，作为区间年份采集时的校验兜底。
    """
    if not season_id:
        return None
    try:
        import requests
        url = f"https://www.bilibili.com/bangumi/play/ss{int(season_id)}"
        resp = requests.get(
            url,
            timeout=10,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://www.bilibili.com/",
            },
        )
        if resp.status_code != 200:
            return None
        text = resp.text or ""
        m = re.search(r"(\d{4})年\d{1,2}月\d{1,2}日开播", text)
        if not m:
            return None
        y = int(m.group(1))
        if 1900 <= y <= datetime.now().year + 1:
            return y
    except Exception:
        return None
    return None


def _episode_long_name(ep: Dict[str, Any]) -> str:
    """本篇标题：long_title / longtitle；若无则 show_title / share_copy 解析"""
    for key in ("long_title", "longtitle", "index_title"):
        v = ep.get(key)
        if v is not None and str(v).strip():
            return str(v).strip()
    st = ep.get("show_title")
    if st and str(st).strip():
        st = str(st).strip()
        m = re.match(r"^第\s*\d+\s*话\s*(.+)$", st)
        if m and m.group(1).strip():
            return m.group(1).strip()
        return st
    sc = ep.get("share_copy") or ""
    sc = str(sc).strip()
    if sc:
        m = re.search(r"第\s*\d+\s*话\s*(.+)$", sc)
        if m and m.group(1).strip():
            return m.group(1).strip()
        return sc
    return ""


def _episode_row_from_item(ep: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    eid = ep.get("id")
    if eid is None:
        eid = ep.get("ep_id")
    if eid is None:
        return None
    try:
        eid_int = int(eid)
    except (TypeError, ValueError):
        return None
    idx = str(ep.get("title", "") or ep.get("index", "") or "").strip()
    long_name = _episode_long_name(ep)
    return {
        "episode_id": eid_int,
        "index_title": idx,
        "long_title": long_name,
        "duration": int(ep.get("duration", 0) or 0),
        "pub_time": _parse_pub_time(ep.get("pub_time")),
    }


def _merge_episode_lists(ep_list_res: Any, raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    合并 collective_info 中的 episodes 与 pgc/web/season/section 返回的分区列表，
    同一 ep_id 合并字段，避免某一侧缺少 long_title。
    """
    merged: Dict[int, Dict[str, Any]] = {}
    order: List[int] = []

    def ingest(ep_items: Any) -> None:
        if not isinstance(ep_items, list):
            return
        for ep in ep_items:
            if not isinstance(ep, dict):
                continue
            row = _episode_row_from_item(ep)
            if not row:
                continue
            eid = row["episode_id"]
            if eid not in merged:
                merged[eid] = row
                order.append(eid)
            else:
                cur = merged[eid]
                if not cur.get("long_title") and row.get("long_title"):
                    cur["long_title"] = row["long_title"]
                if not cur.get("index_title") and row.get("index_title"):
                    cur["index_title"] = row["index_title"]

    ingest(raw.get("episodes"))
    if isinstance(ep_list_res, dict):
        main = ep_list_res.get("main_section") or {}
        ingest(main.get("episodes"))
        for sec in ep_list_res.get("section") or []:
            if isinstance(sec, dict):
                ingest(sec.get("episodes"))

    return [merged[eid] for eid in order]


def _fetch_season_section_http(season_id: int) -> Dict[str, Any]:
    """直连官方 season/section JSON，部分环境下 bilibili-api 的 get_episode_list 字段不全时用此兜底"""
    if not season_id:
        return {}
    try:
        import requests
        url = f"https://api.bilibili.com/pgc/web/season/section?season_id={int(season_id)}"
        r = requests.get(
            url,
            timeout=18,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://www.bilibili.com/",
            },
        )
        r.raise_for_status()
        data = r.json()
        if data.get("code") != 0:
            return {}
        res = data.get("result")
        return res if isinstance(res, dict) else {}
    except Exception as e:
        logger.warning("HTTP season/section 兜底失败 season_id=%s: %s", season_id, e)
        return {}


def _fill_episode_long_titles_from_http_section(
    season_id: int, episodes: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """对已合并的分集列表补全缺失的 long_title（与官方接口对齐）"""
    if not episodes:
        return episodes
    need = any(not (e.get("long_title") or "").strip() for e in episodes)
    if not need:
        return episodes
    http_block = _fetch_season_section_http(season_id)
    if not http_block:
        return episodes
    titles: Dict[int, str] = {}

    def collect(ep_items: Any) -> None:
        if not isinstance(ep_items, list):
            return
        for ep in ep_items:
            if not isinstance(ep, dict):
                continue
            row = _episode_row_from_item(ep)
            if not row or not row.get("long_title"):
                continue
            eid = row["episode_id"]
            if eid not in titles:
                titles[eid] = row["long_title"]

    main = http_block.get("main_section") or {}
    collect(main.get("episodes"))
    for sec in http_block.get("section") or []:
        if isinstance(sec, dict):
            collect(sec.get("episodes"))

    for row in episodes:
        if (row.get("long_title") or "").strip():
            continue
        eid = row.get("episode_id")
        if eid is None:
            continue
        try:
            eid_int = int(eid)
        except (TypeError, ValueError):
            continue
        t = titles.get(eid_int)
        if t:
            row["long_title"] = t
    return episodes


async def _fetch_one_bangumi_detail(
    season_id: int,
    media_id: int,
    credential=None,
) -> Optional[Dict[str, Any]]:
    """
    拉取单部番剧的详情：meta + stat + episode_list
    使用 season_id 初始化 Bangumi。若传入 credential（B 站登录态），则用该账号请求以降低 412。
    """
    try:
        b = Bangumi(ssid=season_id, credential=credential)
        # 先调 get_meta()，内部会调 get_media_id() -> __fetch_raw()，从而初始化 __raw
        meta = await b.get_meta()
        stat = await b.get_stat()
        ep_list_res = await b.get_episode_list()
        raw, _ = await b.get_raw()
        raw = raw if isinstance(raw, dict) else {}

        media = meta.get("media", {}) or {}
        # 封面：多接口多字段兜底（与网页列表 picture/source 同源的多在 square_cover/cover）
        cover_src = (
            media.get("cover")
            or raw.get("cover")
            or raw.get("square_cover")
            or raw.get("horizontal_cover")
            or raw.get("season_cover")
            or ""
        )
        stat_map = dict(stat) if isinstance(stat, dict) else {}
        # season/stat 有 views、coins、danmakus；收藏数在 collective_info（get_raw）的 stat.favorites / favorite 中
        if isinstance(raw, dict):
            raw_stat = raw.get("stat")
            if isinstance(raw_stat, dict):
                for _k in ("favorites", "favorite"):
                    if raw_stat.get(_k) is not None:
                        stat_map[_k] = raw_stat[_k]
        rating = (media.get("rating") or {}) if isinstance(media.get("rating"), dict) else {}
        score_val = rating.get("score") or stat_map.get("score")
        score_count_val = rating.get("count") or stat_map.get("score_count", 0)

        episodes = _merge_episode_lists(ep_list_res, raw)
        episodes = _fill_episode_long_titles_from_http_section(season_id, episodes)

        # 开播时间：优先用 release_date（作品首播），避免被 pub_time（站内条目时间）误导
        pub_ts = media.get("pub_time") or raw.get("pub_time")
        if pub_ts is None and isinstance(raw.get("publish"), dict):
            pub_ts = raw["publish"].get("release_date") or raw["publish"].get("pub_time")
        play_count = stat_map.get("view") or stat_map.get("play") or stat_map.get("views") or 0
        follow_count = stat_map.get("follow") or stat_map.get("follow_count") or 0
        # B 站 season/stat 接口字段为 danmakus；旧字段名兜底
        danmaku_count = (
            stat_map.get("danmakus")
            or stat_map.get("danmaku")
            or stat_map.get("danmaku_count")
            or 0
        )
        def _pick_int(d: Dict[str, Any], keys: Tuple[str, ...]) -> int:
            for k in keys:
                if k not in d:
                    continue
                v = d.get(k)
                if v is None:
                    continue
                try:
                    return int(v)
                except (TypeError, ValueError):
                    continue
            return 0

        coin_count = _pick_int(stat_map, ("coins", "coin", "coin_count"))
        fav_count = _pick_int(stat_map, ("favorites", "favorite", "fav", "fav_count"))
        try:
            score_float = float(score_val) if score_val is not None else None
        except (TypeError, ValueError):
            score_float = None
        try:
            score_count_int = int(score_count_val) if score_count_val is not None else 0
        except (TypeError, ValueError):
            score_count_int = 0

        # 标签：media.styles / raw.styles / raw.label 等，统一成字符串列表供入库
        tags = _collect_tags(media, raw)

        # 简介：pgc/review/user 的 meta.media 通常不带 intro；collective_info（raw）里字段名为 evaluate
        intro_raw = media.get("intro") or raw.get("evaluate") or raw.get("summary") or ""

        # 开播时间：media 常为空，用首集播出时间兜底，便于数据大屏按年/季度统计
        pub_time = _parse_pub_time(pub_ts)
        if pub_time is None and episodes:
            for ep in episodes:
                if ep.get("pub_time"):
                    pub_time = ep["pub_time"]
                    break

        return {
            "media_id": media_id or media.get("media_id") or 0,
            "season_id": season_id,
            "title": (media.get("title") or (raw.get("title") if isinstance(raw, dict) else "") or "").strip(),
            "cover": _normalize_cover(cover_src),
            "intro": str(intro_raw).strip(),
            "pub_time": pub_time,
            "area": _extract_area(media, raw),
            "season_type": int(media.get("season_type") or 1),
            "score": score_float,
            "score_count": score_count_int,
            "follow_count": int(follow_count) if follow_count is not None else 0,
            "play_count": int(play_count) if play_count is not None else 0,
            "danmaku_count": int(danmaku_count) if danmaku_count is not None else 0,
            "coin_count": int(coin_count) if coin_count is not None else 0,
            "fav_count": int(fav_count) if fav_count is not None else 0,
            "series_count": len(episodes),
            "episodes": episodes,
            "tags": tags,
        }
    except Exception as e:
        logger.exception("fetch detail fail season_id=%s: %s", season_id, e)
        return None


def _year_to_api_value(year: Any) -> Any:
    """
    B 站索引 API 的 year 参数需要时间范围字符串（如 [2019,2020)），
    直接传整数会被忽略导致返回默认列表。用 make_time_filter 生成。
    """
    if year is None:
        return -1
    try:
        yr = _year_to_range(year)
        if yr is None:
            return -1
        start_y, end_y = yr
        if start_y is None and end_y is None:
            return -1
        return IndexFilter.make_time_filter(start=start_y, end=end_y, include_start=True, include_end=False)
    except (TypeError, ValueError):
        return -1


async def _fetch_index_page(
    year: Optional[int] = None,
    season_month: Optional[int] = None,
    pn: int = 1,
    ps: int = 20,
    credential=None,
) -> Dict[str, Any]:
    """
    拉取一页番剧索引。传入 credential 时用登录态请求，可降低 412。
    year 会转为 API 要求的时间范围字符串，否则按年份筛选不生效。
    """
    year_param = _year_to_api_value(year)
    season_enum = IndexFilter.Season(season_month) if season_month in (1, 4, 7, 10) else IndexFilter.Season.ALL
    filters = IndexFilterMeta.Anime(
        year=year_param,
        season=season_enum,
    )
    sort_mode = IndexFilter.Sort.ASC if (year is not None or season_month in (1, 4, 7, 10)) else IndexFilter.Sort.DESC
    if credential is not None:
        from bilibili_api.utils.utils import get_api
        from bilibili_api.utils.network import Api
        api = get_api("bangumi")["info"]["index"]
        params = {}
        for key, value in filters.__dict__.items():
            if value is not None:
                if isinstance(value, EnumType):
                    params[key] = value.value
                else:
                    params[key] = value
        params["order"] = IndexFilter.Order.ANIME_RELEASE.value
        params["sort"] = sort_mode.value
        params["page"] = pn
        params["pagesize"] = ps
        params["type"] = 1
        return await Api(**api, credential=credential).update_params(**params).result
    return await get_index_info(
        filters=filters,
        order=IndexFilter.Order.ANIME_RELEASE,
        sort=sort_mode,
        pn=pn,
        ps=ps,
    )


def _index_result_to_list(index_res: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从 get_index_info 返回中解析出番剧列表（season_id, media_id 等）"""
    items = []
    # 不同版本 API 可能 result 或 data 或 list
    for key in ("result", "data", "list"):
        raw = index_res.get(key)
        if isinstance(raw, list):
            items = raw
            break
        if isinstance(raw, dict) and "list" in raw:
            items = raw.get("list", [])
            break
        if isinstance(raw, dict) and "data" in raw:
            items = raw.get("data", [])
            break
    if not items and isinstance(index_res.get("result"), dict):
        items = index_res["result"].get("list", index_res["result"].get("data", []))
    return items if isinstance(items, list) else []


class BangumiCollector:
    """
    番剧采集器：索引分页 + 详情拉取 + 写入数据库
    """

    def __init__(
        self,
        delay: float = DEFAULT_DELAY,
        max_retries: int = MAX_RETRIES,
    ):
        self.delay = delay
        self.max_retries = max_retries

    def run_index_and_collect(
        self,
        year: Any = None,
        season_month: Optional[int] = None,
        max_pages: int = 5,
        page_size: int = 20,
        credential=None,
        progress_callback=None,
    ) -> List[Dict[str, Any]]:
        """
        拉取指定年份/季度的番剧索引，并逐条拉取详情（含分集）。
        credential: 可选，B 站登录态。progress_callback: 可选，回调 (current_page, max_pages, items_count, message)。
        """
        if credential:
            logger.info("使用 B 站登录态采集（索引与详情均带当前账号 Cookie）")
        all_details = []
        scan_pages = max_pages
        # 区间年份采集时，缓存每个 season_id 的主页年份，避免重复请求页面
        page_year_cache: Dict[int, Optional[int]] = {}
        if progress_callback:
            progress_callback(0, scan_pages, 0, "正在拉取索引…")

        for pn in range(1, scan_pages + 1):
            _delay(self.delay)
            if progress_callback:
                progress_callback(pn - 1, scan_pages, len(all_details), f"正在拉取第 {pn}/{scan_pages} 页索引…")
            try:
                index_res = run_async(
                    _fetch_index_page(year=year, season_month=season_month, pn=pn, ps=page_size, credential=credential)
                )
            except Exception as e:
                if _is_412(e):
                    logger.warning("索引页触发风控 412，等待 %s 秒后重试本页...", DELAY_AFTER_412)
                    _delay(DELAY_AFTER_412)
                    try:
                        index_res = run_async(
                            _fetch_index_page(year=year, season_month=season_month, pn=pn, ps=page_size, credential=credential)
                        )
                    except Exception as e2:
                        logger.warning("index page pn=%s 重试仍失败: %s", pn, e2)
                        continue
                else:
                    logger.warning("index page pn=%s fail: %s", pn, e)
                    continue

            items = _index_result_to_list(index_res)
            if not items:
                if progress_callback:
                    progress_callback(scan_pages, scan_pages, len(all_details), f"本页无数据，结束。共 {len(all_details)} 条")
                break
            if progress_callback:
                progress_callback(pn, scan_pages, len(all_details), f"第 {pn}/{scan_pages} 页，本页约 {len(items)} 条，拉取详情中…")

            for item in items:
                season_id = item.get("season_id") or item.get("ssid")
                media_id = item.get("media_id")
                if not season_id:
                    # 部分接口只给 media_id
                    media_id = media_id or item.get("media", {}).get("media_id") if isinstance(item.get("media"), dict) else None
                    if not media_id:
                        continue
                    b = Bangumi(media_id=media_id, credential=credential)
                    try:
                        season_id = run_async(b.get_season_id())
                    except Exception:
                        continue
                else:
                    media_id = media_id or item.get("media_id")

                if not media_id:
                    media_id = run_async(Bangumi(ssid=season_id, credential=credential).get_media_id()) if season_id else None

                _delay(self.delay)
                for attempt in range(self.max_retries):
                    try:
                        detail = run_async(_fetch_one_bangumi_detail(season_id, media_id or 0, credential))
                        if detail:
                            # 详情可能不给 pub_time，先尝试用索引条目推断，再做年份/季度过滤
                            if detail.get("pub_time") is None:
                                detail["pub_time"] = _infer_pub_time_from_index_item(item)
                            detail["media_id"] = detail.get("media_id") or media_id
                            # 优先用索引条目的封面（与网页列表 picture/source 同源），没有再用详情接口的
                            cover_from_item = _cover_from_index_item(item)
                            if (cover_from_item or "").strip():
                                detail["cover"] = cover_from_item
                            elif not (detail.get("cover") or "").strip():
                                pass  # 保持空，前端会显示占位
                            # 仅“单年”筛选时才补默认时间；区间筛选不补，避免把 2009-2005 全归到 2005
                            if detail.get("pub_time") is None and (year is not None or season_month is not None):
                                y = None
                                if isinstance(year, int):
                                    y = year
                                elif isinstance(year, str) and year.strip().isdigit():
                                    y = int(year.strip())
                                if y is not None:
                                    m = int(season_month) if season_month in (1, 4, 7, 10) else 1
                                    detail["pub_time"] = datetime(y, m, 1, 0, 0, 0)
                            # 详情无标签时用索引条目的 styles/label 补全，便于「标签分布」图有数据
                            if not (detail.get("tags") or []):
                                item_media = item.get("media") if isinstance(item.get("media"), dict) else {}
                                detail["tags"] = _collect_tags(item_media, item)
                            # 只要设置了年份筛选（单年或区间），都用番剧主页开播年做一次校验纠偏
                            if year is not None:
                                sid = int(season_id) if season_id else 0
                                if sid:
                                    if sid not in page_year_cache:
                                        page_year_cache[sid] = _fetch_pub_year_from_bangumi_page(sid)
                                    page_year = page_year_cache.get(sid)
                                    if page_year is not None:
                                        pt = detail.get("pub_time")
                                        if pt is None:
                                            detail["pub_time"] = datetime(page_year, 1, 1, 0, 0, 0)
                                        elif pt.year != page_year:
                                            detail["pub_time"] = datetime(
                                                page_year, pt.month, pt.day, pt.hour, pt.minute, pt.second
                                            )
                            # 用户要求：年份筛选仅用于抓取范围，不做硬过滤；
                            # 入库年份以 B 站详情页校正后的 pub_time 为准。
                            keep_item = True
                            if season_month in (1, 4, 7, 10):
                                keep_item = _match_year_season(detail.get("pub_time"), None, season_month)
                            if keep_item:
                                all_details.append(detail)
                        break
                    except Exception as e:
                        if _is_412(e):
                            wait_sec = DELAY_AFTER_412
                            logger.warning("详情请求触发风控 412，等待 %s 秒后%s...", wait_sec,
                                          "重试" if attempt < self.max_retries - 1 else "跳过")
                            _delay(wait_sec)
                            if attempt == self.max_retries - 1:
                                break
                        else:
                            logger.warning("retry detail season_id=%s: %s", season_id, e)
                            _delay(self.delay)

            if progress_callback:
                progress_callback(pn, scan_pages, len(all_details), f"第 {pn}/{scan_pages} 页完成，已采集 {len(all_details)} 条")

        if progress_callback:
            progress_callback(scan_pages, scan_pages, len(all_details), f"采集完成，共 {len(all_details)} 条")
        return all_details


def run_sync_subscribed(
    credential,
    bilibili_uid: int,
    progress_callback=None,
    delay: float = 6.0,
    max_pages: int = 50,
) -> List[Dict[str, Any]]:
    """
    拉取当前 B 站账号的追番列表，逐条拉取详情并返回（用于写入本地 DB，便于追番标签分布等图表更全）。
    credential 为 None 时仅拉列表不拉详情（会少很多字段），建议传入登录态。
    """
    from bilibili_api.user import User as BiliUser
    from bilibili_api.user import BangumiType, BangumiFollowStatus

    all_details = []
    ps = 30
    pn = 1
    total_fetched = 0
    if progress_callback:
        progress_callback(0, 1, 0, "正在拉取追番列表…")
    while pn <= max_pages:
        _delay(delay)
        try:
            bili_user = BiliUser(uid=int(bilibili_uid), credential=credential or None)
            res = run_async(
                bili_user.get_subscribed_bangumi(
                    type_=BangumiType.BANGUMI,
                    follow_status=BangumiFollowStatus.ALL,
                    pn=pn,
                    ps=ps,
                )
            )
        except Exception as e:
            logger.warning("拉取追番列表 pn=%s 失败: %s", pn, e)
            break
        if not res or not isinstance(res, dict):
            break
        data = res.get("data") or res.get("result") or res
        lst = data.get("list") if isinstance(data, dict) else []
        if not lst:
            break
        if progress_callback:
            progress_callback(pn, pn + 1, total_fetched, f"追番列表第 {pn} 页共 {len(lst)} 条，正在拉取详情…")
        for item in lst:
            if not isinstance(item, dict):
                continue
            season_id = item.get("season_id") or item.get("ssid")
            media_id = item.get("media_id")
            if not season_id and not media_id:
                continue
            if not media_id:
                media_id = item.get("media_id") or (item.get("media") or {}).get("media_id") if isinstance(item.get("media"), dict) else None
            if not season_id and media_id:
                try:
                    b = Bangumi(media_id=media_id, credential=credential)
                    season_id = run_async(b.get_season_id())
                except Exception:
                    continue
            if not media_id and season_id:
                try:
                    media_id = run_async(Bangumi(ssid=season_id, credential=credential).get_media_id())
                except Exception:
                    pass
            _delay(delay)
            for attempt in range(MAX_RETRIES):
                try:
                    detail = run_async(_fetch_one_bangumi_detail(season_id, media_id or 0, credential))
                    if detail:
                        detail["media_id"] = detail.get("media_id") or media_id
                        cover_from_item = (item.get("cover") or item.get("square_cover") or "").strip()
                        if cover_from_item.startswith("//"):
                            cover_from_item = "https:" + cover_from_item
                        if not (detail.get("cover") or "").strip() and cover_from_item:
                            detail["cover"] = cover_from_item
                        if not (detail.get("tags") or []):
                            item_media = item.get("media") if isinstance(item.get("media"), dict) else {}
                            detail["tags"] = _collect_tags(item_media, item)
                        # 详情无开播时间时，从追番列表项里取（便于数据大屏按年/季度显示）
                        if detail.get("pub_time") is None:
                            item_ts = (item.get("media") or {}).get("pub_time") if isinstance(item.get("media"), dict) else None
                            if item_ts is None:
                                item_ts = item.get("pub_time")
                            if item_ts is not None:
                                detail["pub_time"] = _parse_pub_time(item_ts)
                        all_details.append(detail)
                        total_fetched += 1
                        if progress_callback:
                            progress_callback(pn, pn + 1, total_fetched, f"已同步 {total_fetched} 部追番…")
                    break
                except Exception as e:
                    if _is_412(e):
                        _delay(DELAY_AFTER_412)
                    if attempt == MAX_RETRIES - 1:
                        logger.warning("追番详情 season_id=%s 拉取失败: %s", season_id, e)
                    else:
                        _delay(delay)
        if len(lst) < ps:
            break
        pn += 1
    if progress_callback:
        progress_callback(pn, pn, total_fetched, f"追番同步完成，共 {len(all_details)} 条")
    return all_details
