# -*- coding: utf-8 -*-
"""
番剧数据写入与查询服务
- 将 crawler 采集结果写入 MySQL（番剧信息、分集、标签、每日快照）
- 提供基础 CRUD 与列表查询
"""

from datetime import datetime, date
from typing import List, Dict, Any, Optional

from flask_sqlalchemy import SQLAlchemy

# 延迟导入避免循环依赖，在具体方法内 from models import ...
def _get_models(db: SQLAlchemy):
    from models.bangumi import BangumiInfo, BangumiEpisode, BangumiSeason
    from models.tag import TagInfo, BangumiTag
    from models.bangumi import BangumiDailySnapshot
    return BangumiInfo, BangumiEpisode, BangumiSeason, TagInfo, BangumiTag, BangumiDailySnapshot


def save_bangumi_list(db: SQLAlchemy, details: List[Dict[str, Any]], snapshot_date: Optional[date] = None):
    """
    将采集到的番剧详情列表写入/更新数据库。
    - 番剧基本信息存在则更新，否则插入
    - 返回 (新增条数, 更新条数)，便于前端区分“真的多了新番”还是“只更新了已有番”
    """
    BangumiInfo, BangumiEpisode, BangumiSeason, TagInfo, BangumiTag, BangumiDailySnapshot = _get_models(db)
    snapshot_date = snapshot_date or date.today()
    inserted_count = 0
    updated_count = 0

    for d in details:
        media_id = d.get("media_id")
        if not media_id:
            continue
        # 原子 upsert（INSERT ... ON DUPLICATE KEY UPDATE）：
        # 多用户并发同步同一部番剧（追番重叠）时由数据库层处理冲突，
        # 避免「查询→插入」竞态导致的唯一键冲突异常。
        # 先尝试插入，冲突则退化为更新。
        info = BangumiInfo.query.filter_by(media_id=media_id).first()
        if info:
            updated_count += 1
            info.season_id = d.get("season_id") or info.season_id
            info.title = d.get("title") or info.title
            info.cover = d.get("cover") or info.cover
            info.intro = d.get("intro") or info.intro
            info.pub_time = d.get("pub_time")
            info.score = d.get("score")
            info.score_count = d.get("score_count", 0)
            info.follow_count = d.get("follow_count", 0)
            info.play_count = d.get("play_count", 0)
            info.danmaku_count = d.get("danmaku_count", 0)
            info.coin_count = d.get("coin_count", 0)
            info.fav_count = d.get("fav_count", 0)
            info.series_count = d.get("series_count", 0)
            info.area = d.get("area") or info.area
            info.season_type = d.get("season_type", 1)
        else:
            info = BangumiInfo(
                media_id=media_id,
                season_id=d.get("season_id", 0),
                title=d.get("title", ""),
                cover=d.get("cover", ""),
                intro=d.get("intro", ""),
                pub_time=d.get("pub_time"),
                score=d.get("score"),
                score_count=d.get("score_count", 0),
                follow_count=d.get("follow_count", 0),
                play_count=d.get("play_count", 0),
                danmaku_count=d.get("danmaku_count", 0),
                coin_count=d.get("coin_count", 0),
                fav_count=d.get("fav_count", 0),
                series_count=d.get("series_count", 0),
                area=d.get("area", ""),
                season_type=d.get("season_type", 1),
            )
            db.session.add(info)
            inserted_count += 1
        # 并发兜底：flush 遇到唯一键冲突（另一用户刚插入同 media_id）时，
        # 回滚并改走「按现有记录更新」路径，保证不抛异常。
        try:
            db.session.flush()  # 获取 info.id 若需要
        except Exception:
            db.session.rollback()
            info = BangumiInfo.query.filter_by(media_id=media_id).first()
            if info is None:
                raise
            info.season_id = d.get("season_id") or info.season_id
            info.title = d.get("title") or info.title
            info.cover = d.get("cover") or info.cover
            info.intro = d.get("intro") or info.intro
            info.pub_time = d.get("pub_time")
            info.score = d.get("score")
            info.score_count = d.get("score_count", 0)
            info.follow_count = d.get("follow_count", 0)
            info.play_count = d.get("play_count", 0)
            info.danmaku_count = d.get("danmaku_count", 0)
            info.coin_count = d.get("coin_count", 0)
            info.fav_count = d.get("fav_count", 0)
            info.series_count = d.get("series_count", 0)
            info.area = d.get("area") or info.area
            info.season_type = d.get("season_type", 1)
            if inserted_count > 0:
                inserted_count -= 1
            updated_count += 1
            db.session.flush()

        # 分集：删除旧分集再插入（简化）
        BangumiEpisode.query.filter_by(season_id=info.season_id).delete()
        for ep in d.get("episodes") or []:
            ep_row = BangumiEpisode(
                season_id=info.season_id,
                episode_id=ep.get("episode_id", 0),
                index_title=ep.get("index_title", ""),
                long_title=ep.get("long_title", ""),
                duration=ep.get("duration", 0),
                pub_time=ep.get("pub_time"),
            )
            db.session.add(ep_row)

        # 标签：styles 可能是字符串列表
        tag_names = d.get("tags") or []
        if isinstance(tag_names, list):
            for name in tag_names:
                if not name:
                    continue
                tname = name if isinstance(name, str) else (name.get("name") or str(name))
                tag = TagInfo.query.filter_by(tag_name=tname).first()
                if not tag:
                    tag = TagInfo(tag_name=tname)
                    db.session.add(tag)
                    db.session.flush()
                bt = BangumiTag.query.filter_by(media_id=media_id, tag_id=tag.id).first()
                if not bt:
                    db.session.add(BangumiTag(media_id=media_id, tag_id=tag.id))

        # 每日快照
        snap = BangumiDailySnapshot.query.filter_by(
            media_id=media_id, snapshot_date=snapshot_date
        ).first()
        if snap:
            snap.play_count = d.get("play_count", 0)
            snap.follow_count = d.get("follow_count", 0)
            snap.danmaku_count = d.get("danmaku_count", 0)
            snap.coin_count = d.get("coin_count", 0)
            snap.fav_count = d.get("fav_count", 0)
            snap.score = d.get("score")
            snap.score_count = d.get("score_count", 0)
        else:
            db.session.add(BangumiDailySnapshot(
                media_id=media_id,
                snapshot_date=snapshot_date,
                play_count=d.get("play_count", 0),
                follow_count=d.get("follow_count", 0),
                danmaku_count=d.get("danmaku_count", 0),
                coin_count=d.get("coin_count", 0),
                fav_count=d.get("fav_count", 0),
                score=d.get("score"),
                score_count=d.get("score_count", 0),
            ))

    db.session.commit()
    return inserted_count, updated_count


