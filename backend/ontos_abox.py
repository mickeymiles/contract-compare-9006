"""本体 ABox 读取层：把 9006 数据库记录 → 本体事实 → 调 ontos 纯函数计算。

═══ 分层原则（重要）═══
- ``ontos/``      ：纯语义层。TBox 声明 + Function 实现，**零 DB / 零 app 耦合**，可单测。
- ``本模块``      ：ABox 适配层。唯一有 DB 依赖的本体层：读物理表 → 构造本体事实 → 调 ontos。
- ``routes_ontos``：API 层。只做参数校验与响应包装。

这样 Function 的语义可在无数据库环境下测试，而数据口径只在一个地方维护。

═══ 回款周期场景的数据来源（与用户确认）═══
- 项目 = 主数据（core_project）
- PMO  = 里程碑（plm_milestone，其中 plan_payback_date 是**计划**回款）
- 财经 = 收付款明细（finance_detail，kind='recv'/'pay'，这才是**真实**回款/付款记录）

因此本体计算默认以 **finance_detail 为真实回款来源**，里程碑时间点作为回退/对照，
并在结果里同时返回两个来源的值，便于核对口径差异。
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))              # backend/
REPO_ROOT = os.path.abspath(os.path.join(BASE_DIR, '..'))
ONTOS_ROOT = os.path.join(REPO_ROOT, 'ontos')                      # submodule 根

from core import project as project_core          # noqa: E402
from core import project_metrics as pm            # noqa: E402 复用现网读取口径，避免漂移


# ═══════════════════════════════════════════════════════════════════════
# ontos 加载（submodule；包在 <repo>/ontos/ontos/，故 sys.path 指向 submodule 根）
# ═══════════════════════════════════════════════════════════════════════
def load_ontos():
    """导入并返回 ontos.domain_business 模块（失败抛 ImportError，由调用方降级）。"""
    if ONTOS_ROOT not in sys.path:
        sys.path.insert(0, ONTOS_ROOT)
    from ontos import domain_business
    return domain_business


# ═══════════════════════════════════════════════════════════════════════
# ABox 事实构造：物理表 → 本体事实
# ═══════════════════════════════════════════════════════════════════════
def main_row(no: str) -> Optional[Dict[str, Any]]:
    """主数据行（core_project）：合同号或项目号命中，取最新一条。"""
    conn = project_core.get_conn()
    try:
        r = conn.execute(
            "SELECT * FROM core_project WHERE contract_no=? OR project_no=? "
            "ORDER BY project_id DESC LIMIT 1", (no, no)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def receipt_facts(no: str, alt_no: Optional[str] = None) -> List[Dict[str, Any]]:
    """财经【回款】明细 → 本体 Receipt 事实列表（kind='recv'，按日期升序）。

    ★修正现网缺陷：get_finance_detail 的 SQL 是
      ``WHERE project_no=? OR (COALESCE(project_no,'')='' AND contract_no=?)``
      即 project_no 一旦回填非空，就**不再回落** contract_no。于是用合同号查询时，
      若明细行的 project_no 已回填成真实项目号，会整条落空（回款周期算成 NaN）。
      这里对「查询键 + 备选键」各查一次并去重取并集，保证合同号/项目号都能命中。
    """
    rows, seen = [], set()
    for key in (no, alt_no):
        if not key:
            continue
        for r in pm.get_finance_detail(key).get('recv') or []:
            d = r.get('occur_date')
            if d is None:
                continue
            iso = d.isoformat() if hasattr(d, 'isoformat') else str(d)
            sig = (iso, r.get('amount'))
            if sig in seen:
                continue
            seen.add(sig)
            rows.append({'received_date': iso, 'amount': r.get('amount') or 0.0})
    rows.sort(key=lambda x: x['received_date'])
    return rows


def payment_facts(no: str, alt_no: Optional[str] = None) -> List[Dict[str, Any]]:
    """财经【付款】明细 → 本体 Payment 事实列表（kind='pay'）；双键取并集，同 receipt_facts。"""
    rows, seen = [], set()
    for key in (no, alt_no):
        if not key:
            continue
        for r in pm.get_finance_detail(key).get('pay') or []:
            d = r.get('occur_date')
            if d is None:
                continue
            iso = d.isoformat() if hasattr(d, 'isoformat') else str(d)
            sig = (iso, r.get('amount'))
            if sig in seen:
                continue
            seen.add(sig)
            rows.append({'paid_date': iso, 'amount': r.get('amount') or 0.0})
    rows.sort(key=lambda x: x['paid_date'])
    return rows


def milestone_payback(no: str) -> Dict[str, Any]:
    """PMO 里程碑回款时间点（经 plm_milestone→plm_project→plm_contract 链路）。

    注意：plm_milestone.plan_payback_date 是**计划**回款，payback_date 是导入的回款时间；
    本函数把两者都返回，由调用方决定取用（默认本体以 finance_detail 为真实口径）。
    """
    return pm.milestone_payback_point(no)


def _norm_date(v) -> Optional[str]:
    """把各种日期表示归一为 'YYYY-MM-DD' 字符串；无法解析返回 None。

    兼容三类输入：datetime/date 对象、常见日期字符串、**Excel 序列值**。
    Excel 序列值很关键——总合同表部分日期列（含 sign_date）是序列值而非日期格式，
    历史上正是它导致回款周期批量算成 NaN。
    """
    from datetime import datetime as _dt, date as _date, timedelta as _td

    if v is None or v == '' or v == '-':
        return None
    if isinstance(v, _dt):
        return v.date().isoformat()
    if isinstance(v, _date):
        return v.isoformat()
    s = str(v).strip()
    if s.startswith('='):
        return None
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d', '%Y%m%d'):
        try:
            return _dt.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    # Excel 序列值：基准 1899-12-30（避开 Excel 1900 闰年 bug）；区间 1954–2064
    try:
        f = float(s)
        if 20000 <= f <= 60000:
            return (_dt(1899, 12, 30) + _td(days=f)).date().isoformat()
    except ValueError:
        pass
    return None


# ═══════════════════════════════════════════════════════════════════════
# 场景：回款周期（ABox 事实 → ontos F-payment-cycle）
# ═══════════════════════════════════════════════════════════════════════
def abox_payment_cycle(no: str, basis: str = "last",
                       prefer: str = "finance_detail") -> Dict[str, Any]:
    """回款周期场景：读 ABox 事实 → 调 ontos F-payment-cycle 计算。

    basis  : 'last'(默认，对齐 9006 现网：最后一笔回款) | 'first'(首笔回款速度)。
    prefer : 'finance_detail'(默认，用户口径：财经明细才是真实回款)
             | 'milestone'(现网口径：优先里程碑回款时间点，缺则回落明细)。

    返回包含：本体计算结果 + 两个来源的回款日（便于核对口径差异）+ 缺数据说明。
    """
    biz = load_ontos()
    row = main_row(no)
    if not row:
        return {'no': no, 'success': False, 'error': 'no_main_data',
                'message': f'主数据(core_project)无此合同/项目：{no}'}

    sign_date = _norm_date(row.get('sign_date'))
    # 双键查询：明细行 project_no 已回填时，仅用合同号会落空，故补 project_no 作为备选键
    alt_no = row.get('project_no') or None
    recvs = receipt_facts(no, alt_no=alt_no)
    ms = milestone_payback(no)

    # 两个来源的回款日
    detail_dates = [r['received_date'] for r in recvs if r.get('received_date')]
    detail_last = max(detail_dates) if detail_dates else None
    detail_first = min(detail_dates) if detail_dates else None
    ms_actual = _norm_date(ms.get('actual')) if ms.get('has_milestone') else None
    ms_plan = _norm_date(ms.get('plan')) if ms.get('has_milestone') else None

    # 按 prefer 选择主口径
    if prefer == 'milestone':
        receipts = [{'received_date': ms_actual or ms_plan}] if (ms_actual or ms_plan) else recvs
        source = 'plm_milestone' if (ms_actual or ms_plan) else 'finance_detail'
    else:
        receipts = recvs or ([{'received_date': ms_actual or ms_plan}]
                             if (ms_actual or ms_plan) else [])
        source = 'finance_detail' if recvs else ('plm_milestone' if (ms_actual or ms_plan) else None)

    result = biz.functions.call('F-payment-cycle', sign_date=sign_date,
                                receipts=receipts, basis=basis, recv_source=source)
    result.update({
        'no': no,
        'success': True,
        'project_no': row.get('project_no'),
        'contract_no': row.get('contract_no'),
        'name': row.get('name'),
        'sign_amount': row.get('sign_amount'),
        'accum_received': row.get('accum_received'),
        'sign_date_raw': row.get('sign_date'),
        'sources': {
            'finance_detail': {'count': len(recvs), 'first': detail_first, 'last': detail_last},
            'plm_milestone': {'has': bool(ms.get('has_milestone')),
                              'actual': ms_actual, 'plan': ms_plan,
                              'name': ms.get('name', '')},
            'maindata_last_received_date': _norm_date(row.get('last_received_date')),
        },
        'prefer': prefer,
    })
    return result


def payment_cycle_all(basis: str = "last", prefer: str = "finance_detail",
                      limit: int = 500) -> Dict[str, Any]:
    """全量回款周期汇总：遍历主数据合同，逐条计算 + 统计（平均/分布/缺数据清单）。"""
    conn = project_core.get_conn()
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT project_no, contract_no, name, sign_date, sign_amount "
            "FROM core_project ORDER BY project_id DESC LIMIT ?", (limit,)).fetchall()]
    finally:
        conn.close()

    if not rows:
        return {'success': False, 'error': 'empty_main_data',
                'message': '主数据 core_project 为空，请先在「主数据」页导入总合同表'}

    items, valid, missing = [], [], []
    for r in rows:
        no = r.get('contract_no') or r.get('project_no')
        if not no:
            continue
        one = abox_payment_cycle(no, basis=basis, prefer=prefer)
        items.append(one)
        if one.get('success') and one.get('cycle_days') is not None:
            valid.append(one)
        else:
            missing.append({'no': no, 'name': r.get('name'),
                            'reason': one.get('note') or one.get('message') or '缺数据'})

    days = [x['cycle_days'] for x in valid]
    buckets = {'0-30天': 0, '31-60天': 0, '61-90天': 0, '91-180天': 0,
               '181-365天': 0, '365天以上': 0}
    for d in days:
        if d <= 30:
            buckets['0-30天'] += 1
        elif d <= 60:
            buckets['31-60天'] += 1
        elif d <= 90:
            buckets['61-90天'] += 1
        elif d <= 180:
            buckets['91-180天'] += 1
        elif d <= 365:
            buckets['181-365天'] += 1
        else:
            buckets['365天以上'] += 1

    return {
        'success': True,
        'basis': basis,
        'prefer': prefer,
        'total': len(items),
        'valid_count': len(valid),
        'missing_count': len(missing),
        'avg_days': round(sum(days) / len(days), 1) if days else None,
        'max_days': max(days) if days else None,
        'min_days': min(days) if days else None,
        'buckets': buckets,
        'items': items,
        'missing': missing[:50],           # 缺数据清单（截断，避免响应过大）
    }
