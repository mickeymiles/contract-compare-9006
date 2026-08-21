"""
备品备件采购询比价智能体 — 数据模型与数据库初始化
SQLite, 4 张表: procurement_task / procurement_master_data / procurement_ledger / procurement_op_log
与 contract-compare-9006 现有 models.py 共用同一个 SQLite 文件 (contract_compare.db)

字段定义依据: .trae/documents/备品备件采购询比价智能体设计文档.md 第 4 章
状态枚举依据: 同文档第 3.2 节
"""

import sqlite3
import os
import json
import time
import uuid
from datetime import datetime, timezone, timedelta

# 复用现有 models.py 的 DB 路径（同一 SQLite 文件）
DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
DB_PATH = os.path.join(DB_DIR, 'contract_compare.db')

# 时区：本系统业务在国内，统一用 +08:00
CN_TZ = timezone(timedelta(hours=8))


def get_db():
    """获取数据库连接（与 models.py 一致风格）"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _now_iso():
    """当前时间的 ISO 字符串（北京时区）"""
    return datetime.now(CN_TZ).strftime('%Y-%m-%d %H:%M:%S')


def _ts():
    """当前时间的 unix 时间戳（秒）"""
    return int(time.time())


# ===================== 表 1: 询比价任务 =====================

TASK_STATUS_ENUM = (
    '询比价进行中', '已选型确认', '供应商发货中', '待收货测试', '流程闭环',  # 正常
    '部分供应商超时', '全部供应商超时', '收货测试失败', '任务已取消',  # 异常
)

EMERGENCY_LEVEL_ENUM = ('2h', '4h', '5h')

# 紧急等级 → 截止时长（秒）
EMERGENCY_SECONDS = {
    '2h': 2 * 3600,
    '4h': 4 * 3600,
    '5h': 5 * 3600,
}

TEST_RESULT_ENUM = (None, '通过', '失败')


def init_procurement_db():
    """初始化备件采购 4 张表（幂等，已存在不重建）"""
    conn = get_db()
    c = conn.cursor()

    # 1. 询比价任务表
    c.execute("""
        CREATE TABLE IF NOT EXISTS procurement_task (
            task_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            project_name TEXT DEFAULT '',
            contract_no TEXT DEFAULT '',
            spare_part_model TEXT NOT NULL,
            purchase_qty REAL NOT NULL,
            emergency_level TEXT NOT NULL,
            reply_deadline TEXT NOT NULL,
            inquiry_supplier_list TEXT DEFAULT '[]',
            replied_supplier_quotes TEXT DEFAULT '[]',
            no_reply_supplier TEXT DEFAULT '[]',
            selected_supplier TEXT DEFAULT '{}',
            deal_unit_price REAL DEFAULT 0,
            delivery_time TEXT DEFAULT '',
            logistics_no TEXT DEFAULT '',
            test_result TEXT DEFAULT '',
            task_status TEXT NOT NULL DEFAULT '询比价进行中',
            cancel_reason TEXT DEFAULT '',
            ledger_written INTEGER DEFAULT 0,
            creator TEXT DEFAULT '',
            create_time TEXT NOT NULL,
            updated_at TEXT DEFAULT ''
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_proc_task_status ON procurement_task(task_status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_proc_task_project ON procurement_task(project_id)")

    # 2. 主数据配置表（项目-合同-备件-供应商，管理员维护，业务只读）
    c.execute("""
        CREATE TABLE IF NOT EXISTS procurement_master_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            project_name TEXT DEFAULT '',
            contract_no TEXT DEFAULT '',
            allow_spare_parts TEXT DEFAULT '[]',
            default_suppliers TEXT DEFAULT '[]',
            default_emergency_level TEXT DEFAULT '4h',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_proc_master_project ON procurement_master_data(project_id)")

    # 3. 采购业务台账表（闭环自动写入，结算凭证）
    c.execute("""
        CREATE TABLE IF NOT EXISTS procurement_ledger (
            ledger_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            project_id TEXT DEFAULT '',
            project_name TEXT DEFAULT '',
            contract_no TEXT DEFAULT '',
            spare_part_model TEXT DEFAULT '',
            purchase_qty REAL DEFAULT 0,
            selected_supplier_name TEXT DEFAULT '',
            deal_unit_price REAL DEFAULT 0,
            delivery_time TEXT DEFAULT '',
            logistics_no TEXT DEFAULT '',
            test_result TEXT DEFAULT '',
            task_close_time TEXT DEFAULT '',
            remark TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_proc_ledger_task ON procurement_ledger(task_id)")

    # 4. 操作日志表
    c.execute("""
        CREATE TABLE IF NOT EXISTS procurement_op_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            operator TEXT DEFAULT '',
            action TEXT NOT NULL,
            action_time TEXT DEFAULT (datetime('now','localtime')),
            remark TEXT DEFAULT ''
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_proc_oplog_task ON procurement_op_log(task_id)")

    conn.commit()
    conn.close()


# ===================== Task CRUD =====================

def create_task(*, project_id, project_name, contract_no, spare_part_model,
                purchase_qty, emergency_level, inquiry_supplier_list, creator=''):
    """创建询比价任务实例（Skill-01 调用入口）"""
    if emergency_level not in EMERGENCY_LEVEL_ENUM:
        raise ValueError(f"非法 emergency_level: {emergency_level}")
    now = _now_iso()
    deadline_ts = _ts() + EMERGENCY_SECONDS[emergency_level]
    reply_deadline = datetime.fromtimestamp(deadline_ts, CN_TZ).strftime('%Y-%m-%d %H:%M:%S')
    task_id = f"PROC-{datetime.now(CN_TZ).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
    # 初始未回复 = 全部询价供应商
    suppliers_json = json.dumps(inquiry_supplier_list, ensure_ascii=False)
    no_reply_json = json.dumps(inquiry_supplier_list, ensure_ascii=False)
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO procurement_task
        (task_id, project_id, project_name, contract_no, spare_part_model, purchase_qty,
         emergency_level, reply_deadline, inquiry_supplier_list, no_reply_supplier,
         task_status, creator, create_time, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '询比价进行中', ?, ?, ?)
    """, (task_id, project_id, project_name, contract_no, spare_part_model, purchase_qty,
          emergency_level, reply_deadline, suppliers_json, no_reply_json,
          creator, now, now))
    _add_op_log(c, task_id, creator, 'create_inquiry', f'发起询价，紧急等级 {emergency_level}')
    conn.commit()
    conn.close()
    return get_task(task_id)


def get_task(task_id):
    """按 task_id 查询任务详情"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM procurement_task WHERE task_id=?", (task_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return _row_to_task(row)


def list_tasks(*, status=None, project_id=None, limit=200):
    """列出任务（可按状态/项目过滤）"""
    conn = get_db()
    c = conn.cursor()
    sql = "SELECT * FROM procurement_task"
    where, params = [], []
    if status:
        where.append("task_status=?")
        params.append(status)
    if project_id:
        where.append("project_id=?")
        params.append(project_id)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY create_time DESC LIMIT ?"
    params.append(limit)
    c.execute(sql, params)
    rows = c.fetchall()
    conn.close()
    return [_row_to_task(r) for r in rows]


def update_task_quote(*, task_id, replied_supplier_quotes, no_reply_supplier, all_replied=False):
    """回填报价（Skill-03 调用），并刷新未回复清单"""
    conn = get_db()
    c = conn.cursor()
    now = _now_iso()
    c.execute("""
        UPDATE procurement_task
        SET replied_supplier_quotes=?, no_reply_supplier=?, updated_at=?
        WHERE task_id=?
    """, (json.dumps(replied_supplier_quotes, ensure_ascii=False),
          json.dumps(no_reply_supplier, ensure_ascii=False), now, task_id))
    if all_replied:
        # 全部回复完成，状态保持"询比价进行中"，但飞书会触发"全部收齐"通知
        c.execute("UPDATE procurement_task SET task_status='询比价进行中' WHERE task_id=?", (task_id,))
    conn.commit()
    conn.close()
    return get_task(task_id)


def update_task_status_on_deadline(*, task_id, has_replied, all_timeout):
    """截止时间到达的状态跳转（scheduler 调用）"""
    if all_timeout:
        new_status = '全部供应商超时'
    elif has_replied:
        new_status = '部分供应商超时'
    else:
        return get_task(task_id)  # 不该走到这
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE procurement_task SET task_status=?, updated_at=? WHERE task_id=?",
              (new_status, _now_iso(), task_id))
    _add_op_log(c, task_id, 'system:scheduler', 'deadline_reach',
                f'截止到达，状态置为 {new_status}')
    conn.commit()
    conn.close()
    return get_task(task_id)


def confirm_selection(*, task_id, selected_supplier, deal_unit_price, operator=''):
    """选型确认（Skill-05 调用）：状态 → 已选型确认"""
    conn = get_db()
    c = conn.cursor()
    now = _now_iso()
    c.execute("""
        UPDATE procurement_task
        SET selected_supplier=?, deal_unit_price=?, task_status='已选型确认', updated_at=?
        WHERE task_id=?
    """, (json.dumps(selected_supplier, ensure_ascii=False), deal_unit_price, now, task_id))
    _add_op_log(c, task_id, operator, 'confirm_selection',
                f"选中供应商 {selected_supplier.get('name','')}, 成交单价 {deal_unit_price}")
    conn.commit()
    conn.close()
    return get_task(task_id)


def update_task_delivery(*, task_id, delivery_time, logistics_no, operator='system:mail'):
    """回填发货信息（Skill-06 调用）：状态 → 供应商发货中"""
    conn = get_db()
    c = conn.cursor()
    now = _now_iso()
    c.execute("""
        UPDATE procurement_task
        SET delivery_time=?, logistics_no=?, task_status='供应商发货中', updated_at=?
        WHERE task_id=?
    """, (delivery_time, logistics_no, now, task_id))
    _add_op_log(c, task_id, operator, 'delivery_update',
                f"发货时间 {delivery_time}, 物流 {logistics_no}")
    conn.commit()
    conn.close()
    return get_task(task_id)


def input_test_result(*, task_id, test_result, remark='', operator=''):
    """测试结果录入（Skill-07 调用）
    通过 → 状态 流程闭环 + 触发台账写入；失败 → 收货测试失败
    """
    if test_result not in ('通过', '失败'):
        raise ValueError(f"非法 test_result: {test_result}")
    new_status = '流程闭环' if test_result == '通过' else '收货测试失败'
    conn = get_db()
    c = conn.cursor()
    now = _now_iso()
    c.execute("""
        UPDATE procurement_task SET test_result=?, task_status=?, updated_at=? WHERE task_id=?
    """, (test_result, new_status, now, task_id))
    _add_op_log(c, task_id, operator, 'input_test_result',
                f"测试结果 {test_result} 备注 {remark}")
    task_row = c.execute("SELECT * FROM procurement_task WHERE task_id=?", (task_id,)).fetchone()
    conn.commit()
    conn.close()
    if test_result == '通过':
        write_ledger(task_id)  # 闭环自动写台账
    return _row_to_task(task_row)


def cancel_task(*, task_id, cancel_reason, operator=''):
    """任务取消（Skill-09 调用）：状态 → 任务已取消，不写台账"""
    conn = get_db()
    c = conn.cursor()
    now = _now_iso()
    c.execute("""
        UPDATE procurement_task
        SET task_status='任务已取消', cancel_reason=?, updated_at=? WHERE task_id=?
    """, (cancel_reason, now, task_id))
    _add_op_log(c, task_id, operator, 'cancel_task', f"取消原因: {cancel_reason}")
    conn.commit()
    conn.close()
    return get_task(task_id)


# ===================== 台账 =====================

def write_ledger(task_id):
    """任务闭环写入采购业务台账（Skill-08 调用）
    幂等：ledger_written=1 则不再写
    """
    task = get_task(task_id)
    if not task:
        raise ValueError(f"task_id 不存在: {task_id}")
    if task['ledger_written']:
        return None
    ledger_id = f"LED-{datetime.now(CN_TZ).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
    sel = task['selected_supplier'] or {}
    remark = ''
    if task['task_status'] == '任务已取消':
        remark = f"任务取消: {task['cancel_reason']}"
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO procurement_ledger
        (ledger_id, task_id, project_id, project_name, contract_no,
         spare_part_model, purchase_qty, selected_supplier_name, deal_unit_price,
         delivery_time, logistics_no, test_result, task_close_time, remark)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (ledger_id, task_id, task['project_id'], task['project_name'], task['contract_no'],
          task['spare_part_model'], task['purchase_qty'], sel.get('name', ''), task['deal_unit_price'],
          task['delivery_time'], task['logistics_no'], task['test_result'],
          _now_iso(), remark))
    c.execute("UPDATE procurement_task SET ledger_written=1, updated_at=? WHERE task_id=?",
              (_now_iso(), task_id))
    _add_op_log(c, task_id, 'system:ledger', 'write_ledger', f'台账写入 {ledger_id}')
    conn.commit()
    conn.close()
    return {'ledger_id': ledger_id, 'task_id': task_id}


def list_ledger(*, project_id=None, limit=200):
    conn = get_db()
    c = conn.cursor()
    sql = "SELECT * FROM procurement_ledger"
    params = []
    if project_id:
        sql += " WHERE project_id=?"
        params.append(project_id)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    c.execute(sql, params)
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ===================== 主数据 CRUD =====================

def list_master_data():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM procurement_master_data ORDER BY id ASC")
    rows = c.fetchall()
    conn.close()
    return [_row_to_master(r) for r in rows]


def get_master_data(master_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM procurement_master_data WHERE id=?", (master_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return _row_to_master(row)


def get_master_by_project(project_id, contract_no=None):
    """按项目ID(+合同号) 查主数据，供前端新建询价下拉联动"""
    conn = get_db()
    c = conn.cursor()
    if contract_no:
        c.execute("SELECT * FROM procurement_master_data WHERE project_id=? AND contract_no=?",
                  (project_id, contract_no))
    else:
        c.execute("SELECT * FROM procurement_master_data WHERE project_id=?", (project_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return _row_to_master(row)


def create_master_data(*, project_id, project_name, contract_no,
                       allow_spare_parts, default_suppliers,
                       default_emergency_level='4h'):
    if default_emergency_level not in EMERGENCY_LEVEL_ENUM:
        raise ValueError(f"非法 default_emergency_level: {default_emergency_level}")
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO procurement_master_data
        (project_id, project_name, contract_no, allow_spare_parts,
         default_suppliers, default_emergency_level)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (project_id, project_name, contract_no,
          json.dumps(allow_spare_parts, ensure_ascii=False),
          json.dumps(default_suppliers, ensure_ascii=False),
          default_emergency_level))
    new_id = c.lastrowid
    conn.commit()
    conn.close()
    return get_master_data(new_id)


def update_master_data(*, master_id, **fields):
    """更新主数据，支持 allow_spare_parts / default_suppliers / default_emergency_level 等字段"""
    allowed = ('project_name', 'contract_no', 'allow_spare_parts',
               'default_suppliers', 'default_emergency_level')
    sets, params = [], []
    for k in allowed:
        if k in fields:
            v = fields[k]
            if k in ('allow_spare_parts', 'default_suppliers'):
                v = json.dumps(v, ensure_ascii=False)
            sets.append(f"{k}=?")
            params.append(v)
    if not sets:
        return get_master_data(master_id)
    sets.append("updated_at=datetime('now','localtime')")
    params.append(master_id)
    conn = get_db()
    c = conn.cursor()
    c.execute(f"UPDATE procurement_master_data SET {', '.join(sets)} WHERE id=?", params)
    conn.commit()
    conn.close()
    return get_master_data(master_id)


def delete_master_data(master_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM procurement_master_data WHERE id=?", (master_id,))
    conn.commit()
    conn.close()


# ===================== 操作日志 =====================

def _add_op_log(c, task_id, operator, action, remark=''):
    """内部：往 op_log 写一条日志（c 是已打开的 cursor，不单独 commit）"""
    c.execute("""
        INSERT INTO procurement_op_log (task_id, operator, action, remark)
        VALUES (?, ?, ?, ?)
    """, (task_id, operator, action, remark))


def list_op_logs(task_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM procurement_op_log WHERE task_id=? ORDER BY id DESC", (task_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ===================== 行转 dict + JSON 字段反序列化 =====================

def _row_to_task(row):
    if not row:
        return None
    d = dict(row)
    # JSON 字段反序列化
    for k in ('inquiry_supplier_list', 'replied_supplier_quotes', 'no_reply_supplier'):
        try:
            d[k] = json.loads(d.get(k) or '[]')
        except Exception:
            d[k] = []
    try:
        d['selected_supplier'] = json.loads(d.get('selected_supplier') or '{}')
    except Exception:
        d['selected_supplier'] = {}
    d['ledger_written'] = bool(d.get('ledger_written'))
    return d


def _row_to_master(row):
    if not row:
        return None
    d = dict(row)
    for k in ('allow_spare_parts', 'default_suppliers'):
        try:
            d[k] = json.loads(d.get(k) or '[]')
        except Exception:
            d[k] = []
    return d


# ===================== 种子数据（仅初始化时表空才插，幂等）=====================

SEED_MASTER_DATA = [
    {
        'project_id': 'PRJ-DEMO-001',
        'project_name': '示范项目A期',
        'contract_no': 'IDZB2607070A',
        'allow_spare_parts': [
            '华为 AR6280 路由器主板',
            '华为 S5700 交换机电源模块',
            'H3C MSR3640 路由器内存条 8GB',
            '锐捷 EG2100-E 网关电源模块',
        ],
        'default_suppliers': [
            {'name': '深圳华信通信设备', 'email': 'szhuaxin_tech@example.com'},
            {'name': '北京数码视讯科技', 'email': 'bjshuma_shixun@example.com'},
            {'name': '上海云创网络设备', 'email': 'shyunchuang_net@example.com'},
        ],
        'default_emergency_level': '4h',
    },
    {
        'project_id': 'PRJ-DEMO-002',
        'project_name': '运维节点B期扩容',
        'contract_no': 'CSZB2512210A',
        'allow_spare_parts': [
            '浪潮 NF5280M6 服务器内存条 16GB',
            '戴尔 R740 RAID 卡电池模块',
            '联想 SR650 电源模块 800W',
        ],
        'default_suppliers': [
            {'name': '浪潮电子设备供应', 'email': 'inspur_supply@example.com'},
            {'name': '戴尔(中国)代理', 'email': 'dell_cn_agent@example.com'},
        ],
        'default_emergency_level': '5h',
    },
]


def seed_procurement_master():
    """初始化种子主数据（幂等：表非空则跳过，避免覆盖用户后续通过页面新增的记录）"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) AS n FROM procurement_master_data")
    n = c.fetchone()['n']
    if n > 0:
        conn.close()
        return {'skipped': True, 'existing': n}
    for row in SEED_MASTER_DATA:
        c.execute("""
            INSERT INTO procurement_master_data
            (project_id, project_name, contract_no, allow_spare_parts,
             default_suppliers, default_emergency_level)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (row['project_id'], row['project_name'], row['contract_no'],
              json.dumps(row['allow_spare_parts'], ensure_ascii=False),
              json.dumps(row['default_suppliers'], ensure_ascii=False),
              row['default_emergency_level']))
    conn.commit()
    conn.close()
    return {'inserted': len(SEED_MASTER_DATA)}

