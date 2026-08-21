/**
 * B站番剧数据分析系统 - 前端逻辑
 * 番剧列表、详情、数据大屏、用户登录与收藏
 */

const API_BASE = "/api";
const AUTH_BASE = "/auth";

/**
 * 获取或复用 ECharts 实例：已有实例直接返回（不重建），首次调用才 init。
 * 大幅提升重复进入页面/图表时的加载速度（避免每次 dispose→init 的 300ms+ 开销）。
 */
function ensureChart(el, theme) {
  if (!el) return null;
  let inst = echarts.getInstanceByDom(el);
  if (!inst) inst = echarts.init(el, theme || null);
  return inst;
}

/** 浅色图表主题：打印（含黑白）时对比更清晰 */
const CHART_THEME = {
  bg: "#ffffff",
  text: "#1f2937",
  muted: "#374151",
  axisLine: "#9ca3af",
  splitLine: "#e5e7eb",
  palette: ["#0284c7", "#b45309", "#15803d", "#7c3aed", "#be123c", "#0f766e", "#c2410c", "#525252", "#0369a1", "#a16207"],
};

function chartTooltipLight() {
  return {
    backgroundColor: "#ffffff",
    borderColor: "#e5e7eb",
    borderWidth: 1,
    textStyle: { color: "#1f2937" },
  };
}

// ---------- 路由 ----------
/** 顶栏导航高亮：detail 视为列表下的子页，仍高亮「番剧列表」 */
function updateNavActive(pageId) {
  const navRoot = document.querySelector(".nav-tabs");
  if (!navRoot) return;
  const tabKey = pageId === "detail" ? "home" : pageId;
  navRoot.querySelectorAll("a[data-page]").forEach(a => {
    const on = a.dataset.page === tabKey;
    a.classList.toggle("active", on);
    if (on) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
}

function showPage(pageId) {
  document.querySelectorAll(".page").forEach(el => el.classList.remove("active"));
  const el = document.getElementById("page-" + pageId);
  if (el) el.classList.add("active");
  updateNavActive(pageId);
  if (pageId === "home") loadList();
  if (pageId === "dashboard") loadDashboard();
  if (pageId === "subscribed") loadSubscribedPage();
  if (pageId === "user") loadUserPage();
  if (pageId === "admin") loadAdminPage();
}

// 顶部导航与详情页「返回列表」等所有带 data-page 的链接统一处理
document.querySelectorAll("a[data-page]").forEach(a => {
  a.addEventListener("click", e => {
    e.preventDefault();
    showPage(a.dataset.page);
  });
});

// ---------- 番剧列表 ----------
let currentPage = 1;
let pageSize = 20;
let totalCount = 0;

function getListParams() {
  return {
    keyword: document.getElementById("search-keyword").value.trim() || "",
    year: document.getElementById("search-year").value.trim() || "",
    season: document.getElementById("search-season").value || "",
    order_by: document.getElementById("search-order").value || "play_count",
    order_desc: "true",
    page: currentPage,
    page_size: pageSize,
  };
}

// 只把“有值”的筛选条件传给接口，默认不传 year/season/keyword，这样先显示全部再筛选
function buildListQueryString() {
  const raw = getListParams();
  const params = new URLSearchParams();
  params.set("page", raw.page);
  params.set("page_size", raw.page_size);
  params.set("order_by", raw.order_by);
  params.set("order_desc", raw.order_desc);
  if (raw.keyword) params.set("keyword", raw.keyword);
  if (raw.year) params.set("year", raw.year);
  if (raw.season) params.set("season", raw.season);
  const tagEl = document.getElementById("search-tags");
  if (tagEl && tagEl.value.trim()) params.set("tags", tagEl.value.trim());
  const ns = document.getElementById("search-no-score");
  if (ns && ns.value === "1") params.set("no_score", "1");
  const smin = document.getElementById("search-score-min");
  const smax = document.getElementById("search-score-max");
  const slt = document.getElementById("search-score-lt");
  if (smin && smin.value.trim()) params.set("score_min", smin.value.trim());
  if (smax && smax.value.trim()) params.set("score_max", smax.value.trim());
  if (slt && slt.value.trim()) params.set("score_lt", slt.value.trim());
  const pmin = document.getElementById("search-play-min");
  const pmax = document.getElementById("search-play-max");
  if (pmin && pmin.value.trim()) params.set("play_min", pmin.value.trim());
  if (pmax && pmax.value.trim()) params.set("play_max", pmax.value.trim());
  const ar = document.getElementById("search-area");
  if (ar && ar.value.trim()) params.set("area", ar.value.trim());
  const serMin = document.getElementById("search-series-min");
  const serMax = document.getElementById("search-series-max");
  if (serMin && serMin.value.trim()) params.set("series_min", serMin.value.trim());
  if (serMax && serMax.value.trim()) params.set("series_max", serMax.value.trim());
  return params.toString();
}

function renderList(items) {
  const container = document.getElementById("list-result");
  if (!items.length) {
    container.innerHTML =
      "<p style='color:#1f2937'>暂无数据，请先运行采集脚本或放宽筛选条件。</p>" +
      "<p style='color:#1f2937;font-size:12px;margin-top:8px'>若已采集过：请确认 run.py 与 run_crawler.py 使用同一 MySQL（config 里数据库名 bilibili_bangumi）。可在 MySQL 中执行 SELECT COUNT(*) FROM bangumi_info; 查看是否有记录。</p>";
    return;
  }
  container.innerHTML = items.map(item => {
    const fav = !!item.favorited;
    const favBtn = window.currentUser
      ? `<button type="button" class="btn-fav ${fav ? 'favorited' : ''}" data-media-id="${item.media_id}" data-favorited="${fav}">${fav ? "已收藏" : "收藏"}</button>`
      : "";
    return `
    <div class="card" data-media-id="${item.media_id}" style="cursor:pointer">
      <img src="${normalizeCoverUrl(item.cover) || ''}" alt="${escapeHtml(item.title)}" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><rect fill=%22%23e5e7eb%22 width=%22100%22 height=%22100%22/><text x=%2250%22 y=%2255%22 fill=%22%23374151%22 text-anchor=%22middle%22>无图</text></svg>'">
      <div class="card-body">
        <div class="card-text">
          <div class="card-title">${escapeHtml(item.title)}</div>
          <div class="card-meta">播放 ${formatNum(item.play_count)} · 评 ${item.score != null ? item.score : '-'}</div>
        </div>
        ${favBtn}
      </div>
    </div>
  `;
  }).join("");
  container.querySelectorAll(".card").forEach(card => {
    card.addEventListener("click", (e) => {
      if (e.target.closest(".btn-fav")) return;
      openDetail(parseInt(card.dataset.mediaId, 10));
    });
  });
  container.querySelectorAll(".card-body .btn-fav").forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      const mediaId = parseInt(btn.dataset.mediaId, 10);
      const favorited = btn.dataset.favorited === "true";
      toggleFavorite(mediaId, favorited, btn);
      btn.dataset.favorited = favorited ? "false" : "true";
      btn.textContent = favorited ? "收藏" : "已收藏";
      btn.classList.toggle("favorited", !favorited);
    });
  });
}

function renderPagination() {
  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));
  const div = document.getElementById("pagination");
  div.innerHTML = `
    <button ${currentPage <= 1 ? "disabled" : ""} data-page="${currentPage - 1}">上一页</button>
    <span style="align-self:center">第 ${currentPage} / ${totalPages} 页，共 ${totalCount} 条</span>
    <button ${currentPage >= totalPages ? "disabled" : ""} data-page="${currentPage + 1}">下一页</button>
  `;
  div.querySelectorAll("button[data-page]").forEach(btn => {
    btn.addEventListener("click", () => {
      currentPage = parseInt(btn.dataset.page, 10);
      loadList();
    });
  });
}

function loadList() {
  const query = buildListQueryString();
  fetch(`${API_BASE}/bangumi?${query}`)
    .then(r => r.json())
    .then(res => {
      if (!res.ok) throw new Error(res.error || "请求失败");
      totalCount = res.total;
      renderList(res.items || []);
      renderPagination();
    })
    .catch(err => {
      document.getElementById("list-result").innerHTML =
        "<p class='error'>" + escapeHtml(err.message) + "</p>" +
        "<p style='color:#1f2937;font-size:12px;margin-top:8px'>请确认服务已启动且与采集时使用同一 MySQL 数据库（数据库名见 .env 配置）。</p>";
    });
}

function clearDashboardDrivenFilters() {
  const st = document.getElementById("search-tags");
  if (st) st.value = "";
  ["search-score-min", "search-score-max", "search-score-lt", "search-play-min", "search-play-max", "search-area", "search-series-min", "search-series-max", "search-no-score"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.value = "";
  });
}

document.getElementById("btn-search").addEventListener("click", () => {
  clearDashboardDrivenFilters();
  currentPage = 1;
  loadList();
});

/** 数据大屏图表联动：列表筛选（年/季/标签/评分区间/地区/话数等） */
function applyDashboardLinkToList(opts) {
  const o = opts || {};
  clearDashboardDrivenFilters();
  document.getElementById("search-keyword").value = "";
  document.getElementById("search-year").value = o.year != null && o.year !== "" ? String(o.year) : "";
  document.getElementById("search-season").value = o.season != null && o.season !== "" ? String(o.season) : "";
  const st = document.getElementById("search-tags");
  if (st && o.tags != null && String(o.tags).trim()) st.value = String(o.tags).trim();
  const setH = (id, v) => {
    const el = document.getElementById(id);
    if (!el || v === undefined || v === null || v === "") return;
    el.value = String(v);
  };
  setH("search-score-min", o.scoreMin);
  setH("search-score-max", o.scoreMax);
  setH("search-score-lt", o.scoreLt);
  setH("search-play-min", o.playMin);
  setH("search-play-max", o.playMax);
  setH("search-area", o.area);
  setH("search-series-min", o.seriesMin);
  setH("search-series-max", o.seriesMax);
  if (o.noScore) {
    const ns = document.getElementById("search-no-score");
    if (ns) ns.value = "1";
  }
  currentPage = 1;
  showPage("home");
  loadList();
}

