"""主数据全量导入器（md_* 表）—— 本体数据源的基础层。

设计原则（对应"全量导入、全量建表、作为本体数据源"）：
- 读取 xlsx 首表【全部列】，忠实保留原始中文列名作为表字段（SQLite 支持
  UTF-8 标识符，建表/查询时统一双引号包裹，嵌入双引号转义为双写）。
- 全量覆盖：每次导入 DROP 旧表重建，保证"全量"语义、无脏数据累积。
- 类型推断：某列非空值【全部】为数值 → REAL，否则 TEXT（金额列可聚合、
  文本列保真）。空列记为 TEXT。
- 列元数据登记到 md_meta(table_name, col_idx, col_name, col_type)，供前端
  渲染列头与后续 ontos 做字段映射（列名即原始中文，可直接对齐本体属性）。
- 不裁剪：所有列入表，派生列也原样留存（口径加工交由 Function，不在本层做）。

本模块只负责"忠实落库"，不关心业务语义；业务裁剪表(core_project /
finance_detail / plm_milestone)的回写在 routes.py 里复用既有导入函数完成，
保证既有分析页不因主数据重构而崩。
"""
from typing import List, Dict, Any, Optional, Tuple
import re

from core import project_metrics as pm


# ── 列名规范化 ──────────────────────────────────────────────
def _norm_col_name(raw: str, seen: set) -> str:
    """原始表头 → 安全且可读的列名。

    - 去除控制字符；空表头回退为「未命名列」。
    - 双引号改单引号（避免破坏 SQL 双引号引用）。
    - 同名追加 _2 / _3 去重（源表确实存在的冗余列）。
    """
    s = re.sub(r'[\x00-\x1f\x7f]', '', str(raw if raw is not None else '')).strip()
    if not s:
        s = '未命名列'
    s = s.replace('"', "'")
    base = s
    i = 2
    while s in seen:
        s = f"{base}_{i}"
        i += 1
    seen.add(s)
    return s


def _is_number(v: Any) -> bool:
    if v is None or isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return True
    s = str(v).strip().replace(',', '').replace('%', '')
    if s in ('', '-', '—', '~', 'N/A', 'NA', 'nan', 'None'):
        return False
    try:
        float(s)
        return True
    except (ValueError, TypeError):
        return False


def _to_float(v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    s = str(v).strip().replace(',', '').replace('%', '')
    if s in ('', '-', '—', '~', 'N/A', 'NA', 'nan', 'None'):
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _clean_cell(v: Any, ct: str) -> Any:
    if v is None:
        return None
    if ct == 'REAL':
        f = _to_float(v)
        return f
    s = str(v).strip()
    return s if s != '' else None


# ── xlsx 读取 ───────────────────────────────────────────────
def read_xlsx_full(path: str) -> Tuple[List[str], List[List[Any]]]:
    """读取首表全部列与全部数据行（跳过全空行）。返回 (表头列表, 数据行列表)。"""
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows:
        return [], []
    headers = [str(h) if h is not None else '' for h in rows[0]]
    data: List[List[Any]] = []
    for r in rows[1:]:
        if not any(c is not None and str(c).strip() != '' for c in r):
            continue
        data.append(list(r))
    return headers, data


# ── 全量导入 ────────────────────────────────────────────────
def full_import_xlsx(table: str, path: str, conn=None) -> Dict[str, Any]:
    """全量导入：DROP 旧表重建，写入全部列与全部行，登记 md_meta。

    返回 {'success', 'table', 'columns', 'rows', 'col_names', 'col_types'}。
    """
    headers, data = read_xlsx_full(path)
    if not headers:
        return {'success': False, 'error': '空表或无表头'}

    seen: set = set()
    col_names = [_norm_col_name(h, seen) for h in headers]

    # 类型推断（按列：非空值全为数值 → REAL）
    col_types: List[str] = []
    for j in range(len(col_names)):
        vals = [r[j] if j < len(r) else None for r in data]
        non_empty = [v for v in vals if v is not None and str(v).strip() != '']
        col_types.append('REAL' if (non_empty and all(_is_number(v) for v in non_empty)) else 'TEXT')

    own = conn is None
    c = conn or pm.get_conn()
    try:
        c.execute(f'DROP TABLE IF EXISTS "{table}"')
        cols_sql = ', '.join(f'"{cn}" {ct}' for cn, ct in zip(col_names, col_types))
        c.execute(f'CREATE TABLE "{table}" (row_id INTEGER PRIMARY KEY AUTOINCREMENT, {cols_sql})')

        col_list = ', '.join(f'"{cn}"' for cn in col_names)
        ph = ', '.join(['?'] * len(col_names))
        sql = f'INSERT INTO "{table}" ({col_list}) VALUES ({ph})'
        for r in data:
            row = list(r) + [None] * (len(headers) - len(r))
            row = row[:len(headers)]
            vals = [_clean_cell(v, ct) for v, ct in zip(row, col_types)]
            c.execute(sql, vals)
        c.commit()

        c.execute('''CREATE TABLE IF NOT EXISTS md_meta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT, col_idx INTEGER, col_name TEXT, col_type TEXT)''')
        c.execute('DELETE FROM md_meta WHERE table_name=?', (table,))
        for j, (cn, ct) in enumerate(zip(col_names, col_types)):
            c.execute('INSERT INTO md_meta(table_name, col_idx, col_name, col_type) VALUES(?,?,?,?)',
                      (table, j, cn, ct))
        c.commit()
        return {'success': True, 'table': table, 'columns': len(col_names),
                'rows': len(data), 'col_names': col_names, 'col_types': col_types}
    finally:
        if own:
            c.close()


# ── 列表查询 ────────────────────────────────────────────────
def list_md(table: str, keyword: str = '', limit: int = 200, offset: int = 0) -> Dict[str, Any]:
    """返回某 md_* 表的列头与分页数据。keyword 任意列模糊匹配。"""
    c = pm.get_conn()
    try:
        meta = c.execute('SELECT col_name, col_type FROM md_meta WHERE table_name=? ORDER BY col_idx',
                         (table,)).fetchall()
        if meta:
            col_names = [m['col_name'] for m in meta]
        else:
            pr = c.execute(f'PRAGMA table_info("{table}")').fetchall()
            col_names = [r['name'] for r in pr if r['name'] != 'row_id']
        if not col_names:
            return {'success': True, 'columns': [], 'rows': [], 'total': 0}

        sel = 'row_id, ' + ', '.join(f'"{cn}"' for cn in col_names)
        sql = f'SELECT {sel} FROM "{table}"'
        args: List[Any] = []
        if keyword and keyword.strip():
            like = '%' + keyword.strip() + '%'
            conds = [f'"{cn}" LIKE ?' for cn in col_names]
            sql += ' WHERE ' + ' OR '.join(conds)
            args += [like] * len(col_names)
        sql += ' ORDER BY row_id LIMIT ? OFFSET ?'
        args += [limit, offset]
        rows = c.execute(sql, args).fetchall()
        total = c.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        return {'success': True, 'columns': col_names,
                'rows': [dict(r) for r in rows], 'total': total}
    finally:
        c.close()


def list_md_tables() -> List[str]:
    c = pm.get_conn()
    try:
        return [r['name'] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'md_%'").fetchall()]
    finally:
        c.close()
