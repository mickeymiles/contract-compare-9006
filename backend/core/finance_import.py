"""财经 收款表/付款表 → finance_detail 导入与列表模块。

列映射（Excel 中文列头 → finance_detail 字段，忽略空格/下划线，命中首个匹配）：
- 付款(pay): 合同编号/合同号→contract_no，实际支付时间/支付时间→occur_date，
              实际支付金额/支付金额→amount，合同额/合同金额→contract_amount(随带)。
- 收款(recv): 合同号/合同编号→contract_no，回款日期/回款时间→occur_date，
               到款金额/回款金额/收款金额→amount，合同额/合同金额→contract_amount(随带)。
行无 contract_no 则跳过。写 finance_detail 复用 project_metrics（供资金占用计算复用）。
"""
from datetime import datetime
from typing import List, Dict, Any, Optional

from core import project_metrics as pm

# kind → 目标字段 → 候选中文列名（"包含"匹配，忽略空格/下划线/横线）
FINANCE_COLUMN_MAP: Dict[str, Dict[str, List[str]]] = {
    'pay': {
        'contract_no': ['合同编号', '合同号'],
        'occur_date': ['实际支付时间', '支付时间'],
        'amount': ['实际支付金额', '支付金额'],
        'contract_amount': ['合同额', '合同金额'],
    },
    'recv': {
        'contract_no': ['合同号', '合同编号'],
        'occur_date': ['回款日期', '回款时间'],
        'amount': ['到款金额', '回款金额', '收款金额'],
        'contract_amount': ['合同额', '合同金额'],
    },
}


def _norm(h: Any) -> str:
    return str(h or '').strip().replace(' ', '').replace('_', '').replace('-', '')


def _find_col(headers: List[str], candidates: List[str]) -> Optional[int]:
    """精确命中优先，随后退到包含匹配；两者都忽略空格/下划线/横线。"""
    targets = [_norm(c) for c in candidates]
    norm_headers = [_norm(h) for h in headers]
    # 精确匹配
    for i, hn in enumerate(norm_headers):
        if hn in targets:
            return i
    # 包含匹配（避免"支付时间"被"预计支付时间"抢占等场景，按候选优先级匹配）
    for t in targets:
        for i, hn in enumerate(norm_headers):
            if t and t in hn:
                return i
    return None


def _parse_float(v: Any) -> Optional[float]:
    if v is None or v == '' or v == '-':
        return None
    if isinstance(v, bool):
        return None
    try:
        return round(float(str(v).strip().replace(',', '')), 2)
    except (ValueError, TypeError):
        return None


def _parse_date_str(v: Any) -> Optional[str]:
    d = pm._d(v)
    return d.isoformat() if d else None


def read_finance_xlsx(path: str, kind: str) -> tuple:
    """读取首表，返回 (rows, matched_columns)。rows 为 dict 列表，行无 contract_no 已跳过。

    matched_columns: {'中文列名': '目标字段'}。
    """
    import openpyxl
    kind = 'recv' if kind == 'recv' else 'pay'
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows:
        return [], {}

    headers = [str(h) if h is not None else '' for h in rows[0]]
    col_def = FINANCE_COLUMN_MAP.get(kind, FINANCE_COLUMN_MAP['pay'])
    idx: Dict[str, int] = {}
    matched: Dict[str, str] = {}
    for field, cands in col_def.items():
        ci = _find_col(headers, cands)
        if ci is not None:
            idx[field] = ci
            matched[headers[ci]] = field

    if 'contract_no' not in idx:
        return [], matched

    def _cell(i, j):
        if i not in idx or idx[i] >= len(j):
            return None
        return j[idx[i]]

    out: List[Dict[str, Any]] = []
    for r in rows[1:]:
        if not any(c is not None and str(c).strip() != '' for c in r):
            continue
        cno = str(_cell('contract_no', r) or '').strip()
        if not cno:
            continue  # 行无 contract_no 则跳过
        out.append({
            'contract_no': cno,
            'occur_date': _parse_date_str(_cell('occur_date', r)),
            'amount': _parse_float(_cell('amount', r)),
            'contract_amount': _parse_float(_cell('contract_amount', r)),
        })
    return out, matched


def _contract_project_map() -> Dict[str, str]:
    """建 core_project contract_no → project_no 映射（1:1，project_no 优先）。

    行内 contract_no 命中即回填 project_no；未命中保持空字符串，资金占用回落 contract_no。
    """
    conn = pm.get_conn()
    try:
        m: Dict[str, str] = {}
        for r in conn.execute(
                "SELECT contract_no, project_no FROM core_project "
                "WHERE contract_no IS NOT NULL AND contract_no<>'' "
                "AND project_no IS NOT NULL AND project_no<>''").fetchall():
            m.setdefault(r['contract_no'], r['project_no'])
        return m
    finally:
        conn.close()


def import_finance_xlsx(path: str, kind: str) -> Dict[str, Any]:
    """把 excel 收款/付款明细写入 finance_detail，返回
    {'success', 'inserted', 'skipped', 'total', 'matched_columns'}。

    主口径 project_no：由 contract_no→project_no 映射回填，提高 7000+ 行导入速度
    （单事务 + executemany 批量写入，避免逐行独立 commit）。
    """
    kind = 'recv' if kind == 'recv' else 'pay'
    rows, matched = read_finance_xlsx(path, kind)
    pmap = _contract_project_map()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    records = []
    for it in rows:
        records.append((
            it['contract_no'],
            pmap.get(it['contract_no'], ''),
            kind,
            it['occur_date'],
            it['amount'] if it['amount'] is not None else 0.0,
            it['contract_amount'],
            '',
            now, now,
        ))
    inserted = pm.bulk_add_finance_detail(records)
    return {'success': True, 'inserted': inserted, 'skipped': len(rows) - inserted,
            'total': len(rows), 'matched_columns': matched}


def list_finance(kind: str, keyword: str = '') -> List[Dict[str, Any]]:
    """查询 finance_detail 指定 kind 的明细，按 occur_date 倒序（keyword 匹配合同号/备注）。"""
    kind = 'recv' if kind == 'recv' else 'pay'
    pm.ensure_finance_detail()
    conn = pm.get_conn()
    try:
        sql = "SELECT * FROM finance_detail WHERE kind=?"
        args: List[Any] = [kind]
        kw = (keyword or '').strip()
        if kw:
            like = '%' + kw + '%'
            sql += " AND (contract_no LIKE ? OR remark LIKE ?)"
            args += [like, like]
        sql += " ORDER BY occur_date DESC, id DESC"
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()