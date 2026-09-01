"""总合同表 v2 导入映射 + 主数据新增字段 upsert + 三大计算（假数据/演示数据）测试。

隔离：monkeypatch core.project._DB 到独立测试库，不改动真实 contract_compare.db。
"""
import os
import sqlite3

import pytest

sys_path_setup_done = False


def _setup_path():
    global sys_path_setup_done
    if not sys_path_setup_done:
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
        sys_path_setup_done = True


_setup_path()

TEST_DB = os.path.join(os.path.dirname(__file__), '..', 'contract_compare_v2_test.db')
FAKE_XLSX = os.path.join(os.path.dirname(__file__), '_fake_total_contract.xlsx')


@pytest.fixture(scope='module', autouse=True)
def _v2_db():
    from core import project as core
    orig = core._DB
    core._DB = TEST_DB
    for suffix in ('', '-wal', '-shm'):
        if os.path.exists(TEST_DB + suffix):
            os.remove(TEST_DB + suffix)
    core.init_core_db()
    # 灌演示数据（主数据 + plm 里程碑链路 + finance_detail）
    from core import seed_demo
    seed_demo.seed_demo()
    yield
    core._DB = orig
    for suffix in ('', '-wal', '-shm'):
        p = TEST_DB + suffix
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass
    if os.path.exists(FAKE_XLSX):
        try:
            os.remove(FAKE_XLSX)
        except OSError:
            pass


def _make_fake_xlsx():
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(['项目号', '合同号', '项目名称', '客户名称', '甲方名称', '合同金额', '签订日期',
               '综合毛利率', '签单毛利', '硬件预估成本', '软件预估实施费', '累计实施成本预估',
               '区域', '行业', '业务线', '部门', '年份', '最后一笔回款日期'])
    ws.append(['X-PRJ-01', 'X-CT-01', '导入项目一', '客户甲', '甲方甲', '500000', '2026-05-01',
               '28', '140000', '80000', '60000', '120000', '华东', '交通', '企业业务', '交付部',
               '2026', '2026-08-01'])
    ws.append(['X-PRJ-02', 'X-CT-02', '导入项目二', '客户乙', '甲方乙', '300000', '2026-06-01',
               '', '', '0', '', '60000', '华南', '能源', '', '', '2026', ''])
    wb.save(FAKE_XLSX)


# ── 导入映射 ──────────────────────────────────────────────
def test_total_contract_mapping_reads_fake_xlsx():
    from core import import_total_contract as imp
    _make_fake_xlsx()
    rows = imp.read_total_contract_xlsx(FAKE_XLSX)
    assert len(rows) == 2
    r1 = next(r for r in rows if r.get('contract_no') == 'X-CT-01')
    assert r1['project_no'] == 'X-PRJ-01'
    assert r1['sign_amount'] == 500000.0          # 数值归一化为 float
    assert r1['gross_rate'] == 28.0
    assert r1['sign_gross_profit'] == 140000.0
    assert r1['hardware_est'] == 80000.0
    assert r1['region'] == '华东' and r1['industry'] == '交通'
    assert r1['last_received_date'] == '2026-08-01'
    # 仅映射存在的列才提取：空白/未映射列被丢弃
    assert 'contract_amount' not in r1
    r2 = next(r for r in rows if r.get('contract_no') == 'X-CT-02')
    assert r2['sign_amount'] == 300000.0
    assert r2['sign_gross_profit'] is None       # 空值 → None
    assert r2['software_est'] is None


def test_upsert_total_contracts_dedup_and_new_fields():
    from core import import_total_contract as imp
    from core import project as core
    rows = [
        {'contract_no': 'UP-CT-1', 'project_no': 'UP-PRJ-1', 'name': 'Upsert项目',
         'region': '东北', 'industry': '政务', 'last_received_date': '2026-07-01',
         'sign_amount': 100000, 'sign_gross_profit': 20000},
        {'contract_no': 'UP-CT-1', 'project_no': 'UP-PRJ-1', 'name': 'Upsert项目',
         'region': '华南', 'industry': '政务', 'last_received_date': '2026-08-01',  # 覆盖
         'sign_amount': 100000, 'sign_gross_profit': 20000},
    ]
    # 跨两次 upsert：首次插入 1，二次同号两行被去重为 1 → 更新不新增
    first = imp.upsert_total_contracts(rows[:1])
    assert first['created'] == 1 and first['updated'] == 0
    got = core.list_projects()
    hit = [p for p in got if p['contract_no'] == 'UP-CT-1'][0]
    assert hit['region'] == '东北'
    assert hit['last_received_date'] == '2026-07-01'
    assert hit['sign_gross_profit'] == 20000.0
    second = imp.upsert_total_contracts(rows)
    assert second['created'] == 0 and second['updated'] == 1  # 同号去重后仅更新
    assert len([p for p in core.list_projects() if p['contract_no'] == 'UP-CT-1']) == 1
    got2 = [p for p in core.list_projects() if p['contract_no'] == 'UP-CT-1'][0]
    assert got2['region'] == '华南' and got2['last_received_date'] == '2026-08-01'