// ---------- 番剧详情 ----------
function openDetail(mediaId) {
  showPage("detail");
  const content = document.getElementById("detail-content");
  content.innerHTML = "<p>加载中...</p>";
  fetch(`${API_BASE}/bangumi/${mediaId}`, { credentials: "include" })
    .then(r => r.json())
    .then(res => {
      if (!res.ok) throw new Error(res.error || "加载失败");
      const d = res.data;
      const introSnippet = (d.intro || "").trim().slice(0, 500);
      const introHtml = introSnippet
        ? escapeHtml(introSnippet)
        : '<span class="muted">暂无简介，请在个人中心「爬取数据」重新采集该番详情后刷新。</span>';
      const biliUrl = (d.media_id ? `https://www.bilibili.com/bangumi/media/md${d.media_id}` : (d.season_id ? `https://www.bilibili.com/bangumi/play/ss${d.season_id}` : ""));
      content.innerHTML = `
        <div class="detail-poster">
          <img src="${normalizeCoverUrl(d.cover) || ''}" alt="${escapeHtml(d.title)}" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><rect fill=%22%23e5e7eb%22 width=%22100%22 height=%22100%22/><text x=%2250%22 y=%2255%22 fill=%22%23374151%22 text-anchor=%22middle%22>无图</text></svg>'">
          <div style="margin-top:12px;display:flex;flex-wrap:wrap;gap:10px;align-items:center">
            ${window.currentUser ? `<button id="btn-fav" style="padding:8px 16px;cursor:pointer;background:${d.favorited ? '#e5e7eb' : '#0284c7'};color:${d.favorited ? '#1f2937' : '#fff'};border:none;border-radius:6px">${d.favorited ? '已收藏' : '收藏'}</button>` : ""}
            ${biliUrl ? `<a href="${biliUrl}" target="_blank" rel="noopener noreferrer" style="padding:8px 16px;background:#0284c7;color:#fff;border-radius:6px;text-decoration:none;font-size:14px">在 B 站打开</a>` : ""}
          </div>
        </div>
        <div class="detail-info">
          <h2>${escapeHtml(d.title)}</h2>
          <p>简介：${introHtml}</p>
          <p>播放 ${formatNum(d.play_count)} · 追番 ${formatNum(d.follow_count)} · 弹幕 ${formatNum(d.danmaku_count)} · 评分 ${d.score != null ? d.score : '-'}（${d.score_count}人）</p>
          <p>地区：${escapeHtml(d.area || '-')} · 集数：${d.series_count || '-'}</p>
          <div class="detail-tags">${(d.tags || []).map(t => `<span class="tag">${escapeHtml(t)}</span>`).join("")}</div>
          <h4 style="margin-top:20px">分集</h4>
          <ul style="list-style:none;max-height:200px;overflow:auto">
            ${(d.episodes || []).map(ep => {
              const num = String(ep.index_title || "").trim();
              const sub = String(ep.long_title || "").trim();
              let line;
              if (sub && num && /^\d+$/.test(num)) line = `第${num}话 · ${sub}`;
              else if (sub && num) line = `${num} · ${sub}`;
              else if (sub) line = sub;
              else if (num) line = num;
              else line = "第" + ep.episode_id + "集";
              return `<li style="padding:4px 0">${escapeHtml(line)}</li>`;
            }).join("")}
          </ul>
        </div>
      `;
      const btnFav = document.getElementById("btn-fav");
      if (btnFav) {
        btnFav.dataset.favorited = d.favorited ? "true" : "false";
        btnFav.addEventListener("click", () => {
          const favorited = btnFav.dataset.favorited === "true";
          toggleFavorite(mediaId, favorited, btnFav);
        });
      }
    })
    .catch(err => { content.innerHTML = "<p class='error'>" + escapeHtml(err.message) + "</p>"; });
}

function toggleFavorite(mediaId, currentFavorited, btn) {
  const method = currentFavorited ? "DELETE" : "POST";
  if (btn && btn.isConnected) btn.disabled = true;
  return fetch(`${API_BASE}/favorite/${mediaId}`, { method, credentials: "include" })
    .then(r => r.json())
    .then(res => {
      if (!res || !res.ok) return res;
      const nowFavorited = method === "POST";
      if (btn && btn.isConnected) {
        btn.textContent = nowFavorited ? "已收藏" : "收藏";
        btn.dataset.favorited = nowFavorited ? "true" : "false";
        if (btn.classList.contains("btn-fav")) {
          btn.classList.toggle("favorited", nowFavorited);
          /* 列表卡片样式由 CSS 的 .btn-fav / .favorited 决定；勿留内联色，否则取消收藏会变成详情页那种蓝底 */
          btn.style.removeProperty("background");
          btn.style.removeProperty("color");
          btn.style.removeProperty("border");
          btn.style.removeProperty("border-color");
        } else {
          btn.style.background = nowFavorited ? "#e5e7eb" : "#0284c7";
          btn.style.color = nowFavorited ? "#1f2937" : "#fff";
        }
      }
      return res;
    })
    .catch(() => ({ ok: false }))
    .finally(() => {
      if (btn && btn.isConnected) btn.disabled = false;
    });
}

// ---------- 数据大屏 ----------
const DASHBOARD_EXTRA_CHART_IDS = [
  "chart-score-hist", "chart-play-score-scatter", "chart-area-top",
  "chart-engagement-radar", "chart-series-hist", "chart-pub-heatmap", "chart-snapshot-trend",
];

