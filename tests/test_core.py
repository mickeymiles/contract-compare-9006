"""主数据域 core（R3）测试：Project 主数据 CRUD、三号链路、Ops 联系信息、API、迁移回填。

使用独立测试库（monkeypatch core.project._DB），不改动真实 contract_compare.db。
"""
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

TEST_DB = os.path.join(os.path.dirname(__file__), '..', 'contract_compare_core_test.db')


@pytest.fixture(scope='module', autouse=True)
def _core_db():
    from core import project as core
    orig = core._DB
    core._DB = TEST_DB
    for suffix in ('', '-wal', '-shm'):
        if os.path.exists(core._DB + suffix):
            os.remove(core._DB + suffix)
    core.init_core_db()
    yield
    core._DB = orig
    for suffix in ('', '-wal', '-shm'):
        p = TEST_DB + suffix
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


def test_project_crud_and_three_no_chain():
    from core import project as core
    # 建项目 + 三号各自独立
    r = core.create_project({'project_no': 'PRJ-T-001', 'opportunity_no': 'OPP-T-1',
                             'contract_no': 'CT-T-001', 'name': '测试项目', 'status': 'active'})
    assert r['success'] and r['project_id']
    pid = r['project_id']
    # 唯一性约束：同号拒绝
    assert core.create_project({'project_no': 'PRJ-T-001', 'name': 'x'})['success'] is False
    # 查/取
    got = core.get_project(pid)
    assert got['project_no'] == 'PRJ-T-001' and got['contract_no'] == 'CT-T-001'
    assert len(core.list_projects()) >= 1
    # 更新
    assert core.update_project(pid, {'dept': '研发部'})['success']
    assert core.get_project(pid)['dept'] == '研发部'
    # 子项目余量字段存在
    assert 'parent_project_id' in got


def test_ops_contact_multi_per_project():
    from core import project as core
    r = core.create_project({'project_no': 'PRJ-T-002', 'name': '运维'})
    pid = r['project_id']
    core.create_ops_contact(pid, {'contact_role': '收件人', 'contact_name': '张三', 'contact_phone': '13800001111'})
    core.create_ops_contact(pid, {'contact_role': '现场负责人', 'contact_name': '李四'})
    lst = core.list_ops_contacts(pid)
    assert len(lst) == 2  # 1:N
    assert lst[0]['contact_role'] == '收件人'
    # 删除一个
    cid = lst[0]['contact_id']
    assert core.delete_ops_contact(cid)['success']
    assert len(core.list_ops_contacts(pid)) == 1


def test_core_api_crud():
    from fastapi.testclient import TestClient
    import main as app_module
    c = TestClient(app_module.app)
    r = c.post('/api/core/projects', json={'project_no': 'PRJ-API-1', 'contract_no': 'CT-API-1', 'name': 'API项目'})
    assert r.status_code == 200 and r.json()['success']
    pid = r.json()['project_id']
    assert c.get(f'/api/core/projects/{pid}').status_code == 200
    assert c.get('/api/core/projects').json()['success']
    # 重复 409
    assert c.post('/api/core/projects', json={'project_no': 'PRJ-API-1', 'name': 'x'}).status_code == 409
    # Ops 联系 API
    r = c.post('/api/core/ops-contacts', json={'project_id': pid, 'contact_role': '收件人', 'contact_name': '王五'})
    assert r.status_code == 200 and r.json()['success']
    assert c.get('/api/core/ops-contacts').json()['success']
    # 清理
    c.delete('/api/core/projects/' + str(pid))


def test_migrate_backfill_idempotent():
    from core import project as core
    from core import migrate
    # 造一张与唤醒回填映射连通的来源表 'procurement_contract'
    conn = sqlite3.connect(TEST_DB)
    conn.execute("DROP TABLE IF EXISTS procurement_contract")
    conn.execute("CREATE TABLE procurement_contract (id INTEGER PRIMARY KEY, contract_no TEXT, project_id INTEGER)")
    conn.execute("INSERT INTO procurement_contract (contract_no) VALUES ('BC-1'),('BC-2')")
    conn.commit()
    conn.close()  # 提前提交并释放写锁，避免阻塞后续 core 建映射
    # 建立 core_project + core_contract 映射（两单都登记）
    for no in ('BC-1', 'BC-2'):
        pr = core.create_project({'project_no': no, 'contract_no': no, 'name': no})
        pid = pr['project_id']
        conn = sqlite3.connect(TEST_DB)
        conn.execute("INSERT INTO core_contract (contract_no, project_id, project_no) VALUES (?,?,?)",
                     (no, pid, no))
        conn.commit()
        conn.close()
    # 插入一条无映射的孤儿合同 → 期望 project_id 留 NULL
    conn = sqlite3.connect(TEST_DB)
    conn.execute("INSERT INTO procurement_contract (contract_no) VALUES ('BC-NO-MAP')")
    conn.commit()
    conn.close()
    # 回填
    r = migrate.backfill_project_id(apply=True)
    assert r['procurement_contract'] == '2/3'  # 两条命中，一条(BC-NO-MAP)无映射留 null
    # 幂等：再跑不抛错、结果不变
    r2 = migrate.backfill_project_id(apply=True)
    assert r2['procurement_contract'] == '2/3'
    # 校验实际回填
    conn = sqlite3.connect(TEST_DB)
    rows = conn.execute("SELECT contract_no, project_id FROM procurement_contract").fetchall()
    conn.close()
    mapped = {no: pid for no, pid in rows if no in ('BC-1', 'BC-2')}
    assert len(mapped) == 2 and all(pid for pid in mapped.values())
    orphan = [no for no, pid in rows if no == 'BC-NO-MAP']
    assert orphan and orphan[0] == 'BC-NO-MAP'