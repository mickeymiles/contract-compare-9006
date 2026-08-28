"""R3 存量数据 → core 主数据 迁移/对账脚本（幂等，仅新增/更新，不删存量）。

原则：
- 主数据 = 项目号 (project_no)；多数 项目号=合同号。
- 以非空 contract_no 作为去重键，逐条 upsert 到 core_project（project_no=contract_no）。
- 同时维护 core_contract（contract_no↔project_id 映射层）。
- 对账报告：列出每来源表的行数、有 contract_no 数、命中/未命中 core_project 数。
仅本地执行，默认不动现网部署。
"""
from typing import List, Dict
from core import project as P

# 来源表：(表名, 合同号列, 项目号列(可为 None))
SOURCE_TABLES: List[tuple] = [
    ('contracts',           'contract_no', None),
    ('procurement_contract','contract_no', None),
    ('procurement_ledger',  'contract_no', None),
    ('procurement_task',    'contract_no', None),
    ('fund_metrics',        'contract_no', None),
]


def _collect() -> Dict[str, List[str]]:
    """返回 {contract_no: [来源表...]} 的去重注册表。"""
    reg: Dict[str, List[str]] = {}
    conn = P.get_conn()
    try:
        for table, ccol, _pcol in SOURCE_TABLES:
            try:
                rows = conn.execute(f"SELECT DISTINCT {ccol} FROM {table}").fetchall()
            except Exception:
                continue
            for r in rows:
                no = str(r[0] or '').strip()
                if not no:
                    continue
                reg.setdefault(no, []).append(table)
    finally:
        conn.close()
    return reg


def _reconcile(reg: Dict[str, List[str]]) -> Dict:
    conn = P.get_conn()
    try:
        existing = set(r[0] for r in conn.execute("SELECT project_no FROM core_project").fetchall())
        existing_contracts = set(r[0] for r in conn.execute("SELECT contract_no FROM core_contract WHERE contract_no IS NOT NULL").fetchall())
    finally:
        conn.close()
    all_no = set(reg)
    return {
        'distinct_contract_no': len(all_no),
        'matched_in_core_project': len(all_no & existing),
        'not_in_core_project_yet': sorted(all_no - existing),
        'source_footprint': {no: tables for no, tables in reg.items()},
    }


def migrate(apply: bool = True) -> Dict:
    """迁移存量 contract_no → core_project/project_no + core_contract 映射层。"""
    reg = _collect()
    if not apply:
        return {'mode': 'dry-run', **{'distinct_contract_no': len(reg)}}
    conn = P.get_conn()
    now = P._now()
    created = skipped = mapped = 0
    try:
        for no, tables in reg.items():
            exists = conn.execute("SELECT project_id FROM core_project WHERE project_no=?", (no,)).fetchone()
            if exists:
                skipped += 1
                pid = exists[0]
            else:
                conn.execute(
                    "INSERT INTO core_project (project_no, contract_no, name, status, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                    (no, no, no, 'active', now, now))
                pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                created += 1
            # 生成/更新 core_contract 映射层（接入主数据）
            if not conn.execute("SELECT 1 FROM core_contract WHERE contract_no=?", (no,)).fetchone():
                conn.execute(
                    "INSERT INTO core_contract (contract_no, project_id, project_no, created_at, updated_at) VALUES (?,?,?,?,?)",
                    (no, pid, no, now, now))
            else:
                conn.execute("UPDATE core_contract SET project_id=?, project_no=? WHERE contract_no=?", (pid, no, no))
            mapped += 1
        conn.commit()
    finally:
        conn.close()
    recon = _reconcile(reg)
    return {'mode': 'apply', 'created_projects': created, 'skipped_existing': skipped,
            'mapped_contracts': mapped, **recon}


def report() -> Dict:
    """只对账，不写库。"""
    reg = _collect()
    return _reconcile(reg)


def backfill_project_id(apply: bool = True) -> Dict:
    """给来源表加 project_id 列并回填（按 contract_no → core_contract.project_id）。

    幂等：列不存在才 ADD；回填可重复执行。只把能匹配到映射层的行填上，未匹配留 NULL。"""
    conn = P.get_conn()
    result = {}
    try:
        cols_by_table = {t: [r[1] for r in conn.execute(f"PRAGMA table_info('{t}')").fetchall()]
                         for t, _, _ in SOURCE_TABLES}
        for table, ccol, _pcol in SOURCE_TABLES:
            # 表不存在（PRAGMA 无列）时跳过，不尝试 ALTER
            if table not in cols_by_table or not cols_by_table[table]:
                continue
            if 'project_id' not in cols_by_table[table]:
                if not apply:
                    result[table] = 'need_add_column'
                    continue
                conn.execute(f"ALTER TABLE {table} ADD COLUMN project_id INTEGER")
            total = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if apply:
                conn.execute(
                    f"""UPDATE {table} SET project_id = (
                         SELECT cc.project_id FROM core_contract cc WHERE cc.contract_no = {table}.{ccol}
                       ) WHERE {ccol} IS NOT NULL AND {ccol} <> ''""")
            filled = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE project_id IS NOT NULL").fetchone()[0]
            result[table] = f'{filled}/{total}'
        if apply:
            conn.commit()
    finally:
        conn.close()
    return result