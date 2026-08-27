"""
CC-010 项目全生命周期管理 — 行为测试

覆盖 changes/2026-08-27-project-lifecycle/specs/CC-010-project-lifecycle/spec.md 的
FR-1 ~ FR-11。用例编号与规格条目一一对应，遵循 specs/TRACEABILITY.md 的维护约定。

使用独立测试库 contract_compare_plm_test.db，避免污染本地运行数据。
"""

import os
import sys
import sqlite3

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import plm_models as plm  # noqa: E402

TEST_DB = os.path.join(os.path.dirname(__file__), '..', 'contract_compare_plm_test.db')


# ===================== 夹具 =====================

@pytest.fixture(scope='session', autouse=True)
def _redirect_db():
    """整个测试会话把 plm 与既有 models 都指向独立测试库，结束后恢复并清理。"""
    import models as cc_models
    orig_plm, orig_cc = plm.DB_PATH, cc_models.DB_PATH
    plm.DB_PATH = TEST_DB
    cc_models.DB_PATH = TEST_DB
    cc_models.init_db()
    yield
    plm.DB_PATH = orig_plm
    cc_models.DB_PATH = orig_cc
    for suffix in ('', '-wal', '-shm'):
        p = TEST_DB + suffix
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


@pytest.fixture(autouse=True)
def fresh_db():
    """每个用例重建表并清空数据，保证用例隔离。"""
    conn = sqlite3.connect(TEST_DB)
    conn.execute("PRAGMA journal_mode=WAL")
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'plm_%'").fetchall()]
    for t in tables:
        conn.execute("DROP TABLE IF EXISTS %s" % t)
    conn.commit()
    conn.close()
    plm.init_plm_db()
    plm.seed_plm_master()
    yield


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    import main as app_main
    app_main.plm.DB_PATH = TEST_DB
    return TestClient(app_main.app)


def _ymd(days_from_today):
    from datetime import date, timedelta
    return (date.today() + timedelta(days=days_from_today)).strftime('%Y-%m-%d')


def _make_opportunity(income=1000000, items=None):
    r = plm.create_opportunity({'opp_name': '智慧园区一期', 'customer': '某集团',
                                'owner': '张三', 'expect_income': income, 'status': '投标中'})
    oid = r['id']
    plm.save_opportunity_estimate(oid, {'items': items if items is not None else [
        {'category': '人力成本', 'item_name': '实施', 'plan_amount': 400000},
        {'category': '分包成本', 'item_name': '外包', 'plan_amount': 250000},
        {'category': '其他费用', 'item_name': '差旅', 'plan_amount': 50000},
    ]})
    return oid


def _to_project():
    """商机 → 中标 → 联动立项，返回 (opp_id, project_id, contract_id, baseline_id)。"""
    oid = _make_opportunity()
    plm.update_opportunity(oid, {'status': '中标'})
    cv = plm.convert_opportunity({
        'opportunity_id': oid,
        'contract': {'sign_amount': 1000000, 'customer': '某集团'},
        'project': {'project_name': '智慧园区交付项目', 'manager': '李四', 'dept': '一部',
                    'start_date': _ymd(-120), 'end_date': _ymd(120),
                    'milestones': [{'name': '一期交付', 'plan_start': _ymd(-120),
                                    'plan_end': _ymd(60), 'is_key': True}]},
    })
    return oid, cv['project_id'], cv['contract_id'], cv['estimate_baseline_id']


# ===================== FR-1 商机与投标概算 =====================

def test_fr1_estimate_rollup_from_items():
    """# CC-010 FR-1 投标概算分项自动汇总成本/毛利/毛利率。"""
    oid = _make_opportunity()
    est = plm.get_opportunity_estimate(oid)
    assert est['total_income'] == 1000000
    assert est['total_cost'] == 700000
    assert est['gross'] == 300000
    assert round(est['gross_rate'], 4) == 0.3
    assert len(est['items']) == 3


def test_fr1_gross_rate_none_when_no_income():
    """# CC-010 FR-1 预估收入为 0 时毛利率返回 None 而非报错。"""
    r = plm.create_opportunity({'opp_name': '零收入商机', 'expect_income': 0})
    res = plm.save_opportunity_estimate(r['id'], {'items': [
        {'category': '人力成本', 'plan_amount': 100000}]})
    assert res['success'] is True
    assert res['total_cost'] == 100000
    assert res['gross'] == -100000
    assert res['gross_rate'] is None


def test_fr1_opp_no_auto_generated_and_unique():
    """# CC-010 FR-1 商机编号自动生成；重复编号被拒绝。"""
    a = plm.create_opportunity({'opp_name': '商机A'})
    b = plm.create_opportunity({'opp_name': '商机B'})
    assert a['opp_no'].startswith('SJ-')
    assert a['opp_no'] != b['opp_no']
    dup = plm.create_opportunity({'opp_name': '商机C', 'opp_no': a['opp_no']})
    assert dup['success'] is False and '已存在' in dup['error']