function renderDashboardExtraCharts(ex) {
  const exData = ex || {};
  // 复用已有实例（不 dispose 重建），提升重复进入速度

  const scoreBins = exData.score_bins || [];
  const scatter = exData.scatter || [];
  const areaTop = exData.area_top || [];
  const tagAvgPlayRank = exData.tag_avg_play_rank || [];
  const seriesBins = exData.series_bins || [];
  const pubHeat = exData.pub_heatmap || [];
  const weekdays = exData.pub_heatmap_weekdays || ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];
  const snapLines = exData.snapshot_lines || [];
  const snapAgg = exData.snapshot_aggregate || [];
  const months = ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"];

  const elScore = document.getElementById("chart-score-hist");
  if (elScore) {
    const ch = ensureChart(elScore);
    ch.setOption({
      backgroundColor: CHART_THEME.bg,
      textStyle: { color: CHART_THEME.text },
      tooltip: chartTooltipLight(),
      grid: { left: 44, right: 12, top: 28, bottom: 40, containLabel: true },
      xAxis: {
        type: "category",
        data: scoreBins.map(b => b.label),
        axisLabel: { rotate: 0, color: CHART_THEME.muted, fontSize: 10, margin: 8 },
        axisLine: { lineStyle: { color: CHART_THEME.axisLine } },
      },
      yAxis: {
        type: "value",
        name: "部数",
        nameLocation: "middle",
        nameGap: 36,
        nameTextStyle: { color: CHART_THEME.muted },
        axisLabel: { color: CHART_THEME.muted, margin: 6 },
        splitLine: { lineStyle: { color: CHART_THEME.splitLine } },
      },
      series: [{ type: "bar", data: scoreBins.map(b => b.count), itemStyle: { color: CHART_THEME.palette[1] } }],
      title: scoreBins.length === 0 ? { text: "暂无数据", left: "center", top: "center", textStyle: { color: CHART_THEME.muted } } : { show: false },
    });
    ch.off("click");
    ch.on("click", (params) => {
      if (params.componentType !== "series" || params.dataIndex == null) return;
      const b = scoreBins[params.dataIndex];
      if (!b || !b.count) return;
      if (b.no_score) {
        applyDashboardLinkToList({ noScore: true });
        return;
      }
      applyDashboardLinkToList({
        scoreMin: b.score_min != null ? b.score_min : undefined,
        scoreMax: b.score_max != null ? b.score_max : undefined,
        scoreLt: b.score_lt != null ? b.score_lt : undefined,
      });
    });
    setTimeout(() => ch.resize(), 100);
  }

  const elScat = document.getElementById("chart-play-score-scatter");
  if (elScat) {
    const ch = ensureChart(elScat);
    const pts = scatter.map(s => ({
      value: [s.play_count, s.score, s.score_count || 0],
      name: s.title || "",
    }));
    ch.setOption({
      backgroundColor: CHART_THEME.bg,
      textStyle: { color: CHART_THEME.text },
      tooltip: {
        ...chartTooltipLight(),
        formatter: (p) => {
          const idx = p.dataIndex;
          const s = scatter[idx];
          if (!s) return "";
          return `${escapeHtml(s.title || "")}<br/>播放 ${formatNum(s.play_count)} · 评分 ${s.score != null ? s.score : "-"} · 评分人数 ${formatNum(s.score_count || 0)}`;
        },
      },
      grid: { left: 56, right: 18, top: 32, bottom: 40, containLabel: true },
      xAxis: {
        type: "log",
        name: "播放量",
        min: 1,
        nameLocation: "middle",
        nameGap: 26,
        nameTextStyle: { color: CHART_THEME.muted, fontSize: 11 },
        axisLabel: {
          color: CHART_THEME.muted,
          margin: 8,
          formatter: (v) => {
            const n = Number(v);
            if (Number.isNaN(n)) return String(v);
            if (n >= 1e8) return (n / 1e8).toFixed(1) + "亿";
            if (n >= 1e4) return (n / 1e4).toFixed(0) + "万";
            return String(n);
          },
        },
        axisLine: { lineStyle: { color: CHART_THEME.axisLine } },
        splitLine: { lineStyle: { color: CHART_THEME.splitLine } },
      },
      yAxis: {
        type: "value",
        name: "评分",
        min: 4,
        max: 10,
        nameLocation: "middle",
        nameGap: 40,
        nameTextStyle: { color: CHART_THEME.muted, fontSize: 11 },
        axisLabel: { color: CHART_THEME.muted, margin: 6 },
        axisLine: { lineStyle: { color: CHART_THEME.axisLine } },
        splitLine: { lineStyle: { color: CHART_THEME.splitLine } },
      },
      series: [{
        type: "scatter",
        data: pts,
        symbolSize: (raw) => {
          const v = raw && raw.value ? raw.value[2] : 0;
          const sc = Math.log10(1 + Number(v));
          return Math.min(22, 5 + sc * 6);
        },
        itemStyle: { color: CHART_THEME.palette[0], opacity: 0.78 },
      }],
      title: scatter.length === 0 ? { text: "暂无有效散点数据", left: "center", top: "center", textStyle: { color: CHART_THEME.muted, fontSize: 12 } } : { show: false },
    });
    ch.off("click");
    ch.on("click", (params) => {
      if (params.seriesType !== "scatter" || params.dataIndex == null) return;
      const s = scatter[params.dataIndex];
      if (s && s.media_id != null) openDetail(s.media_id);
    });
    setTimeout(() => ch.resize(), 100);
  }

  const elArea = document.getElementById("chart-area-top");
  if (elArea) {
    const ch = ensureChart(elArea);
    const labels = areaTop.map(a => a.name);
    const vals = areaTop.map(a => a.value);
    ch.setOption({
      backgroundColor: CHART_THEME.bg,
      textStyle: { color: CHART_THEME.text },
      tooltip: chartTooltipLight(),
      grid: { left: 72, right: 20, top: 8, bottom: 8, containLabel: false },
      xAxis: { type: "value", axisLabel: { color: CHART_THEME.muted, margin: 8 }, splitLine: { lineStyle: { color: CHART_THEME.splitLine } } },
      yAxis: {
        type: "category",
        data: labels,
        inverse: true,
        axisLabel: {
          color: CHART_THEME.muted,
          fontSize: 11,
          width: 64,
          overflow: "truncate",
          ellipsis: "…",
        },
        axisLine: { lineStyle: { color: CHART_THEME.axisLine } },
      },
      series: [{ type: "bar", data: vals, itemStyle: { color: CHART_THEME.palette[2] } }],
      title: areaTop.length === 0 ? { text: "暂无地区数据", left: "center", top: "center", textStyle: { color: CHART_THEME.muted } } : { show: false },
    });
    ch.off("click");
    ch.on("click", (params) => {
      if (params.componentType !== "series" || params.dataIndex == null) return;
      const row = areaTop[params.dataIndex];
      if (!row || !row.value) return;
      if (row.filter == null || row.filter === "") return;
      applyDashboardLinkToList({ area: row.filter });
    });
    setTimeout(() => ch.resize(), 100);
  }

  const elRad = document.getElementById("chart-engagement-radar");
  if (elRad) {
    const ch = ensureChart(elRad);
    const labels = tagAvgPlayRank.map((x) => x.name);
    const avgs = tagAvgPlayRank.map((x) => Math.max(0, Number(x.avg_play) || 0));
    ch.setOption({
      backgroundColor: CHART_THEME.bg,
      textStyle: { color: CHART_THEME.text },
      tooltip: {
        ...chartTooltipLight(),
        trigger: "axis",
        axisPointer: { type: "shadow" },
        formatter: (params) => {
          const p = Array.isArray(params) ? params[0] : params;
          const i = p && p.dataIndex != null ? p.dataIndex : -1;
          const row = tagAvgPlayRank[i];
          if (!row) return "";
          return (
            `${escapeHtml(row.name)}<br/>` +
            `平均播放量：<b>${formatNum(Math.round(row.avg_play || 0))}</b><br/>` +
            `样本番剧数：<b>${row.count}</b> 部`
          );
        },
      },
      grid: { left: 76, right: 64, top: 10, bottom: 36, containLabel: false },
      xAxis: {
        type: "value",
        name: "平均播放量",
        nameLocation: "middle",
        nameGap: 30,
        nameTextStyle: { fontSize: 11, color: CHART_THEME.muted },
        axisLabel: {
          color: CHART_THEME.muted,
          margin: 10,
          formatter: (v) => {
            const n = Number(v);
            if (Number.isNaN(n)) return String(v);
            if (n >= 1e8) return (n / 1e8).toFixed(1) + "亿";
            if (n >= 1e4) return (n / 1e4).toFixed(0) + "万";
            return String(n);
          },
        },
        splitLine: { lineStyle: { color: CHART_THEME.splitLine } },
        axisLine: { lineStyle: { color: CHART_THEME.axisLine } },
      },
      yAxis: {
        type: "category",
        data: labels,
        inverse: true,
        axisLabel: {
          color: CHART_THEME.muted,
          fontSize: 11,
          width: 70,
          overflow: "truncate",
          ellipsis: "…",
          interval: 0,
        },
        axisLine: { lineStyle: { color: CHART_THEME.axisLine } },
      },
      series: [{
        type: "bar",
        data: avgs.map((v, i) => ({ value: v, itemStyle: { color: CHART_THEME.palette[i % CHART_THEME.palette.length] } })),
        label: {
          show: true,
          position: "right",
          distance: 6,
          formatter: (p) => formatNum(Math.round(avgs[p.dataIndex] || 0)),
          color: CHART_THEME.text,
          fontSize: 11,
        },
        barMaxWidth: 18,
      }],
      title: tagAvgPlayRank.length === 0
        ? { text: "暂无标签或样本不足（需至少 3 部番共现一标签）", left: "center", top: "center", textStyle: { color: CHART_THEME.muted, fontSize: 12 } }
        : { show: false },
    });
    ch.off("click");
    ch.on("click", (params) => {
      if (params.componentType !== "series" || params.dataIndex == null) return;
      const row = tagAvgPlayRank[params.dataIndex];
      if (!row || !row.name) return;
      applyDashboardLinkToList({ year: null, season: null, tags: row.name });
    });
    setTimeout(() => ch.resize(), 100);
  }

  const elSer = document.getElementById("chart-series-hist");
  if (elSer) {
    const ch = ensureChart(elSer);
    ch.setOption({
      backgroundColor: CHART_THEME.bg,
      textStyle: { color: CHART_THEME.text },
      tooltip: chartTooltipLight(),
      grid: { left: 44, right: 12, top: 28, bottom: 32, containLabel: true },
      xAxis: {
        type: "category",
        data: seriesBins.map(b => b.label),
        axisLabel: { color: CHART_THEME.muted, margin: 8, rotate: 0, fontSize: 11 },
        axisLine: { lineStyle: { color: CHART_THEME.axisLine } },
      },
      yAxis: {
        type: "value",
        name: "部数",
        nameLocation: "middle",
        nameGap: 36,
        nameTextStyle: { color: CHART_THEME.muted },
        axisLabel: { color: CHART_THEME.muted, margin: 6 },
        splitLine: { lineStyle: { color: CHART_THEME.splitLine } },
      },
      series: [{ type: "bar", data: seriesBins.map(b => b.count), itemStyle: { color: CHART_THEME.palette[4] } }],
      title: seriesBins.length === 0 ? { text: "暂无数据", left: "center", top: "center", textStyle: { color: CHART_THEME.muted } } : { show: false },
    });
    ch.off("click");
    ch.on("click", (params) => {
      if (params.componentType !== "series" || params.dataIndex == null) return;
      const b = seriesBins[params.dataIndex];
      if (!b || !b.count) return;
      if (b.label === "未知/0") {
        applyDashboardLinkToList({ seriesMin: 0, seriesMax: 0 });
        return;
      }
      const o = {};
      if (b.series_min != null) o.seriesMin = b.series_min;
      if (b.series_max != null) o.seriesMax = b.series_max;
      applyDashboardLinkToList(o);
    });
    setTimeout(() => ch.resize(), 100);
  }

  const elHm = document.getElementById("chart-pub-heatmap");
  if (elHm) {
    const ch = ensureChart(elHm);
    let vmax = 0;
    pubHeat.forEach((cell) => { if (cell[2] > vmax) vmax = cell[2]; });
    ch.setOption({
      backgroundColor: CHART_THEME.bg,
      textStyle: { color: CHART_THEME.text },
      tooltip: {
        ...chartTooltipLight(),
        formatter: (p) => {
          const d = p.data;
          if (!d || d.length < 3) return "";
          const wx = d[0];
          const my = d[1];
          return `${weekdays[wx] || ""} · ${months[my] || ""}<br/>${d[2]} 部`;
        },
      },
      grid: { left: 48, right: 92, top: 14, bottom: 32 },
      xAxis: {
        type: "category",
        data: weekdays,
        splitArea: { show: true },
        axisLabel: { color: CHART_THEME.muted, fontSize: 10, margin: 8 },
      },
      yAxis: {
        type: "category",
        data: months,
        splitArea: { show: true },
        axisLabel: { color: CHART_THEME.muted, fontSize: 10, margin: 6 },
      },
      visualMap: { min: 0, max: Math.max(1, vmax), calculable: true, orient: "vertical", right: 4, top: "middle", textStyle: { color: CHART_THEME.muted } },
      series: [{
        type: "heatmap",
        data: pubHeat,
        label: { show: vmax > 0 && vmax <= 40, fontSize: 9, color: CHART_THEME.text },
        emphasis: { itemStyle: { shadowBlur: 6 } },
      }],
      title: pubHeat.length === 0 ? { text: "暂无开播日期", left: "center", top: "center", textStyle: { color: CHART_THEME.muted } } : { show: false },
    });
    setTimeout(() => ch.resize(), 100);
  }

  const elSnap = document.getElementById("chart-snapshot-trend");
  if (elSnap) {
    const ch = ensureChart(elSnap);
    let opt;
    if (snapLines.length > 0) {
      const dateSet = new Set();
      snapLines.forEach((line) => {
        (line.points || []).forEach((pt) => { dateSet.add(pt[0]); });
      });
      const cats = [...dateSet].sort();
      const series = snapLines.map((line, idx) => ({
        type: "line",
        name: line.title || ("id:" + line.media_id),
        smooth: true,
        showSymbol: cats.length < 22,
        data: cats.map((d) => {
          const found = (line.points || []).find((p) => p[0] === d);
          return found ? found[1] : null;
        }),
        itemStyle: { color: CHART_THEME.palette[idx % CHART_THEME.palette.length] },
      }));
      opt = {
        backgroundColor: CHART_THEME.bg,
        textStyle: { color: CHART_THEME.text },
        tooltip: { ...chartTooltipLight(), trigger: "axis" },
        legend: { type: "scroll", bottom: 2, textStyle: { color: CHART_THEME.muted, fontSize: 11 }, padding: [0, 0, 4, 0] },
        grid: { left: 56, right: 20, top: 28, bottom: 66, containLabel: true },
        xAxis: { type: "category", data: cats, axisLabel: { color: CHART_THEME.muted, rotate: cats.length > 18 ? 32 : 0, fontSize: 9, margin: 10 } },
        yAxis: {
          type: "value",
          name: "播放量",
          nameLocation: "middle",
          nameGap: 42,
          nameTextStyle: { color: CHART_THEME.muted },
          axisLabel: {
            color: CHART_THEME.muted,
            margin: 6,
            formatter: (v) => {
              const n = Number(v);
              if (Number.isNaN(n)) return String(v);
              if (n >= 1e8) return (n / 1e8).toFixed(1) + "亿";
              if (n >= 1e4) return (n / 1e4).toFixed(0) + "万";
              return String(n);
            },
          },
          splitLine: { lineStyle: { color: CHART_THEME.splitLine } },
        },
        series,
      };
    } else if (snapAgg.length > 0) {
      const cats = snapAgg.map(x => x.date);
      opt = {
        backgroundColor: CHART_THEME.bg,
        textStyle: { color: CHART_THEME.text },
        tooltip: { ...chartTooltipLight(), trigger: "axis" },
        grid: { left: 52, right: 16, top: 28, bottom: 48, containLabel: true },
        xAxis: { type: "category", data: cats, axisLabel: { color: CHART_THEME.muted, rotate: cats.length > 18 ? 32 : 0, fontSize: 9, margin: 10 } },
        yAxis: {
          type: "value",
          name: "快照条数",
          nameLocation: "middle",
          nameGap: 36,
          nameTextStyle: { color: CHART_THEME.muted },
          axisLabel: { color: CHART_THEME.muted, margin: 6 },
          splitLine: { lineStyle: { color: CHART_THEME.splitLine } },
        },
        series: [{ type: "line", name: "每日快照条数", data: snapAgg.map(x => x.count), smooth: true, itemStyle: { color: CHART_THEME.palette[0] } }],
      };
    } else {
      opt = {
        backgroundColor: CHART_THEME.bg,
        title: { text: "暂无快照数据（需写入 bangumi_daily_snapshot）", left: "center", top: "center", textStyle: { color: CHART_THEME.muted, fontSize: 12 } },
      };
    }
    ch.setOption(opt);
    ch.off("click");
    ch.on("click", (params) => {
      if (!snapLines.length) return;
      if (params.componentType !== "series" || params.seriesIndex == null) return;
      const line = snapLines[params.seriesIndex];
      if (line && line.media_id != null) openDetail(line.media_id);
    });
    setTimeout(() => ch.resize(), 100);
  }
}

