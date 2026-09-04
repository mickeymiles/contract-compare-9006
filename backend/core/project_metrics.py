"""主数据三大计算：项目毛利率／回款周期／资金占用。

数据来源：
- 毛利率：主数据 core_project（sign_gross_profit / sign_amount / gross_rate / contract_profit）。
- 回款周期：主数据 sign_date + PLM 里程碑回款时间点（plm_milestone→plm_project→plm_contract 链路解析
  contract_no），回退主数据 last_received_date；无数据给 NaN + 说明。
- 资金占用：finance 收付款明细（finance_detail，contract_no 关联），FIFO 冲抵口径与
  main.py /api/fund 一致。

finance_detail 为「财经收付款明细」补齐表（原系统仅有 Excel，未落库），带 contract_no 关联主数据。
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, date, timedelta
import re
import hashlib
import json

from core import project as project_core

FINANCE_DETAIL_SCHEMA = """
CREATE TABLE IF NOT EXISTS finance_detail (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  contract_no TEXT NOT NULL,
  project_no TEXT DEFAULT '',     -- 项目号（主口径；导入时由 contract_no→project_no 映射回填）
  kind TEXT NOT NULL,            -- 'pay' 付款 / 'recv' 收款
  occur_date TEXT,               -- 发生日期（付款日期 / 回款日期，YYYY-MM-DD）
  amount REAL DEFAULT 0,
  contract_amount REAL DEFAULT 0, -- 合同额（付款明细行随带）
  remark TEXT DEFAULT '',
  created_at TEXT,
  updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_finance_detail_no ON finance_detail(contract_no);
CREATE INDEX IF NOT EXISTS idx_finance_detail_kind ON finance_detail(contract_no, kind);
"""


def get_conn():
    return project_core.get_conn()


def ensure_finance_detail() -> None:
    """补齐 finance 收付款明细表（幂等）。

    先建表/补 project_no 列，再建 project_no 索引——否则存量库里 project_no
    列缺失时，建 project_no 索引会先于 ALTER 报 "no such column: project_no"。
    """
    conn = get_conn()
    try:
        # 1) 建表（表已存在则跳过）＋ 先建不依赖 project_no 的索引
        conn.execute("""CREATE TABLE IF NOT EXISTS finance_detail (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          contract_no TEXT NOT NULL,
          project_no TEXT DEFAULT '',
          kind TEXT NOT NULL,
          occur_date TEXT,
          amount REAL DEFAULT 0,
          contract_amount REAL DEFAULT 0,
          remark TEXT DEFAULT '',
          created_at TEXT,
          updated_at TEXT
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_finance_detail_no ON finance_detail(contract_no)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_finance_detail_kind ON finance_detail(contract_no, kind)")
        # 2) 幂等补列：存量 finance_detail 表缺 project_no 时 ALTER 补上
        existing = {r[1] for r in conn.execute("PRAGMA table_info(finance_detail)").fetchall()}
        if 'project_no' not in existing:
            conn.execute("ALTER TABLE finance_detail ADD COLUMN project_no TEXT DEFAULT ''")
        # 3) 列就绪后再建 project_no 索引
        conn.execute("CREATE INDEX IF NOT EXISTS idx_finance_detail_project ON finance_detail(project_no)")
        conn.commit()
    finally:
        conn.close()


def _f(v) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _d(v) -> Optional[date]:
    if v is None or v == '' or v == '-':
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d', '%Y%m%d'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


# ── 1) 项目毛利率 ─────────────────────────────────────────
def project_gross_margin(contract_no: str) -> Dict[str, Any]:
    """基于主数据输出毛利率。口径：优先 sign_gross_profit / sign_amount；缺省回退 gross_rate。
    返回 {'contract_no', 'sign_amount', 'sign_gross_profit', 'gross_rate', 'method', 'note'}。"""
    row = _main_by_no(contract_no)
    if not row:
        return {'contract_no': contract_no, 'sign_amount': None, 'sign_gross_profit': None,
                'gross_rate': None, 'method': 'no_data', 'note': '主数据无此合同'}
    amt = _f(row.get('sign_amount'))
    gp = _f(row.get('sign_gross_profit'))
    gr = _f(row.get('gross_rate'))
    if amt and amt > 0 and gp is not None:
        rate = round(gp / amt * 100, 2)
        return {'contract_no': contract_no, 'sign_amount': amt, 'sign_gross_profit': gp,
                'gross_rate': rate, 'method': 'computed', 'note': '由 签单毛利/合同金额 计算'}
    if gr is not None:
        return {'contract_no': contract_no, 'sign_amount': amt, 'sign_gross_profit': gp,
                'gross_rate': gr, 'method': 'stored', 'note': '直接取综合毛利率字段'}
    return {'contract_no': contract_no, 'sign_amount': amt, 'sign_gross_profit': gp,
            'gross_rate': None, 'method': 'no_data', 'note': '缺签单毛利与毛利率，无可计算值'}


# ── 2) 回款周期 ───────────────────────────────────────────
def _main_by_no(contract_no: str) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    try:
        r = conn.execute(
            "SELECT * FROM core_project WHERE contract_no=? OR project_no=? ORDER BY project_id DESC LIMIT 1",
            (contract_no, contract_no)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def milestone_payback_point(contract_no: str) -> Dict[str, Optional[str]]:
    """经 plm_milestone→plm_project→plm_contract 链路取回款里程碑时间点。
    优先级：导入的「回款时间」＞「计划回款时间」＞按名称含“回款/收款”的里程碑实际/计划完成时间。
    返回 {'has_milestone', 'actual', 'plan', 'payback_amount', 'name'}。"""
    conn = get_conn()
    try:
        rows = [dict(r) for r in conn.execute(
            """SELECT m.name, m.actual_end, m.plan_end,
                      m.payback_date, m.plan_payback_date, m.payback_amount
               FROM plm_milestone m
               JOIN plm_project pp ON pp.id = m.project_id
               JOIN plm_contract pc ON pc.id = pp.contract_id
               WHERE pc.contract_no = ?""", (contract_no,)).fetchall()]
    finally:
        conn.close()
    r = None
    if rows:
        r = next((x for x in rows if x.get('payback_date')), None) or \
            next((x for x in rows if x.get('plan_payback_date')), None) or \
            next((x for x in rows if (x.get('name') or '').find('回款') >= 0
                  or (x.get('name') or '').find('收款') >= 0), None)
    if not r:
        return {'has_milestone': False, 'actual': None, 'plan': None,
                'payback_amount': None, 'name': ''}
    return {'has_milestone': True,
            'actual': r.get('payback_date') or r.get('actual_end') or None,
            'plan': r.get('plan_payback_date') or r.get('plan_end') or None,
            'payback_amount': r.get('payback_amount'),
            'name': r.get('name') or ''}


def _last_recv_from_detail(no: str) -> Optional[date]:
    """最后一笔回款日期：收款明细(kind=recv) 的最大 occur_date，算出来的，不读主数据列。"""
    mx: Optional[date] = None
    for x in (get_finance_detail(no).get('recv') or []):
        d0 = x.get('occur_date')
        if d0 and (mx is None or d0 > mx):
            mx = d0
    return mx


def payment_cycle(contract_no: str) -> Dict[str, Any]:
    """回款周期（天）：= 最后一笔回款时间 − 合同签订时间。

    回款时间优先级：PLM 回款里程碑实际/计划时间点 ＞ finance_detail 收款明细 ＞
    主数据 last_received_date（总合同表导入即填充，见 core.import_total_contract）＞
    主数据 payback_cycle 字段（直接给定值时作为权威兜底）。均无则返回 NaN 与说明。
    """
    row = _main_by_no(contract_no)
    if not row:
        return {'contract_no': contract_no, 'sign_date': None, 'last_received_date': None,
                'cycle_days': None, 'note': '主数据无此合同', 'source': 'no_data'}
    sign = _d(row.get('sign_date'))
    ms = milestone_payback_point(contract_no)
    recv_date = None
    source = ''
    if ms['has_milestone']:
        recv_date = _d(ms['actual']) or _d(ms['plan'])
        source = 'plm'
    if recv_date is None:
        recv_date = _last_recv_from_detail(contract_no)
        if recv_date is not None:
            source = 'finance'
    if recv_date is None:
        # 兜底：主数据 last_received_date（总合同表导入即填充，见 import_total_contract）
        lrd = _d(row.get('last_received_date'))
        if lrd is not None:
            recv_date = lrd
            source = 'core'
    # 主数据直接给定回款周期字段时，作为权威值兜底（无任何回款时间点来源时）
    pc_direct = _f(row.get('payback_cycle'))
    if recv_date is None and pc_direct is not None and pc_direct > 0:
        return {'contract_no': contract_no, 'sign_date': row.get('sign_date'),
                'last_received_date': row.get('last_received_date'),
                'milestone_payback': ms, 'recv_date': None,
                'cycle_days': int(round(pc_direct)), 'source': 'core',
                'note': '采用主数据回款周期字段'}
    if sign is None or recv_date is None:
        return {'contract_no': contract_no, 'sign_date': row.get('sign_date'),
                'last_received_date': row.get('last_received_date'),
                'milestone_payback': ms,
                'cycle_days': None, 'note': 'NaN：缺合同签订时间或回款时间点',
                'source': source}
    days = (recv_date - sign).days
    return {'contract_no': contract_no, 'sign_date': row.get('sign_date'),
            'last_received_date': row.get('last_received_date'),
            'milestone_payback': ms, 'recv_date': recv_date.isoformat(),
            'cycle_days': days, 'source': source,
            'note': 'NaN，视为无有效回款' if days is None else ''}


# ── 3) 资金占用（FIFO，口径与 main.py /api/fund 一致）────────
def get_finance_detail(no: str) -> Dict[str, List[Dict[str, Any]]]:
    """读 finance_detail，返回 {'pay': [...occur_date, amount], 'recv': [...]}（日期升序）。

    归集口径：优先按 project_no（主口径），命中不到再回落 contract_no（兼容存量/演示数据）。
    """
    con = get_conn()
    try:
        rows = [dict(r) for r in con.execute(
            "SELECT * FROM finance_detail WHERE project_no=? "
            "OR (COALESCE(project_no,'')='' AND contract_no=?) "
            "ORDER BY occur_date, id",
            (no, no)).fetchall()]
    finally:
        con.close()
    pay = [{'occur_date': _d(r['occur_date']), 'amount': _f(r['amount']) or 0.0, 'date': r['occur_date']}
           for r in rows if r['kind'] == 'pay']
    recv = [{'occur_date': _d(r['occur_date']), 'amount': _f(r['amount']) or 0.0, 'date': r['occur_date']}
            for r in rows if r['kind'] == 'recv']
    # 真实库含 occur_date 为空的行，排序需对 None 兼容（None 排最后），否则比对崩溃
    def _sort_key(x, seq):
        d = x['occur_date']
        return (d is not None, d or date.min, seq)
    pay.sort(key=lambda x: _sort_key(x, 0))
    recv.sort(key=lambda x: _sort_key(x, 1))
    return {'pay': pay, 'recv': recv}


def fifo_occupy_upto(payments: List[Dict[str, Any]], collections: List[Dict[str, Any]],
                     cutoff: date) -> float:
    """FIFO 冲抵资金占用：与 main.py._fifo_occupy_upto 口径一致。"""
    if not payments:
        return 0.0
    first_pay = payments[0]['occur_date']
    if first_pay is None or first_pay > cutoff:
        return 0.0
    pre = sum(c['amount'] for c in collections if c['occur_date'] is not None and c['occur_date'] < first_pay)
    pool: List[float] = []
    for p in payments:
        if p['occur_date'] is None or p['occur_date'] > cutoff:
            continue
        remaining = p['amount']
        if pre > 0:
            off = min(pre, remaining)
            remaining -= off
            pre -= off
        if remaining > 0:
            pool.append(remaining)
    for c in sorted([c for c in collections if c['occur_date'] is not None
                     and first_pay <= c['occur_date'] <= cutoff], key=lambda x: x['occur_date']):
        left = c['amount']
        while left > 0 and pool:
            if pool[0] <= left:
                left -= pool[0]
                pool.pop(0)
            else:
                pool[0] -= left
                left = 0
    return round(sum(pool), 2)


def fund_occupancy(no: str, cutoff: Optional[str] = None) -> Dict[str, Any]:
    """当前资金占用/周转：FIFO 冲抵，返回占用额、付款/回款累计、周转天数。

    no 为归集键：优先按 project_no 归集，无则回落 contract_no。
    """
    fd = get_finance_detail(no)
    if not fd['pay'] and not fd['recv']:
        return {'contract_no': no, 'has_data': False, 'current_occupy': 0.0,
                'total_pay': 0.0, 'total_recv': 0.0, 'turnover_days': None,
                'note': 'finance_detail 无该收付款明细'}
    if cutoff:
        c = _d(cutoff)
    else:
        c = date.today()
    if c is None:
        c = date.today()
    occupy = fifo_occupy_upto(fd['pay'], fd['recv'], c)
    total_pay = round(sum(p['amount'] for p in fd['pay']), 2)
    total_recv = round(sum(r['amount'] for r in fd['recv']), 2)
    # 周转天数：回款累计 ＞0 时用「回款日落差/回款额」近似 + 首付首收时间差简单口径
    turnover_days = None
    recv_days = [d for d in [x['date'] for x in fd['recv']] if d]
    pay_days = [d for d in [x['date'] for x in fd['pay']] if d]
    if total_recv > 0 and pay_days and recv_days:
        first_pay = _d(min(pay_days))
        spans = [(_d(x) - first_pay).days for x in recv_days if _d(x)]
        if spans:
            turnover_days = round(sum(spans) / len(spans), 1)
    return {'contract_no': no, 'has_data': True, 'cutoff': c.isoformat(),
            'current_occupy': occupy, 'total_pay': total_pay, 'total_recv': total_recv,
            'turnover_days': turnover_days, 'note': ''}


# ── finance_detail 写操作（供 seed / 测试）─────────────────
def add_finance_detail(contract_no: str, kind: str, occur_date: str,
                       amount: float, contract_amount: Optional[float] = None,
                       remark: str = '', project_no: str = '') -> Dict[str, Any]:
    if kind not in ('pay', 'recv'):
        return {'success': False, 'error': 'kind 必须为 pay/recv'}
    ensure_finance_detail()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO finance_detail (contract_no, project_no, kind, occur_date, amount, contract_amount, remark, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (contract_no, project_no or '', kind, occur_date, amount, contract_amount, remark, now, now))
        conn.commit()
        return {'success': True, 'id': cur.lastrowid}
    except Exception as e:
        return {'success': False, 'error': str(e)}
    finally:
        conn.close()


def bulk_add_finance_detail(records: List[tuple]) -> int:
    """单事务批量写 finance_detail（供大表导入提速，executemany）。

    records 为 9 元组 (contract_no, project_no, kind, occur_date, amount,
    contract_amount, remark, created_at, updated_at)，返回写入行数。
    """
    ensure_finance_detail()
    conn = get_conn()
    try:
        conn.execute("BEGIN")
        conn.executemany(
            "INSERT INTO finance_detail (contract_no, project_no, kind, occur_date, amount, contract_amount, remark, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            records)
        conn.commit()
        return len(records)
    finally:
        conn.close()


def list_finance_detail(contract_no: str = '') -> List[Dict[str, Any]]:
    conn = get_conn()
    try:
        sql = "SELECT * FROM finance_detail"
        args = ()
        if contract_no:
            sql += " WHERE contract_no=?"
            args = (contract_no,)
        sql += " ORDER BY occur_date, id"
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


# ════ 全量聚合（供财经分析页 /api/core/metrics/* 与数据核对复用）════
def _list_main_projects() -> List[Dict[str, Any]]:
    """取全部主数据行的 (project_no, contract_no, sign_date, sign_amount)。"""
    conn = get_conn()
    try:
        return [dict(r) for r in conn.execute(
            "SELECT project_id, project_no, contract_no, name, sign_date, sign_amount,"
            "  sign_gross_profit, gross_rate, last_received_date, hardware_est, software_est, service_est"
            " FROM core_project ORDER BY project_no, project_id").fetchall()]
    finally:
        conn.close()


def _main_key(row: Dict[str, Any]) -> str:
    """偏好用主数据 project_no，与 finance_detail 主口径保持一致；缺则回落 contract_no。"""
    return (row.get('project_no') or '').strip() or (row.get('contract_no') or '').strip()


def payment_cycle_all() -> Dict[str, Any]:
    """全量回款周期：逐主数据行调用 payment_cycle，汇总明细 + 来源/NaN 统计。"""
    rows = _list_main_projects()
    details: List[Dict[str, Any]] = []
    source_count: Dict[str, int] = {}
    nan_names = []
    valid = 0
    for r in rows:
        no = _main_key(r)
        if not no:
            continue
        d = payment_cycle(no)
        src = d.get('source') or 'no_data'
        source_count[src] = source_count.get(src, 0) + 1
        if d.get('cycle_days') is None:
            nan_names.append(no)
        else:
            valid += 1
        details.append({
            'project_no': r.get('project_no') or '',
            'contract_no': no,
            'name': r.get('name') or '',
            'sign_date': r.get('sign_date'),
            'cycle_days': d.get('cycle_days'),
            'source': src,
            'note': d.get('note', ''),
            'has_milestone': bool((d.get('milestone_payback') or {}).get('has_milestone')),
        })
    return {
        'total': len(details), 'valid': valid, 'nan': len(nan_names),
        'source_count': source_count, 'nan_names': nan_names, 'rows': details,
    }


def _finance_detail_keys() -> List[str]:
    """资金占用归集键：按 project_no 优先，落到 contract_no。确保 project_no 列存在。"""
    ensure_finance_detail()
    conn = get_conn()
    try:
        return [r[0] for r in conn.execute(
            "SELECT DISTINCT CASE WHEN COALESCE(project_no,'')<>'' " 
            "THEN project_no ELSE contract_no END AS k FROM finance_detail"
            " WHERE k<>'' ORDER BY k").fetchall()]
    finally:
        conn.close()


def fund_occupancy_all(cutoff: Optional[str] = None) -> Dict[str, Any]:
    """全量资金占用：按归集键（project_no→contract_no）FIFO 冲抵，汇总明细与校验。"""
    keys = _finance_detail_keys()
    rows = []
    total_pay = total_recv = total_occupy = 0.0
    keys_with_data = 0
    for k in keys:
        d = fund_occupancy(k, cutoff)
        tp = d.get('total_pay') or 0.0
        tr = d.get('total_recv') or 0.0
        to = d.get('current_occupy') or 0.0
        total_pay += tp
        total_recv += tr
        total_occupy += to
        if d.get('has_data'):
            keys_with_data += 1
        rows.append({
            'key': k,
            'total_pay': tp, 'total_recv': tr, 'current_occupy': to,
            'turnover_days': d.get('turnover_days'),
            'has_data': d.get('has_data'),
            'note': d.get('note', ''),
        })
    return {
        'total_keys': len(keys), 'keys_with_data': keys_with_data,
        'total_pay': round(total_pay, 2), 'total_recv': round(total_recv, 2),
        'total_occupy': round(total_occupy, 2), 'rows': rows,
    }


def gross_margin_all() -> Dict[str, Any]:
    """全量毛利率：逐主数据行按 签单毛利/合同额 计算，汇总方法/缺失统计。"""
    rows = _list_main_projects()
    details = []
    method_count: Dict[str, int] = {}
    missing_amount = missing_gross_profit = 0
    for r in rows:
        no = _main_key(r)
        if not no:
            continue
        d = project_gross_margin(no)
        method = d.get('method') or 'no_data'
        method_count[method] = method_count.get(method, 0) + 1
        amt = d.get('sign_amount')
        gp = d.get('sign_gross_profit')
        if amt is None or (isinstance(amt, (int, float)) and amt <= 0):
            missing_amount += 1
        if gp is None:
            missing_gross_profit += 1
        details.append({
            'project_no': r.get('project_no') or '',
            'contract_no': no,
            'name': r.get('name') or '',
            'sign_amount': amt,
            'sign_gross_profit': gp,
            'gross_rate': d.get('gross_rate'),
            'method': method,
            'note': d.get('note', ''),
        })
    return {
        'total': len(details),
        'method_count': method_count,
        'missing_amount': missing_amount,
        'missing_gross_profit': missing_gross_profit,
        'rows': details,
    }


# ── 指标快照缓存（reads 秒级；显式 ?refresh=1 才全量重算）────────────────
# 复用 models.analysis_snapshots 表（job_key UNIQUE / result_json / updated_at），
# 按 'metrics:payment-cycle' / 'metrics:fund' / 'metrics:gross' 存 JSON 结果。
def snapshot_get(key: str) -> Optional[Dict[str, Any]]:
    """读指标快照：返回 {'payload': 已反序列化 dict, 'updated_at': str}；无快照返回 None。"""
    conn = get_conn()
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS analysis_snapshots ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  job_key TEXT UNIQUE NOT NULL,"
            "  result_json TEXT NOT NULL,"
            "  updated_at TEXT DEFAULT (datetime('now','localtime')))")
        r = conn.execute(
            "SELECT result_json, updated_at FROM analysis_snapshots WHERE job_key=?",
            (key,)).fetchone()
        if not r:
            return None
        return {'payload': json.loads(r['result_json']), 'updated_at': r['updated_at']}
    finally:
        conn.close()


def snapshot_delete(key: str) -> None:
    """删除指标快照（导入新数据后清掉，强制下次访问重算）。"""
    conn = get_conn()
    try:
        conn.execute("DELETE FROM analysis_snapshots WHERE job_key=?", (key,))
        conn.commit()
    finally:
        conn.close()


METRIC_SNAPSHOT_KEYS = ('metrics:payment-cycle', 'metrics:fund',
                        'metrics:gross', 'metrics:cost-warning')


def invalidate_metric_snapshots() -> None:
    """导入主数据/收付款明细后调用：清除指标快照缓存。

    避免前端默认读缓存时命中「导入前」的空快照，导致「数据已导入但指标算不出来」。
    清掉后下次访问自动重算并写入新快照。
    """
    for k in METRIC_SNAPSHOT_KEYS:
        snapshot_delete(k)


def snapshot_put(key: str, payload: Any) -> str:
    """写指标快照（UPSERT，result_json / updated_at），返回 updated_at 字符串。"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = get_conn()
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS analysis_snapshots ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  job_key TEXT UNIQUE NOT NULL,"
            "  result_json TEXT NOT NULL,"
            "  updated_at TEXT DEFAULT (datetime('now','localtime')))")
        conn.execute(
            "INSERT INTO analysis_snapshots (job_key, result_json, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(job_key) DO UPDATE SET "
            "  result_json=excluded.result_json, updated_at=excluded.updated_at",
            (key, json.dumps(payload, ensure_ascii=False, default=str), now))
        conn.commit()
    finally:
        conn.close()
    return now


# ════════════════════════════════════════════════════════════════════
# 财经独立页 · 1:1 复刻旧门户（openFundOccupancy / openPaymentCycle）所需富数据
# 数据来源统一为 finance_detail 收付款明细 + core_project 主数据维度。
# 旧门户资金占用列一个不落地照搬（含片段数/元天/周期/成本/同比/风险），
# 缺省的「年化成本率」按旧门户 REPORT_CUTOFF/ANNUAL_COST_RATE 常量补齐；
# 客户键沿用旧门户确定性脱敏编码（不展示真实客户名）。
# ════════════════════════════════════════════════════════════════════
REPORT_CUTOFF = '2026-08-12'
ANNUAL_COST_RATE = 0.03


def _si(v):
    return '' if v is None else str(v).strip()


def _encode_customer_key(name):
    """确定性脱敏编码（对齐 main._encode_customer_key）。"""
    if not name:
        return ''
    s = str(name).strip()
    if re.fullmatch(r'[A-Za-z0-9]{2,20}', s):
        return s
    return hashlib.md5(s.encode('utf-8')).hexdigest()[:8].upper()


def _risk_config():
    """读 risk_config 阈值（与主数据同库），缺省用旧门户默认值。"""
    defaults = {'days_green': 30, 'days_yellow': 90, 'days_orange': 180,
                'recv_rate': 0.5, 'intensity': 0.5, 'amount_high': 1000000,
                'trend_months': 2}
    try:
        conn = get_conn()
        try:
            for r in conn.execute("SELECT key, value FROM risk_config").fetchall():
                defaults[r['key']] = float(r['value'])
        finally:
            conn.close()
    except Exception:
        pass
    return defaults


def _calc_risk_level(occupy_days, recv_rate, occupy_intensity, occupy_amount, cfg):
    """风险分级纯函数（对齐 main._calc_risk_level）。"""
    days_green = cfg.get('days_green', 30)
    days_yellow = cfg.get('days_yellow', 90)
    days_orange = cfg.get('days_orange', 180)
    rr = cfg.get('recv_rate', 0.5)
    inten = cfg.get('intensity', 0.5)
    amount_high = cfg.get('amount_high', 1000000)
    if recv_rate == 0 and occupy_amount >= amount_high:
        return 'red', '回款为0且占用金额超阈值，立即催收并上报'
    if occupy_days <= days_green:
        return 'healthy', '正常回款周期内'
    if occupy_days <= days_yellow:
        return 'yellow', '占用超过回款周期，提醒跟进回款'
    if occupy_days <= days_orange:
        if recv_rate >= rr:
            return 'yellow', '占用偏高但回款率达标，持续关注'
        return 'orange', '占用偏高且回款率不足，通知区域/部门负责人'
    if occupy_intensity <= inten:
        return 'orange', '长期占用但占用强度可控，安排对账催收'
    return 'red', '长期占用且占用强度过高，强制干预（催收/对账/上报）'


def _calc_trend_warning(monthly_occupy, trend_months=2):
    """趋势预警纯函数（对齐 main._calc_trend_warning）。"""
    if len(monthly_occupy) < trend_months + 1:
        return False, ''
    vals = [float(m.get('occupy', 0) or 0) for m in monthly_occupy]
    tail = vals[-(trend_months + 1):]
    ok = all(tail[i + 1] > tail[i] for i in range(trend_months))
    if ok:
        desc = '、'.join("%s:%.0f" % (m['month'], float(m.get('occupy', 0) or 0))
                         for m in monthly_occupy[-trend_months - 1:])
        return True, '占用金额连续%d个月上升（%s）' % (trend_months, desc)
    return False, ''


def _main_for_key(key):
    """按归集键（project_no 优先回落 contract_no）取 core_project 主数据行。"""
    conn = get_conn()
    try:
        r = conn.execute(
            "SELECT * FROM core_project WHERE project_no=? OR contract_no=? "
            "ORDER BY project_id DESC LIMIT 1", (key, key)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def _fund_dims(row):
    """从 core_project 主数据行映射资金占用维度字段（旧门户列名）。"""
    if not row:
        return {}
    d = _d(row.get('sign_date'))
    return {
        '区域': _si(row.get('region')),
        '省份': _si(row.get('province')),
        '部门': _si(row.get('biz_line') or row.get('dept')),
        '业务线': _si(row.get('biz_line')),
        '行业': _si(row.get('industry')),
        '客户键': _encode_customer_key(row.get('customer_key')),
        '项目状态': _si(row.get('status')),
        '合同状态': _si(row.get('status')),
        '签约年份': _si(row.get('stat_year')) or (str(d.year) if d else ''),
        '合同额': _f(row.get('sign_amount')) or 0,
    }


def _fund_seg_metrics(pay, recv, cutoff):
    """FIFO 垫资片段计算（对齐主门户 fund_analyze 逐片段口径）。

    返回 dict：segments/current_occupy/sum_amount_day/cycle_start/cycle_days/
    avg_occupy/estimate_cost/settled/occupying/segment_count/occupy_days/preset。
    """
    p_eff = [p for p in pay if p.get('occur_date') is not None]
    base = {'segments': [], 'current_occupy': 0, 'sum_amount_day': 0, 'cycle_start': None,
            'cycle_days': 0, 'avg_occupy': 0, 'estimate_cost': 0,
            'settled': 0, 'occupying': 0, 'segment_count': 0, 'occupy_days': 0, 'preset': 0}
    if not p_eff:
        return base
    first_pay = min(p['occur_date'] for p in p_eff)
    pre = [c for c in recv if c.get('occur_date') is not None and c['occur_date'] < first_pay]
    reg = [c for c in recv if c.get('occur_date') is not None and c['occur_date'] >= first_pay]
    pre_bal = sum(c['amount'] for c in pre)
    segments = []
    pool = []
    for p in p_eff:
        rem = p['amount']
        if pre_bal > 0:
            off = min(pre_bal, rem)
            rem -= off
            pre_bal -= off
            if off > 0:
                segments.append({'segment_status': 'PRESETTLED',
                                 'pay_occur_date': p['occur_date'].isoformat(),
                                 'segment_amount': round(off),
                                 'end_date': p['occur_date'].isoformat(),
                                 'occupy_days': 0, 'amount_day': 0})
        if rem > 0:
            pool.append({'pay_date': p['occur_date'], 'remain': rem})
    for c in sorted(reg, key=lambda x: x['occur_date']):
        left = c['amount']
        while left > 0 and pool:
            item = pool[0]
            days = (c['occur_date'] - item['pay_date']).days
            if days < 0:
                days = 0
            if item['remain'] <= left:
                segments.append({'segment_status': 'SETTLED',
                                 'pay_occur_date': item['pay_date'].isoformat(),
                                 'segment_amount': round(item['remain']),
                                 'end_date': c['occur_date'].isoformat(),
                                 'occupy_days': days,
                                 'amount_day': round(item['remain'] * days)})
                left -= item['remain']
                pool.pop(0)
            else:
                segments.append({'segment_status': 'SETTLED',
                                 'pay_occur_date': item['pay_date'].isoformat(),
                                 'segment_amount': round(left),
                                 'end_date': c['occur_date'].isoformat(),
                                 'occupy_days': days,
                                 'amount_day': round(left * days)})
                item['remain'] -= left
                left = 0
    for item in pool:
        days = (cutoff - item['pay_date']).days
        if days < 0:
            days = 0
        segments.append({'segment_status': 'OCCUPYING',
                         'pay_occur_date': item['pay_date'].isoformat(),
                         'segment_amount': round(item['remain']),
                         'end_date': cutoff.isoformat(),
                         'occupy_days': days,
                         'amount_day': round(item['remain'] * days)})
    current_occupy = round(sum(s['segment_amount'] for s in segments
                               if s['segment_status'] == 'OCCUPYING'))
    sum_amount_day = round(sum(s['amount_day'] for s in segments))
    cycle_days = (cutoff - first_pay).days
    if cycle_days <= 0:
        cycle_days = 0
    avg_occupy = round(sum_amount_day / cycle_days) if cycle_days > 0 else 0
    estimate_cost = round(sum_amount_day * (ANNUAL_COST_RATE / 365))
    settled = sum(1 for s in segments if s['segment_status'] == 'SETTLED')
    occupying = sum(1 for s in segments if s['segment_status'] == 'OCCUPYING')
    preset = len(segments) - settled - occupying
    occ_amt = sum(s['segment_amount'] for s in segments if s['segment_status'] == 'OCCUPYING')
    occupy_days = round(sum(s['amount_day'] for s in segments if s['segment_status'] == 'OCCUPYING')
                        / occ_amt) if occ_amt > 0 else 0
    return {'segments': segments, 'current_occupy': current_occupy,
            'sum_amount_day': sum_amount_day, 'cycle_start': first_pay,
            'cycle_days': cycle_days, 'avg_occupy': avg_occupy,
            'estimate_cost': estimate_cost, 'settled': settled, 'occupying': occupying,
            'segment_count': len(segments), 'occupy_days': occupy_days, 'preset': preset}


def fund_result_full(cutoff: Optional[str] = None) -> Dict[str, Any]:
    """资金占用全量富数据（1:1 复刻旧门户 /api/fund/metrics + /api/fund/analyze）。

    返回 data：summary / columns / rows(逐合同含全列) / flows / yoy / 汇总键。
    """
    cd = _d(cutoff or REPORT_CUTOFF) or date(2026, 8, 12)
    prev_cd = date(cd.year - 1, cd.month, cd.day)
    risk_cfg = _risk_config()
    keys = _finance_detail_keys()
    rows = []
    global_flows = []
    grand_prev = 0
    for k in keys:
        fd = get_finance_detail(k)
        pay, recv = fd['pay'], fd['recv']
        total_pay = round(sum(p['amount'] for p in pay))
        total_recv = round(sum(r['amount'] for r in recv))
        # 全局现金流序列（供同比/总览图）
        ev = []
        for p in pay:
            if p['occur_date'] is not None:
                ev.append((p['occur_date'], 'PAY', -round(p['amount'])))
        for r in recv:
            if r['occur_date'] is not None:
                ev.append((r['occur_date'], 'RECEIVE', round(r['amount'])))
        ev.sort(key=lambda x: (x[0], 1 if x[1] == 'RECEIVE' else 0))
        bal = 0
        for d0, t, amt in ev:
            bal += amt
            global_flows.append({'date': d0.isoformat(), 'type': t, 'amount': amt})
        dims = _fund_dims(_main_for_key(k))
        contract_amount = round(dims.get('合同额') or 0)
        seg = _fund_seg_metrics(pay, recv, cd)
        prev_occupy = round(fifo_occupy_upto(pay, recv, prev_cd))
        grand_prev += prev_occupy
        current_occupy = seg['current_occupy']
        recv_rate = round(total_recv / contract_amount, 4) if contract_amount > 0 else 0
        occupy_intensity = (round(current_occupy / contract_amount, 4) if contract_amount > 0
                            else (round(current_occupy / total_pay, 4) if total_pay > 0 else 0))
        risk_level, suggestion = _calc_risk_level(seg['occupy_days'], recv_rate,
                                                  occupy_intensity, current_occupy, risk_cfg)
        recv_dates = [r['occur_date'] for r in recv if r['occur_date'] is not None]
        last_recv = max(recv_dates).isoformat() if recv_dates else ''
        rows.append({
            '合同编号': k,
            '合同额': contract_amount,
            '累计付款': total_pay,
            '累计收款': total_recv,
            '净现金流': total_recv - total_pay,
            '当前资金占用': current_occupy,
            '上年同期占用': prev_occupy,
            '元天合计': seg['sum_amount_day'],
            '周期起始日': seg['cycle_start'].isoformat() if seg['cycle_start'] else '-',
            '周期总天数': seg['cycle_days'],
            '平均资金占用': seg['avg_occupy'],
            '预估资金成本': seg['estimate_cost'],
            '年化成本率': '%d%%' % (ANNUAL_COST_RATE * 100),
            '片段数': seg['segment_count'],
            '已结清片段': seg['settled'],
            '占用中片段': seg['occupying'],
            '区域': dims.get('区域', ''),
            '省份': dims.get('省份', ''),
            '部门': dims.get('部门', ''),
            '业务线': dims.get('业务线', ''),
            '行业': dims.get('行业', ''),
            '客户键': dims.get('客户键', ''),
            '项目状态': dims.get('项目状态', ''),
            '合同状态': dims.get('合同状态', ''),
            '签约年份': dims.get('签约年份', ''),
            '回款率': recv_rate,
            '占用强度': occupy_intensity,
            '风险等级': risk_level,
            '风险建议': suggestion,
            '最后一次回款': last_recv,
        })
    # 过滤纯收款合同（无付款、无占用），排序：纯付款→有付有收→组内占用降序
    def _skey(r):
        pay = r['累计付款']
        recv = r['累计收款']
        cat = 0 if (pay > 0 and recv == 0) else (1 if (pay > 0 and recv > 0) else 2)
        return (cat, -r['当前资金占用'])
    rows = [r for r in rows if r['累计付款'] > 0]
    rows.sort(key=_skey)
    n = len(rows)
    grand_pay = sum(r['累计付款'] for r in rows)
    grand_recv = sum(r['累计收款'] for r in rows)
    grand_occupy = sum(r['当前资金占用'] for r in rows)
    grand_day = sum(r['元天合计'] for r in rows)
    grand_cost = sum(r['预估资金成本'] for r in rows)
    summary = {
        '合同总数': '%d个' % n,
        '累计付款总额': '¥%s' % format(grand_pay, ','),
        '累计收款总额': '¥%s' % format(grand_recv, ','),
        '净现金流总额': '¥%s' % format(grand_recv - grand_pay, ','),
        '当前资金占用总额': '¥%s' % format(grand_occupy, ','),
        '总加权资金占用': format(grand_day, ','),
        '预估资金成本': '¥%s' % format(grand_cost, ','),
        '年化成本率': '%d%%' % (ANNUAL_COST_RATE * 100),
        '报表截止日': cd.isoformat(),
    }
    columns = ['合同编号', '累计付款', '累计收款', '净现金流', '当前资金占用',
               '平均资金占用', '预估资金成本', '周期总天数', '片段数']
    return {
        'success': True,
        'message': '分析完成：%d个合同，当前资金占用 ¥%s' % (n, format(grand_occupy, ',')),
        'data': {
            'summary': summary, 'columns': columns, 'rows': rows,
            'flows': global_flows, 'yoy': {'occupy_prev': round(grand_prev)},
            'total_keys': len(keys), 'keys_with_data': n,
            'total_pay': grand_pay, 'total_recv': grand_recv, 'total_occupy': grand_occupy,
        },
    }


def fund_dim_aggregate(dim: str = 'region') -> Dict[str, Any]:
    """维度聚合（区域/省份/客户集合/签约年份），对齐旧门户 /api/fund/dim/aggregate。"""
    data = fund_result_full()
    rows = data['data']['rows']
    dim_map = {'region': '区域', 'province': '省份', 'customer_key': '客户键',
               'sign_year': '签约年份'}
    col = dim_map.get(dim, '区域')
    groups = {}
    order = []
    for r in rows:
        k = _si(r.get(col)) or '未知'
        if k not in groups:
            groups[k] = {'cnt': 0, 'occ': 0.0, 'prev': 0.0, 'recv': 0.0, 'pay': 0.0,
                         'amt': 0.0, 'risk': {'healthy': 0, 'yellow': 0, 'orange': 0, 'red': 0}}
            order.append(k)
        g = groups[k]
        g['cnt'] += 1
        g['occ'] += r['当前资金占用']
        g['prev'] += r['上年同期占用']
        g['recv'] += r['累计收款']
        g['pay'] += r['累计付款']
        g['amt'] += r['合同额']
        g['risk'][r['风险等级']] = g['risk'].get(r['风险等级'], 0) + 1
    out = []
    for k in order:
        g = groups[k]
        amt = g['amt'] if g['amt'] > 0 else g['pay']
        recv_rate = round(g['recv'] / amt, 4) if amt > 0 else 0
        occupy_intensity = round(g['occ'] / amt, 4) if amt > 0 else 0
        risk_level = ('red' if g['risk']['red'] > 0 else 'orange' if g['risk']['orange'] > 0
                      else 'yellow' if g['risk']['yellow'] > 0 else 'healthy')
        out.append({'name': k, 'contract_count': g['cnt'], 'current_occupy': round(g['occ']),
                    'prev_occupy': round(g['prev']), 'total_recv': round(g['recv']),
                    'total_pay': round(g['pay']), 'contract_amount': round(g['amt']),
                    'recv_rate': recv_rate, 'occupy_intensity': occupy_intensity,
                    'risk_level': risk_level, 'risk_count': g['risk']})
    return {'success': True, 'rows': out}


def fund_dim_drill(dim: str, value: str) -> Dict[str, Any]:
    """维度穿透下钻：返回该维度桶下的合同清单（对齐旧 /api/fund/dim/drill）。"""
    data = fund_result_full()
    rows = data['data']['rows']
    dim_map = {'region': '区域', 'province': '省份', 'customer_key': '客户键',
               'sign_year': '签约年份'}
    col = dim_map.get(dim, '区域')
    hit = [r for r in rows if (_si(r.get(col)) or '未知') == value]
    total_occ = sum(r['当前资金占用'] for r in hit)
    return {'success': True, 'rows': hit, 'total_occupy': round(total_occ)}


def fund_risk_list() -> Dict[str, Any]:
    """预警清单（对齐旧 /api/fund/risk/list 与风险卡统计）。"""
    data = fund_result_full()
    rows = data['data']['rows']
    stat = {'healthy': 0, 'yellow': 0, 'orange': 0, 'red': 0}
    rname = {'healthy': '健康', 'yellow': '关注', 'orange': '预警', 'red': '高危'}
    out = []
    for r in rows:
        lv = r['风险等级']
        stat[lv] = stat.get(lv, 0) + 1
        out.append({
            'contract_no': r['合同编号'], 'customer_key': r['客户键'], 'region': r['区域'],
            'dept': r['部门'], 'project_status': r['项目状态'],
            'current_occupy': r['当前资金占用'], 'recv_rate': r['回款率'],
            'occupy_intensity': r['占用强度'], 'risk_level': lv,
            'risk_name': rname.get(lv, lv), 'suggestion': r['风险建议'],
        })
    return {'success': True, 'stat': stat, 'rows': out}


def save_risk_config(payload: Dict[str, Any]) -> Dict[str, Any]:
    """持久化风险阈值（对齐旧 /api/fund/risk/config POST），缺表时先建表再 UPSERT。"""
    allowed = {'days_green', 'days_yellow', 'days_orange', 'recv_rate',
               'intensity', 'amount_high', 'trend_months'}
    try:
        conn = get_conn()
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS risk_config "
                "(key TEXT PRIMARY KEY, value REAL, description TEXT)")
            desc_map = {'days_green': '占用≤N天为健康', 'days_yellow': '占用N天以内为关注',
                        'days_orange': '占用>N天进入预警/高危判定', 'recv_rate': '回款率阈值',
                        'intensity': '占用强度阈值', 'amount_high': '回款率=0 且占用金额阈值',
                        'trend_months': '占用金额环比连续上升N个月'}
            for k, v in (payload or {}).items():
                if k not in allowed:
                    continue
                val = float(v)
                conn.execute(
                    "INSERT INTO risk_config (key, value, description) VALUES (?,?,?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (k, val, desc_map.get(k, '')))
            conn.commit()
        finally:
            conn.close()
        return {'success': True, 'message': '已保存并生效（重新加载资金占用分析）'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def _month_end(yr, mo):
    if mo == 12:
        return date(yr, 12, 31)
    nxt = date(yr, mo + 1, 1)
    return nxt - timedelta(days=1)


def fund_risk_trend(dim: str = 'region') -> Dict[str, Any]:
    """维度趋势预警：按月占用序列判断连续上升（对齐旧 /api/fund/risk/trend）。"""
    cfg = _risk_config()
    dim_col = {'region': '区域', 'customer_key': '客户键', 'province': '省份',
               'sign_year': '签约年份'}.get(dim, '区域')
    from collections import defaultdict
    key_dims = {}
    for k in _finance_detail_keys():
        key_dims[k] = _si(_fund_dims(_main_for_key(k)).get(dim_col)) or '未知'
    # 近数月（含 8 月截止日）
    months = []
    for mo in (4, 5, 6, 7):
        months.append(_month_end(2026, mo))
    monthly = defaultdict(lambda: defaultdict(float))
    for k in _finance_detail_keys():
        fd = get_finance_detail(k)
        dimname = key_dims[k]
        for me in months:
            monthly[dimname][me] += fifo_occupy_upto(fd['pay'], fd['recv'], me)
    warnings = []
    for dimname, seq in monthly.items():
        seq_list = [{'month': me.strftime('%Y-%m'), 'occupy': seq[me]} for me in months]
        ok, desc = _calc_trend_warning(seq_list, int(cfg.get('trend_months', 2)))
        if ok:
            warnings.append({'dim': dim, 'dim_value': dimname, 'message': desc})
    return {'success': True, 'warnings': warnings}


def fund_segments_detail(key: str) -> Dict[str, Any]:
    """资金占用详情弹窗富数据（对齐旧 /api/fund/segments/{cno}）。"""
    fd = get_finance_detail(key)
    pay, recv = fd['pay'], fd['recv']
    cd = _d(REPORT_CUTOFF) or date(2026, 8, 12)
    seg_metrics = _fund_seg_metrics(pay, recv, cd)
    payments = [{'flow_id': f'{key}-PAY-{i:03d}', 'occur_date': p['occur_date'].isoformat()
                 if p['occur_date'] else '', 'amount': round(p['amount'])}
                for i, p in enumerate(pay, 1)]
    collections = [{'flow_id': f'{key}-REC-{i:03d}', 'occur_date': c['occur_date'].isoformat()
                    if c['occur_date'] else '', 'amount': round(c['amount'])}
                   for i, c in enumerate(recv, 1)]
    ev = []
    for p in pay:
        if p['occur_date'] is not None:
            ev.append((p['occur_date'], 'PAY', -round(p['amount'])))
    for c in recv:
        if c['occur_date'] is not None:
            ev.append((c['occur_date'], 'RECEIVE', round(c['amount'])))
    ev.sort(key=lambda x: (x[0], 1 if x[1] == 'RECEIVE' else 0))
    cashflow = []
    bal = 0
    for d0, t, amt in ev:
        bal += amt
        cashflow.append({'date': d0.isoformat(), 'type': t, 'amount': amt, 'balance': round(bal)})
    monthly = {}
    for d0, t, amt in ev:
        mk = d0.strftime('%Y-%m')
        m = monthly.setdefault(mk, {'month': mk, 'pay_amount': 0, 'recv_amount': 0})
        if t == 'PAY':
            m['pay_amount'] += amt
        else:
            m['recv_amount'] += amt
    cm = []
    mbal = 0
    for mk in sorted(monthly):
        m = monthly[mk]
        mbal += m['recv_amount'] + m['pay_amount']
        cm.append({'month': mk, 'pay_amount': round(m['pay_amount']),
                   'recv_amount': round(m['recv_amount']),
                   'net': round(m['recv_amount'] + m['pay_amount']),
                   'balance': round(mbal)})
    total_pay = round(sum(p['amount'] for p in pay))
    total_recv = round(sum(c['amount'] for c in recv))
    local_summary = {
        'current_occupy': seg_metrics['current_occupy'],
        'sum_amount_day': seg_metrics['sum_amount_day'],
        'total_segments': seg_metrics['segment_count'],
        'total_pay': total_pay, 'total_recv': total_recv,
        'net': total_recv - total_pay,
        'turnover_days': None,
    }
    return {'success': True, 'segments': seg_metrics['segments'],
            'flows': {'payments': payments, 'collections': collections},
            'cashflow': cashflow, 'cashflow_monthly': cm,
            'local_summary': local_summary}


# ── 回款周期 · 富数据（1:1 复刻旧门户 /api/analysis/payment-cycle）──
def _pc_cycle_fields(no):
    d = payment_cycle(no)
    return d.get('cycle_days'), (d.get('recv_date') or '')


def _pc_enrich(records, target_year):
    # ★统一入口（2026-09-03）：回款周期一律走本体 ontos F-payment-cycle，
    # 与 /api/ontos/scenario/payment-cycle 及智能体问答(ontology_compute)共用同一份算法，
    # 避免同一平台内多套口径并存。延迟导入以避免与 ontos_abox 循环依赖。
    from ontos_abox import abox_payment_cycle, _norm_date

    out = []
    for r in records:
        no = _main_key(r)
        if not no:
            continue
        # 用 _norm_date 而非 _d：core_project.sign_date 存的是 Excel 序列值
        # （如 46234），_d 不解析会导致全部记录被 continue 掉、页面无数据。
        sign = _norm_date(r.get('sign_date'))
        if not sign or int(sign[:4]) != target_year:
            continue
        o = abox_payment_cycle(no, basis='last')
        cd = o.get('cycle_days') if o.get('success') else None
        rd = o.get('recv_date') or ''
        note = (o.get('note') or '').strip()
        anomaly = bool(o.get('anomaly')) or (cd is not None and cd < 0) or ('异常' in note)
        # ★语义：负周期为数据异常（回款早于签约），不可落入正常时间桶，
        # 否则会被 years<0.5 误判为"0.5年以内"，污染分布与区域均值。
        if anomaly:
            years = 0
            zone = '异常(回款早于签约)'
        else:
            years = round(cd / 365, 4) if cd else 0
            if years < 0.5:
                zone = '0.5以内'
            elif years < 1:
                zone = '0.5-1年'
            elif years < 2:
                zone = '1年以上'
            elif years < 3:
                zone = '2年以上'
            else:
                zone = '3年以上'
        # _list_main_projects 未 select 区域/省份/部门，需按归集键补主数据维度
        m = _main_for_key(no) or {}
        out.append({'contract_no': no, 'sign_date': sign,
                    'dept': _si(m.get('biz_line') or m.get('dept')),
                    'region': _si(m.get('region')), 'province': _si(m.get('province')),
                    'amount': _f(r.get('sign_amount')) or 0,
                    'last_payback_date': rd, 'cycle_days': cd, 'years': years, 'zone': zone,
                    'anomaly': anomaly, 'note': note})
    return out


def payment_cycle_result_full() -> Dict[str, Any]:
    """回款周期富数据：months/icid/department/zones/enriched_rows/regions/province_stats。"""
    rows = _list_main_projects()
    e26 = _pc_enrich(rows, 2026)
    e25 = _pc_enrich(rows, 2025)

    def _region_agg(enr, key):
        st = {}
        for r in enr:
            k = _si(r.get(key)) or '未知'
            g = st.setdefault(k, {'count': 0, 'total_days': 0, 'with_payment': 0,
                                  'no_payment': 0, 'total_amount': 0.0})
            cd = r.get('cycle_days') or 0
            amt = r.get('amount') or 0
            g['count'] += 1
            g['total_days'] += cd
            g['total_amount'] += amt
            if cd > 0:
                g['with_payment'] += 1
            else:
                g['no_payment'] += 1
        return [{'name': k, 'count': v['count'],
                 # ★均值只对有周期值的记录求（除以 with_payment 而非 count），
                 # 否则"算不出"的会被当成 0 天计入分母，把区域均值整体拉低。
                 'avg_days': (round(v['total_days'] / v['with_payment'])
                              if v['with_payment'] > 0 else 0),
                 'with_payment': v['with_payment'], 'no_payment': v['no_payment'],
                 'amount': round(v['total_amount'])}
                for k, v in sorted(st.items(), key=lambda x: -x[1]['count'])]

    region_agg = _region_agg(e26, 'region')
    prov_agg = _region_agg(e26, 'province')
    # 兼容 renderPaymentAnalysis 期望的字段名 region/province（旧接口直接透传）
    region_out = [{'region': r['name'], 'count': r['count'], 'avg_days': r['avg_days'],
                   'with_payment': r['with_payment'], 'no_payment': r['no_payment'],
                   'amount': r['amount']} for r in region_agg]
    prov_out = [{'province': r['name'], 'count': r['count'], 'avg_days': r['avg_days'],
                 'with_payment': r['with_payment'], 'no_payment': r['no_payment'],
                 'amount': r['amount']} for r in prov_agg]

    target_months = [(2026, 6), (2026, 7), (2026, 8)]

    def _calc_metrics(lst):
        count = len(lst)
        total_amount = sum(r['amount'] for r in lst)
        # ★统一入口后 cycle_days 可能为 None（无里程碑计划回款 = 算不出）。
        # 求和与均值只统计有值的记录，不可把"算不出"当 0 天计入——那会拉低
        # 平均值、污染分布（正是旧 ETL 宽表 82% 填 0 的老毛病）。
        days = [r['cycle_days'] for r in lst if r.get('cycle_days') is not None]
        total_cycle = sum(days)
        avg_cycle = round(total_cycle / len(days), 1) if days else 0
        avg_years = round(avg_cycle / 365, 2) if avg_cycle > 0 else 0
        zones = [0, 0, 0, 0, 0]
        for r in lst:
            yrs = r['years']
            if yrs <= 0:
                continue
            if yrs < 0.5:
                zones[0] += 1
            elif yrs < 1:
                zones[1] += 1
            elif yrs < 2:
                zones[2] += 1
            elif yrs < 3:
                zones[3] += 1
            else:
                zones[4] += 1
        return {'project_count': count, 'valid_count': len(days),
                'contract_amount': round(total_amount / 10000, 2),
                'cumulative_days': total_cycle, 'avg_days': avg_cycle,
                'avg_years': avg_years, 'zones': zones}

    def _in_month(sign_date, year, month):
        sd = _d(sign_date)
        if not sd:
            return False
        return sd.year < year or (sd.year == year and sd.month <= month)

    months_result = []
    icid_result = {'project_count': {}, 'cumulative_days': {}, 'avg_days': {},
                   'avg_years': {}, 'contract_amount': {}}
    dept_result = {'project_count': {}, 'cumulative_days': {}, 'avg_days': {},
                   'avg_years': {}, 'contract_amount': {}}
    zones_result = []
    for y, m in target_months:
        m_key = '%d-%02d' % (y, m)
        py = 2025
        cur = [r for r in e26 if _in_month(r['sign_date'], y, m)]
        prev = [r for r in e25 if _in_month(r['sign_date'], py, m)]
        cur_icid = _calc_metrics(cur)
        prev_icid = _calc_metrics(prev)
        cur_dept = _calc_metrics([r for r in cur if '系统集成' in r['dept']])
        prev_dept = _calc_metrics([r for r in prev if '系统集成' in r['dept']])
        months_result.append({'key': m_key, 'label': '%d年%d月' % (y, m),
                              'current': '%d年%d月' % (y, m), 'last_year': '%d年%d月' % (py, m)})
        def _diff(cv, pv):
            if isinstance(cv, (int, float)) and isinstance(pv, (int, float)):
                return round(cv - pv, 2)
            return None
        for metric in ['project_count', 'cumulative_days', 'avg_days', 'avg_years',
                       'contract_amount']:
            cv, pv = cur_icid[metric], prev_icid[metric]
            icid_result[metric][m_key] = {'current': cv, 'previous': pv, 'diff': _diff(cv, pv)}
            cv, pv = cur_dept[metric], prev_dept[metric]
            dept_result[metric][m_key] = {'current': cv, 'previous': pv, 'diff': _diff(cv, pv)}
        for zi in range(5):
            if len(zones_result) <= zi:
                zones_result.append({})
            zones_result[zi][m_key] = {'current': cur_icid['zones'][zi],
                                       'previous': prev_icid['zones'][zi],
                                       'diff': cur_icid['zones'][zi] - prev_icid['zones'][zi]}
    total_row = {}
    for m in months_result:
        mk = m['key']
        tc = sum(zones_result[zi][mk]['current'] for zi in range(5))
        tp = sum(zones_result[zi][mk]['previous'] for zi in range(5))
        total_row[mk] = {'current': tc, 'previous': tp, 'diff': tc - tp}
    zones_result.append(total_row)

    pc_all = payment_cycle_all()
    return {
        'success': True,
        'data': {
            'source_version': 1,
            'months': months_result,
            'icid': icid_result,
            'department': dept_result,
            'zones': [{'data': z} for z in zones_result],
            'enriched_rows': e26[:500],
            'enriched_total': len(e26),
            'regions': region_out,
            'province_stats': prov_out,
            # 兼容旧 /api/core/metrics/payment-cycle（payment_cycle_all 结构）
            'total': pc_all['total'], 'valid': pc_all['valid'], 'nan': pc_all['nan'],
            'source_count': pc_all['source_count'],
            'rows': [{'project_no': r.get('project_no') or '', 'contract_no': r['contract_no'],
                      'name': r.get('name') or '', 'sign_date': r.get('sign_date'),
                      'cycle_days': r.get('cycle_days'), 'source': r.get('source'),
                      'note': r.get('note'), 'has_milestone': r.get('has_milestone')}
                     for r in pc_all['rows']],
        },
    }


# ── 4) 成本预警（概算/预算 vs 当前成本）────────────────────
# 数据来源：
# - 概算/预算：plm_baseline（scope_type='project'，四算基线）。概算=stage
#   estimate_locked/estimate_bid（total_cost），预算=stage='budget'（total_cost），
#   每个 scope_id/每个 stage 取最新版本（MAX(id)）。关联：plm_project.project_no
#   （主）+ plm_contract.contract_no（经 plm_project.contract_id）。
# - 当前成本：finance_detail 累计付款（按 project_no 归集，回落 contract_no），
#   与资金占用/付款明细（资金口径）保持一致。
# 剩余成本 = 预算 - 当前成本；预算完成比 = 当前成本 / 预算。
BASELINE_EST_STAGES = ('estimate_locked', 'estimate_bid')
COST_WARNING_RATIO = 0.9  # 预算完成比阈值：≥90% 触发预警


def _baseline_cost_map() -> Dict[str, Dict[str, Any]]:
    """从 plm_baseline 聚合每个项目的 概算/预算（total_cost）。

    返回 {key: {'estimate': float|None, 'budget': float|None}}，key 为项目行号
    （plm_project.project_no 优先，兼容 plm_contract.contract_no）。plm 表缺失
    或异常时返回 {}（调用方按「无基线」处理，不影响主数据/资金计算）。
    """
    try:
        conn = get_conn()
        try:
            conn.execute("SELECT 1 FROM plm_baseline LIMIT 1").fetchone()
            proj = {r['id']: dict(r) for r in conn.execute(
                "SELECT id, project_no, contract_id FROM plm_project").fetchall()}
            cno_of = {}
            for r in conn.execute("SELECT id, contract_no FROM plm_contract").fetchall():
                cno_of[r['id']] = (r['contract_no'] or '').strip()
            rows = [dict(r) for r in conn.execute(
                "SELECT id, scope_id, stage, total_cost FROM plm_baseline"
                " WHERE scope_type='project'").fetchall()]
        finally:
            conn.close()
    except Exception:
        return {}
    est: Dict[int, tuple] = {}   # scope_id -> (total_cost, id)
    bud: Dict[int, tuple] = {}
    for r in rows:
        sid = r['scope_id']
        if r['stage'] in BASELINE_EST_STAGES:
            cur = est.get(sid)
            if cur is None or r['id'] > cur[1]:
                est[sid] = (r['total_cost'], r['id'])
        elif r['stage'] == 'budget':
            cur = bud.get(sid)
            if cur is None or r['id'] > cur[1]:
                bud[sid] = (r['total_cost'], r['id'])
    out: Dict[str, Dict[str, Any]] = {}
    for sid, pr in proj.items():
        has_est = sid in est
        has_bud = sid in bud
        if not has_est and not has_bud:
            continue
        pno = (pr.get('project_no') or '').strip()
        cid_ref = pr.get('contract_id')
        cno = cno_of.get(cid_ref) if cid_ref is not None else ''
        keys = []
        if pno:
            keys.append(pno)
        if cno and cno != pno:
            keys.append(cno)
        if not keys:
            keys.append(str(sid))
        entry = {'estimate': est[sid][0] if has_est else None,
                 'budget': bud[sid][0] if has_bud else None}
        for k in keys:
            out[k] = entry
    return out


def _cost_status(budget: Optional[float], current_cost: Optional[float]):
    """成本预警规则纯函数，返回 (status, note)。

    ★ 遗留参考实现：live 路径（cost_warning_all）已改走本体 F-project-cost-warning；
    本函数保留仅供 ontos 影子比对（test_shadow_vs_legacy）校验语义一致，note 文本勿改。

    - 有预算：当前成本>预算 → 超支；预算完成比≥阈值 → 预警；否则 正常。
    - 无预算：无法比较（概/预算缺失按“不可判”对待）→ 正常 + 说明，不因缺预算而误报。
    """
    b = budget if budget is not None else None
    c = current_cost if current_cost is not None else 0.0
    if b is None or b <= 0:
        if c > 0:
            return '正常', '缺预算，暂无法判定预警（当前成本 ¥%s）' % format(round(c), ',')
        return '正常', '缺预算且无当前成本，无法比较'
    ratio = c / b if b > 0 else None
    if ratio is not None and c > b:
        return '超支', '当前成本 ¥%s 已超过预算（超支 ¥%s）' % (
            format(round(c), ','), format(round(c - b), ','))
    if ratio is not None and ratio >= COST_WARNING_RATIO:
        return '预警', '预算完成比已达 %d%%，接近预算上限' % round(ratio * 100)
    return '正常', '预算执行在阈值内（预算完成比 %d%%）' % (round(ratio * 100) if ratio is not None else 0)


def _contract_cost_baseline_map() -> Dict[str, Dict[str, Any]]:
    """读 md_contract 权威成本列（= ontos COST_FORMULA_POLICY 声明的物理列）→ 按去重合同号：
        {cno: {'budget': 累计实施成本预估(预算), 'current_cost': 累计实施成本实际(成本)}}。

    ★单一真相对齐：ontos 声明 budget.formula = 硬件集成费+服务预估成本+软件预估实施费、
    cost.formula = 六分项实际；这两列已逐行验算 ≡ 对应分项汇总（见工作记忆），故直接读列即可。
    平台侧不再自拼 service_est 单分项 / finance_detail 付款口径。
    """
    try:
        conn = get_conn()
        try:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(md_contract)")]
            need = [c for c in ('合同编号', '累计实施成本预估', '累计实施成本实际') if c in cols]
            if '合同编号' not in need:
                return {}
            sql = 'SELECT %s FROM md_contract' % ','.join('"%s"' % c for c in need)
            rows = [dict(r) for r in conn.execute(sql).fetchall()]
        finally:
            conn.close()
    except Exception:
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        cno = str(r.get('合同编号') or '').strip()
        if not cno or cno == '合同编号' or cno in out:
            continue
        out[cno] = {
            'budget': _f(r.get('累计实施成本预估')),
            'current_cost': _f(r.get('累计实施成本实际')),
        }
    return out


def cost_warning_all() -> Dict[str, Any]:
    """全量成本预警：逐业务单元(合同/项目)计算 预算/当前成本/剩余成本/完成比/状态。

    ★口径收敛到 ontos：预算/当前成本 取自 md_contract 权威列（= COST_FORMULA_POLICY 物理列，
    由 _contract_cost_baseline_map 映射），判定统一走本体 F-project-cost-warning；不再自拼口径。
    仅纳入具备任一数据（概算/预算/当前成本>0）的业务单元。
    """
    # ★ 收敛：预警判定统一走本体 F-project-cost-warning（固化/探索同一份纯函数）
    from ontos import domain_business as biz
    # 预算/成本 的 ontos 权威口径：md_contract 累计实施成本预估/实际（≡ COST_FORMULA_POLICY 分项和）
    md_map = _contract_cost_baseline_map()
    details: List[Dict[str, Any]] = []
    total_budget = total_current = 0.0
    status_count: Dict[str, int] = {'正常': 0, '预警': 0, '超支': 0}
    for r in _list_main_projects():
        pno = (r.get('project_no') or '').strip()
        cno = (r.get('contract_no') or '').strip()
        key = cno or pno
        if not key:
            continue
        # 预算 = 累计实施成本预估；当前成本 = 累计实施成本实际（已 ≡ 本体声明的分项汇总）
        m = md_map.get(cno) or md_map.get(key) or {}
        budget = m.get('budget')
        current_cost = round(m.get('current_cost') or 0.0, 2)
        # 概算不参与成本预警判定（ontos：estimate 非 F-project-cost-warning 入参）；主数据无独立概算列
        estimate = None
        if budget is None and current_cost <= 0:
            continue
        # ★ 收敛：判定改走本体（单一权威口径；与 demo/agent 同函数）
        res = biz.functions.call(
            "F-project-cost-warning",
            budget=float(budget) if budget is not None else None,
            current_cost=current_cost,
        )
        status = res['status']
        note = res['note']
        remaining = res['remaining_cost']
        ratio = res['budget_ratio']
        status_count[status] = status_count.get(status, 0) + 1
        total_current += current_cost
        if budget is not None:
            total_budget += budget
        details.append({
            'project_no': pno,
            'contract_no': cno,
            'name': r.get('name') or '',
            'estimate': estimate,
            'budget': budget,
            'current_cost': current_cost,
            'remaining': remaining,
            'budget_ratio': ratio,
            'status': status,
            'note': note,
        })
    n = len(details)
    total_remaining = round(total_budget - total_current, 2)
    summary = {
        '项目数': '%d 个' % n,
        '预算金额合计': '¥%s' % format(round(total_budget), ','),
        '当前成本合计': '¥%s' % format(round(total_current), ','),
        '剩余成本合计': '¥%s' % format(round(total_remaining), ','),
        '超支项目': status_count.get('超支', 0),
        '预警项目': status_count.get('预警', 0),
    }
    return {
        'total': n,
        'total_budget': round(total_budget, 2),
        'total_current_cost': round(total_current, 2),
        'total_remaining': total_remaining,
        'status_count': status_count,
        'summary': summary,
        'rows': details,
    }