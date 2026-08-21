#!/usr/bin/env bash
# Bilibilibs 一键启动脚本
# 用法：./start-public.sh [port] [bind_ip]
#   port    - 监听端口（默认 5000）
#   bind_ip - 绑定地址：0.0.0.0 = 公网直连（需云安全组放行）；127.0.0.1 = 仅本机（默认）
# 公网直连前提：云安全组放行端口 + 域名 A 记录指向服务器公网 IP
set -e
cd "$(dirname "$0")"

PORT="${1:-5000}"
BIND_IP="${2:-127.0.0.1}"
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
  echo ">> 启动 gunicorn (${BIND_IP}:${PORT})..."
  FLASK_ENV=production \
  MYSQL_PASSWORD="${MYSQL_PASSWORD:-123456}" \
  SECRET_KEY="${SECRET_KEY:-$(python3 -c 'import secrets; print(secrets.token_hex(32))')}" \
  ADMIN_USERNAME="${ADMIN_USERNAME:-admin}" \
  CORS_ORIGINS="${CORS_ORIGINS:-}" \
  nohup .venv/bin/gunicorn -w 2 -b "${BIND_IP}:${PORT}" --timeout 120 run:app \
    >> "$LOG_DIR/gunicorn.log" 2>&1 &
  sleep 5
fi
echo ">> 本地验证: $(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PORT}/" || echo 'FAIL')"

echo ""
echo "=========================================="
if [ "$BIND_IP" = "0.0.0.0" ]; then
  echo "  🟢 公网直连模式："
  echo "  域名: http://sxklzyb.cn:${PORT}  (或 http://www.sxklzyb.cn:${PORT})"
  echo "  要求: 域名 A 记录指向服务器公网 IP + 安全组放行 ${PORT} 端口"
  echo "  CORS: 若前端报跨域错，设置环境变量 CORS_ORIGINS=https://sxklzyb.cn"
else
  echo "  仅本机模式: http://127.0.0.1:${PORT}"
  echo "  公网访问需 cloudflared 隧道或改 bind_ip=0.0.0.0"
fi
echo "  管理员注册用户名: ${ADMIN_USERNAME:-admin}"
echo "=========================================="