def test_fr1_presale_doc_and_follow_records():
    """# CC-010 FR-1 售前资料归档与跟进记录。"""
    oid = _make_opportunity()
    d = plm.create_presale_doc({'opportunity_id': oid, 'doc_name': '投标方案V2',
                                'doc_type': '投标方案'}, operator='张三')
    assert d['success'] is True
    assert len(plm.list_presale_docs(oid)) == 1
    f = plm.add_follow_record(oid, '客户确认下周评审', operator='张三')
    assert f['success'] is True and len(f['records']) == 1
    assert plm.create_presale_doc({'opportunity_id': 99999, 'doc_name': 'x'})['success'] is False


# ===================== FR-2 合同立项与概算基线锁定 =====================

def test_fr2_convert_links_three_levels():
    """# CC-010 FR-2 中标商机联动立项：商机-合同-项目三级溯源。"""
    oid, pid, cid, bid = _to_project()
    proj = plm.get_project(pid)
    assert proj['contract_id'] == cid
    assert proj['opportunity_id'] == oid
    assert proj['opportunity']['opp_no'].startswith('SJ-')
    ct = plm.get_contract(cid)
    assert ct['opportunity']['id'] == oid
    assert [p['id'] for p in ct['projects']] == [pid]
    est = plm.get_baseline(bid)
    assert est['stage'] == 'estimate_locked'
    assert est['total_cost'] == 700000
    assert est['source_baseline_id'] == plm.get_opportunity_estimate(oid)['id']


def test_fr2_convert_rejects_non_won_opportunity():
    """# CC-010 FR-2 非「中标」状态商机不可联动立项。"""
    oid = _make_opportunity()
    res = plm.convert_opportunity({'opportunity_id': oid, 'project': {}})
    assert res['success'] is False and '中标' in res['error']


def test_fr2_lock_baseline_and_change_is_audited():
    """# CC-010 FR-2 锁定概算后调整金额，操作日志留存前后值。"""
    oid, pid, cid, bid = _to_project()
    assert plm.lock_baseline(bid, operator='PMO')['success'] is True
    assert plm.get_baseline(bid)['status'] == '已锁定'
    res = plm.save_baseline({'id': bid, 'stage': 'estimate_locked', 'project_id': pid,
                             'total_cost': 720000, 'items': []}, operator='李四')
    assert res['success'] is True
    assert '留痕' in res['warning']
    logs = plm.list_logs('baseline', str(bid))
    assert any(l['action'] == '锁定概算基线' for l in logs)
    adjust = [l for l in logs if 'total_cost' in (l['change'] or {})]
    assert adjust and adjust[0]['change']['total_cost'] == {'before': 700000, 'after': 720000}


def test_fr2_delete_guard_on_referenced_records():
    """# CC-010 FR-2 存在下游引用时禁止删除商机/合同/项目。"""
    oid, pid, cid, bid = _to_project()
    assert plm.delete_opportunity(oid)['success'] is False
    assert plm.delete_contract(cid)['refs']['项目'] == 1
    assert plm.delete_project(pid)['success'] is False


def test_fr2_kickoff_rough_milestones_created():
    """# CC-010 FR-2 立项时创建的是粗里程碑。"""
    oid, pid, cid, bid = _to_project()
    ms = plm.list_milestones(pid)
    assert len(ms) == 1 and ms[0]['level'] == '粗' and ms[0]['is_key'] == 1


# ===================== FR-3 四算基线 =====================

def test_fr3_budget_within_estimate_saves_and_compares():
    """# CC-010 FR-3 预算在概算内正常保存并输出差异。"""
    oid, pid, cid, bid = _to_project()
    res = plm.save_baseline({'project_id': pid, 'stage': 'budget', 'total_income': 1000000,
                             'items': [{'category': '人力成本', 'plan_amount': 800000},
                                       {'category': '其他费用', 'plan_amount': 300000}]})
    assert res['success'] is True
    assert res['total_cost'] == 1100000
    cmp_ = plm.compare_baselines(pid)
    assert cmp_['estimate']['total_cost'] == 700000
    assert cmp_['budget']['total_cost'] == 1100000
    assert cmp_['estimate_vs_budget'] == 400000
    assert '超出概算' in cmp_['budget_usage_note']


def test_fr3_over_estimate_only_warns_when_switch_off():
    """# CC-010 FR-3 管控开关关闭：超概算只提示不拦截。"""
    assert plm.get_config('baseline_constraint') == 'off'
    oid, pid, cid, bid = _to_project()
    res = plm.save_baseline({'project_id': pid, 'stage': 'budget', 'total_cost': 900000})
    assert res['success'] is True
    assert res['over_estimate'] == 200000
    assert '未拦截' in res['warning']