def save_bangumi_list_safe(db: SQLAlchemy, details: List[Dict[str, Any]], snapshot_date: Optional[date] = None, max_retries: int = 3):
    """
    并发安全的写入入口：封装 save_bangumi_list，遇 MySQL 死锁（1213）或
    唯一键冲突（1062，多用户同步重叠追番时发生）自动重试。
    重试间小幅随机退避，降低再次碰撞概率。
    返回 (新增条数, 更新条数)。
    """
    import time as _time
    import random as _random
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            return save_bangumi_list(db, details, snapshot_date)
        except Exception as e:
            # MySQL 死锁 1213 / 锁等待超时 1205 / 唯一键冲突 1062
            msg = str(e)
            is_retryable = (
                "1213" in msg or "Deadlock" in msg
                or "1205" in msg or "Lock wait timeout" in msg
                or "1062" in msg or "Duplicate entry" in msg
            )
            if not is_retryable or attempt >= max_retries:
                raise
            last_exc = e
            try:
                db.session.rollback()
            except Exception:
                pass
            _time.sleep(0.1 + _random.random() * 0.2)
    raise last_exc if last_exc else RuntimeError("save_bangumi_list_safe: 重试耗尽")


class BangumiService:
    """番剧查询与写入封装"""

    def __init__(self, db: SQLAlchemy):
        self.db = db

    def get_list(
        self,
        keyword: Optional[str] = None,
        tags: Optional[List[str]] = None,
        year: Optional[int] = None,
        season: Optional[int] = None,
        score_min: Optional[float] = None,
        score_max: Optional[float] = None,
        score_lt: Optional[float] = None,
        play_min: Optional[int] = None,
        play_max: Optional[int] = None,
        area: Optional[str] = None,
        series_min: Optional[int] = None,
        series_max: Optional[int] = None,
        no_score: bool = False,
        order_by: str = "play_count",
        order_desc: bool = True,
        page: int = 1,
        page_size: int = 20,
    ):
        """分页+多条件筛选"""
        from models.bangumi import BangumiInfo
        from models.tag import BangumiTag, TagInfo

        q = BangumiInfo.query
        if keyword:
            q = q.filter(BangumiInfo.title.contains(keyword))
        if no_score:
            q = q.filter(BangumiInfo.score.is_(None))
        # 仅在有有效年份时按年筛选（避免 0/undefined 导致筛掉全部）
        if year is not None and year > 0:
            from sqlalchemy import extract
            q = q.filter(extract("year", BangumiInfo.pub_time) == year)
        # 仅在有有效季度时按季度筛选
        if season is not None and season in (1, 4, 7, 10):
            months = {1: (1, 2, 3), 4: (4, 5, 6), 7: (7, 8, 9), 10: (10, 11, 12)}
            from sqlalchemy import extract
            q = q.filter(extract("month", BangumiInfo.pub_time).in_(months[season]))
        if not no_score:
            if score_min is not None:
                q = q.filter(BangumiInfo.score >= score_min)
            if score_lt is not None:
                q = q.filter(BangumiInfo.score < score_lt)
            if score_max is not None:
                q = q.filter(BangumiInfo.score <= score_max)
        if area is not None:
            from sqlalchemy import or_
            if area == "__empty__":
                q = q.filter(or_(BangumiInfo.area.is_(None), BangumiInfo.area == ""))
            else:
                q = q.filter(BangumiInfo.area == area)
        if series_min is not None:
            q = q.filter(BangumiInfo.series_count >= series_min)
        if series_max is not None:
            q = q.filter(BangumiInfo.series_count <= series_max)
        if play_min is not None:
            q = q.filter(BangumiInfo.play_count >= play_min)
        if play_max is not None:
            q = q.filter(BangumiInfo.play_count <= play_max)
        if tags:
            from sqlalchemy import func, select
            # 筛选出同时拥有所有指定标签的 media_id（无 relationship 时需显式 join ON）
            sub = (
                select(BangumiTag.media_id)
                .select_from(BangumiTag)
                .join(TagInfo, BangumiTag.tag_id == TagInfo.id)
                .where(TagInfo.tag_name.in_(tags))
                .group_by(BangumiTag.media_id)
                .having(func.count(func.distinct(TagInfo.id)) >= len(tags))
            )
            q = q.filter(BangumiInfo.media_id.in_(sub))

        order_col = getattr(BangumiInfo, order_by, BangumiInfo.play_count)
        if order_desc:
            q = q.order_by(order_col.desc())
        else:
            q = q.order_by(order_col.asc())
        total = q.count()
        items = q.offset((page - 1) * page_size).limit(page_size).all()
        return {"total": total, "items": items, "page": page, "page_size": page_size}

    def get_by_media_id(self, media_id: int):
        """根据 media_id 获取番剧详情（含分集、标签）"""
        from models.bangumi import BangumiInfo, BangumiEpisode
        from models.tag import BangumiTag, TagInfo

        info = BangumiInfo.query.filter_by(media_id=media_id).first()
        if not info:
            return None
        episodes = BangumiEpisode.query.filter_by(season_id=info.season_id).order_by(BangumiEpisode.episode_id).all()
        tag_ids = [r.tag_id for r in BangumiTag.query.filter_by(media_id=media_id).all()]
        tag_names = [t.tag_name for t in TagInfo.query.filter(TagInfo.id.in_(tag_ids)).all()] if tag_ids else []
        return {
            "info": info,
            "episodes": episodes,
            "tags": tag_names,
        }

    def recommend_by_favorite_tags(self, user_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        """
        基于用户已收藏番剧的标签做内容推荐：统计各 tag 在收藏中的出现次数作为权重，
        对未收藏番剧中每个命中标签累加权重，按总分与播放量降序取 Top。
        """
        from sqlalchemy import func

        from models.user import UserFavorite
        from models.bangumi import BangumiInfo
        from models.tag import BangumiTag, TagInfo

        fav_ids = [
            r[0]
            for r in UserFavorite.query.with_entities(UserFavorite.media_id)
            .filter_by(user_id=user_id)
            .all()
        ]
        if not fav_ids:
            return []

        tw_rows = (
            self.db.session.query(BangumiTag.tag_id, func.count())
            .filter(BangumiTag.media_id.in_(fav_ids))
            .group_by(BangumiTag.tag_id)
            .all()
        )
        tag_weight = {int(tid): int(cnt) for tid, cnt in tw_rows}
        if not tag_weight:
            return []

        pairs = (
            self.db.session.query(BangumiTag.media_id, BangumiTag.tag_id)
            .filter(~BangumiTag.media_id.in_(fav_ids), BangumiTag.tag_id.in_(list(tag_weight.keys())))
            .all()
        )
        scores: Dict[int, float] = {}
        overlap: Dict[int, set] = {}
        for mid, tid in pairs:
            w = tag_weight.get(int(tid), 0)
            if w <= 0:
                continue
            mid = int(mid)
            tid = int(tid)
            scores[mid] = scores.get(mid, 0) + w
            overlap.setdefault(mid, set()).add(tid)
        if not scores:
            return []

        mids = [m for m in scores.keys()]
        infos = BangumiInfo.query.filter(BangumiInfo.media_id.in_(mids)).all()
        id2info = {i.media_id: i for i in infos}
        mids = [m for m in mids if m in id2info]

        def sort_key(m: int):
            info = id2info[m]
            pc = info.play_count or 0
            return (-scores[m], -pc)

        cap = max(1, min(int(limit), 100))
        mids_sorted = sorted(mids, key=sort_key)[:cap]

        all_tid = set(tag_weight.keys())
        for s in overlap.values():
            all_tid |= s
        tid_to_name = {t.id: t.tag_name for t in TagInfo.query.filter(TagInfo.id.in_(all_tid)).all()}

        out: List[Dict[str, Any]] = []
        for mid in mids_sorted:
            info = id2info[mid]
            matched = sorted(tid_to_name[i] for i in overlap.get(mid, set()) if i in tid_to_name)
            out.append({
                "info": info,
                "tag_score": int(scores[mid]),
                "matched_tags": matched,
            })
        return out
