"""假数据 seed：为主数据三大计算准备可跑出非空结果的演示数据。

- 2 条 core_project（含成本概算/毛利/回款累计）；
- 对应 PLM 里程碑链路（plm_contract → plm_project → plm_milestone，「回款」里程碑带时间点）；
- 对应 finance_detail 收付款明细（契约号 contract_no 关联）。

幂等可重复执行（同 contract_no 先清理再重建相关关联行）。返回各表写入计数。
"""
from datetime import datetime

from core import project as project_core
from core import project_metrics as metrics

PLM_SCHEMA = """
CREATE TABLE IF NOT EXISTS plm_contract (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  contract_no TEXT UNIQUE NOT NULL,
  contract_name TEXT DEFAULT '',
  customer TEXT DEFAULT '',
  industry TEXT DEFAULT '',
  region TEXT DEFAULT '',
  dept TEXT DEFAULT '',
  sign_amount REAL DEFAULT 0,
  sign_date TEXT DEFAULT '',
  status TEXT DEFAULT '已签署'
);
CREATE TABLE IF NOT EXISTS plm_project (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_no TEXT UNIQUE NOT NULL,
  project_name TEXT NOT NULL,
  customer TEXT DEFAULT '',
  dept TEXT DEFAULT '',
  region TEXT DEFAULT '',
  manager TEXT DEFAULT '',
  status TEXT DEFAULT '待启动',
  contract_id INTEGER
);
CREATE TABLE IF NOT EXISTS plm_milestone (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL,
  parent_id INTEGER,
  level TEXT DEFAULT '细',
  name TEXT NOT NULL,
  plan_start TEXT DEFAULT '',
  plan_end TEXT DEFAULT '',
  actual_start TEXT DEFAULT '',
  actual_end TEXT DEFAULT '',
  progress REAL DEFAULT 0,
  status TEXT DEFAULT '已完成',
  task_no TEXT DEFAULT '',
  plan_payback_date TEXT DEFAULT '',
  payback_date TEXT DEFAULT '',
  payback_amount REAL DEFAULT 0
);
"""

DEMO_CONTRACTS = [
    dict(
        project_no='DEMO-2026-001', contract_no='HT-DEMO-001', name='示范项目·华北智慧园区',
        customer_key='客户A', party_a='甲方A科技有限公司', region='华北', province='河北省',
        industry='智慧园区', biz_type='集成', customer_cls='重点客户', biz_line='企业业务',
        stat_year='2026', dept='集成交付部', status='active', sign_date='2026-01-15',
        sign_amount=1200000.0, sign_gross_profit=360000.0, gross_rate=30.0,
        contract_profit=300000.0, payback_profit=180000.0, accum_received=600000.0,
        last_received_date='2026-06-30', payback_cycle=166,
        hardware_est=300000.0, software_est=250000.0, service_est=200000.0,
        accum_cost_est=750000.0, accum_cost_actual=720000.0,
    ),
    dict(
        project_no='DEMO-2026-002', contract_no='HT-DEMO-002', name='示范项目·华南制造云',
        customer_key='客户B', party_a='甲方B智造有限公司', region='华南', province='广东省',
        industry='智能制造', biz_type='软件', customer_cls='战略客户', biz_line='制造行业',
        stat_year='2026', dept='软件产品部', status='active', sign_date='2026-03-10',
        sign_amount=800000.0, sign_gross_profit=200000.0, gross_rate=25.0,
        contract_profit=180000.0, payback_profit=80000.0, accum_received=240000.0,
        last_received_date='2026-07-20', payback_cycle=132,
        hardware_est=100000.0, software_est=300000.0, service_est=150000.0,
        accum_cost_est=550000.0, accum_cost_actual=540000.0,
    ),
]


