#!/usr/bin/env bash
# =============================================================================
# 合同比对系统 - 新环境一键初始化
#
# 功能：
#   1. 创建 Python 虚拟环境并安装依赖
#   2. 初始化数据库（建表）
#   3. 导入脱敏种子数据（seeds/seed_data.sql，幂等）
#   4. 启动服务（可选，默认不启动）
#
# 用法：
#   ./bootstrap.sh            # 仅初始化
#   ./bootstrap.sh --run      # 初始化并启动服务（默认端口 9006，可用 CC_PORT 覆盖）
#   CC_PORT=9006 ./bootstrap.sh --run
# =============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

echo "==> [1/4] 创建虚拟环境并安装依赖"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r backend/requirements.txt

echo "==> [2/4] 初始化数据库（建表）"
python -c "from backend.models import init_db; init_db(); print('建表完成')"

echo "==> [3/4] 导入脱敏种子数据"
if [ ! -f "seeds/seed_data.sql" ]; then
    echo "    未找到 seeds/seed_data.sql，跳过导入（无种子数据）"
else
    python scripts/import_seed.py
fi

echo "==> [4/4] 校验"
python -c "
from backend.models import get_db
conn = get_db()
for t in ['fund_metrics', 'indicator_metrics', 'analysis_snapshots', 'etl_jobs']:
    n = conn.execute(f'SELECT count(*) FROM {t}').fetchone()[0]
    print(f'  {t}: {n} 行')
conn.close()
"

if [ "${1:-}" = "--run" ]; then
    PORT="${CC_PORT:-9006}"
    echo "==> 启动服务: http://0.0.0.0:${PORT}"
    exec python backend/main.py
fi

echo "✅ 初始化完成。可运行: python backend/main.py （端口默认 9006，可用 CC_PORT 覆盖）"