def test_fr3_over_estimate_blocked_when_switch_on():
    """# CC-010 FR-3 管控开关开启：超概算被拒绝保存。"""
    oid, pid, cid, bid = _to_project()
    plm.set_config('baseline_constraint', 'on')
    try:
        bad = plm.save_baseline({'project_id': pid, 'stage': 'budget', 'total_cost': 900000})
        assert bad['success'] is False and bad.get('blocked') is True
        assert '禁止保存' in bad['error']
        ok = plm.save_baseline({'project_id': pid, 'stage': 'budget', 'total_cost': 650000})
        assert ok['success'] is True and ok.get('over_estimate') in (None, 0, 0.0)
    finally:
        plm.set_config('baseline_constraint', 'off')


def test_fr3_accounting_and_final_are_reserved():
    """# CC-010 FR-3 核算/决算仅占位：录入入口存在但不计算毛利。"""
    oid, pid, cid, bid = _to_project()
    res = plm.save_baseline({'project_id': pid, 'stage': 'accounting', 'total_cost': 500000})
    assert res['success'] is True and res['reserved'] is True
    assert res['gross'] is None
    cmp_ = plm.compare_baselines(pid)
    assert cmp_['accounting']['reserved'] is True
    assert cmp_['accounting']['note'] == plm.RESERVED_NOTE
    assert cmp_['final']['reserved'] is True


def test_fr3_locked_baseline_cannot_be_deleted():
    oid, pid, cid, bid = _to_project()
    plm.lock_baseline(bid)
    assert plm.delete_baseline(bid)['success'] is False


# ===================== FR-4 里程碑与任务 =====================

def test_fr4_fine_milestones_under_rough_and_rollup():
    """# CC-010 FR-4 粗里程碑拆解为细里程碑，完成度向上汇总。"""
    oid, pid, cid, bid = _to_project()
    rough = plm.list_milestones(pid)[0]
    a = plm.create_milestone({'project_id': pid, 'parent_id': rough['id'], 'name': '需求确认',
                              'progress': 100, 'status': '已完成'})
    b = plm.create_milestone({'project_id': pid, 'parent_id': rough['id'], 'name': '联调',
                              'progress': 60, 'status': '进行中'})
    parent = [m for m in plm.list_milestones(pid) if m['id'] == rough['id']][0]
    assert parent['level'] == '粗'
    assert sorted(x['name'] for x in parent['children']) == sorted(['需求确认', '联调'])
    assert parent['progress'] == 80 and parent['status'] == '进行中'
    assert a['success'] and b['success']


def test_fr4_task_binds_three_levels_and_validates_project():
    """# CC-010 FR-4 任务绑定项目/里程碑并校验同项目；三级可上溯。"""
    oid, pid, cid, bid = _to_project()
    rough = plm.list_milestones(pid)[0]
    fine = plm.create_milestone({'project_id': pid, 'parent_id': rough['id'], 'name': '开发'})
    t = plm.create_task({'project_id': pid, 'milestone_id': fine['id'], 'name': '接口开发',
                         'owner': '王五', 'plan_hours': 40, 'deliverable': '接口文档'})
    assert t['success'] is True
    row = plm.list_tasks(project_id=pid)[0]
    assert row['milestone_name'] == '开发' and row['owner'] == '王五'
    other = plm.create_project({'project_name': '另一个项目'})['id']
    bad = plm.create_task({'project_id': other, 'milestone_id': fine['id'], 'name': '错绑'})
    assert bad['success'] is False and '同一项目' in bad['error']


def test_fr4_milestone_delete_guard_with_children():
    """# CC-010 FR-4 里程碑下有子节点或任务时禁止删除。"""
    oid, pid, cid, bid = _to_project()
    rough = plm.list_milestones(pid)[0]
    fine = plm.create_milestone({'project_id': pid, 'parent_id': rough['id'], 'name': '测试'})
    plm.create_task({'project_id': pid, 'milestone_id': fine['id'], 'name': '用例执行'})
    assert plm.delete_milestone(fine['id'])['refs']['任务'] == 1
    assert plm.delete_milestone(rough['id'])['refs']['子里程碑'] == 1


# ===================== FR-5 双维度进度 =====================

def test_fr5_schedule_metrics():
    """# CC-010 FR-5 按期进度：完成数、按时完成率、延期节点与超期天数。"""
    oid, pid, cid, bid = _to_project()
    rough = plm.list_milestones(pid)[0]
    plm.create_milestone({'project_id': pid, 'parent_id': rough['id'], 'name': '按期完成',
                          'plan_start': _ymd(-60), 'plan_end': _ymd(-20),
                          'actual_end': _ymd(-22), 'progress': 100, 'status': '已完成'})
    plm.create_milestone({'project_id': pid, 'parent_id': rough['id'], 'name': '超期未完成',
                          'plan_start': _ymd(-60), 'plan_end': _ymd(-10),
                          'progress': 30, 'status': '进行中'})
    prog = plm.project_progress(pid)
    sc = prog['schedule']
    assert sc['milestone_total'] == 2
    assert sc['milestone_done'] == 1
    assert sc['on_time_rate'] == 1.0
    assert sc['milestone_overdue'] == 1
    assert sc['max_overdue_days'] >= 10
    names = [n['name'] for n in sc['overdue_nodes']]
    assert '超期未完成' in names