function loadDashboard() {
  const dashChartsP = fetch(`${API_BASE}/analysis/dashboard-charts`, { credentials: "include" })
    .then(r => r.json())
    .then(j => (j && j.ok ? j.data : {}))
    .catch(() => ({}));

  Promise.all([
    fetch(`${API_BASE}/analysis/trend`, { credentials: "include" }).then(r => r.json()),
    fetch(`${API_BASE}/analysis/tags`, { credentials: "include" }).then(r => r.json()),
    fetch(`${API_BASE}/rank?order=play_count&limit=15`, { credentials: "include" }).then(r => r.json()),
    dashChartsP,
  ]).then(([trendRes, tagRes, rankRes, extraCharts]) => {
    const trendData = trendRes.data || {};
    const byYear = trendData.by_year || [];
    const bySeason = trendData.by_season || [];
    const totalInDb = trendData.total_in_db != null ? trendData.total_in_db : 0;
    const totalWithDate = trendData.total_with_date != null ? trendData.total_with_date : 0;
    const tags = (tagRes.data || []).slice(0, 20);
    const rank = rankRes.data || [];

    const hintEl = document.getElementById("dashboard-trend-hint");
    if (hintEl) {
      hintEl.textContent = "年度/季度趋势仅反映本系统库内已采集的数据，数据量越大、覆盖年份与季度越全，图越有参考价值。当前库内共 " + totalInDb + " 条番剧，其中 " + totalWithDate + " 条有开播日期参与趋势统计。若想提高准确性，建议：在「个人中心」页上方使用「爬取数据」多选几年与季度、增加页数，或使用个人中心「同步追番到本地」补充数据。交互提示：点击「年度」折线上的点按该年筛选列表；点击「季度」柱子按年+季筛选；点击「标签」扇区按标签筛选；点击「播放量」柱子进入该番详情。下方扩展图中：评分柱、地区条、话数柱可联动番剧列表；播放量–评分散点与快照折线点击可进入该番详情。";
    }

    const chartYearEl = document.getElementById("chart-year");
    const chartYear = ensureChart(chartYearEl);
    chartYear.setOption({
      backgroundColor: CHART_THEME.bg,
      textStyle: { color: CHART_THEME.text },
      grid: { left: 48, right: 18, top: 32, bottom: 28, containLabel: true },
      tooltip: {
        ...chartTooltipLight(),
        trigger: "axis",
        axisPointer: { type: "line", lineStyle: { color: CHART_THEME.axisLine, width: 1 } },
      },
      xAxis: {
        type: "category",
        data: byYear.map(x => String(x.year)),
        axisLine: { lineStyle: { color: CHART_THEME.axisLine } },
        axisLabel: { color: CHART_THEME.muted, margin: 8 },
      },
      yAxis: {
        type: "value",
        name: "数量",
        nameLocation: "middle",
        nameGap: 32,
        nameTextStyle: { color: CHART_THEME.muted },
        axisLine: { lineStyle: { color: CHART_THEME.axisLine } },
        axisLabel: { color: CHART_THEME.muted, margin: 6 },
        splitLine: { lineStyle: { color: CHART_THEME.splitLine } },
      },
      series: [{
        type: "line",
        data: byYear.map(x => x.count),
        smooth: true,
        triggerLineEvent: true,
        showSymbol: true,
        symbol: "circle",
        symbolSize: 7,
        itemStyle: { color: CHART_THEME.palette[0] },
        lineStyle: { width: 2 },
      }],
      title: byYear.length === 0 ? { text: "暂无数据", left: "center", top: "center", textStyle: { color: CHART_THEME.muted } } : { show: false },
    });
    chartYear.off("click");
    chartYear.on("click", (params) => {
      if (params.componentType !== "series" || params.dataIndex == null) return;
      const row = byYear[params.dataIndex];
      if (!row || row.year === "未知") return;
      const yi = parseInt(String(row.year), 10);
      if (Number.isNaN(yi)) return;
      applyDashboardLinkToList({ year: yi, season: null, tags: null });
    });
    setTimeout(() => chartYear.resize(), 100);

    const chartSeasonEl = document.getElementById("chart-season");
    const chartSeason = ensureChart(chartSeasonEl);
    chartSeason.setOption({
      backgroundColor: CHART_THEME.bg,
      textStyle: { color: CHART_THEME.text },
      grid: { left: 48, right: 16, top: 28, bottom: 52, containLabel: true },
      tooltip: chartTooltipLight(),
      xAxis: {
        type: "category",
        data: bySeason.map(x => x.label),
        axisLabel: { rotate: 30, color: CHART_THEME.muted, margin: 10 },
        axisLine: { lineStyle: { color: CHART_THEME.axisLine } },
      },
      yAxis: {
        type: "value",
        name: "数量",
        nameLocation: "middle",
        nameGap: 32,
        nameTextStyle: { color: CHART_THEME.muted },
        axisLine: { lineStyle: { color: CHART_THEME.axisLine } },
        axisLabel: { color: CHART_THEME.muted, margin: 6 },
        splitLine: { lineStyle: { color: CHART_THEME.splitLine } },
      },
      series: [{ type: "bar", data: bySeason.map(x => x.count), itemStyle: { color: CHART_THEME.palette[0] } }],
      title: bySeason.length === 0 ? { text: "暂无数据", left: "center", top: "center", textStyle: { color: CHART_THEME.muted } } : { show: false },
    });
    chartSeason.off("click");
    chartSeason.on("click", (params) => {
      if (params.componentType !== "series" || params.dataIndex == null) return;
      const row = bySeason[params.dataIndex];
      if (!row || row.label === "未知") return;
      const yr = row.year != null ? parseInt(String(row.year), 10) : NaN;
      const sn = row.season != null ? parseInt(String(row.season), 10) : NaN;
      if (Number.isNaN(yr) || Number.isNaN(sn) || ![1, 4, 7, 10].includes(sn)) return;
      applyDashboardLinkToList({ year: yr, season: sn, tags: null });
    });
    setTimeout(() => chartSeason.resize(), 100);

    const chartTagEl = document.getElementById("chart-tag");
    const chartTag = ensureChart(chartTagEl);
    chartTag.setOption({
      backgroundColor: CHART_THEME.bg,
      textStyle: { color: CHART_THEME.text },
      tooltip: chartTooltipLight(),
      color: CHART_THEME.palette,
      series: [{
        type: "pie",
        radius: "60%",
        data: tags.map(t => ({ name: t.name, value: t.value })),
        itemStyle: { borderColor: "#fff", borderWidth: 1 },
        label: { color: CHART_THEME.text },
      }],
      title: tags.length === 0 ? { text: "暂无标签数据", left: "center", top: "center", textStyle: { color: CHART_THEME.muted } } : { show: false },
    });
    chartTag.off("click");
    chartTag.on("click", (params) => {
      if (params.seriesType !== "pie" || !params.name) return;
      if (params.name === "未知") return;
      applyDashboardLinkToList({ year: null, season: null, tags: params.name });
    });
    setTimeout(() => chartTag.resize(), 100);

    const chartRankEl = document.getElementById("chart-rank");
    const chartRank = ensureChart(chartRankEl);
    chartRank.setOption({
      backgroundColor: CHART_THEME.bg,
      textStyle: { color: CHART_THEME.text },
      tooltip: {
        ...chartTooltipLight(),
        formatter: (params) => {
          const p = Array.isArray(params) ? params[0] : params;
          const name = rank[p.dataIndex] ? (rank[p.dataIndex].title || "") : "";
          const v = p.value != null ? p.value : 0;
          return `${escapeHtml(name)}<br/>播放量：${formatNum(v)}`;
        },
      },
      grid: { left: 52, right: 14, top: 36, bottom: 58, containLabel: true },
      xAxis: {
        type: "category",
        data: rank.map(r => (r.title || "").slice(0, 8)),
        axisLabel: { rotate: 30, color: CHART_THEME.muted, margin: 10 },
        axisLine: { lineStyle: { color: CHART_THEME.axisLine } },
      },
      yAxis: {
        type: "value",
        name: "播放量",
        nameLocation: "middle",
        nameGap: 40,
        nameTextStyle: { color: CHART_THEME.muted },
        axisLine: { lineStyle: { color: CHART_THEME.axisLine } },
        axisLabel: {
          color: CHART_THEME.muted,
          margin: 6,
          formatter: (v) => {
            const n = Number(v);
            if (Number.isNaN(n)) return String(v);
            if (n >= 1e8) return (n / 1e8).toFixed(1) + "亿";
            if (n >= 1e4) return (n / 1e4).toFixed(0) + "万";
            return String(n);
          },
        },
        splitLine: { lineStyle: { color: CHART_THEME.splitLine } },
      },
      series: [{ type: "bar", data: rank.map(r => r.play_count || 0), itemStyle: { color: CHART_THEME.palette[0] } }],
      title: rank.length === 0 ? { text: "暂无数据", left: "center", top: "center", textStyle: { color: CHART_THEME.muted } } : { show: false },
    });
    chartRank.off("click");
    chartRank.on("click", (params) => {
      if (params.componentType !== "series" || params.dataIndex == null) return;
      const row = rank[params.dataIndex];
      if (!row || row.media_id == null) return;
      openDetail(parseInt(row.media_id, 10));
    });
    setTimeout(() => chartRank.resize(), 100);

    renderDashboardExtraCharts(extraCharts);
  }).catch(err => {
    console.error("数据大屏加载失败", err);
    ["chart-year", "chart-season", "chart-tag", "chart-rank", ...DASHBOARD_EXTRA_CHART_IDS].forEach(id => {
      const el = document.getElementById(id);
      if (el) {
        const chart = ensureChart(el);
        chart.setOption({
          backgroundColor: CHART_THEME.bg,
          title: { text: "加载失败", left: "center", top: "center", textStyle: { color: "#dc2626" } },
        });
      }
    });
  });
}

// ---------- 用户 ----------
window.currentUser = null;

function applyAdminNav(user) {
  const navAdmin = document.getElementById("nav-admin");
  if (navAdmin) {
    navAdmin.classList.toggle("hidden", !(user && user.is_admin));
  }
}

