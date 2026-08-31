#!/usr/bin/env bash
# ═══════════════════════════════════════════
# 服务器端部署执行脚本（GitHub Actions CD / 手动 deploy.sh 调用）
# 职责：确保 venv → 安装依赖 → 安装并重启 systemd 服务 → 健康检查
# 用法：在服务器部署目录内执行  bash scripts/remote_deploy.sh
# ═══════════════════════════════════════════
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${PORT:-9006}"
SERVICE="${SERVICE:-neuops-9006}"
# venv 放在部署目录内（rsync 已排除 .venv，首次需自建）
PYTHON_BIN="${PYTHON_BIN:-$DEPLOY_DIR/.venv/bin/python3}"

echo "═══ 远端部署 $DEPLOY_DIR (端口 $PORT / 服务 $SERVICE) ═══"

# 0. 确保 venv 存在（修复：原硬编码 /home/ubuntu/recon/.venv 在此部署目录不存在）
if [ ! -x "$PYTHON_BIN" ]; then
  echo "── 创建 venv：$DEPLOY_DIR/.venv"
  python3 -m venv "$DEPLOY_DIR/.venv"
fi
PYTHON_BIN="$DEPLOY_DIR/.venv/bin/python3"

# 1. 安装依赖（依赖文件位于 backend/）
"$PYTHON_BIN" -m pip install --upgrade pip -q
"$PYTHON_BIN" -m pip install -r "$DEPLOY_DIR/backend/requirements.txt" -q

# 2. 安装/更新 systemd 单元（动态写入真实路径，修复 recon 陈旧路径）
UNIT_SRC="$DEPLOY_DIR/scripts/neuops-9006.service"
if [ -f "$UNIT_SRC" ]; then
  sudo install -m 0644 "$UNIT_SRC" /etc/systemd/system/neuops-9006.service
  sudo sed -i "s#__DEPLOY_DIR__#$DEPLOY_DIR#g; s#__PYTHON_BIN__#$PYTHON_BIN#g" /etc/systemd/system/neuops-9006.service
  sudo systemctl daemon-reload
  sudo systemctl enable neuops-9006
fi

# 3. 重启 systemd 服务
sudo systemctl restart "$SERVICE"
sleep 2

# 3.5 客户/项目敏感信息清理（清空 fund_metrics 客户名/项目名 + 就地删除 xlsx 敏感列）
if [ -f "$DEPLOY_DIR/scripts/clean_privacy.py" ]; then
  echo "═══ 清理客户/项目敏感信息 ═══"
  "$PYTHON_BIN" "$DEPLOY_DIR/scripts/clean_privacy.py" || echo "⚠️ 清理脚本执行异常（不影响服务启动）"
fi

# 4. 健康检查（9006 首页返回 200 即视为存活）
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
