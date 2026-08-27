"""
合同域符号隔离回归测试（CC-001 FR-1 / FR-3）

背景缺陷：`from procurement_models import create_contract, delete_contract` 遮蔽了
`models.py` 的同名函数，迫使 `/api/contracts` 用 `import contract_models`（该模块不存在）
兜底，导致前端「＋ 新建合同」点击后 500 ModuleNotFoundError。

修复：采购侧同名函数改为 `proc_create_contract` / `proc_delete_contract` 别名导入，
遗留合同路由直接调用 models 的实现。本文件锁死该行为，防止再次被遮蔽。
"""

import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import models as cc_models              # noqa: E402  合同比对域数据层
import plm_models                       # noqa: E402  CC-010 项目全生命周期
import procurement_models as pm         # noqa: E402  备品备件采购域数据层

TEST_DB = os.path.join(os.path.dirname(__file__), '..', 'contract_compare_domain_test.db')


@pytest.fixture(scope='module', autouse=True)
def _redirect_db():
    """把三个数据域全部指向独立测试库，会话结束后恢复并清理。"""
    orig = (cc_models.DB_PATH, pm.DB_PATH, plm_models.DB_PATH)
    cc_models.DB_PATH = pm.DB_PATH = plm_models.DB_PATH = TEST_DB
    for suffix in ('', '-wal', '-shm'):
        if os.path.exists(TEST_DB + suffix):
            os.remove(TEST_DB + suffix)
    cc_models.init_db()
    pm.init_procurement_db()
    plm_models.init_plm_db()
    yield
    cc_models.DB_PATH, pm.DB_PATH, plm_models.DB_PATH = orig
    for suffix in ('', '-wal', '-shm'):
        p = TEST_DB + suffix
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


@pytest.fixture
def client():
    import main as app_main
    app_main.plm.DB_PATH = TEST_DB
    from fastapi.testclient import TestClient
    return TestClient(app_main.app)


def _conn():
    c = sqlite3.connect(TEST_DB)
    c.row_factory = sqlite3.Row
    return c


# ===================== 遮蔽守卫 =====================

def test_main_create_contract_is_models_version(client):
    """# CC-001 FR-1 main 全局的 create_contract 必须仍属合同比对域，不得被采购域遮蔽。"""
    import main as app_main
    assert app_main.create_contract is cc_models.create_contract
    assert app_main.delete_contract is cc_models.delete_contract
    # 采购域通过别名暴露，且与 models 是两个不同实现
    assert app_main.proc_create_contract is pm.create_contract
    assert app_main.proc_delete_contract is pm.delete_contract
    assert app_main.proc_create_contract is not app_main.create_contract


# ===================== CC-001 FR-1 合同创建 =====================

def test_post_api_contracts_creates_row(client):
    """# CC-001 FR-1 前端「新建合同」调用的接口应真实落库。"""
    r = client.post('/api/contracts?name=测试合同甲&no=HT-T-001&sign_date=2026-08-27')
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['success'] is True and body['contract_id']
    c = _conn()
    row = c.execute("SELECT * FROM contracts WHERE id=?", (body['contract_id'],)).fetchone()
    c.close()
    assert row is not None
    assert row['contract_name'] == '测试合同甲'
    assert row['contract_no'] == 'HT-T-001'
    assert row['sign_date'] == '2026-08-27'


def test_post_api_contracts_rejects_blank_name(client):
    """# CC-001 FR-1 空名称返回 400 而非 500。"""
    r = client.post('/api/contracts', params={'name': '   ', 'no': '', 'sign_date': ''})
    assert r.status_code == 400
    assert r.json()['success'] is False


def test_created_contract_visible_in_list(client):
    """# CC-001 FR-2 新建合同可被列表接口检索到。"""
    cid = client.post('/api/contracts', params={'name': '可检索合同', 'no': 'HT-T-002'}).json()['contract_id']
    rows = client.get('/api/contracts').json()['contracts']
    assert cid in [x['id'] for x in rows]


# ===================== CC-001 FR-3 删除与级联 =====================

def test_delete_api_contracts_cascades(client):
    """# CC-001 FR-3 / NFR-2 删除合同级联清理明细，不留半删除状态。"""
    cid = client.post('/api/contracts', params={'name': '待删合同', 'no': 'HT-T-003'}).json()['contract_id']
    c = _conn()
    c.execute("INSERT INTO contract_items (contract_id, device_name) VALUES (?, '服务器A')", (cid,))
    c.commit()
    c.close()
    assert client.delete('/api/contracts/%d' % cid).json()['success'] is True
    c = _conn()
    assert c.execute("SELECT COUNT(*) n FROM contracts WHERE id=?", (cid,)).fetchone()['n'] == 0
    assert c.execute("SELECT COUNT(*) n FROM contract_items WHERE contract_id=?", (cid,)).fetchone()['n'] == 0
    c.close()


# ===================== 三个合同域互不串写 =====================

def test_three_contract_domains_do_not_cross_write(client):
    """# CC-001 FR-5 多合同隔离：合同比对 / 备件采购 / 项目全生命周期三域各自落自己的表。"""
    legacy_id = client.post('/api/contracts', params={'name': '域隔离-比对', 'no': 'DOM-A'}).json()['contract_id']
    proc_id = client.post('/api/procurement/contracts',
                          json={'contract_no': 'DOM-B', 'contract_name': '域隔离-采购',
                                'pm_name': '张'}).json()['data']['id']
    plm_id = client.post('/api/plm/contracts',
                         json={'contract_no': 'DOM-C', 'contract_name': '域隔离-项目',
                               'customer': '客户X', 'sign_amount': 1000}).json()['id']
    c = _conn()
    assert c.execute("SELECT contract_name FROM contracts WHERE id=?", (legacy_id,)).fetchone()[0] == '域隔离-比对'
    assert c.execute("SELECT contract_no FROM procurement_contract WHERE id=?", (proc_id,)).fetchone()[0] == 'DOM-B'
    assert c.execute("SELECT contract_no FROM plm_contract WHERE id=?", (plm_id,)).fetchone()[0] == 'DOM-C'
    # 任一域的记录都不会出现在另外两域
    assert c.execute("SELECT COUNT(*) n FROM contracts WHERE contract_no='DOM-B'").fetchone()['n'] == 0
    assert c.execute("SELECT COUNT(*) n FROM contracts WHERE contract_no='DOM-C'").fetchone()['n'] == 0
    assert c.execute("SELECT COUNT(*) n FROM plm_contract WHERE contract_no='DOM-B'").fetchone()['n'] == 0
    c.close()


def test_procurement_contract_delete_still_works(client):
    """修复遮蔽不得回退采购域行为：删除采购合同主数据仍走 procurement_models。"""
    cid = client.post('/api/procurement/contracts',
                      json={'contract_no': 'DOM-D', 'contract_name': '采购可删',
                            'pm_name': '李'}).json()['data']['id']
    r = client.delete('/api/procurement/contracts/%d' % cid)
    assert r.status_code == 200
    assert r.json()['success'] is True
    c = _conn()
    assert c.execute("SELECT COUNT(*) n FROM procurement_contract WHERE id=?", (cid,)).fetchone()['n'] == 0
    c.close()