def test_fr5_budget_progress_and_gap():
    """# CC-010 FR-5 按预算进度：消耗占比、剩余预算、与完成进度的剪刀差。"""
    oid, pid, cid, bid = _to_project()
    plm.save_baseline({'project_id': pid, 'stage': 'budget', 'total_income': 1000000,
                       'total_cost': 1000000})
    rough = plm.list_milestones(pid)[0]
    plm.create_milestone({'project_id': pid, 'parent_id': rough['id'], 'name': 'M1',
                          'progress': 62.5, 'status': '进行中'})
    plm.create_ledger({'project_id': pid, 'kind': 'cost', 'category': '分包成本',
                       'plan_or_actual': '实际', 'amount': 530000})
    bg = plm.project_progress(pid)['budget']
    assert bg['budget_total'] == 1000000
    assert bg['actual_cum'] == 530000
    assert round(bg['budget_usage_rate'], 4) == 0.53
    assert bg['remaining'] == 470000
    assert abs(bg['time_vs_cost_gap'] - (0.53 - 0.625)) < 1e-6


def test_fr5_missing_budget_falls_back_gracefully():
    """# CC-010 FR-5 未录预算时按期进度正常、按预算各项为空且不报错。"""
    oid, pid, cid, bid = _to_project()
    prog = plm.project_progress(pid)
    assert prog['schedule']['milestone_total'] == 1
    assert prog['budget']['budget_total'] is None
    assert prog['budget']['budget_usage_rate'] is None
    assert prog['budget']['note'] == '未录入执行预算'


# ===================== FR-6 人力与工时 =====================

def test_fr6_timesheet_converts_to_labor_cost():
    """# CC-010 FR-6 80 小时 × 2000 元/人天 ÷ 8 = 20000 元自动归集。"""
    oid, pid, cid, bid = _to_project()
    s = plm.create_staff({'name': '袁一', 'role': '实施工程师', 'cost_rate': 2000,
                          'available_hours': 160})
    plm.create_assignment({'staff_id': s['id'], 'project_id': pid, 'planned_hours': 100})
    plm.create_timesheet({'staff_id': s['id'], 'project_id': pid, 'hours': 80,
                          'work_date': _ymd(-1)})
    led = [x for x in plm.list_ledger(project_id=pid) if x['source'] == '工时归集']
    assert len(led) == 1 and led[0]['amount'] == 20000 and led[0]['category'] == '人力成本'
    # 幂等：再补 8 小时，记录被覆写而非新增
    plm.create_timesheet({'staff_id': s['id'], 'project_id': pid, 'hours': 8,
                          'work_date': _ymd(0)})
    led2 = [x for x in plm.list_ledger(project_id=pid) if x['source'] == '工时归集']
    assert len(led2) == 1 and led2[0]['amount'] == 22000
    # 手工成本记录不受归集影响
    plm.create_ledger({'project_id': pid, 'kind': 'cost', 'category': '分包成本',
                       'plan_or_actual': '实际', 'amount': 5000})
    plm.sync_labor_cost(project_id=pid)
    assert len([x for x in plm.list_ledger(project_id=pid)
                if x['source'] == '手工录入' and x['kind'] == 'cost']) == 1


def test_fr6_labor_ledger_is_system_managed():
    """# CC-010 FR-6 工时归集台账禁止手工改删。"""
    oid, pid, cid, bid = _to_project()
    s = plm.create_staff({'name': '钱二', 'cost_rate': 2500, 'available_hours': 160})
    plm.create_timesheet({'staff_id': s['id'], 'project_id': pid, 'hours': 16})
    auto = [x for x in plm.list_ledger(project_id=pid) if x['source'] == '工时归集'][0]
    assert plm.update_ledger(auto['id'], {'amount': 1})['success'] is False
    assert plm.delete_ledger(auto['id'])['success'] is False


def test_fr6_staff_load_three_states():
    """# CC-010 FR-6 负荷三态：过载（>120%）/ 正常 / 闲置，并给出并行项目数。"""
    oid, pid, cid, bid = _to_project()
    other = plm.create_project({'project_name': '并行项目'})['id']
    over = plm.create_staff({'name': '孙三', 'cost_rate': 1800, 'available_hours': 160})
    normal = plm.create_staff({'name': '李四', 'cost_rate': 1800, 'available_hours': 160})
    idle = plm.create_staff({'name': '周七', 'cost_rate': 1800, 'available_hours': 160})
    plm.create_assignment({'staff_id': over['id'], 'project_id': pid, 'planned_hours': 120})
    plm.create_assignment({'staff_id': over['id'], 'project_id': other, 'planned_hours': 100})
    plm.create_assignment({'staff_id': normal['id'], 'project_id': pid, 'planned_hours': 80})
    loads = {x['name']: x for x in plm.staff_load()}
    assert loads['孙三']['load_state'] == '过载'
    assert loads['孙三']['parallel_projects'] == 2
    assert abs(loads['孙三']['load_rate'] - 1.375) < 1e-6
    assert loads['李四']['load_state'] == '正常'
    assert loads['周七']['load_state'] == '闲置'