def _now() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def seed_demo() -> dict:
    metrics.ensure_finance_detail()
    conn = project_core.get_conn()
    now = _now()
    try:
        conn.executescript(PLM_SCHEMA)
        # 清理同名演示关联行，保证幂等
        for no in [c['contract_no'] for c in DEMO_CONTRACTS]:
            pid_rows = conn.execute(
                "SELECT pp.id FROM plm_project pp "
                "JOIN plm_contract pc ON pc.id = pp.contract_id WHERE pc.contract_no=?", (no,)).fetchall()
            for (pid,) in pid_rows:
                conn.execute("DELETE FROM plm_milestone WHERE project_id=?", (pid,))
                conn.execute("DELETE FROM plm_project WHERE id=?", (pid,))
            conn.execute("DELETE FROM plm_contract WHERE contract_no=?", (no,))
            conn.execute("DELETE FROM finance_detail WHERE contract_no=?", (no,))

        # 主数据：经同一 conn 直接 upsert（避免嵌套连接于非 WAL 库被锁）
        CORE_COLS = [
            'project_no', 'contract_no', 'name', 'customer_key', 'party_a', 'region',
            'province', 'industry', 'biz_type', 'customer_cls', 'biz_line', 'stat_year',
            'dept', 'status', 'sign_date', 'sign_amount', 'sign_gross_profit', 'gross_rate',
            'contract_profit', 'payback_profit', 'accum_received', 'last_received_date',
            'payback_cycle', 'hardware_est', 'software_est', 'service_est',
            'accum_cost_est', 'accum_cost_actual', 'created_at', 'updated_at',
        ]
        for c in DEMO_CONTRACTS:
            # 先删同名（按 contract_no 清回测试库），再插入，保证幂等
            conn.execute("DELETE FROM core_project WHERE contract_no=?", (c['contract_no'],))
            vals = [c.get(col) for col in CORE_COLS if col not in ('created_at', 'updated_at')] + [now, now]
            cols = [col for col in CORE_COLS if col not in ('created_at', 'updated_at')] + ['created_at', 'updated_at']
            conn.execute(
                f"INSERT INTO core_project ({', '.join(cols)}) VALUES ({', '.join('?'*len(cols))})",
                vals)

        # PLM 链路 + 回款里程碑
        for c in DEMO_CONTRACTS:
            cur = conn.execute(
                "INSERT INTO plm_contract (contract_no, contract_name, customer, industry, region, dept, sign_amount, sign_date, status) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (c['contract_no'], c['name'], c['customer_key'], c['industry'], c['region'],
                 c['dept'], c['sign_amount'], c['sign_date'], '已签署'))
            cid = cur.lastrowid
            cur = conn.execute(
                "INSERT INTO plm_project (project_no, project_name, customer, dept, region, status, contract_id) "
                "VALUES (?,?,?,?,?,?,?)",
                (c['project_no'], c['name'], c['customer_key'], c['dept'], c['region'],
                 '执行中', cid))
            pid = cur.lastrowid
            conn.execute(
                "INSERT INTO plm_milestone (project_id, level, name, plan_start, plan_end, actual_start, actual_end, progress, status) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (pid, '粗', '合同签订', c['sign_date'], c['sign_date'], c['sign_date'], c['sign_date'], 100, '已完成'))
            conn.execute(
                "INSERT INTO plm_milestone (project_id, level, name, plan_start, plan_end, actual_start, actual_end, progress, status) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (pid, '细', '首笔回款到账', '2026-04-01', '2026-05-15', '2026-04-16', '2026-05-14', 100, '已完成'))

        # finance_detail 收付款明细，直接经同一 conn 写入（避免事务嵌套锁）
        def add_fin(no, kind, d, amt, camt):
            conn.execute(
                "INSERT INTO finance_detail (contract_no, kind, occur_date, amount, contract_amount, remark, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (no, kind, d, amt, camt, '', now, now))
        # 001：付款 3 笔共 95 万，回款 2 笔共 60 万（一笔预收 20 万）
        for (date_, amt) in [('2026-02-20', 300000.0), ('2026-04-10', 350000.0), ('2026-06-25', 300000.0)]:
            add_fin('HT-DEMO-001', 'pay', date_, amt, 1200000.0)
        for (date_, amt) in [('2026-02-10', 200000.0), ('2026-05-20', 400000.0)]:
            add_fin('HT-DEMO-001', 'recv', date_, amt, 1200000.0)
        # 002：付款 2 笔共 60 万，回款 2 笔共 24 万
        for (date_, amt) in [('2026-04-05', 400000.0), ('2026-06-15', 200000.0)]:
            add_fin('HT-DEMO-002', 'pay', date_, amt, 800000.0)
        for (date_, amt) in [('2026-05-01', 120000.0), ('2026-07-10', 120000.0)]:
            add_fin('HT-DEMO-002', 'recv', date_, amt, 800000.0)

        conn.commit()
        contracts = conn.execute("SELECT COUNT(*) n FROM core_project WHERE contract_no LIKE 'HT-DEMO-%'").fetchone()[0]
        details = conn.execute("SELECT COUNT(*) n FROM finance_detail ").fetchone()[0]
        return {'success': True, 'demo_contracts': len(DEMO_CONTRACTS),
                'core_project_matched': contracts, 'finance_detail_rows': details}
    finally:
        conn.close()


if __name__ == '__main__':
    import json
    project_core.init_core_db()
    print(json.dumps(seed_demo(), ensure_ascii=False))