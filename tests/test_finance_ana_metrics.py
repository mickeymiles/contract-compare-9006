# -*- coding: utf-8 -*-
"""财经资金运作三指标 · 基于当前库真实数据的数据核对 (finance-ana 迁移配套).

跑三项计算：回款周期 / 资金占用 / 毛利率，逐项核对数据质量问题并输出结论。
这些断言校验的是计算"结构性"成立与否；数据质量问题以 print 的核对结论呈现，
由报告人工研判（不因真实数据的多/缺而让测试红）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend'))

import sqlite3  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
from core import project_metrics as pm  # noqa: E402
import models  # noqa: E402


# ─────────────────────────────────────────────
# 0) 新页面 + 指标接口连通性（TestClient 进程内）
# ─────────────────────────────────────────────
def test_finance_ana_endpoints_200():
    client = TestClient(main.app)
    # 新独立页（回款周期 / 资金占用）/ 毛利率复用 /gross
    for path in ('/finance-cycle', '/finance-cycle.app.js', '/finance-fund',
                 '/finance-fund.app.js', '/gross'):
        r = client.get(path)
        assert r.status_code == 200, f"{path} -> {r.status_code}"
    # 三个指标接口
    for path in ('/api/core/metrics/payment-cycle', '/api/core/metrics/fund',
                 '/api/core/metrics/gross'):
        r = client.get(path)
        assert r.status_code == 200, f"{path} -> {r.status_code}"
        assert r.json().get('success') is True, f"{path} 返回结构异常: {r.text[:200]}"


def _raw(sql, args=()):
    conn = sqlite3.connect(models.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _print_block(title, lines):
    print("\n" + "=" * 60)
    print(title)
    print("-" * 60)
    for k, v in lines:
        print(f"  {k}: {v}")


# ─────────────────────────────────────────────
# 1) 回款周期
# ─────────────────────────────────────────────
def test_payment_cycle_data_check():
    pc = pm.payment_cycle_all()
    main_n = len(_raw("SELECT project_id FROM core_project"))
    # 里程碑 → 主数据的可关联性（现有 JOIN 经 plm_contract，该表在库里为空）
    joined = _raw("""
        SELECT COUNT(DISTINCT m.project_id) AS cnt
        FROM plm_milestone m
        JOIN plm_project pp ON pp.id = m.project_id
        JOIN plm_contract pc ON pc.id = pp.contract_id
    """)[0]['cnt']
    plm_contract_n = _raw("SELECT COUNT(*) AS n FROM plm_contract")[0]['n']
    # 备选：plm_project.project_no 能匹配 core_project.project_no 的主数据数
    alt = _raw("""
        SELECT COUNT(DISTINCT cp.project_id) AS c
        FROM core_project cp
        JOIN plm_project pp ON pp.project_no = cp.project_no
    """)[0]['c']

    assert pc['total'] == main_n, "回款周期明细应覆盖全部主数据行"
    assert pc['total'] == pc['valid'] + pc['nan'], "valid + NaN 应等于总数"

    print("\n[回款周期] 数据核对结论")
    _print_block("回款周期 · 覆盖与缺失", [
        ("主数据合同数", main_n),
        ("有回款周期(天)数", pc['valid']),
        ("NaN(缺签订时间/回款时间点)", pc['nan']),
        ("来源分布 source_count", pc['source_count']),
        ("经 plm_contract 关联的里程碑覆盖(合同数)", joined),
        ("plm_contract 表行数", plm_contract_n),
        ("备选里程碑关联: plm_project.project_no 命中 core_project 数", alt),
    ])
    _print_block("回款周期 · 无有效回款(说明)top5", [
        (r['contract_no'], f"source={r['source']} note={r['note']} 里程碑={r['has_milestone']}")
        for r in pc['rows'] if r['cycle_days'] is None][:5])


# ─────────────────────────────────────────────
# 2) 资金占用
# ─────────────────────────────────────────────
def test_fund_data_check():
    pm.ensure_finance_detail()  # 幂等补齐 project_no 列，兼容当前库
    fd = _raw("""
        SELECT SUM(CASE WHEN kind='pay' THEN amount ELSE 0 END) AS pay_total,
               SUM(CASE WHEN kind='recv' THEN amount ELSE 0 END) AS recv_total,
               SUM(CASE WHEN project_no IS NULL OR project_no='' THEN 1 ELSE 0 END) AS no_pno,
               COUNT(*) AS n,
               COUNT(DISTINCT contract_no) AS distinct_no
        FROM finance_detail
    """)[0]

    fam = pm.fund_occupancy_all()
    # 归集键 sum 应等于明细表合计（每行唯一落一个键）
    assert abs(fam['total_pay'] - _num(fd['pay_total'])) < 0.01
    assert abs(fam['total_recv'] - _num(fd['recv_total'])) < 0.01

    pct = (fd['no_pno'] / fd['n'] * 100) if fd['n'] else 0.0
    print("\n[资金占用] 数据核对结论")
    _print_block("资金占用 · 归集与一致性", [
        ("finance_detail 行数", fd['n']),
        ("project_no 为空的明细行数(占比)", f"{fd['no_pno']} ({pct:.1f}%)"),
        ("明细按 contract_no 去重数", fd['distinct_no']),
        ("归集键数(按 project_no→contract_no)", fam['total_keys']),
        ("有明细(has_data)键数", fam['keys_with_data']),
        ("明细表付款合计(元)", round(_num(fd['pay_total']), 2)),
        ("归集 sum 累计付款(元)", fam['total_pay']),
        ("明细表收款合计(元)", round(_num(fd['recv_total']), 2)),
        ("归集 sum 累计收款(元)", fam['total_recv']),
        ("当前资金占用合计(元)", fam['total_occupy']),
        ("归集金额与明细合计是否一致", fam['total_pay'] == round(_num(fd['pay_total']), 2)
         and fam['total_recv'] == round(_num(fd['recv_total']), 2)),
    ])


# ─────────────────────────────────────────────
# 3) 毛利率
# ─────────────────────────────────────────────
def test_gross_data_check():
    gm = pm.gross_margin_all()
    main_n = len(_raw("SELECT project_id FROM core_project"))
    # 主数据层面直接统计
    agg = _raw("""
        SELECT SUM(CASE WHEN sign_amount IS NULL OR sign_amount<=0 THEN 1 ELSE 0 END) AS no_amt,
               SUM(CASE WHEN sign_gross_profit IS NULL THEN 1 ELSE 0 END) AS no_gp,
               SUM(CASE WHEN gross_rate IS NULL THEN 1 ELSE 0 END) AS no_gr
        FROM core_project
    """)[0]
    # 可直接由 sign_gross_profit/sign_amount 计算的行
    computable = [
        r for r in gm['rows']
        if _num(r['sign_amount']) > 0 and r['sign_gross_profit'] is not None
    ]

    print("\n[毛利率] 数据核对结论")
    _print_block("毛利率 · 主数据覆盖与缺失", [
        ("主数据合同数", main_n),
        ("计算 method_count", gm['method_count']),
        ("缺 sign_amount(≤0/空)行", gm['missing_amount']),
        ("缺 sign_gross_profit 行", gm['missing_gross_profit']),
        ("主数据层面 缺金额/缺毛利/缺毛利率", (agg['no_amt'], agg['no_gp'], agg['no_gr'])),
        ("可计算(金额>0且毛利非空)行数", len(computable)),
    ])


# ─────────────────────────────────────────────
# 4) 统一小结 (仅 print)
# ─────────────────────────────────────────────
def test_dump_summary():
    pc = pm.payment_cycle_all()
    fam = pm.fund_occupancy_all()
    gm = pm.gross_margin_all()
    print("\n\n================  财经资金运作 · 数据核对小结  ================")
    print(f"[回款周期] 可算出回款周期 {pc['valid']}/{pc['total']}；NaN {pc['nan']}；"
          f"来源 {pc['source_count']}")
    print(f"[资金占用] 明细 {fam['total_pay']}/{fam['total_recv']}(付/收)；占用 {fam['total_occupy']}；"
          f"键 {fam['total_keys']}，有数据 {fam['keys_with_data']}")
    print(f"[毛利率] 方法 {gm['method_count']}；缺金额 {gm['missing_amount']}；缺毛利 {gm['missing_gross_profit']}")
    print("=" * 60)
    # 仅校验“结构成立”，不因真实数据多/缺而红（见模块 docstring）
    assert isinstance(pc, dict) and 'total' in pc
    assert isinstance(fam, dict) and 'total_keys' in fam
    assert isinstance(gm, dict) and 'total' in gm