def test_fr6_efficiency_fields_reserved():
    """# CC-010 FR-6 人效/元效为预留数据源，仅沉淀不计算。"""
    pan = _to_project()
    p = plm.project_panorama(pan[1])
    assert '预留' in p['hr_area']['efficiency']['note']


# ===================== FR-7 成本与毛利 =====================

def test_fr7_actual_gross_and_rate():
    """# CC-010 FR-7 收入 1,500,000 − 实际成本 900,000 → 毛利 600,000 / 40%。"""
    oid, pid, cid, bid = _to_project()
    plm.create_ledger({'project_id': pid, 'kind': 'income', 'category': '签单收入',
                       'amount': 1200000, 'plan_or_actual': '实际'})
    plm.create_ledger({'project_id': pid, 'kind': 'income', 'category': '变更收入',
                       'amount': 300000, 'plan_or_actual': '实际'})
    plm.create_ledger({'project_id': pid, 'kind': 'cost', 'category': '分包成本',
                       'amount': 900000, 'plan_or_actual': '实际'})
    fin = plm.project_finance(pid)
    assert fin['income']['total'] == 1500000 + 1000000  # 联动立项已归集合同签单收入 1,000,000
    assert fin['cost']['actual_cum'] == 900000
    income = fin['income']['total']
    assert fin['gross']['actual'] == income - 900000
    assert round(fin['gross']['actual_rate'], 4) == round((income - 900000) / income, 4)
    # 预估毛利口径：收入合计 − 概算成本（700,000）
    assert fin['gross']['estimate'] == income - 700000
    assert round(fin['gross']['estimate_rate'], 4) == round((income - 700000) / income, 4)


def test_fr7_three_line_variance():
    """# CC-010 FR-7 概算-预算-实际三线差异与方向。"""
    oid, pid, cid, bid = _to_project()
    plm.save_baseline({'id': bid, 'stage': 'estimate_locked', 'project_id': pid,
                       'total_income': 1000000, 'total_cost': 1200000, 'items': []})
    plm.save_baseline({'project_id': pid, 'stage': 'budget', 'total_cost': 1150000,
                       'total_income': 1000000})
    plm.create_ledger({'project_id': pid, 'kind': 'cost', 'category': '人力成本',
                       'amount': 610000, 'plan_or_actual': '实际'})
    fin = plm.project_finance(pid)
    assert fin['baseline']['estimate_cost'] == 1200000
    assert fin['variance']['estimate_vs_budget'] == -50000
    assert fin['variance']['budget_vs_actual'] == -540000
    assert round(fin['variance']['budget_usage_rate'], 4) == 0.5304
    assert fin['variance']['direction'] == '节支'


def test_fr7_empty_finance_returns_none():
    """# CC-010 FR-7 无收入无成本时比率返回 None。"""
    pid = plm.create_project({'project_name': '空项目'})['id']
    fin = plm.project_finance(pid)
    assert fin['gross']['actual_rate'] is None
    assert fin['variance']['budget_usage_rate'] is None


# ===================== FR-8 项目全景视图 =====================

def test_fr8_panorama_has_seven_fixed_blocks():
    """# CC-010 FR-8 全景视图固定 7 板块。"""
    oid, pid, cid, bid = _to_project()
    pan = plm.project_panorama(pid)
    assert list(pan.keys()) == ['base_info', 'baseline_area', 'pmo_area', 'hr_area',
                                'finance_area', 'alert_area', 'quick_links']


def test_fr8_panorama_base_info_and_consistency():
    """# CC-010 FR-8 基础信息区完整，且与子模块明细一致。"""
    oid, pid, cid, bid = _to_project()
    s = plm.create_staff({'name': '吴八', 'cost_rate': 2000, 'available_hours': 160})
    plm.create_assignment({'staff_id': s['id'], 'project_id': pid, 'planned_hours': 40})
    plm.create_timesheet({'staff_id': s['id'], 'project_id': pid, 'hours': 24})
    pan = plm.project_panorama(pid)
    bi = pan['base_info']
    assert bi['project_no'].startswith('XM-')
    assert bi['customer'] == '某集团'
    assert bi['contract_no'].startswith('HT-')
    assert bi['opportunity_no'].startswith('SJ-')
    assert bi['manager'] == '李四'
    assert bi['status'] == '待启动'
    assert pan['hr_area']['hours_total'] == 24
    assert pan['finance_area']['cost']['hours_total'] == 24
    assert pan['hr_area']['participants'][0]['name'] == '吴八'
    assert pan['pmo_area']['schedule']['milestone_total'] == len(pan['pmo_area']['milestones'])


