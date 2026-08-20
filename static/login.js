/**
 * 登录页：账号密码登录（默认视图）+ 注册（切换视图）+ B 站扫码（点按钮展开二维码）。
 * 扫码成功但未绑定系统账号时，显示绑定面板（绑定已有账号 / 注册新账号并绑定）。
 */
const API_BASE = "/api";
const AUTH_BASE = "/auth";

// 已登录用户访问 /login 时直接进入首页
fetch(`${AUTH_BASE}/me`, { credentials: "include" })
  .then(r => r.json())
  .then(res => { if (res.user) window.location.replace("/"); });

let gateBiliQrPollTimer = null;
let currentBindToken = null;

function stopGateBiliQrPoll() {
  if (gateBiliQrPollTimer) { clearInterval(gateBiliQrPollTimer); gateBiliQrPollTimer = null; }
}

// ---------- 视图切换：登录 ⇄ 注册 ----------
function showLoginView() {
  document.getElementById("view-login").classList.remove("hidden");
  document.getElementById("view-register").classList.add("hidden");
  document.getElementById("pw-error").textContent = "";
}
function showRegisterView() {
  stopGateBiliQrPoll();
  document.getElementById("view-login").classList.add("hidden");
  document.getElementById("view-register").classList.remove("hidden");
  document.getElementById("reg-error").textContent = "";
}
document.getElementById("btn-pw-register").addEventListener("click", showRegisterView);
document.getElementById("link-back-login").addEventListener("click", (e) => { e.preventDefault(); showLoginView(); });

// ---------- 账号密码登录 ----------
document.getElementById("pw-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const username = document.getElementById("pw-username").value.trim();
  const password = document.getElementById("pw-password").value;
  const errEl = document.getElementById("pw-error");
  if (!username || !password) { errEl.textContent = "请输入用户名和密码"; return; }
  errEl.textContent = "";
  const btn = document.getElementById("btn-pw-login");
  btn.disabled = true;
  btn.textContent = "登录中...";
  fetch(`${AUTH_BASE}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ username, password }),
  })
    .then(r => r.json())
    .then(res => {
      if (res.ok) {
        btn.textContent = "登录成功，跳转中...";
        window.location.replace("/");
      } else {
        btn.disabled = false;
        btn.textContent = "登录";
        errEl.textContent = res.error || "登录失败，请检查用户名和密码";
      }
    })
    .catch(() => {
      btn.disabled = false;
      btn.textContent = "登录";
      errEl.textContent = "网络异常，请重试";
    });
});

// ---------- 注册 ----------
document.getElementById("reg-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const username = document.getElementById("reg-username").value.trim();
  const password = document.getElementById("reg-password").value;
  const email = document.getElementById("reg-email").value.trim();
  const errEl = document.getElementById("reg-error");
  if (!username || !password) { errEl.textContent = "请输入用户名和密码"; return; }
  errEl.textContent = "";
  const btn = document.getElementById("btn-reg-submit");
  btn.disabled = true;
  btn.textContent = "注册中...";
  fetch(`${AUTH_BASE}/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ username, password, email }),
  })
    .then(r => r.json())
    .then(res => {
      if (res.ok) {
        btn.textContent = "注册成功，跳转中...";
        window.location.replace("/");
      } else {
        btn.disabled = false;
        btn.textContent = "注册";
        errEl.textContent = res.error || "注册失败，请重试";
      }
    })
    .catch(() => {
      btn.disabled = false;
      btn.textContent = "注册";
      errEl.textContent = "网络异常，请重试";
    });
});

// ---------- 绑定面板（扫码成功但未绑定） ----------
function showBindView(bindToken, bilibiliUid) {
  stopGateBiliQrPoll();
  currentBindToken = bindToken;
  document.getElementById("bind-bili-uid").textContent = bilibiliUid != null ? bilibiliUid : "未知";
  document.getElementById("bind-error").textContent = "";
  document.getElementById("gate-bind-view").classList.remove("hidden");
}

