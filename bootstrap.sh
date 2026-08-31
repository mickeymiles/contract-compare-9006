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
python -c "from backend.models import init_db; init_db(); print('    核心域建表完成')"
# 采购域（procurement_task 双流列 / mail_inquiry_task 等）独立于 models.init_db，
# 漏掉会导致备件采购流程因缺列而不可用，必须一并初始化（幂等，可重复执行）
python -c "from backend.procurement_models import init_procurement_db; init_procurement_db(); print('    采购域建表/补列完成')"

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

# 采购域 schema 校验：备件采购流程强依赖双流列与 mail_inquiry_task 表，
# 缺列时页面/接口会在运行期才炸，这里提前失败（快速失败原则）
echo "==> 采购域 schema 校验"
python -c "
from backend.models import get_db

REQUIRED_COLUMNS = ('source', 'internal_status', 'external_status')
REQUIRED_TABLES = ('procurement_task', 'mail_inquiry_task', 'procurement_supplier', 'procurement_spare_part')

conn = get_db()
try:
    tables = {r[0] for r in conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")}
    ok = True
    for t in REQUIRED_TABLES:
        if t not in tables:
            print(f'  [FAIL] 缺少表: {t}')
            ok = False
        else:
            cols = [r[1] for r in conn.execute(f'PRAGMA table_info({t})')]
            print(f'  [ OK ] {t}: {len(cols)} 列')
    cols = [r[1] for r in conn.execute('PRAGMA table_info(procurement_task)')]
    missing = [c for c in REQUIRED_COLUMNS if c not in cols]
    if missing:
        print(f'  [FAIL] procurement_task 缺少关键列: {missing}')
        ok = False
    else:
        print(f'  [ OK ] procurement_task 关键列齐全: {REQUIRED_COLUMNS}')
    if not ok:
        raise SystemExit('采购域 schema 校验未通过，请重新执行本脚本')
finally:
    conn.close()
print('  采购域 schema 校验通过')
"

if [ "${1:-}" = "--run" ]; then
    PORT="${CC_PORT:-9006}"
    echo "==> 启动服务: http://0.0.0.0:${PORT}"
    exec python backend/main.py
fi

echo "✅ 初始化完成。可运行: python backend/main.py （端口默认 9006，可用 CC_PORT 覆盖）"