def test_fr8_panorama_empty_project_returns_empty_collections():
    """# CC-010 FR-8 刚立项无数据的项目，全景各板块返回空集合而非报错。"""
    pid = plm.create_project({'project_name': '全新项目', 'manager': '赵九'})['id']
    pan = plm.project_panorama(pid)
    assert pan['base_info']['project_name'] == '全新项目'
    assert pan['baseline_area']['estimate_items'] == []
    assert pan['hr_area']['participants'] == []
    assert pan['alert_area']['items'] == []
    assert pan['pmo_area']['milestones'] == []
    assert len(pan['quick_links']) == 5


def test_fr8_panorama_missing_project_returns_none():
    assert plm.project_panorama(4242) is None


# ===================== FR-9 预警 =====================

def _seed_alert_project(budget=1000000, actual_cost=850000):
    oid, pid, cid, bid = _to_project()
    plm.save_baseline({'project_id': pid, 'stage': 'budget', 'total_cost': budget,
                       'total_income': 1000000})
    plm.create_ledger({'project_id': pid, 'kind': 'cost', 'category': '分包成本',
                       'amount': actual_cost, 'plan_or_actual': '实际'})
    return pid


def test_fr9_cost_overrun_alert_triggers():
    """# CC-010 FR-9 预算消耗 85% → 触发预算超耗预警（待处理）。"""
    pid = _seed_alert_project()
    res = plm.scan_alerts()
    assert res['success'] is True and res['created'] >= 1
    hits = [a for a in plm.list_alerts(project_id=pid) if a['dim'] == 'cost']
    assert hits and hits[0]['status'] == '待处理'
    assert hits[0]['rule_key'] == 'cost_overrun_warn'


def test_fr9_alert_dedup_and_value_update():
    """# CC-010 FR-9 同项目同规则未闭环只保留一条，重复扫描更新数值不回退状态。"""
    pid = _seed_alert_project(actual_cost=850000)
    plm.scan_alerts()
    first = [a for a in plm.list_alerts(project_id=pid) if a['rule_key'] == 'cost_overrun_warn'][0]
    plm.handle_alert(first['id'], {'status': '处理中', 'note': '已在核减分包'}, operator='PMO')
    plm.create_ledger({'project_id': pid, 'kind': 'cost', 'category': '服务成本',
                       'amount': 200000, 'plan_or_actual': '实际'})
    plm.scan_alerts()
    same = [a for a in plm.list_alerts(project_id=pid) if a['rule_key'] == 'cost_overrun_warn']
    assert len(same) == 1
    assert same[0]['status'] == '处理中'          # 状态不被扫描回退
    assert same[0]['metric_value'] > first['metric_value']  # 数值被更新
    assert same[0]['level'] == '提醒'             # 该规则自身等级不变
    crit = [a for a in plm.list_alerts(project_id=pid) if a['rule_key'] == 'cost_overrun_crit']
    assert len(crit) == 1 and crit[0]['level'] == '严重'  # 105% 命中另一条严重规则


def test_fr9_alert_close_loop_records_handler():
    pid = _seed_alert_project()
    plm.scan_alerts()
    a = plm.list_alerts(project_id=pid, status='待处理')[0]
    r = plm.handle_alert(a['id'], {'status': '已闭环', 'note': '风险已处置'}, operator='财务')
    assert r['success'] is True
    after = [x for x in plm.list_alerts(project_id=pid) if x['id'] == a['id']][0]
    assert after['status'] == '已闭环' and after['handler'] == '财务'
    assert after['handle_note'] == '风险已处置' and after['handle_time']
    assert plm.handle_alert(a['id'], {'status': '未知'})['success'] is False
    assert any(l['action'] == '预警处置' for l in plm.list_logs('alert'))


def test_fr9_threshold_change_takes_effect():
    """# CC-010 FR-9 毛利底线阈值 15%→25% 后，毛利率 20% 的项目由无预警变为触发。"""
    oid, pid, cid, bid = _to_project()
    plm.create_ledger({'project_id': pid, 'kind': 'income', 'category': '其他收入',
                       'amount': 250000, 'plan_or_actual': '实际'})
    plm.create_ledger({'project_id': pid, 'kind': 'cost', 'category': '分包成本',
                       'amount': 1000000, 'plan_or_actual': '实际'})
    # 收入 1,250,000 成本 1,000,000 → 毛利率 20%
    assert abs(plm.project_finance(pid)['gross']['actual_rate'] - 0.2) < 1e-6
    plm.scan_alerts()
    assert [a for a in plm.list_alerts(project_id=pid) if a['dim'] == 'gross'] == []
    plm.update_alert_rule('gross_low_warn', {'threshold': 0.25}, operator='财务')
    plm.scan_alerts()
    hits = [a for a in plm.list_alerts(project_id=pid) if a['dim'] == 'gross']
    assert len(hits) == 1 and hits[0]['status'] == '待处理'


