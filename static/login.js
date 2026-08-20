/**
 * 登录页：仅 B 站扫码登录，成功则跳转到首页 /
 */
const API_BASE = "/api";
const AUTH_BASE = "/auth";

// 已登录用户访问 /login 时直接进入首页
fetch(`${AUTH_BASE}/me`, { credentials: "include" })
  .then(r => r.json())
  .then(res => { if (res.user) window.location.replace("/"); });

let gateBiliQrPollTimer = null;
function stopGateBiliQrPoll() {
  if (gateBiliQrPollTimer) { clearInterval(gateBiliQrPollTimer); gateBiliQrPollTimer = null; }
}

document.getElementById("gate-btn-show-qr").addEventListener("click", () => {
  const wrap = document.getElementById("gate-qr-wrap");
  const img = document.getElementById("gate-qr-img");
  const statusEl = document.getElementById("gate-qr-status");
  stopGateBiliQrPoll();
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
                stopGateBiliQrPoll();
                statusEl.textContent = "登录成功，正在跳转...";
                window.location.replace("/");
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