function loadUserPage() {
  fetch(`${AUTH_BASE}/me`, { credentials: "include" })
    .then(r => r.json())
    .then(res => {
      if (res.user) {
        window.currentUser = res.user;
        document.getElementById("user-login-form").classList.add("hidden");
        document.getElementById("user-favorites").classList.remove("hidden");
        document.getElementById("user-name").textContent = res.user.username;
        document.getElementById("user-name").classList.remove("hidden");
        document.getElementById("btn-logout").classList.remove("hidden");
        loadFavorites();
        loadBilibiliCookieStatus();
      } else {
        window.currentUser = null;
        document.getElementById("user-login-form").classList.remove("hidden");
        document.getElementById("user-favorites").classList.add("hidden");
        document.getElementById("user-name").classList.add("hidden");
        document.getElementById("btn-logout").classList.add("hidden");
      }
      applyAdminNav(res.user);
    });
}

function loadBilibiliCookieStatus() {
  fetch(`${API_BASE}/user/bilibili-cookie`, { credentials: "include" })
    .then(r => r.json())
    .then(res => {
      const el = document.getElementById("bili-cookie-status");
      if (el) el.textContent = res.has_cookie ? "已设置 B 站 Cookie" : "";
      // B 站账号绑定状态
      const bindEl = document.getElementById("bili-bind-status");
      if (bindEl) {
        if (res.has_bind && res.bilibili_uid != null) {
          bindEl.innerHTML = '<span style="color:#16a34a;font-weight:600">✓ 已绑定 B 站账号（UID: ' + res.bilibili_uid + '）</span>';
        } else if (res.has_cookie) {
          bindEl.innerHTML = '<span style="color:#b45309">已设置 B 站 Cookie，但尚未绑定 B 站账号 UID。可扫码绑定。</span>';
        } else {
          bindEl.innerHTML = '<span style="color:#6b7280">未绑定 B 站账号。扫码绑定后，以后可直接用该 B 站账号扫码登录。</span>';
        }
      }
    });
}

// 个人中心「扫码绑定 B 站账号」按钮 → 复用扫码弹窗
document.addEventListener("DOMContentLoaded", () => {
  const bindBtn = document.getElementById("btn-bili-bind-show");
  if (bindBtn) {
    bindBtn.addEventListener("click", () => {
      const showBtn = document.getElementById("btn-bili-qr-show");
      if (showBtn) showBtn.click();
    });
  }
});

let crawlStatusTimer = null;
function stopCrawlStatusPoll() {
  if (crawlStatusTimer) { clearInterval(crawlStatusTimer); crawlStatusTimer = null; }
}
/**
 * 统一渲染采集进度条。
 * res: /crawl/status 或 /admin/crawl/status 的返回
 * targets: { wrap, bar, msg, extraLink? } 对应的 DOM id 前缀
 */
function renderCrawlProgress(res, targets) {
  const wrap = document.getElementById(targets.wrap);
  const bar = document.getElementById(targets.bar);
  const msg = document.getElementById(targets.msg);
  if (!wrap || !bar || !msg) return;
  if (res.running) {
    wrap.style.display = "block";
    const pages = res.pages || 0;
    const page = res.page || 0;
    if (pages > 1) {
      bar.classList.remove("indeterminate");
      const pct = Math.min(100, Math.round((page / pages) * 100));
      bar.style.width = pct + "%";
      msg.textContent = (res.message || "") + `（${page}/${pages}）`;
    } else {
      bar.classList.add("indeterminate");
      msg.textContent = res.message || "采集中…";
    }
  } else {
    wrap.style.display = "block";
    bar.classList.remove("indeterminate");
    bar.style.width = "100%";
    if (res.job) {
      // 完成态：保持进度条满格，展示结果消息
      msg.innerHTML = (res.message || "完成") + (res.items > 0 && targets.extraLink ? targets.extraLink : "");
    } else {
      // 无任务记录：隐藏进度条
      wrap.style.display = "none";
      msg.textContent = "";
    }
  }
}

function pollCrawlStatus(msgEl, targets) {
  stopCrawlStatusPoll();
  const t = targets || null;
  crawlStatusTimer = setInterval(() => {
    fetch(`${API_BASE}/crawl/status`, { credentials: "include" })
      .then(r => r.json())
      .then(res => {
        if (!res.ok) return;
        if (res.running) {
          renderCrawlProgress(res, t);
        } else {
          // 完成态：构建「去番剧列表」链接（仅列表页用）
          const link = res.items > 0 ? ' <a href="#" id="crawl-goto-list" style="color:#0369a1;margin-left:6px">去番剧列表</a>' : "";
          if (t) {
            renderCrawlProgress({ ...res, job: res.job || "done" }, {
              ...t,
              extraLink: link,
            });
          }
          const el = document.getElementById("crawl-goto-list");
          if (el) el.addEventListener("click", function(e) {
            e.preventDefault();
            document.getElementById("search-year").value = "";
            document.getElementById("search-season").value = "";
            showPage("home");
            loadList();
          });
          stopCrawlStatusPoll();
          if (res.items > 0 && document.getElementById("page-home").classList.contains("active")) loadList();
        }
      })
      .catch(() => {});
  }, 2000);
}

document.getElementById("btn-save-bili-cookie").addEventListener("click", () => {
  const sessdata = document.getElementById("bili-sessdata").value.trim();
  const bili_jct = document.getElementById("bili-bili-jct").value.trim();
  fetch(`${API_BASE}/user/bilibili-cookie`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ sessdata, bili_jct }),
  })
    .then(r => r.json())
    .then(res => {
      if (res.ok) { loadBilibiliCookieStatus(); document.getElementById("bili-cookie-status").textContent = "已保存"; }
    });
});

// B 站扫码登录（弹层展示二维码）
let biliQrPollTimer = null;
function stopBiliQrPoll() {
  if (biliQrPollTimer) { clearInterval(biliQrPollTimer); biliQrPollTimer = null; }
}
function closeBiliQrModal() {
  stopBiliQrPoll();
  const modal = document.getElementById("bili-qr-modal");
  if (modal) modal.classList.add("hidden");
}
document.getElementById("btn-bili-qr-show").addEventListener("click", () => {
  const modal = document.getElementById("bili-qr-modal");
  const img = document.getElementById("bili-qr-img");
  const statusEl = document.getElementById("bili-qr-status");
  stopBiliQrPoll();
  img.style.display = "block";
  img.alt = "登录二维码";
  img.removeAttribute("src");
  statusEl.textContent = "正在获取二维码...";
  modal.classList.remove("hidden");
  fetch(`${API_BASE}/bilibili-qr/generate`, { credentials: "include" })
    .then(r => r.json())
    .then(res => {
      if (!res.ok || !res.qrcode_key) {
        statusEl.textContent = "获取失败，请重试";
        return;
      }
      if (res.qrcode_image_base64) {
        img.src = "data:image/png;base64," + res.qrcode_image_base64;
      } else {
        img.alt = "请使用链接: " + (res.url || "");
        img.style.display = "none";
        statusEl.innerHTML = "若未显示图片，请复制链接到浏览器打开后扫码：<br>" + (res.url || "");
      }
      statusEl.textContent = "请使用 B 站 App 或网页扫描二维码";
      const key = res.qrcode_key;
      biliQrPollTimer = setInterval(() => {
        fetch(`${API_BASE}/bilibili-qr/poll?qrcode_key=${encodeURIComponent(key)}`, { credentials: "include" })
          .then(r => r.json())
          .then(pollRes => {
            if (pollRes.status === "done") {
              stopBiliQrPoll();
              statusEl.textContent = "登录成功，Cookie 已保存";
              loadBilibiliCookieStatus();
              document.getElementById("bili-cookie-status").textContent = "已通过扫码登录";
              setTimeout(closeBiliQrModal, 1600);
            } else if (pollRes.status === "confirm") {
              statusEl.textContent = "已扫码，请在手机上确认登录";
            } else if (pollRes.status === "timeout") {
              stopBiliQrPoll();
              statusEl.textContent = "二维码已过期，请点击「显示登录二维码」重新获取";
            } else if (pollRes.status === "error") {
              stopBiliQrPoll();
              statusEl.textContent = pollRes.error || "扫码成功，但保存登录状态失败";
            }
          });
      }, 2000);
    })
    .catch(() => { statusEl.textContent = "请求失败"; });
});
document.getElementById("btn-bili-qr-close").addEventListener("click", closeBiliQrModal);
document.getElementById("bili-qr-modal-backdrop").addEventListener("click", closeBiliQrModal);
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  const modal = document.getElementById("bili-qr-modal");
  if (modal && !modal.classList.contains("hidden")) closeBiliQrModal();
});

function loadFavorites(options = {}) {
  const { refreshTagRecommend = true } = options;
  fetch(`${API_BASE}/favorites`, { credentials: "include" })
    .then(r => r.json())
    .then(res => {
      const list = document.getElementById("favorite-list");
      if (!res.items || !res.items.length) {
        list.innerHTML = "<p style='color:#1f2937'>暂无收藏</p>";
        return;
      }
      list.innerHTML = res.items.map(item => `
        <div class="card" data-media-id="${item.media_id}" style="cursor:pointer">
          <img src="${normalizeCoverUrl(item.cover) || ''}" alt="${escapeHtml(item.title)}" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><rect fill=%22%23e5e7eb%22 width=%22100%22 height=%22100%22/><text x=%2250%22 y=%2255%22 fill=%22%23374151%22 text-anchor=%22middle%22>无图</text></svg>'">
          <div class="card-body">
            <div class="card-text">
              <div class="card-title">${escapeHtml(item.title)}</div>
              <div class="card-meta">播放 ${formatNum(item.play_count)}</div>
            </div>
            <button type="button" class="btn-fav favorited" data-media-id="${item.media_id}" data-favorited="true">取消收藏</button>
          </div>
        </div>
      `).join("");
      list.querySelectorAll(".card").forEach(card => {
        card.addEventListener("click", (e) => {
          if (e.target.closest(".btn-fav")) return;
          openDetail(parseInt(card.dataset.mediaId, 10));
        });
      });
      list.querySelectorAll(".card-body .btn-fav").forEach(btn => {
        btn.addEventListener("click", (e) => {
          e.preventDefault();
          e.stopPropagation();
          const mediaId = parseInt(btn.dataset.mediaId, 10);
          toggleFavorite(mediaId, true, btn).then((res) => {
            if (!res || !res.ok) return;
            loadFavorites({ refreshTagRecommend: true });
          });
        });
      });
    })
    .finally(() => {
      if (refreshTagRecommend) loadTagRecommendations();
    });
}

