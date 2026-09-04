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
healthy=0
for i in $(seq 1 20); do
  if curl -fsS -m 3 "http://127.0.0.1:$PORT/" >/dev/null 2>&1; then
    echo "✅ 服务健康 (${i}x3s)"
    healthy=1
    break
  fi
  sleep 3
done

if [ "$healthy" -ne 1 ]; then
  echo "❌ 健康检查超时，部署失败" >&2
  exit 1
fi

# 5. 将部署结果提交进服务器本地 git，防止 git reset/checkout/clean 回滚已部署文件
#    CI 仅 rsync 同步文件、不触碰服务器 git 元数据；此前 HEAD(1207cc1) 长期落后于
#    工作区(rsync 漂移)，一旦有人/脚本执行 git checkout/reset/clean 就会丢失最新部署。
#    此处提交后 HEAD 跟上工作区，任何 git 回滚都不再丢代码。本仓为独立本地仓，不 push。
echo "═══ 提交部署结果到本地 git（防回滚）═══"
cd "$DEPLOY_DIR"
git config user.email "deploy@localhost" 2>/dev/null || true
git config user.name "CI Deploy" 2>/dev/null || true
git add -A
if git diff --cached --quiet; then
  echo "（无新增变更，跳过 commit）"
else
  if git commit -q -m "deploy: $(date +%Y-%m-%dT%H:%M:%S) auto-commit via remote_deploy"; then
    echo "✅ 已提交部署变更 ($(git rev-parse --short HEAD))"
  else
    echo "⚠️ git commit 失败（不影响服务运行）"
  fi
fi

exit 0
