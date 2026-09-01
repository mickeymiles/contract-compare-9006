"""主数据域 core：项目主数据（本体根）与关联域的数据层 + CRUD。

项目号(project_no) 为主数据唯一主键；商机号/合同号/项目号三号各自独立。
项目 - 合同默认 1:1，预留 parent_project_id 支持 1:N 子项目。
运维联系信息（Ops：联系人/收件人/现场地址）由运维域维护，不作为主数据字段。
"""
import sqlite3
from typing import Optional, List, Dict, Any

# 复用统一 DB（与 models.get_db 同库：contract_compare.db）
from models import DB_PATH as _DB


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# 总合同表 v2 → core_project 新增可空字段（金额/数值 REAL，日期/文本 TEXT）
EXTRA_PROJECT_COLUMNS: List[tuple] = [
    ('region', 'TEXT'),
    ('province', 'TEXT'),
    ('industry', 'TEXT'),
    ('biz_type', 'TEXT'),
    ('customer_cls', 'TEXT'),
    ('biz_line', 'TEXT'),
    ('stat_year', 'TEXT'),
    ('party_a', 'TEXT'),
    ('hardware_est', 'REAL'),
    ('software_est', 'REAL'),
    ('service_est', 'REAL'),
    ('accum_cost_est', 'REAL'),
    ('accum_cost_actual', 'REAL'),
    ('sign_gross_profit', 'REAL'),
    ('gross_rate', 'REAL'),
    ('gross_rate_est', 'REAL'),
    ('contract_profit', 'REAL'),
    ('payback_profit', 'REAL'),
    ('accum_received', 'REAL'),
    ('payback_cycle', 'REAL'),
    ('last_received_date', 'TEXT'),
]

