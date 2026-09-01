#!/usr/bin/env bash
# ═════════════════════════════════════════════
# 部署脚本：项目管理功能（三层架构：项目→合同→备件）
# 用法：在服务器 contract-compare 目录下执行  bash scripts/deploy_project_mgmt.sh
# ═════════════════════════════════════════════
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DB_PATH="$DEPLOY_DIR/contract_compare.db"
PYTHON_BIN="${PYTHON_BIN:-/home/ubuntu/recon/.venv/bin/python3}"
SERVICE="${SERVICE:-neuops-9006}"

echo "═══ 部署项目管理功能 ═══"
echo "部署目录: $DEPLOY_DIR"
echo "数据库: $DB_PATH"

# 1. 数据库迁移：添加 project_id 列到 procurement_contract（如果不存在）
echo "═══ 步骤1: 数据库迁移 ═══"
$PYTHON_BIN -c "
import sqlite3
conn = sqlite3.connect('$DB_PATH')
c = conn.cursor()

# 检查并添加 project_id 列
c.execute('PRAGMA table_info(procurement_contract)')
cols = [r[1] for r in c.fetchall()]
if 'project_id' not in cols:
    c.execute('ALTER TABLE procurement_contract ADD COLUMN project_id INTEGER DEFAULT 0')
    print('已添加 project_id 列到 procurement_contract')
else:
    print('project_id 列已存在，跳过')

conn.commit()
conn.close()
print('数据库迁移完成')
"

# 2. 运行初始化脚本创建新表
echo "═══ 步骤2: 创建新表 ═══"
cd "$DEPLOY_DIR/backend"
$PYTHON_BIN -c "
from procurement_models import init_procurement_db
init_procurement_db()
print('新表创建完成（procurement_project, procurement_contract_spare_part 等）')
"

# 3. 插入种子数据（如果项目表为空）
echo "═══ 步骤3: 插入项目种子数据 ═══"
$PYTHON_BIN -c "
import sqlite3
conn = sqlite3.connect('$DB_PATH')
c = conn.cursor()

# 检查项目表是否为空
c.execute('SELECT COUNT(*) FROM procurement_project')
count = c.fetchone()[0]

if count == 0:
    seed_projects = [
        ('PRJ-001', '示范项目A期-IT基础设施扩容', '示范客户集团', '数据中心基础设施升级'),
        ('PRJ-002', '运维节点B期扩容', '示范客户集团', '服务器配件扩容项目'),
        ('PRJ-003', '核心机房光模块集中采购', '核心机房运营方', '光模块框架采购'),
        ('PRJ-004', '园区交换机备件及年度维保', '园区管理方', '园区网络运维'),
    ]
    c.executemany('''
        INSERT INTO procurement_project(project_code, project_name, client_name, remark)
        VALUES (?,?,?,?)
    ''', seed_projects)
    print(f'已插入 {len(seed_projects)} 条项目种子数据')
    
    # 将现有合同关联到对应项目
    # PRJ-001 关联 IDZB2607070A
    c.execute('UPDATE procurement_contract SET project_id=(SELECT id FROM procurement_project WHERE project_code=\"PRJ-001\") WHERE contract_no=\"IDZB2607070A\"')
    # PRJ-002 关联 QTZB2603080C  
    c.execute('UPDATE procurement_contract SET project_id=(SELECT id FROM procurement_project WHERE project_code=\"PRJ-002\") WHERE contract_no=\"QTZB2603080C\"')
    # PRJ-003 关联 CGZB2605112B
    c.execute('UPDATE procurement_contract SET project_id=(SELECT id FROM procurement_project WHERE project_code=\"PRJ-003\") WHERE contract_no=\"CGZB2605112B\"')
    print('已将现有合同关联到对应项目')
else:
    print(f'项目表已有 {count} 条记录，跳过种子数据')

conn.commit()
conn.close()
"

# 4. 重启服务
echo "═══ 步骤4: 重启服务 ═══"
sudo systemctl restart "$SERVICE"
sleep 3

# 5. 健康检查
echo "═══ 步骤5: 健康检查 ═══"
for i in $(seq 1 15); do
  if curl -fsS -m 3 "http://127.0.0.1:9006/api/procurement/projects" >/dev/null 2>&1; then
    echo "✅ 项目管理API健康 (${i}x3s)"
    curl -s "http://127.0.0.1:9006/api/procurement/projects" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f'  项目数: {len(d.get(\"data\",[]))}')
"
    echo "═══ 部署完成 ═══"
    exit 0
  fi
  sleep 3
done

echo "❌ 健康检查超时"
exit 1