def test_fr9_schedule_and_staff_alerts_fire():
    """# CC-010 FR-9 进度延期与人员过载两类预警。"""
    oid, pid, cid, bid = _to_project()
    rough = plm.list_milestones(pid)[0]
    plm.create_milestone({'project_id': pid, 'parent_id': rough['id'], 'name': '超期40天',
                          'plan_start': _ymd(-80), 'plan_end': _ymd(-40),
                          'progress': 20, 'status': '进行中'})
    s = plm.create_staff({'name': '郑十', 'cost_rate': 1500, 'available_hours': 100})
    plm.create_assignment({'staff_id': s['id'], 'project_id': pid, 'planned_hours': 180})
    plm.scan_alerts()
    dims = {a['dim'] for a in plm.list_alerts(project_id=pid)}
    assert 'schedule' in dims and 'staff' in dims
    staff_alert = [a for a in plm.list_alerts(project_id=pid) if a['dim'] == 'staff'][0]
    assert '郑十' in staff_alert['title'] and staff_alert['staff_name'] == '郑十'


def test_fr9_risk_cleared_auto_closes():
    """# CC-010 FR-9 风险消除后系统自动闭环。"""
    pid = _seed_alert_project(actual_cost=850000)
    plm.scan_alerts()
    assert plm.list_alerts(project_id=pid, status='未闭环')
    conn = sqlite3.connect(TEST_DB)
    conn.execute("DELETE FROM plm_ledger WHERE project_id=? AND kind='cost'", (pid,))
    conn.commit()
    conn.close()
    res = plm.scan_alerts()
    assert res['auto_closed'] >= 1
    remain = [a for a in plm.list_alerts(project_id=pid) if a['dim'] == 'cost']
    assert all(a['status'] == '已闭环' for a in remain)


def test_fr9_finished_project_skips_cost_and_schedule_alerts():
    pid = _seed_alert_project(actual_cost=1200000)
    plm.update_project(pid, {'status': '结项'})
    plm.scan_alerts()
    assert [a for a in plm.list_alerts(project_id=pid, status='未闭环')
            if a['dim'] in ('cost', 'schedule')] == []


def test_fr9_alert_filters():
    pid = _seed_alert_project()
    plm.scan_alerts()
    all_open = plm.list_alerts(status='未闭环')
    assert all(a['status'] != '已闭环' for a in all_open)
    assert plm.list_alerts(project_id=99999, status='未闭环') == []
    assert all(a['dim'] == 'cost' for a in plm.list_alerts(dim='cost', status='未闭环'))


# ===================== FR-10 报表导出 =====================

@pytest.mark.parametrize('report', list(plm.REPORTS))
def test_fr10_all_reports_exportable(report):
    """# CC-010 FR-10 5 类报表均可导出为 xlsx。"""
    oid, pid, cid, bid = _to_project()
    fn, data = plm.export_report(report, project_id=pid)
    assert data[:2] == b'PK'                       # xlsx 是 zip 容器
    assert len(data) > 3000
    assert fn.endswith('.xlsx')


def test_fr10_unknown_report_and_missing_id_raise():
    with pytest.raises(ValueError):
        plm.export_report('not-exist')
    with pytest.raises(ValueError):
        plm.export_report('panorama')


def test_fr10_export_endpoint_returns_attachment(client):
    """# CC-010 FR-10 导出接口返回 xlsx 流与中文文件名。"""
    oid, pid, cid, bid = _to_project()
    r = client.get('/api/plm/export/cost')
    assert r.status_code == 200
    assert r.content[:2] == b'PK'
    assert 'attachment' in r.headers['content-disposition']
    bad = client.get('/api/plm/export/panorama')
    assert bad.status_code == 400


# ===================== FR-11 配置 / 字典 / 留痕 =====================

def test_fr11_dict_maintenance_flows_into_options():
    """# CC-010 FR-11 新增成本科目后出现在下拉枚举中。"""
    assert '云资源租赁费' not in plm.dict_options('cost_category')
    r = plm.create_dict('cost_category', '云资源租赁费', '云资源租赁费', 7, operator='管理员')
    assert r['success'] is True
    assert '云资源租赁费' in plm.dict_options('cost_category')
    assert plm.create_dict('cost_category', '云资源租赁费', '重复')['success'] is False
    assert plm.delete_dict(r['id'])['success'] is True
    assert '云资源租赁费' not in plm.dict_options('cost_category')


