# -*- coding: utf-8 -*-
"""
数据分析与统计模块
- 基于 Pandas/NumPy：宏观趋势、作品深度分析、榜单生成
"""

from datetime import datetime
from typing import List, Dict, Any, Optional

import pandas as pd
import numpy as np
from flask_sqlalchemy import SQLAlchemy


class AnalysisService:
    """番剧数据分析服务"""

    def __init__(self, db: SQLAlchemy):
        self.db = db

    def _bangumi_df(self, extra_filters: Optional[Dict] = None):
        """将番剧表转为 DataFrame，便于分析"""
        from models.bangumi import BangumiInfo
        from sqlalchemy import text

        q = self.db.session.query(BangumiInfo)
        if extra_filters:
            if extra_filters.get("year"):
                from sqlalchemy import extract
                q = q.filter(extract("year", BangumiInfo.pub_time) == extra_filters["year"])
            if extra_filters.get("season"):
                from sqlalchemy import extract
                months = {1: (1, 2, 3), 4: (4, 5, 6), 7: (7, 8, 9), 10: (10, 11, 12)}
                if extra_filters["season"] in months:
                    q = q.filter(extract("month", BangumiInfo.pub_time).in_(months[extra_filters["season"]]))
        rows = q.all()
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame([{
            "media_id": r.media_id,
            "season_id": r.season_id,
            "title": r.title,
            "pub_time": r.pub_time,
            "score": float(r.score) if r.score is not None else None,
            "score_count": r.score_count or 0,
            "follow_count": r.follow_count or 0,
            "play_count": r.play_count or 0,
            "danmaku_count": r.danmaku_count or 0,
            "coin_count": r.coin_count or 0,
            "fav_count": r.fav_count or 0,
            "series_count": r.series_count or 0,
            "area": r.area or "",
            "season_type": r.season_type or 1,
        } for r in rows])

    def macro_trend(self) -> Dict[str, Any]:
        """宏观：各年度/季度新番产出趋势。pub_time 为空的记录归为「未知」，同步追番等无日期的也会被统计进去"""
        df = self._bangumi_df()
        if df.empty or "pub_time" not in df.columns:
            return {"by_year": [], "by_season": [], "total_in_db": 0, "total_with_date": 0}
        df["pub_time"] = pd.to_datetime(df["pub_time"], errors="coerce")
        has_date = df["pub_time"].notna()
        n_unknown = int((~has_date).sum())

        by_year = []
        by_season = []
        if has_date.any():
            df_dated = df.loc[has_date].copy()
            df_dated["year"] = df_dated["pub_time"].dt.year.astype(int)
            df_dated["month"] = df_dated["pub_time"].dt.month
            def month_to_season(m):
                if m in (1, 2, 3): return 1
                if m in (4, 5, 6): return 4
                if m in (7, 8, 9): return 7
                return 10
            df_dated["season"] = df_dated["month"].map(month_to_season)
            by_year = df_dated.groupby("year").agg(count=("media_id", "count")).reset_index()
            by_year["year"] = by_year["year"].astype(str)
            by_year = by_year.to_dict("records")
            by_season = df_dated.groupby(["year", "season"]).agg(count=("media_id", "count")).reset_index()
            by_season["label"] = by_season["year"].astype(str) + "年" + by_season["season"].map({1: "冬", 4: "春", 7: "夏", 10: "秋"}) + "季"
            by_season = by_season.to_dict("records")

        # 无开播日期的（如仅通过「同步追番」入库的）归为「未知」，在图中显示
        if n_unknown > 0:
            by_year.append({"year": "未知", "count": n_unknown})
            by_season.append({"label": "未知", "count": n_unknown})

        total_in_db = len(df)
        total_with_date = int(has_date.sum())
        return {
            "by_year": by_year,
            "by_season": by_season,
            "total_in_db": total_in_db,
            "total_with_date": total_with_date,
        }

    def tag_distribution(self) -> List[Dict[str, Any]]:
        """标签分布（需番剧-标签关联表有数据）"""
        from models.tag import TagInfo, BangumiTag
        from sqlalchemy import func

        rows = self.db.session.query(TagInfo.tag_name, func.count(BangumiTag.media_id).label("cnt")).join(
            BangumiTag, BangumiTag.tag_id == TagInfo.id
        ).group_by(TagInfo.id, TagInfo.tag_name).order_by(func.count(BangumiTag.media_id).desc()).limit(50).all()
        return [{"name": r.tag_name, "value": r.cnt} for r in rows]

    def tag_distribution_by_media_ids(
        self, media_ids: List[int], limit: int = 20
    ) -> tuple:
        """
        按 media_id 列表统计标签分布（用于「追番的标签分布」等）。
        返回 (标签列表, 有标签的 media_id 数量)，便于前端提示「共 M 部追番中仅 N 部已采集」。
        """
        from models.tag import TagInfo, BangumiTag
        from sqlalchemy import func

        if not media_ids:
            return [], 0
        ids = list(media_ids)[:500]
        rows = (
            self.db.session.query(TagInfo.tag_name, func.count(BangumiTag.media_id).label("cnt"))
            .join(BangumiTag, BangumiTag.tag_id == TagInfo.id)
            .filter(BangumiTag.media_id.in_(ids))
            .group_by(TagInfo.id, TagInfo.tag_name)
            .order_by(func.count(BangumiTag.media_id).desc())
            .limit(limit)
            .all()
        )
        tag_list = [{"name": r.tag_name, "value": r.cnt} for r in rows]
        matched = self.db.session.query(BangumiTag.media_id).filter(BangumiTag.media_id.in_(ids)).distinct().count()
        return tag_list, matched

    def tag_avg_play_rank(self, min_bangumi: int = 3, limit: int = 20) -> List[Dict[str, Any]]:
        """各标签下番剧的平均播放量排行（需至少 min_bangumi 部带该标签，避免样本过小）"""
        from models.bangumi import BangumiInfo
        from models.tag import BangumiTag, TagInfo
        from sqlalchemy import func

        rows = (
            self.db.session.query(
                TagInfo.tag_name.label("name"),
                func.avg(BangumiInfo.play_count).label("avg_play"),
                func.count(BangumiInfo.media_id).label("cnt"),
            )
            .select_from(BangumiTag)
            .join(TagInfo, BangumiTag.tag_id == TagInfo.id)
            .join(BangumiInfo, BangumiInfo.media_id == BangumiTag.media_id)
            .group_by(TagInfo.id, TagInfo.tag_name)
            .having(func.count(BangumiInfo.media_id) >= min_bangumi)
            .order_by(func.avg(BangumiInfo.play_count).desc())
            .limit(limit)
            .all()
        )
        out: List[Dict[str, Any]] = []
        for r in rows:
            ap = r.avg_play
            out.append({
                "name": r.name,
                "avg_play": round(float(ap), 0) if ap is not None else 0.0,
                "count": int(r.cnt or 0),
            })
        return out

    def dashboard_charts(self) -> Dict[str, Any]:
        """大屏扩展图：评分分布、播放-评分散点、地区、标签均播排行、话数分布、开播热力、快照趋势"""
        from models.bangumi import BangumiInfo, BangumiDailySnapshot
        from sqlalchemy import func

        empty = {
            "score_bins": [],
            "scatter": [],
            "area_top": [],
            "tag_avg_play_rank": [],
            "series_bins": [],
            "pub_heatmap": [],
            "pub_heatmap_weekdays": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"],
            "snapshot_lines": [],
            "snapshot_aggregate": [],
        }
        df = self._bangumi_df()
        if df.empty:
            return empty

        # --- 评分分布（含「无评分」；区间左闭右开，末段 9–10 为闭区间）---
        na_score = int(df["score"].isna().sum())
        score_bins = []
        if na_score > 0:
            score_bins.append({
                "label": "无评分",
                "count": na_score,
                "score_min": None,
                "score_max": None,
                "score_lt": None,
                "no_score": True,
            })
        scored = df.loc[df["score"].notna()].copy()
        if not scored.empty:
            bins_spec = [
                ("<6", None, 6.0, None),
                ("6–6.5", 6.0, 6.5, None),
                ("6.5–7", 6.5, 7.0, None),
                ("7–7.5", 7.0, 7.5, None),
                ("7.5–8", 7.5, 8.0, None),
                ("8–8.5", 8.0, 8.5, None),
                ("8.5–9", 8.5, 9.0, None),
                ("9–10", 9.0, None, 10.0),
            ]
            for lab, lo, hi, mx in bins_spec:
                if mx is not None:
                    cnt = int(((scored["score"] >= lo) & (scored["score"] <= mx)).sum())
                    score_bins.append({
                        "label": lab, "count": cnt,
                        "score_min": lo, "score_max": mx, "score_lt": None, "no_score": False,
                    })
                else:
                    cnt = int(((scored["score"] >= lo) & (scored["score"] < hi)).sum()) if lo is not None else int((scored["score"] < hi).sum())
                    row = {"label": lab, "count": cnt, "score_min": lo, "score_max": None, "score_lt": hi, "no_score": False}
                    if lo is None:
                        row["score_min"] = None
                    score_bins.append(row)

        # --- 播放量 vs 评分（抽样，排除播放量为 0 以便对数轴）---
        scat = df.loc[df["score"].notna() & (df["play_count"].fillna(0) > 0)].copy()
        if len(scat) > 450:
            scat = scat.sample(450, random_state=42)
        scatter = []
        for _, r in scat.iterrows():
            scatter.append({
                "media_id": int(r["media_id"]),
                "title": (str(r["title"])[:40] if r.get("title") is not None else ""),
                "play_count": int(r["play_count"] or 0),
                "score": float(r["score"]),
                "score_count": int(r["score_count"] or 0),
            })

        # --- 地区 Top15 ---
        area_s = df["area"].fillna("").replace("", "（未填）")
        ac = area_s.value_counts().head(15)
        area_top = [{"name": str(k), "value": int(v), "filter": "__empty__" if k == "（未填）" else str(k)} for k, v in ac.items()]

        # --- 标签平均播放量 Top（与标签饼图互补：饼图看数量，本图看「带该标签的番」平均热度）---
        tag_avg_play_rank = self.tag_avg_play_rank(min_bangumi=3, limit=20)

        # --- 话数（series_count）分布 ---
        scnt = df["series_count"].fillna(0).astype(int)

        def series_bucket(n: int) -> tuple:
            if n <= 0:
                return ("未知/0", None, None)
            if n <= 12:
                return ("1–12话", 1, 12)
            if n <= 24:
                return ("13–24话", 13, 24)
            if n <= 52:
                return ("25–52话", 25, 52)
            return ("53话以上", 53, None)

        bucket_keys = {}
        for n in scnt:
            lab, smin, smax = series_bucket(int(n))
            bucket_keys.setdefault(lab, {"label": lab, "count": 0, "series_min": smin, "series_max": smax})
            bucket_keys[lab]["count"] += 1
        order_labs = ["未知/0", "1–12话", "13–24话", "25–52话", "53话以上"]
        series_bins = [bucket_keys[k] for k in order_labs if k in bucket_keys]

        # --- 开播时间：月份 × 星期 ---
        pub_heatmap = []
        dtd = pd.to_datetime(df["pub_time"], errors="coerce")
        mask = dtd.notna()
        if mask.any():
            sub = df.loc[mask].copy()
            pt = pd.to_datetime(sub["pub_time"], errors="coerce")
            sub["_m"] = pt.dt.month.astype(int)
            sub["_w"] = pt.dt.dayofweek.astype(int)
            g = sub.groupby(["_w", "_m"]).size().reset_index(name="cnt")
            for _, rr in g.iterrows():
                pub_heatmap.append([int(rr["_w"]), int(rr["_m"]) - 1, int(rr["cnt"])])

        # --- 快照：库内每日快照条数 + 播放量 Top3 的播放曲线 ---
        snap_total = self.db.session.query(func.count(BangumiDailySnapshot.id)).scalar() or 0
        snapshot_lines = []
        snapshot_aggregate = []
        if snap_total > 0:
            agg_rows = (
                self.db.session.query(
                    BangumiDailySnapshot.snapshot_date,
                    func.count(BangumiDailySnapshot.id).label("c"),
                )
                .group_by(BangumiDailySnapshot.snapshot_date)
                .order_by(BangumiDailySnapshot.snapshot_date.asc())
                .all()
            )
            snapshot_aggregate = [{"date": r[0].isoformat(), "count": int(r[1])} for r in agg_rows[-120:]]

            sub_dates = (
                self.db.session.query(BangumiDailySnapshot.snapshot_date)
                .distinct()
                .order_by(BangumiDailySnapshot.snapshot_date.desc())
                .limit(50)
                .all()
            )
            date_list = sorted([t[0] for t in sub_dates]) if sub_dates else []
            if len(date_list) >= 2:
                tops = BangumiInfo.query.order_by(BangumiInfo.play_count.desc()).limit(8).all()
                for info in tops:
                    snaps = (
                        BangumiDailySnapshot.query.filter(
                            BangumiDailySnapshot.media_id == info.media_id,
                            BangumiDailySnapshot.snapshot_date.in_(date_list),
                        )
                        .order_by(BangumiDailySnapshot.snapshot_date.asc())
                        .all()
                    )
                    if len(snaps) < 2:
                        continue
                    snapshot_lines.append({
                        "media_id": info.media_id,
                        "title": (info.title or str(info.media_id))[:28],
                        "points": [[s.snapshot_date.isoformat(), int(s.play_count or 0)] for s in snaps],
                    })
                    if len(snapshot_lines) >= 3:
                        break

        return {
            "score_bins": score_bins,
            "scatter": scatter,
            "area_top": area_top,
            "tag_avg_play_rank": tag_avg_play_rank,
            "series_bins": series_bins,
            "pub_heatmap": pub_heatmap,
            "pub_heatmap_weekdays": empty["pub_heatmap_weekdays"],
            "snapshot_lines": snapshot_lines,
            "snapshot_aggregate": snapshot_aggregate,
        }

    def rank_by(
        self,
        order: str = "play_count",
        limit: int = 20,
        year: Optional[int] = None,
        season: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """榜单：按播放量/追番数/评分等排序"""
        extra = {}
        if year is not None: extra["year"] = year
        if season is not None: extra["season"] = season
        df = self._bangumi_df(extra)
        if df.empty:
            return []
        allowed = ["play_count", "follow_count", "score", "danmaku_count", "fav_count", "coin_count"]
        if order not in allowed:
            order = "play_count"
        df = df.dropna(subset=[order]) if order == "score" else df
        df = df.sort_values(order, ascending=False).head(limit)
        return df.to_dict("records")
