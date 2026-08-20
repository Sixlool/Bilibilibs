#!/usr/bin/env bash
# Bilibilibs 一键启动脚本（内网穿透公网展示）
# 用法：./start-public.sh [port]
# 依赖：系统 MySQL 已启动、venv 已装好、cloudflared 已安装
set -e
cd "$(dirname "$0")"

PORT="${1:-5000}"
LOG_DIR="logs"
mkdir -p "$LOG_DIR"

# 1. 确认 MySQL
if ! mysqladmin status >/dev/null 2>&1; then
  echo ">> 启动 MySQL..."
  service mysql start >/dev/null 2>&1 || systemctl start mysql >/dev/null 2>&1 || true
  sleep 3
fi

# 2. 启动 gunicorn（若未运行）
if ! pgrep -f "gunicorn.*${PORT}" >/dev/null; then
  echo ">> 启动 gunicorn (127.0.0.1:${PORT})..."
  FLASK_ENV=production \
  MYSQL_PASSWORD="${MYSQL_PASSWORD:-123456}" \
  SECRET_KEY="${SECRET_KEY:-$(python3 -c 'import secrets; print(secrets.token_hex(32))')}" \
  ADMIN_USERNAME="${ADMIN_USERNAME:-admin}" \
  nohup .venv/bin/gunicorn -w 2 -b "127.0.0.1:${PORT}" --timeout 120 run:app \
    >> "$LOG_DIR/gunicorn.log" 2>&1 &
  sleep 5
fi
echo ">> 本地验证: $(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PORT}/" || echo 'FAIL')"

# 3. 启动 cloudflared 隧道（若未运行）
if ! pgrep -f "cloudflared tunnel" >/dev/null; then
  echo ">> 启动 cloudflared 快速隧道..."
  nohup cloudflared tunnel --url "http://127.0.0.1:${PORT}" --no-autoupdate \
    >> "$LOG_DIR/cloudflared.log" 2>&1 &
  sleep 10
fi

URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG_DIR/cloudflared.log" | head -1)
echo ""
echo "=========================================="
echo "  Bilibilibs 公网地址: ${URL:-<请查看 logs/cloudflared.log>}"
echo "  本地地址: http://127.0.0.1:${PORT}"
echo "  管理员注册用户名: ${ADMIN_USERNAME:-admin}"
echo "=========================================="