def test_fr11_seeded_master_data_exists():
    rules = {r['rule_key'] for r in plm.list_alert_rules()}
    assert {'cost_overrun_warn', 'gross_low_warn', 'schedule_overdue_warn',
            'staff_overload_warn'} <= rules
    cfg = {c['key'] for c in plm.list_config()}
    assert {'baseline_constraint', 'labor_day_hours', 'alert_staff_overload'} <= cfg
    assert set(plm.dict_options('project_status')) == set(plm.PROJECT_STATUS)


def test_fr11_seed_is_idempotent_and_preserves_user_edits():
    plm.update_alert_rule('gross_low_warn', {'threshold': 0.30}, operator='财务')
    plm.seed_plm_master()
    rule = [r for r in plm.list_alert_rules() if r['rule_key'] == 'gross_low_warn'][0]
    assert rule['threshold'] == 0.30


def test_fr11_operation_logs_traceable():
    oid, pid, cid, bid = _to_project()
    plm.update_project(pid, {'status': '执行中'})
    s = plm.create_staff({'name': '留痕人员', 'cost_rate': 1000, 'available_hours': 160})
    plm.create_assignment({'staff_id': s['id'], 'project_id': pid, 'planned_hours': 40})
    plm.create_timesheet({'staff_id': s['id'], 'project_id': pid, 'hours': 8})
    plm.create_ledger({'project_id': pid, 'kind': 'cost', 'category': '其他费用',
                       'amount': 1000, 'plan_or_actual': '实际'})
    plm.scan_alerts()
    alerts = plm.list_alerts(project_id=pid, status='待处理')
    if alerts:
        plm.handle_alert(alerts[0]['id'], {'status': '处理中', 'note': '跟进中'},
                         operator='PMO')
    types = {l['target_type'] for l in plm.list_logs()}
    assert {'opportunity', 'estimate', 'contract', 'project', 'milestone', 'staff',
            'assignment', 'timesheet', 'ledger'} <= types
    assert 'baseline' in types  # 联动立项带入概算基线
    proj_log = [l for l in plm.list_logs('project') if l['action'] == '修改项目'][0]
    assert proj_log['change']['status']['before'] == '待启动'
    assert proj_log['change']['status']['after'] == '执行中'


# ===================== 路由冒烟：/plm 与 /api/plm/* =====================

def test_routes_page_and_assets(client):
    """页面路由在 test_frontend_pages_served 中校验（依赖前端文件）。"""
    r = client.get('/api/plm/overview')
    assert r.status_code == 200
    body = r.json()
    assert body['success'] is True
    assert 'kpi' in body['data']


def test_routes_crud_flow_via_http(client):
    """# CC-010 FR-1/FR-2 经 API 完成商机 → 概算 → 中标 → 联动立项。"""
    r = client.post('/api/plm/opportunities', json={'opp_name': 'API商机', 'customer': '客户A',
                                                    'expect_income': 800000})
    oid = r.json()['id']
    e = client.post('/api/plm/opportunities/%d/estimate' % oid, json={'items': [
        {'category': '人力成本', 'plan_amount': 500000}]})
    assert e.json()['total_cost'] == 500000
    client.put('/api/plm/opportunities/%d' % oid, json={'status': '中标'})
    cv = client.post('/api/plm/opportunities/convert', json={
        'opportunity_id': oid, 'contract': {'sign_amount': 800000},
        'project': {'project_name': 'API交付项目', 'manager': 'PM'}})
    body = cv.json()
    assert body['success'] is True and body['estimate_baseline_id']
    pid = body['project_id']
    pan = client.get('/api/plm/projects/%d/panorama' % pid).json()['data']
    assert pan['base_info']['project_name'] == 'API交付项目'
    assert client.post('/api/plm/baselines/%d/lock' % body['estimate_baseline_id'],
                       json={}).json()['success'] is True
    blocked = client.post('/api/plm/projects/%d/baselines' % pid,
                          json={'stage': 'budget', 'total_cost': 900000}).json()
    assert blocked['success'] is True and blocked['over_estimate'] == 400000
    assert client.get('/api/plm/alerts').json()['success'] is True
    assert client.post('/api/plm/alerts/scan', json={}).json()['success'] is True
    assert client.get('/api/plm/staff/load').json()['success'] is True


def test_route_staff_load_not_swallowed_by_id(client):
    """/api/plm/staff/load 必须早于 /api/plm/staff/{staff_id} 注册。"""
    r = client.get('/api/plm/staff/load')
    assert r.status_code == 200
    assert isinstance(r.json()['data'], list)


def test_route_404_for_missing_entities(client):
    assert client.get('/api/plm/projects/987654').status_code == 404
    assert client.get('/api/plm/opportunities/987654').status_code == 404
    assert client.get('/api/plm/projects/987654/panorama').status_code == 404


def test_no_legacy_route_regression(client):
    """CC-010 为新增模块，既有接口不得受影响。"""
    for path in ('/', '/gross', '/api/datasource/tables', '/api/contracts',
                 '/api/gross/metrics', '/api/etl/jobs'):
        assert client.get(path).status_code == 200, path