let bindMode = "bind_existing";
function setBindMode(mode) {
  bindMode = mode;
  document.getElementById("tab-bind-existing").classList.toggle("active", mode === "bind_existing");
  document.getElementById("tab-register").classList.toggle("active", mode === "register");
  document.getElementById("bind-email").classList.toggle("hidden", mode !== "register");
  document.getElementById("bind-password").setAttribute("autocomplete", mode === "register" ? "new-password" : "current-password");
}
document.getElementById("tab-bind-existing").addEventListener("click", () => setBindMode("bind_existing"));
document.getElementById("tab-register").addEventListener("click", () => setBindMode("register"));

document.getElementById("bind-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const username = document.getElementById("bind-username").value.trim();
  const password = document.getElementById("bind-password").value;
  const email = document.getElementById("bind-email").value.trim();
  const errEl = document.getElementById("bind-error");
  if (!username || !password) { errEl.textContent = "请输入用户名和密码"; return; }
  errEl.textContent = "";
  const btn = document.getElementById("btn-bind-submit");
  btn.disabled = true;
  btn.textContent = "绑定中...";
  fetch(`${AUTH_BASE}/bind`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({
      bind_token: currentBindToken,
      mode: bindMode,
      username,
      password,
      email: bindMode === "register" ? email : undefined,
    }),
  })
    .then(r => r.json())
    .then(res => {
      if (res.ok) {
        btn.textContent = "绑定成功，跳转中...";
        window.location.replace("/");
      } else {
        btn.disabled = false;
        btn.textContent = "绑定并登录";
        errEl.textContent = res.error || "绑定失败，请重试";
      }
    })
    .catch(() => {
      btn.disabled = false;
      btn.textContent = "绑定并登录";
      errEl.textContent = "网络异常，请重试";
    });
});

// ---------- B 站扫码登录（点按钮后在下边展开二维码） ----------
document.getElementById("gate-btn-show-qr").addEventListener("click", () => {
  const wrap = document.getElementById("gate-qr-wrap");
  const img = document.getElementById("gate-qr-img");
  const statusEl = document.getElementById("gate-qr-status");
  stopGateBiliQrPoll();
  currentBindToken = null;
  statusEl.textContent = "正在获取二维码...";
  wrap.classList.remove("hidden");
  fetch(`${API_BASE}/bilibili-qr/generate`, { credentials: "include" })
    .then(r => r.json())
    .then(res => {
      if (!res.ok || !res.qrcode_key) {
        statusEl.textContent = "获取失败，请重试";
        return;
      }
      if (res.qrcode_image_base64) {
        img.src = "data:image/png;base64," + res.qrcode_image_base64;
        img.style.display = "block";
      } else {
        img.style.display = "none";
        statusEl.textContent = "请使用 B 站 App 扫描（若未显示图片请复制链接到浏览器）";
      }
      statusEl.textContent = "请使用 B 站 App 扫描二维码";
      const key = res.qrcode_key;
      const startPoll = () => {
        gateBiliQrPollTimer = setInterval(() => {
          fetch(`${API_BASE}/bilibili-qr/poll?qrcode_key=${encodeURIComponent(key)}`, { credentials: "include" })
            .then(r => r.json())
            .then(pollRes => {
              if (pollRes.status === "done") {
                if (pollRes.needs_bind) {
                  // 未绑定：显示绑定面板
                  showBindView(pollRes.bind_token, pollRes.bilibili_uid);
                } else {
                  stopGateBiliQrPoll();
                  statusEl.textContent = "登录成功，正在跳转...";
                  window.location.replace("/");
                }
              } else if (pollRes.status === "confirm") {
                statusEl.textContent = "已扫码，请在手机上确认登录";
              } else if (pollRes.status === "timeout") {
                stopGateBiliQrPoll();
                statusEl.textContent = "二维码已过期，请重新点击「显示登录二维码」";
              } else if (pollRes.ok === false && pollRes.error) {
                stopGateBiliQrPoll();
                statusEl.textContent = pollRes.error || "登录失败，请重试";
              }
            })
            .catch(() => {
              if (!gateBiliQrPollTimer) return;
              statusEl.textContent = "网络异常，请重试";
            });
        }, 2000);
      };
      setTimeout(startPoll, 1200);
    })
    .catch(() => { statusEl.textContent = "请求失败"; });
});
