"""一次性数据清洗：把核心库里的『坏值』修成正常值，供既有计算规则直接使用。

仅清洗数据，不改动任何计算逻辑：
1. core_project.sign_date：Excel 日期序列号(如 46100) → YYYY-MM-DD；#REF! 等无效值置空。
2. core_project.last_received_date：#REF! / 不可解析 → 置空。
3. finance_detail：历史未回填 project_no 的行，用 contract_no→project_no 映射回填。
"""
import os
import sys
from datetime import datetime, date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from models import DB_PATH
from core import project as project_core


def _excel_serial(v) -> str:
    """Excel 日期序号（1900 日期系统）→ YYYY-MM-DD；无效返回 ''。"""
    s = str(v).strip()
    if not s:
        return ''
    try:
        n = float(s)
    except (ValueError, TypeError):
        return ''
    if not (1.0 <= n <= 2958466.0):
        return ''
    d = datetime(1899, 12, 30) + timedelta(days=int(n))
    return d.strftime('%Y-%m-%d')


def _parse_date(v) -> str:
    """常见日期字符串 → YYYY-MM-DD；#REF! 等无效返回 ''。"""
    if v is None:
        return ''
    if isinstance(v, datetime):
        return v.strftime('%Y-%m-%d')
    if isinstance(v, date):
        return v.strftime('%Y-%m-%d')
    s = str(v).strip()
    if not s or s in ('#REF!', '#VALUE!', '#N/A', '-', 'None'):
        return ''
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d', '%Y%m%d'):
        try:
            return datetime.strptime(s, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return ''


def _clean_date(v) -> str:
    return _parse_date(v) or _excel_serial(v)


def clean_core_dates() -> dict:
    """修复 core_project 的 sign_date / last_received_date。"""
    conn = project_core.get_conn()
    fixed_sd = fixed_lrd = 0
    try:
        rows = conn.execute(
            "SELECT project_id, sign_date, last_received_date FROM core_project").fetchall()
        for r in rows:
            pid = r['project_id']
            # sign_date
            sd = r['sign_date']
            old_sd = '' if sd is None else str(sd)
            new_sd = '' if not old_sd.strip() else _clean_date(old_sd)
            if new_sd != old_sd.strip():
                conn.execute("UPDATE core_project SET sign_date=? WHERE project_id=?",
                             (new_sd or None, pid))
                fixed_sd += 1
            # last_received_date
            lrd = r['last_received_date']
            old_lrd = '' if lrd is None else str(lrd)
            new_lrd = '' if not old_lrd.strip() else _clean_date(old_lrd)
            if new_lrd != old_lrd.strip():
                conn.execute("UPDATE core_project SET last_received_date=? WHERE project_id=?",
                             (new_lrd or None, pid))
                fixed_lrd += 1
        conn.commit()
    finally:
        conn.close()
    return {'sign_date_fixed': fixed_sd, 'last_received_date_fixed': fixed_lrd}


def backfill_finance_project_no() -> int:
    """给 finance_detail 历史行回填 project_no（contract_no→project_no 映射）。"""
    idx = {}
    for cp in (project_core.list_projects() or []):
        cno = (cp.get('contract_no') or '').strip()
        pno = (cp.get('project_no') or '').strip()
        if cno and pno:
            idx.setdefault(cno, pno)
    from core.project_metrics import get_conn as fm_conn
    conn = fm_conn()
    fixed = 0
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(finance_detail)")]
        if 'project_no' not in cols:
            conn.execute("ALTER TABLE finance_detail ADD COLUMN project_no TEXT DEFAULT ''")
            conn.commit()
        for r in conn.execute("SELECT id, contract_no, project_no FROM finance_detail"):
            if r['project_no'] and str(r['project_no']).strip():
                continue
            pno = idx.get(str(r['contract_no'] or '').strip())
            if pno:
                conn.execute("UPDATE finance_detail SET project_no=? WHERE id=?", (pno, r['id']))
                fixed += 1
        conn.commit()
    finally:
        conn.close()
    return fixed


if __name__ == '__main__':
    print('DB:', DB_PATH, file=sys.stderr)
    print('clean_core_dates:', clean_core_dates())
    print('backfill_finance_project_no:', backfill_finance_project_no())