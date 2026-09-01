# -*- coding: utf-8 -*-
"""财经 · 成本预警：接口连通性 + 计算结构核对（基于当前库真实数据）。

成本预警 = 概算/预算（PLM 四算基线）+ 当前成本（finance_detail 累计付款，
资金口径）→ 剩余成本 / 预算完成比 / 预警状态。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend'))

from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
from core import project_metrics as pm  # noqa: E402


# ─────────────────────────────────────────────
# 0) 新页面 + 指标接口连通（TestClient 进程内）
# ─────────────────────────────────────────────
def test_cost_warning_endpoints_200():
    client = TestClient(main.app)
    for path in ('/finance-cost', '/finance-cost.app.js'):
        r = client.get(path)
        assert r.status_code == 200, f"{path} -> {r.status_code}"

    # 快照读取
    r = client.get('/api/core/metrics/cost-warning')
    assert r.status_code == 200, f"快照 -> {r.status_code}"
    j = r.json()
    assert j.get('success') is True, f"返回结构异常: {r.text[:300]}"
    assert isinstance(j.get('data', {}).get('rows'), list), "data.rows 应为列表"

    # 强制重算（refresh）
    r = client.get('/api/core/metrics/cost-warning?refresh=1')
    assert r.status_code == 200, f"refresh -> {r.status_code}"
    j2 = r.json()
    assert j2.get('success') is True
    assert j2.get('data', {}).get('total', 0) == j.get('data', {}).get('total', 0), \
        "refresh 后 total 应与快照一致"


# ─────────────────────────────────────────────
# 1) 计算结构核对
# ─────────────────────────────────────────────
def test_cost_warning_data_check():
    res = pm.cost_warning_all()
    assert 'summary' in res and 'status_count' in res
    assert res['status_count']['正常'] >= 0
    assert res['status_count']['预警'] >= 0
    assert res['status_count']['超支'] >= 0
    assert res['total'] == len(res['rows'])
    # 汇总卡字段
    for k in ('项目数', '预算金额合计', '当前成本合计', '剩余成本合计', '超支项目', '预警项目'):
        assert k in res['summary'], f"sumary 缺 {k}"
    # 每行结构
    for row in res['rows']:
        for k in ('project_no', 'contract_no', 'name', 'estimate', 'budget',
                  'current_cost', 'remaining', 'budget_ratio', 'status', 'note'):
            assert k in row, f"rows 缺 {k}: {row}"
        assert row['status'] in ('正常', '预警', '超支')
        # 有预算时：完成比与剩余成本应可算
        if row['budget'] is not None and row['budget'] > 0:
            assert row['budget_ratio'] is not None
            assert row['remaining'] is not None