function loadTagRecommendations() {
  const list = document.getElementById("tag-recommend-list");
  const msg = document.getElementById("tag-recommend-msg");
  if (!list || !msg) return;
  if (!window.currentUser) {
    list.innerHTML = "";
    msg.textContent = "";
    return;
  }
  list.innerHTML = "<p class=\"muted\" style=\"font-size:12px\">加载推荐中…</p>";
  msg.textContent = "";
  fetch(`${API_BASE}/recommendations/by-tags?limit=20`, { credentials: "include" })
    .then(r => r.json())
    .then(res => {
      if (!res.ok) {
        list.innerHTML = "";
        msg.textContent = res.error || "推荐加载失败";
        return;
      }
      msg.textContent = res.message || "";
      if (!res.items || !res.items.length) {
        list.innerHTML = "";
        return;
      }
      list.innerHTML = res.items.map(item => {
        const tags = (item.matched_tags || []).slice(0, 10).map(t => escapeHtml(t)).join(" · ");
        const tagLine = tags
          ? `<div class="card-meta" style="font-size:11px;color:#0369a1;margin-top:4px">命中：${tags}</div>`
          : "";
        const scoreLine = item.tag_score != null
          ? `<div class="card-meta" style="font-size:11px">标签分 ${item.tag_score} · 播放 ${formatNum(item.play_count)}</div>`
          : `<div class="card-meta">播放 ${formatNum(item.play_count)}</div>`;
        const favBtn = window.currentUser
          ? `<button type="button" class="btn-fav" data-media-id="${item.media_id}" data-favorited="false">收藏</button>`
          : "";
        return `
        <div class="card" data-media-id="${item.media_id}" style="cursor:pointer">
          <img src="${normalizeCoverUrl(item.cover) || ''}" alt="${escapeHtml(item.title)}" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><rect fill=%22%23e5e7eb%22 width=%22100%22 height=%22100%22/><text x=%2250%22 y=%2255%22 fill=%22%23374151%22 text-anchor=%22middle%22>无图</text></svg>'">
          <div class="card-body">
            <div class="card-text">
              <div class="card-title">${escapeHtml(item.title)}</div>
              ${scoreLine}
              ${tagLine}
            </div>
            ${favBtn}
          </div>
        </div>`;
      }).join("");
      list.querySelectorAll(".card").forEach(card => {
        card.addEventListener("click", (e) => {
          if (e.target.closest(".btn-fav")) return;
          openDetail(parseInt(card.dataset.mediaId, 10));
        });
      });
      list.querySelectorAll(".card-body .btn-fav").forEach(btn => {
        btn.addEventListener("click", (e) => {
          e.preventDefault();
          e.stopPropagation();
          const mediaId = parseInt(btn.dataset.mediaId, 10);
          const favorited = btn.dataset.favorited === "true";
          const p = toggleFavorite(mediaId, favorited, btn);
          btn.dataset.favorited = favorited ? "false" : "true";
          btn.textContent = favorited ? "收藏" : "已收藏";
          btn.classList.toggle("favorited", !favorited);
          p.then((res) => {
            if (!res || !res.ok) {
              btn.dataset.favorited = favorited ? "true" : "false";
              btn.textContent = favorited ? "已收藏" : "收藏";
              btn.classList.toggle("favorited", favorited);
              return;
            }
            loadFavorites({ refreshTagRecommend: false });
          });
        });
      });
    })
    .catch(() => {
      list.innerHTML = "";
      msg.textContent = "推荐请求失败";
    });
}

let _biliSubscribedCharts = { rank: null, status: null, tags: null };

function drawBilibiliSubscribedCharts(items) {
  const wrap = document.getElementById("bili-subscribed-charts");
  const rankEl = document.getElementById("chart-bili-subscribed-rank");
  const statusEl = document.getElementById("chart-bili-subscribed-status");
  const tagsEl = document.getElementById("chart-bili-subscribed-tags");
  if (!wrap || !rankEl || !statusEl || !tagsEl || !items || !items.length) return;
  wrap.classList.remove("hidden");

  if (_biliSubscribedCharts.rank) _biliSubscribedCharts.rank.dispose();
  if (_biliSubscribedCharts.status) _biliSubscribedCharts.status.dispose();
  if (_biliSubscribedCharts.tags) _biliSubscribedCharts.tags.dispose();

  const sorted = items.slice().sort((a, b) => (b.play_count || 0) - (a.play_count || 0));
  const top10 = sorted.slice(0, 10);
  const rankChart = ensureChart(rankEl);
  const xCats = top10.map((x) => {
    const t = (x.title || "").trim() || "—";
    return t.length > 8 ? t.slice(0, 7) + "…" : t;
  });
  rankChart.setOption({
    backgroundColor: CHART_THEME.bg,
    textStyle: { color: CHART_THEME.text },
    tooltip: {
      ...chartTooltipLight(),
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: (params) => {
        const p = Array.isArray(params) ? params[0] : params;
        const i = p && p.dataIndex != null ? p.dataIndex : -1;
        const row = top10[i];
        if (!row) return "";
        return `${escapeHtml(row.title || "")}<br/>播放量：<b>${formatNum(row.play_count || 0)}</b>`;
      },
    },
    grid: { left: 56, right: 14, top: 28, bottom: 72, containLabel: true },
    xAxis: {
      type: "category",
      data: xCats,
      axisLabel: {
        rotate: 32,
        interval: 0,
        hideOverlap: false,
        color: CHART_THEME.muted,
        fontSize: 10,
        margin: 10,
      },
      axisLine: { lineStyle: { color: CHART_THEME.axisLine } },
    },
    yAxis: {
      type: "value",
      name: "播放量",
      nameLocation: "middle",
      nameGap: 42,
      nameTextStyle: { color: CHART_THEME.muted, fontSize: 11 },
      axisLabel: {
        color: CHART_THEME.muted,
        margin: 6,
        formatter: (v) => {
          const n = Number(v);
          if (Number.isNaN(n)) return String(v);
          if (n >= 1e8) return (n / 1e8).toFixed(1) + "亿";
          if (n >= 1e4) return (n / 1e4).toFixed(0) + "万";
          return String(n);
        },
      },
      axisLine: { lineStyle: { color: CHART_THEME.axisLine } },
      splitLine: { lineStyle: { color: CHART_THEME.splitLine } },
    },
    series: [{
      type: "bar",
      data: top10.map((x) => x.play_count || 0),
      itemStyle: { color: CHART_THEME.palette[0] },
      label: {
        show: true,
        position: "top",
        distance: 4,
        formatter: (p) => formatNum(top10[p.dataIndex].play_count || 0),
        fontSize: 9,
        color: CHART_THEME.muted,
      },
      barMaxWidth: 26,
    }],
    title: top10.length === 0 ? { text: "暂无数据", left: "center", top: "center", textStyle: { color: CHART_THEME.muted } } : { show: false },
  });
  _biliSubscribedCharts.rank = rankChart;

  const statusNames = { 1: "想看", 2: "在看", 3: "已看" };
  const statusCount = {};
  items.forEach(x => {
    const k = x.follow_status != null ? statusNames[x.follow_status] || "其他" : "其他";
    statusCount[k] = (statusCount[k] || 0) + 1;
  });
  const statusData = Object.entries(statusCount).map(([name, value]) => ({ name, value }));
  const statusChart = ensureChart(statusEl);
  statusChart.setOption({
    backgroundColor: CHART_THEME.bg,
    textStyle: { color: CHART_THEME.text },
    tooltip: chartTooltipLight(),
    color: CHART_THEME.palette,
    series: [{
      type: "pie",
      radius: "58%",
      data: statusData,
      itemStyle: { borderColor: "#fff", borderWidth: 1 },
      label: { color: CHART_THEME.text },
    }],
    title: statusData.length === 0 ? { text: "暂无数据", left: "center", top: "center", textStyle: { color: CHART_THEME.muted } } : { show: false },
  });
  _biliSubscribedCharts.status = statusChart;

  const mediaIds = items.map(x => x.media_id).filter(Boolean);
  const hintEl = document.getElementById("bili-subscribed-tags-hint");
  if (hintEl) hintEl.textContent = "";
  if (mediaIds.length > 0) {
    fetch(`${API_BASE}/analysis/tags-by-media-ids?media_ids=${mediaIds.join(",")}`, { credentials: "include" })
      .then(r => r.json())
      .then(res => {
        const tagData = (res.data || []).slice(0, 20);
        const requested = res.requested_count != null ? res.requested_count : mediaIds.length;
        const matched = res.matched_count != null ? res.matched_count : 0;
        if (hintEl) {
          hintEl.textContent = requested > 0
            ? `共 ${requested} 部追番，其中 ${matched} 部已在本系统采集并有标签（仅统计这 ${matched} 部）`
            : "";
        }
        const tagsChart = ensureChart(tagsEl);
        tagsChart.setOption({
          backgroundColor: CHART_THEME.bg,
          textStyle: { color: CHART_THEME.text },
          tooltip: chartTooltipLight(),
          color: CHART_THEME.palette,
          series: [{
            type: "pie",
            radius: "58%",
            data: tagData.map(t => ({ name: t.name, value: t.value })),
            itemStyle: { borderColor: "#fff", borderWidth: 1 },
            label: { color: CHART_THEME.text },
          }],
          title: tagData.length === 0 ? { text: matched === 0 ? "暂无标签（请先采集番剧数据）" : "暂无标签", left: "center", top: "center", textStyle: { color: CHART_THEME.muted, fontSize: 11 } } : { show: false },
        });
        _biliSubscribedCharts.tags = tagsChart;
        setTimeout(() => tagsChart.resize(), 80);
      })
      .catch(() => {
        if (hintEl) hintEl.textContent = "";
        const tagsChart = ensureChart(tagsEl);
        tagsChart.setOption({
          backgroundColor: CHART_THEME.bg,
          title: { text: "加载失败", left: "center", top: "center", textStyle: { color: CHART_THEME.muted } },
        });
        _biliSubscribedCharts.tags = tagsChart;
      });
  } else {
    const tagsChart = ensureChart(tagsEl);
    tagsChart.setOption({
      backgroundColor: CHART_THEME.bg,
      title: { text: "暂无数据", left: "center", top: "center", textStyle: { color: CHART_THEME.muted } },
    });
    _biliSubscribedCharts.tags = tagsChart;
  }
  setTimeout(() => { rankChart.resize(); statusChart.resize(); }, 80);
}

