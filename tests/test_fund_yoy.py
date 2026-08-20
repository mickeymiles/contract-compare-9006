# -*- coding: utf-8 -*-
"""资金占用同比（YoY）测试
# 规格编号: CC-006 资金占用分析（FR-13 同比对比分析）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend'))

import pytest  # noqa: E402

import main  # noqa: E402
from models import init_db  # noqa: E402
from test_fund_multidim import _write_datasource, _patch_ds  # noqa: E402

# 同比窗口（与前端 fundYoY 口径一致）：
# 本期 = 2026-01-01 ~ 2026-08-12（REPORT_CUTOFF），上期 = 2025-01-01 ~ 2025-08-12
P0, CUT = '2026-01-01', '2026-08-12'
P1, P2 = '2025-01-01', '2025-08-12'


@pytest.fixture
def ds_dir(tmp_path, monkeypatch):
    d = _write_datasource(tmp_path)
    _patch_ds(monkeypatch, d)
    init_db()
    main._seed_risk_config()
    return d


def _window_sum(flows, s, e, ftype):
    return sum(f['amount'] for f in flows if f['type'] == ftype and s <= f['date'] <= e)


def test_fund_analyze_has_flows(ds_dir):
    """FR-13 同比：analyze 返回 data.flows（逐笔现金流，付款为负/回款为正）与 data.yoy"""
    res = main.fund_analyze()
    assert res['success'] is True
    flows = res['data']['flows']
    assert isinstance(flows, list) and len(flows) > 0
    for f in flows:
        assert f['date'] >= '2020-01-01'
        assert f['type'] in ('PAY', 'RECEIVE')
        assert isinstance(f['amount'], (int, float))
    pay = [f for f in flows if f['type'] == 'PAY']
    recv = [f for f in flows if f['type'] == 'RECEIVE']
    assert pay and recv
    assert all(f['amount'] < 0 for f in pay)
    assert all(f['amount'] > 0 for f in recv)
    assert 'occupy_prev' in res['data']['yoy']
    assert res['data']['yoy']['occupy_prev'] >= 0


def test_fifo_occupy_upto():
    """FR-13 同比：_fifo_occupy_upto 按 FIFO 计算截至某日的占用"""
    from datetime import datetime
    from collections import namedtuple
    payments = [{'occur_date': datetime(2025, 1, 1), 'amount': 1000000},
                {'occur_date': datetime(2025, 6, 1), 'amount': 500000}]
    collections = [{'occur_date': datetime(2025, 3, 1), 'amount': 200000}]
    cutoff = datetime(2025, 8, 12)
    assert main._fifo_occupy_upto(payments, collections, cutoff) == 1300000
    # cutoff 前的付款计入，cutoff 后的不计入
    payments2 = payments + [{'occur_date': datetime(2025, 9, 1), 'amount': 300000}]
    assert main._fifo_occupy_upto(payments2, collections, cutoff) == 1300000
    # 首付在 cutoff 之后 → 无占用
    assert main._fifo_occupy_upto([{'occur_date': datetime(2026, 1, 1), 'amount': 100}],
                                  [], datetime(2025, 8, 12)) == 0


def test_yoy_occupy_prev(ds_dir):
    """FR-13 同比：上年同期日（2025-08-12）FIFO 占用 = C1 剩余 80 万"""
    res = main.fund_analyze()
    assert res['data']['yoy']['occupy_prev'] == 800000


def test_yoy_window_pay_recv(ds_dir):
    """FR-13 同比：本期(2026)与上期(2025)窗口的付款/回款求和与变化率"""
    res = main.fund_analyze()
    flows = res['data']['flows']
    # 本期：C2 付款50万(2026-07-20) + 回款10万(2026-07-25)；C3 纯收款30万(2026-08-01)
    cur_pay = -_window_sum(flows, P0, CUT, 'PAY')
    cur_recv = _window_sum(flows, P0, CUT, 'RECEIVE')
    assert cur_pay == 500000
    assert cur_recv == 400000  # C2 10万 + C3 30万
    # 上期：C1 付款100万(2025-01-01) + 回款20万(2025-03-01)
    prev_pay = -_window_sum(flows, P1, P2, 'PAY')
    prev_recv = _window_sum(flows, P1, P2, 'RECEIVE')
    assert prev_pay == 1000000
    assert prev_recv == 200000
    # 变化率：付款 (50-100)/100 = -50%；回款 (40-20)/20 = +100%
    assert (cur_pay - prev_pay) / prev_pay == pytest.approx(-0.5)
    assert (cur_recv - prev_recv) / prev_recv == pytest.approx(1.0)


def test_yoy_prev_zero(ds_dir):
    """FR-13 同比：上期无数据时变化率为空（前端渲染"—"，不除零）"""
    res = main.fund_analyze()
    flows = res['data']['flows']
    # 2023 年无任何流水 → 上期为 0
    prev = _window_sum(flows, '2023-01-01', '2023-08-12', 'PAY')
    assert prev == 0
    cur = -_window_sum(flows, P0, CUT, 'PAY')
    pct = None if prev == 0 else (cur - prev) / prev * 100
    assert pct is None


def test_analyze_rows_have_prev_occupy(ds_dir):
    """FR-13 表格同比：明细行含"上年同期占用"，且按合同加总 == yoy.occupy_prev"""
    res = main.fund_analyze()
    rows = res['data']['rows']
    assert rows
    for r in rows:
        assert '上年同期占用' in r
    total_prev = sum(r.get('上年同期占用') or 0 for r in rows)
    assert total_prev == res['data']['yoy']['occupy_prev'] == 800000


def test_fund_metrics_prev_occupy(ds_dir):
    """FR-13 表格同比：宽表 fund_metrics 明细行透出"上年同期占用"（供明细表渲染）"""
    main.fund_analyze()
    res = main.fund_metrics()
    assert res['success'] is True
    rows = res['data']['rows']
    assert rows
    assert all('上年同期占用' in r for r in rows)
    assert sum(r['上年同期占用'] for r in rows) == 800000


def test_dim_aggregate_prev_occupy(ds_dir):
    """FR-13 表格同比：维度聚合行含 prev_occupy（供客户集合表格渲染），总额一致"""
    main.fund_analyze()
    res = main._fund_dim_aggregate_inner('customer_key')
    assert 'error' not in res
    rows = res['rows']
    assert rows
    assert all('prev_occupy' in r for r in rows)
    assert sum(r['prev_occupy'] for r in rows) == 800000