# ── 三大计算（演示数据）────────────────────────────────────
def test_metrics_gross_margin():
    from core import project_metrics as pm
    r = pm.project_gross_margin('HT-DEMO-001')
    assert r['sign_amount'] == 1200000.0
    assert r['sign_gross_profit'] == 360000.0
    assert r['gross_rate'] == 30.0
    assert r['method'] == 'computed'


def test_metrics_payment_cycle_from_milestone():
    from core import project_metrics as pm
    r = pm.payment_cycle('HT-DEMO-001')
    assert r['source'] == 'plm_milestone'
    assert r['milestone_payback']['has_milestone'] is True
    assert r['cycle_days'] == 119  # 2026-05-14 实际回款 vs 2026-01-15 签订
    assert r['recv_date'] == '2026-05-14'


def test_metrics_payment_cycle_no_data_nan():
    from core import project_metrics as pm
    from core import project as core
    # 主数据存在但无回款/里程碑 → 回款周期 NaN + 说明
    core.upsert_project({'contract_no': 'HT-NAN-1', 'project_no': 'NAN-PRJ-1', 'name': '无回款',
                         'sign_date': '2026-01-01', 'region': '华东'})
    r = pm.payment_cycle('HT-NAN-1')
    assert r['cycle_days'] is None
    assert 'NaN' in r['note']
    # 主数据都不存在 → 给出合理说明
    r2 = pm.payment_cycle('HT-NOT-EXIST')
    assert r2['cycle_days'] is None
    assert r2['note']


def test_metrics_fund_occupancy_fifo():
    from core import project_metrics as pm
    r = pm.fund_occupancy('HT-DEMO-001', cutoff='2026-06-30')
    assert r['has_data'] is True
    assert r['total_pay'] == 950000.0
    assert r['total_recv'] == 600000.0
    assert r['current_occupy'] == 350000.0  # FIFO 冲抵后剩余占用
    r2 = pm.fund_occupancy('HT-NOT-EXIST')
    assert r2['has_data'] is False


def test_metrics_fifo_reuses_main_logic():
    from datetime import date
    from core import project_metrics as pm
    pay = [{'occur_date': date(2026, 3, 1), 'amount': 100},
           {'occur_date': date(2026, 4, 1), 'amount': 100}]
    recv = [{'occur_date': date(2026, 3, 15), 'amount': 120}]
    # 首笔付款后回款 120 冲抵首笔 100 + 次笔 20 → 剩 80
    assert pm.fifo_occupy_upto(pay, recv, date(2026, 12, 31)) == 80.0


# ── 迁移补列（存量表 ALTER；置于末位避免破坏演示数据）────────
def test_migrate_add_columns_on_legacy_table():
    import sqlite3
    from core import project as core
    # 建一张旧版 core_project（无 v2 新列），模拟存量库
    conn = sqlite3.connect(TEST_DB)
    conn.execute("DROP TABLE IF EXISTS core_project")
    conn.execute("CREATE TABLE core_project (project_id INTEGER PRIMARY KEY AUTOINCREMENT, "
                 "project_no TEXT UNIQUE NOT NULL, contract_no TEXT, name TEXT NOT NULL, "
                 "sign_date TEXT, sign_amount REAL, created_at TEXT, updated_at TEXT)")
    conn.commit()
    conn.close()
    added = core.migrate_add_columns()
    assert len(added) == len(core.EXTRA_PROJECT_COLUMNS)  # 21 个新列全部补上
    conn = sqlite3.connect(TEST_DB)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(core_project)").fetchall()}
    conn.close()
    assert {'region', 'gross_rate', 'hardware_est', 'last_received_date',
            'sign_gross_profit'} <= cols
    # 幂等：再跑不新增
    assert core.migrate_add_columns() == []