function loadSubscribedPage() {
  // 进入「我的追番」：先检查是否绑定 B 站账号
  fetch(`${API_BASE}/user/bilibili-cookie`, { credentials: "include" })
    .then(r => r.json())
    .then(res => {
      if (res.has_bind) {
        // 已绑定：自动同步追番入库（去重），完成后从数据库展示
        const msgEl = document.getElementById("bili-subscribed-msg");
        const bar = document.getElementById("bili-subscribed-progress-bar") || document.getElementById("crawl-progress-bar");
        const wrap = document.getElementById("bili-subscribed-progress") || document.getElementById("crawl-progress");
        if (wrap) wrap.style.display = "block";
        if (bar) bar.classList.add("indeterminate");
        if (msgEl) msgEl.textContent = "正在同步追番到数据库…";
        fetch(`${API_BASE}/crawl/sync-subscribed`, {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
        })
          .then(r => r.json())
          .then(syncRes => {
            if (syncRes.ok) {
              // 同步中：轮询进度，完成后加载列表
              if (msgEl) msgEl.textContent = syncRes.message || "已开始同步，请稍候…";
              pollSubscribedSync(msgEl);
            } else {
              // 未绑定 Cookie 等错误：仍尝试展示已有追番数据
              if (msgEl) msgEl.textContent = syncRes.error || "同步失败，展示已有数据";
              if (wrap) wrap.style.display = "none";
              loadBilibiliSubscribed();
            }
          })
          .catch(() => {
            if (wrap) wrap.style.display = "none";
            if (msgEl) msgEl.textContent = "请求失败，展示已有数据";
            loadBilibiliSubscribed();
          });
      } else {
        const msgEl = document.getElementById("bili-subscribed-msg");
        const listEl = document.getElementById("bili-subscribed-list");
        const chartsWrap = document.getElementById("bili-subscribed-charts");
        if (msgEl) {
          msgEl.innerHTML = '未绑定 B 站账号，请先前往 <a href="#" data-page="user" style="color:#0369a1">个人中心</a> 绑定后再查看追番。';
          const link = msgEl.querySelector('a[data-page="user"]');
          if (link) link.addEventListener("click", (e) => { e.preventDefault(); showPage("user"); });
        }
        if (listEl) listEl.innerHTML = "";
        if (chartsWrap) chartsWrap.classList.add("hidden");
      }
    })
    .catch(() => {
      const msgEl = document.getElementById("bili-subscribed-msg");
      if (msgEl) msgEl.textContent = "请求失败，请重试";
    });
}

// 追番同步进度轮询（复用 /api/crawl/status，job=sync_subscribed）
let subscribedSyncTimer = null;
function stopSubscribedSyncPoll() {
  if (subscribedSyncTimer) { clearInterval(subscribedSyncTimer); subscribedSyncTimer = null; }
}
function pollSubscribedSync(msgEl) {
  stopSubscribedSyncPoll();
  const wrap = document.getElementById("bili-subscribed-progress") || document.getElementById("crawl-progress");
  const bar = document.getElementById("bili-subscribed-progress-bar") || document.getElementById("crawl-progress-bar");
  subscribedSyncTimer = setInterval(() => {
    fetch(`${API_BASE}/crawl/status`, { credentials: "include" })
      .then(r => r.json())
      .then(res => {
        if (!res.ok) return;
        if (res.running && res.job === "sync_subscribed") {
          if (msgEl) msgEl.textContent = res.message || "同步中…";
          if (bar) { bar.classList.remove("indeterminate"); bar.style.width = (res.pages > 0 ? Math.min(100, Math.round((res.page / res.pages) * 100)) : 30) + "%"; }
        } else if (!res.running) {
          stopSubscribedSyncPoll();
          if (wrap) wrap.style.display = "none";
          if (msgEl) msgEl.textContent = res.message || "同步完成";
          loadBilibiliSubscribed();
        }
      })
      .catch(() => {});
  }, 2000);
}

// 追番分页状态（独立于番剧列表的全局变量）
let subPage = 1;
let subPageSize = 20;
let subAllItems = [];

function renderSubscribedPageItems() {
  const listEl = document.getElementById("bili-subscribed-list");
  if (!listEl) return;
  const total = subAllItems.length;
  const totalPages = Math.max(1, Math.ceil(total / subPageSize));
  if (subPage > totalPages) subPage = totalPages;
  const start = (subPage - 1) * subPageSize;
  const pageItems = subAllItems.slice(start, start + subPageSize);
  if (!pageItems.length) {
    listEl.innerHTML = "<p style='color:#1f2937'>暂无追番，或请先使用 B 站扫码登录</p>";
  } else {
    listEl.innerHTML = pageItems.map(item => {
      const href = item.media_id ? `https://www.bilibili.com/bangumi/media/md${item.media_id}` : `https://www.bilibili.com/bangumi/play/ss${item.season_id || ''}`;
      return `
        <a class="card" href="${href}" target="_blank" rel="noopener" style="text-decoration:none;color:inherit;display:block">
          <img src="${normalizeCoverUrl(item.cover) || ''}" alt="${escapeHtml(item.title)}" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><rect fill=%22%23e5e7eb%22 width=%22100%22 height=%22100%22/><text x=%2250%22 y=%2255%22 fill=%22%23374151%22 text-anchor=%22middle%22>无图</text></svg>'">
          <div class="card-body">
            <div class="card-title">${escapeHtml(item.title)}</div>
            <div class="card-meta">播放 ${formatNum(item.play_count)} · 追番 ${formatNum(item.follow_count)}${item.new_ep_index ? " · " + escapeHtml(item.new_ep_index) : ""}</div>
          </div>
        </a>`;
    }).join("");
  }
  // 分页导航
  const pagEl = document.getElementById("bili-subscribed-pagination");
  if (pagEl) {
    if (totalPages <= 1) {
      pagEl.innerHTML = "";
    } else {
      pagEl.innerHTML = `
        <button ${subPage <= 1 ? "disabled" : ""} data-subpage="${subPage - 1}">上一页</button>
        <span style="align-self:center">第 ${subPage} / ${totalPages} 页，共 ${total} 条</span>
        <button ${subPage >= totalPages ? "disabled" : ""} data-subpage="${subPage + 1}">下一页</button>
      `;
      pagEl.querySelectorAll("button[data-subpage]").forEach(btn => {
        btn.addEventListener("click", () => {
          subPage = parseInt(btn.dataset.subpage, 10);
          renderSubscribedPageItems();
          // 切页后滚回追番列表顶部
          const sec = document.getElementById("page-subscribed");
          if (sec) sec.scrollIntoView({ behavior: "smooth", block: "start" });
        });
      });
    }
  }
}

function loadBilibiliSubscribed() {
  const msgEl = document.getElementById("bili-subscribed-msg");
  const listEl = document.getElementById("bili-subscribed-list");
  const chartsWrap = document.getElementById("bili-subscribed-charts");
  const pagEl = document.getElementById("bili-subscribed-pagination");
  if (!msgEl || !listEl) return;
  msgEl.textContent = "加载中…";
  listEl.innerHTML = "";
  if (pagEl) pagEl.innerHTML = "";
  if (chartsWrap) chartsWrap.classList.add("hidden");
  fetch(`${API_BASE}/user/bilibili-subscribed-bangumi`, { credentials: "include" })
    .then(r => r.json())
    .then(res => {
      if (!res.ok) {
        msgEl.textContent = res.error || "加载失败";
        return;
      }
      subAllItems = (res.items || []).filter(Boolean);
      subPage = 1;
      msgEl.textContent = subAllItems.length ? `共 ${subAllItems.length} 部追番` : "";
      if (!subAllItems.length) {
        listEl.innerHTML = "<p style='color:#1f2937'>暂无追番，或请先使用 B 站扫码登录</p>";
        return;
      }
      renderSubscribedPageItems();
      drawBilibiliSubscribedCharts(subAllItems);
    })
    .catch(() => { msgEl.textContent = "请求失败"; });
}

document.getElementById("btn-load-bili-subscribed")?.addEventListener("click", loadBilibiliSubscribed);

const btnTagRecRefresh = document.getElementById("btn-tag-recommend-refresh");
if (btnTagRecRefresh) {
  btnTagRecRefresh.addEventListener("click", () => loadTagRecommendations());
}

document.getElementById("btn-sync-subscribed")?.addEventListener("click", () => {
  const msgEl = document.getElementById("bili-subscribed-msg");
  if (!msgEl) return;
  msgEl.textContent = "正在启动同步…";
  fetch(`${API_BASE}/crawl/sync-subscribed`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" } })
    .then(r => r.json())
    .then(res => {
      if (res.ok) {
        msgEl.textContent = res.message || "已开始同步，请稍候…";
        pollCrawlStatus(msgEl);
      } else {
        msgEl.textContent = res.error || "同步失败";
      }
    })
    .catch(() => { msgEl.textContent = "请求失败"; });
});

document.getElementById("btn-login").addEventListener("click", () => {
  const username = document.getElementById("login-username").value.trim();
  const password = document.getElementById("login-password").value;
  document.getElementById("login-error").textContent = "";
  if (!username || !password) { document.getElementById("login-error").textContent = "请输入用户名和密码"; return; }
  fetch(`${AUTH_BASE}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ username, password }),
  })
    .then(r => r.json())
    .then(res => {
      if (res.ok) loadUserPage();
      else document.getElementById("login-error").textContent = res.error || "登录失败";
    });
});

document.getElementById("btn-register").addEventListener("click", () => {
  const username = document.getElementById("login-username").value.trim();
  const password = document.getElementById("login-password").value;
  document.getElementById("login-error").textContent = "";
  if (!username || !password) { document.getElementById("login-error").textContent = "请输入用户名和密码"; return; }
  fetch(`${AUTH_BASE}/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ username, password }),
  })
    .then(r => r.json())
    .then(res => {
      if (res.ok) loadUserPage();
      else document.getElementById("login-error").textContent = res.error || "注册失败";
    });
});

document.getElementById("btn-logout").addEventListener("click", () => {
  fetch(`${AUTH_BASE}/logout`, { method: "POST", credentials: "include" })
    .then(() => { window.location.replace("/login"); });
});

// ---------- 工具 ----------
// B 站封面：补全协议；来自 B 站 CDN 的图走代理避免 403（Referer 校验）
function normalizeCoverUrl(url) {
  if (!url || typeof url !== "string") return "";
  const u = url.trim();
  const full = u.startsWith("//") ? "https:" + u : u;
  if (/^https?:\/\/(i0\.hdslb\.com|i\.hdslb\.com)\//.test(full)) {
    return API_BASE + "/cover-proxy?url=" + encodeURIComponent(full);
  }
  return full;
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}
function formatNum(n) {
  if (n == null) return "-";
  if (n >= 1e8) return (n / 1e8).toFixed(1) + "亿";
  if (n >= 1e4) return (n / 1e4).toFixed(1) + "万";
  return String(n);
}

// 初始化：未登录跳转到登录页 /login，已登录则显示主界面并加载列表
fetch(`${AUTH_BASE}/me`, { credentials: "include" })
  .then(r => r.json())
  .then(res => {
    if (!res.user) {
      window.location.replace("/login");
      return;
    }
    window.currentUser = res.user;
    document.getElementById("user-name").textContent = res.user.username;
    document.getElementById("user-name").classList.remove("hidden");
    document.getElementById("btn-logout").classList.remove("hidden");
    applyAdminNav(res.user);
    loadUserPage();
    showPage("home");
    loadList();
  });

// ---------- 后台管理（仅管理员） ----------
let adminCrawlTimer = null;

