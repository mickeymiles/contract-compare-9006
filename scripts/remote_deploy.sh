#!/usr/bin/env bash
# ═════════════════════════════════════════════
# 服务器端部署执行脚本（GitHub Actions CD 调用）
# 职责：安装依赖 → 重启 systemd 服务 → 健康检查
# 用法：在服务器部署目录内执行  bash scripts/remote_deploy.sh
# ═════════════════════════════════════════════
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${PORT:-9006}"
SERVICE="${SERVICE:-neuops-9006}"
# 服务实际使用的 venv（systemd ExecStart 指向 recon venv）
PYTHON_BIN="${PYTHON_BIN:-/home/ubuntu/recon/.venv/bin/python3}"

echo "═══ 远端部署 $DEPLOY_DIR (端口 $PORT / 服务 $SERVICE) ═══"

# 1. 安装依赖（用服务实际 venv，依赖文件位于 backend/）
"$PYTHON_BIN" -m pip install -r "$DEPLOY_DIR/backend/requirements.txt"

# 2. 重启 systemd 服务
sudo systemctl restart "$SERVICE"
sleep 2

# 2.5 客户/项目敏感信息清理（清空 fund_metrics 客户名/项目名 + 就地删除 xlsx 敏感列）
if [ -f "$DEPLOY_DIR/scripts/clean_privacy.py" ]; then
  echo "═══ 清理客户/项目敏感信息 ═══"
  "$PYTHON_BIN" "$DEPLOY_DIR/scripts/clean_privacy.py" || echo "⚠️ 清理脚本执行异常（不影响服务启动）"
fi

# 3. 健康检查（9006 首页返回 200 即视为存活）
echo "═══ 健康检查 http://127.0.0.1:$PORT/ ═══"
for i in $(seq 1 20); do
  if curl -fsS -m 3 "http://127.0.0.1:$PORT/" >/dev/null 2>&1; then
    echo "✅ 服务健康 (${i}x3s)"
    exit 0
  fi
  sleep 3
done

echo "❌ 健康检查超时，部署失败" >&2
exit 1