_EXTRA_COLUMN_SQL = ',\n'.join(f'  {name} {typedef}' for name, typedef in EXTRA_PROJECT_COLUMNS)

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS core_project (
  project_id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_no TEXT UNIQUE NOT NULL,
  opportunity_no TEXT,
  contract_no TEXT,
  contract_id INTEGER,
  parent_project_id INTEGER,
  name TEXT NOT NULL,
  customer_key TEXT,
  status TEXT DEFAULT 'active',
  owner_ref INTEGER,
  dept TEXT,
  sign_amount REAL,
  sign_date TEXT,
  cycle TEXT,
  version TEXT,
{_EXTRA_COLUMN_SQL},
  created_at TEXT,
  updated_at TEXT
);
CREATE TABLE IF NOT EXISTS core_opportunity (
  opportunity_id INTEGER PRIMARY KEY AUTOINCREMENT,
  opportunity_no TEXT UNIQUE NOT NULL,
  project_id INTEGER,
  project_no TEXT,
  status TEXT DEFAULT '跟进',
  estimate_budget REAL,
  created_at TEXT,
  updated_at TEXT
);
CREATE TABLE IF NOT EXISTS core_contract (
  contract_id INTEGER PRIMARY KEY AUTOINCREMENT,
  contract_no TEXT UNIQUE NOT NULL,
  project_id INTEGER,
  project_no TEXT,
  sign_amount REAL,
  sign_date TEXT,
  party_a TEXT,
  party_b TEXT,
  terms TEXT,
  created_at TEXT,
  updated_at TEXT
);
CREATE TABLE IF NOT EXISTS core_ops_contact (
  contact_id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL,
  contact_role TEXT,
  contact_name TEXT,
  contact_phone TEXT,
  address_receiver TEXT,
  address_site TEXT,
  created_at TEXT,
  updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_core_ops_project ON core_ops_contact(project_id);
CREATE INDEX IF NOT EXISTS idx_core_project_no ON core_project(project_no);
"""


def init_core_db() -> None:
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        migrate_add_columns(conn)
        conn.commit()
    finally:
        conn.close()


def migrate_add_columns(conn: Optional[sqlite3.Connection] = None) -> list:
    """为已存在的 core_project 补齐 v2 新列（幂等：列已在则跳过）。返回到被补的列名。"""
    own = conn is None
    conn = conn or get_conn()
    added = []
    try:
        existing = {r[1] for r in conn.execute("PRAGMA table_info(core_project)").fetchall()}
        for name, typedef in EXTRA_PROJECT_COLUMNS:
            if name in existing:
                continue
            conn.execute(f'ALTER TABLE core_project ADD COLUMN {name} {typedef}')
            added.append(name)
        if own:
            conn.commit()
    finally:
        if own:
            conn.close()
    return added


def _now() -> str:
    from datetime import datetime
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


# ── Project ──────────────────────────────────────────────
def create_project(data: Dict[str, Any]) -> dict:
    conn = get_conn()
    try:
        p = data.get('project_no', '').strip()
        if not p:
            return {'success': False, 'error': 'project_no 必填'}
        if conn.execute("SELECT 1 FROM core_project WHERE project_no=?", (p,)).fetchone():
            return {'success': False, 'error': f'项目号已存在: {p}'}
        now = _now()
        conn.execute(
            """INSERT INTO core_project
            (project_no, opportunity_no, contract_no, contract_id, parent_project_id, name,
             customer_key, status, owner_ref, dept, sign_amount, sign_date, cycle, version, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (p, data.get('opportunity_no'), data.get('contract_no'), data.get('contract_id'),
             data.get('parent_project_id'), data.get('name', ''), data.get('customer_key'),
             data.get('status', 'active'), data.get('owner_ref'), data.get('dept'),
             data.get('sign_amount'), data.get('sign_date'), data.get('cycle'),
             data.get('version'), now, now))
        conn.commit()
        pid = conn.execute("SELECT project_id FROM core_project WHERE project_no=?", (p,)).fetchone()[0]
        return {'success': True, 'project_id': pid, 'project_no': p}
    except Exception as e:
        return {'success': False, 'error': str(e)}
    finally:
        conn.close()


def list_projects(keyword: str = '') -> list:
    conn = get_conn()
    try:
        if keyword:
            rows = conn.execute(
                "SELECT * FROM core_project WHERE project_no LIKE ? OR name LIKE ? ORDER BY project_id DESC",
                (f'%{keyword}%', f'%{keyword}%')).fetchall()
        else:
            rows = conn.execute("SELECT * FROM core_project ORDER BY project_id DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_project(project_id: int) -> Optional[dict]:
    conn = get_conn()
    try:
        r = conn.execute("SELECT * FROM core_project WHERE project_id=?", (project_id,)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def update_project(project_id: int, data: Dict[str, Any]) -> dict:
    conn = get_conn()
    try:
        if not conn.execute("SELECT 1 FROM core_project WHERE project_id=?", (project_id,)).fetchone():
            return {'success': False, 'error': '项目不存在'}
        fields = ['opportunity_no', 'contract_no', 'contract_id', 'parent_project_id', 'name',
                  'customer_key', 'status', 'owner_ref', 'dept', 'sign_amount', 'sign_date',
                  'cycle', 'version']
        sets = [f'{f}=?' for f in fields if f in data]
        if not sets:
            return {'success': False, 'error': '无更新字段'}
        vals = [data[f] for f in fields if f in data]
        sets.append('updated_at=?'); vals.append(_now())
        vals.append(project_id)
        conn.execute(f"UPDATE core_project SET {', '.join(sets)} WHERE project_id=?", vals)
        conn.commit()
        return {'success': True}
    except Exception as e:
        return {'success': False, 'error': str(e)}
    finally:
        conn.close()


def delete_project(project_id: int) -> dict:
    conn = get_conn()
    try:
        conn.execute("DELETE FROM core_project WHERE project_id=?", (project_id,))
        conn.commit()
        return {'success': True}
    finally:
        conn.close()


# 允许整体 upsert 写入的列（含 v2 新字段与基础识别字段）
UPSERT_FIELDS: List[str] = [
    'project_no', 'opportunity_no', 'contract_no', 'contract_id', 'parent_project_id',
    'name', 'customer_key', 'status', 'owner_ref', 'dept', 'sign_amount', 'sign_date',
    'cycle', 'version', 'region', 'province', 'industry', 'biz_type', 'customer_cls',
    'biz_line', 'stat_year', 'party_a', 'hardware_est', 'software_est', 'service_est',
    'accum_cost_est', 'accum_cost_actual', 'sign_gross_profit', 'gross_rate', 'gross_rate_est',
    'contract_profit', 'payback_profit', 'accum_received', 'payback_cycle', 'last_received_date',
]


def upsert_project(data: Dict[str, Any]) -> dict:
    """按 project_no 去重/更新主数据；project_no 缺省时取 contract_no。

    已存在则更新（全字段覆盖），否则插入。返回 {'success', 'project_id', 'project_no', 'mode'}。"""
    pno = (data.get('project_no') or '').strip()
    if not pno:
        pno = (data.get('contract_no') or '').strip()
    if not pno:
        return {'success': False, 'error': 'project_no/contract_no 至少一个必填'}
    data = {k: v for k, v in data.items()}
    data['project_no'] = pno
    if not (data.get('contract_no') or '').strip():
        data['contract_no'] = pno
    if not (data.get('name') or '').strip():
        data['name'] = pno
    data['status'] = data.get('status') or 'active'
    conn = get_conn()
    now = _now()
    try:
        existing = conn.execute("SELECT project_id FROM core_project WHERE project_no=?", (pno,)).fetchone()
        fields = [f for f in UPSERT_FIELDS if f in data]
        if existing:
            pid = existing[0]
            if fields:
                sets = [f'{f}=?' for f in fields] + ['updated_at=?']
                vals = [data[f] for f in fields] + [now, pid]
                conn.execute(f"UPDATE core_project SET {', '.join(sets)} WHERE project_id=?", vals)
            mode = 'updated'
        else:
            cols = [f for f in fields] + ['created_at', 'updated_at']
            vals = [data.get(f) for f in fields] + [now, now]
            cur = conn.execute(f"INSERT INTO core_project ({', '.join(cols)}) VALUES ({', '.join('?'*len(cols))})", vals)
            pid = cur.lastrowid
            mode = 'created'
        conn.commit()
        return {'success': True, 'project_id': pid, 'project_no': pno, 'mode': mode}
    except Exception as e:
        return {'success': False, 'error': str(e)}
    finally:
        conn.close()


# ── Ops 联系信息 ────────────────────────────────────────
def list_ops_contacts(project_id: Optional[int] = None) -> list:
    conn = get_conn()
    try:
        if project_id:
            rows = conn.execute("SELECT * FROM core_ops_contact WHERE project_id=? ORDER BY contact_id", (project_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM core_ops_contact ORDER BY contact_id").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def create_ops_contact(project_id: int, data: Dict[str, Any]) -> dict:
    conn = get_conn()
    try:
        now = _now()
        conn.execute(
            """INSERT INTO core_ops_contact
            (project_id, contact_role, contact_name, contact_phone, address_receiver, address_site, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?)""",
            (project_id, data.get('contact_role'), data.get('contact_name'), data.get('contact_phone'),
             data.get('address_receiver'), data.get('address_site'), now, now))
        conn.commit()
        return {'success': True, 'contact_id': conn.execute('SELECT last_insert_rowid()').fetchone()[0]}
    except Exception as e:
        return {'success': False, 'error': str(e)}
    finally:
        conn.close()


def delete_ops_contact(contact_id: int) -> dict:
    conn = get_conn()
    try:
        conn.execute("DELETE FROM core_ops_contact WHERE contact_id=?", (contact_id,))
        conn.commit()
        return {'success': True}
    finally:
        conn.close()