function stopAdminCrawlPoll() {
  if (adminCrawlTimer) { clearInterval(adminCrawlTimer); adminCrawlTimer = null; }
}

function adminPollCrawlStatus(msgEl) {
  stopAdminCrawlPoll();
  adminCrawlTimer = setInterval(() => {
    fetch(`/admin/crawl/status`, { credentials: "include" })
      .then(r => r.json())
      .then(res => {
        if (!res.ok) return;
        renderCrawlProgress(res, { wrap: "admin-crawl-progress", bar: "admin-crawl-progress-bar", msg: "admin-crawl-msg" });
        if (!res.running) {
          stopAdminCrawlPoll();
          document.getElementById("admin-btn-crawl-start").disabled = false;
          document.getElementById("admin-btn-refresh-db").disabled = false;
          document.getElementById("admin-btn-sync-subscribed").disabled = false;
          loadAdminOverview();
        }
      })
      .catch(() => {});
  }, 2000);
}

function loadAdminOverview() {
  fetch(`/admin/overview`, { credentials: "include" })
    .then(r => r.json())
    .then(res => {
      if (!res.ok) { document.getElementById("admin-overview").textContent = "加载失败：" + (res.error || ""); return; }
      const s = res.stats;
      const el = document.getElementById("admin-overview");
      const items = [
        ["番剧总数", s.bangumi_count],
        ["分集总数", s.episode_count],
        ["标签数", s.tag_count],
        ["注册用户", s.user_count],
        ["管理员", s.admin_count],
        ["收藏数", s.favorite_count],
        ["快照数", s.snapshot_count],
      ];
      el.innerHTML = items.map(([k, v]) =>
        `<span style="background:#f1f5f9;border-radius:6px;padding:8px 14px"><b>${k}</b><br><span style="font-size:18px">${v}</span></span>`
      ).join("");
      // 采集状态显示（若有任务运行中，进入页面即显示进度条并轮询）
      if (res.crawl && res.crawl.running) {
        document.getElementById("admin-btn-crawl-start").disabled = true;
        document.getElementById("admin-btn-refresh-db").disabled = true;
        document.getElementById("admin-btn-sync-subscribed").disabled = true;
        renderCrawlProgress(res.crawl, { wrap: "admin-crawl-progress", bar: "admin-crawl-progress-bar", msg: "admin-crawl-msg" });
        adminPollCrawlStatus(document.getElementById("admin-crawl-msg"));
      }
    })
    .catch(() => {});
}

function loadAdminUsers() {
  fetch(`/admin/users`, { credentials: "include" })
    .then(r => r.json())
    .then(res => {
      const tbody = document.getElementById("admin-user-list");
      if (!res.ok) { tbody.innerHTML = `<tr><td colspan="6">加载失败：${escapeHtml(res.error || "")}</td></tr>`; return; }
      tbody.innerHTML = res.users.map(u => `
        <tr style="border-bottom:1px solid #f1f5f9">
          <td style="padding:6px">${u.id}</td>
          <td style="padding:6px">${escapeHtml(u.username)}</td>
          <td style="padding:6px">${u.is_admin ? '<span style="color:#b45309;font-weight:600">管理员</span>' : "普通用户"}</td>
          <td style="padding:6px">${u.bilibili_uid ? "已绑定" : "-"}${u.has_cookie ? " / 有Cookie" : ""}</td>
          <td style="padding:6px">${(u.created_at || "").replace("T", " ").slice(0, 19)}</td>
          <td style="padding:6px">
            <button type="button" data-act="toggle" data-id="${u.id}" data-name="${escapeHtml(u.username)}">${u.is_admin ? "取消管理员" : "设为管理员"}</button>
            <button type="button" data-act="del" data-id="${u.id}" data-name="${escapeHtml(u.username)}" style="margin-left:6px;color:#b91c1c">删除</button>
          </td>
        </tr>`).join("");
      tbody.querySelectorAll("button[data-act]").forEach(btn => {
        btn.addEventListener("click", () => {
          const act = btn.dataset.act;
          const uid = btn.dataset.id;
          const uname = btn.dataset.name;
          if (act === "toggle") {
            fetch(`/admin/users/${uid}/toggle-admin`, { method: "POST", credentials: "include" })
              .then(r => r.json())
              .then(res => {
                if (!res.ok) { alert("操作失败：" + (res.error || "")); return; }
                loadAdminUsers(); loadAdminOverview();
              });
          } else if (act === "del") {
            if (!confirm(`确定删除用户「${uname}」？该操作不可恢复。`)) return;
            fetch(`/admin/users/${uid}`, { method: "DELETE", credentials: "include" })
              .then(r => r.json())
              .then(res => {
                if (!res.ok) { alert("操作失败：" + (res.error || "")); return; }
                loadAdminUsers(); loadAdminOverview();
              });
          }
        });
      });
    })
    .catch(() => {});
}

function loadAdminPage() {
  const user = window.currentUser;
  if (!user || !user.is_admin) {
    alert("需要管理员权限");
    showPage("home");
    return;
  }
  loadAdminOverview();
  loadAdminUsers();
  loadAdminVisits();
  // 后台 Cookie 管理：显示当前状态（同个人中心的绑定状态检查复用）
  loadBilibiliCookieStatus();
}

let adminVisitChart = null;

function loadAdminVisits() {
  const summaryEl = document.getElementById("admin-visit-summary");
  const chartEl = document.getElementById("admin-visit-chart");
  if (!summaryEl || !chartEl) return;
  fetch(`/admin/stats/visits?days=14`, { credentials: "include" })
    .then(r => r.json())
    .then(res => {
      if (!res.ok) { summaryEl.innerHTML = `<span style="color:#dc2626">加载失败：${escapeHtml(res.error || "")}</span>`; return; }
      // 今日汇总卡片
      const t = res.today;
      summaryEl.innerHTML = `
        <span style="background:#f1f5f9;border-radius:6px;padding:8px 14px"><b>今日访问</b><br><span style="font-size:18px">${t.pv}</span> 次</span>
        <span style="background:#f1f5f9;border-radius:6px;padding:8px 14px"><b>今日访客</b><br><span style="font-size:18px">${t.uv}</span> 人</span>
        <span style="background:#f1f5f9;border-radius:6px;padding:8px 14px"><b>近 ${res.days} 天总访问</b><br><span style="font-size:18px">${res.total.pv}</span> 次</span>
        <span style="background:#f1f5f9;border-radius:6px;padding:8px 14px"><b>近 ${res.days} 天总访客</b><br><span style="font-size:18px">${res.total.uv}</span> 人</span>
      `;
      // 折线图
      const dates = res.series.map(s => s.date.slice(5));
      const pv = res.series.map(s => s.pv);
      const uv = res.series.map(s => s.uv);
      if (typeof echarts === "undefined") {
        chartEl.innerHTML = "<p style='color:#6b7280;font-size:12px'>图表库未加载</p>";
        return;
      }
      if (adminVisitChart) { adminVisitChart.dispose(); adminVisitChart = null; }
      adminVisitChart = ensureChart(chartEl);
      adminVisitChart.setOption({
        tooltip: { trigger: "axis" },
        legend: { data: ["访问量 (PV)", "访客数 (UV)"] },
        grid: { left: 40, right: 20, top: 40, bottom: 30 },
        xAxis: { type: "category", data: dates },
        yAxis: { type: "value", minInterval: 1 },
        series: [
          { name: "访问量 (PV)", type: "line", smooth: true, data: pv, itemStyle: { color: "#0284c7" }, areaStyle: { opacity: 0.1 } },
          { name: "访客数 (UV)", type: "line", smooth: true, data: uv, itemStyle: { color: "#16a34a" } },
        ],
      });
    })
    .catch(() => { summaryEl.innerHTML = "<span style='color:#dc2626'>加载失败</span>"; });
}

document.addEventListener("DOMContentLoaded", () => {
  const btnStart = document.getElementById("admin-btn-crawl-start");
  if (btnStart) btnStart.addEventListener("click", () => {
    const year = document.getElementById("admin-crawl-year").value || null;
    const season = document.getElementById("admin-crawl-season").value || null;
    const pages = parseInt(document.getElementById("admin-crawl-pages").value, 10) || 2;
    const delay = parseFloat(document.getElementById("admin-crawl-delay").value) || 3;
    const msg = document.getElementById("admin-crawl-msg");
    const bar = document.getElementById("admin-crawl-progress-bar");
    document.getElementById("admin-crawl-progress").style.display = "block";
    bar.classList.add("indeterminate");
    msg.textContent = "正在启动采集…";
    btnStart.disabled = true;
    fetch(`/admin/crawl/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ year: year || null, season: season ? parseInt(season, 10) : null, pages, delay }),
    })
      .then(r => r.json())
      .then(res => {
        msg.textContent = res.message || "已提交";
        if (res.using_bilibili_cookie) msg.textContent += "（使用 B 站 Cookie）";
        if (res.ok) {
          adminPollCrawlStatus(msg);
        } else {
          btnStart.disabled = false;
        }
      })
      .catch(() => { msg.textContent = "请求失败"; btnStart.disabled = false; });
  });

  const btnRefresh = document.getElementById("admin-btn-refresh-db");
  if (btnRefresh) btnRefresh.addEventListener("click", () => {
    const msg = document.getElementById("admin-crawl-msg");
    const bar = document.getElementById("admin-crawl-progress-bar");
    document.getElementById("admin-crawl-progress").style.display = "block";
    bar.classList.add("indeterminate");
    msg.textContent = "正在启动库内更新…";
    btnRefresh.disabled = true;
    fetch(`/admin/crawl/refresh-in-db`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ delay: parseFloat(document.getElementById("admin-crawl-delay").value) || 4 }),
    })
      .then(r => r.json())
      .then(res => {
        msg.textContent = res.message || "已提交";
        if (res.ok) adminPollCrawlStatus(msg);
        else btnRefresh.disabled = false;
      })
      .catch(() => { msg.textContent = "请求失败"; btnRefresh.disabled = false; });
  });

  const btnSync = document.getElementById("admin-btn-sync-subscribed");
  if (btnSync) btnSync.addEventListener("click", () => {
    const msg = document.getElementById("admin-crawl-msg");
    const bar = document.getElementById("admin-crawl-progress-bar");
    document.getElementById("admin-crawl-progress").style.display = "block";
    bar.classList.add("indeterminate");
    msg.textContent = "正在启动追番同步…";
    btnSync.disabled = true;
    fetch(`/admin/crawl/sync-subscribed`, {
      method: "POST",
      credentials: "include",
    })
      .then(r => r.json())
      .then(res => {
        msg.textContent = res.message || "已提交";
        if (res.ok) adminPollCrawlStatus(msg);
        else btnSync.disabled = false;
      })
      .catch(() => { msg.textContent = "请求失败"; btnSync.disabled = false; });
  });
});
