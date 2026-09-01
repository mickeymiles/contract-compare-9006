"""本体可观测（Ontology）API 守卫测试。

覆盖三件事，都不依赖外部 9007 在跑（迁移后引擎与本工程同进程）：
  1. /api/ontology/* 路由已注册到 9006 主应用（改名/漏挂会立刻红灯）；
  2. 各端点的返回契约是 {"success": True, "data": ...}；
  3. TBox 定义由本进程 ontology_engine 模块字面量直接提供（不依赖 HTTP / 缓存 / 源码回落）。

依赖本体库文件（默认工程根 contract_ontology.db）的用例在文件缺失时跳过 ——
CI 上本体库不一定存在，可观测页本身也对缺库做了降级。
"""

import os
import sys

import pytest

# 测试期间彻底关闭本体轨常驻循环，避免 TestClient 启动钩子拉起后台线程 / 外发邮件。
os.environ.setdefault("ONT_SCHEDULER", "0")
os.environ.setdefault("ONT_MODE", "off")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import ontology_gateway as ont  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402

# 需要真实本体库的用例：库不存在则跳过
requires_db = pytest.mark.skipif(
    not os.path.exists(ont.ONT_DB_PATH),
    reason=f"本体库不存在：{ont.ONT_DB_PATH}",
)
# 本体定义现已进程内直取 ontology_engine 字面量，无需外部 9007 源码目录，故不再跳过。
requires_src = pytest.mark.skipif(False, reason="spec 现已进程内直取，无需外部源码")


EXPECTED_ROUTES = (
    '/api/ontology/overview',
    '/api/ontology/spec',
    '/api/ontology/instances',
    '/api/ontology/knowledge',
    '/api/ontology/actions',
    '/api/ontology/audit',
    '/api/ontology/tasks',
    '/api/ontology/tasks/{task_id}',
    '/api/ontology/ledger',
    '/api/ontology/claim-state',
)


class TestRouteRegistration:
    """路由守卫：手滑改名或漏挂载，这里先红。"""

    def test_ontology_routes_registered(self):
        paths = {r.path for r in main.app.routes if getattr(r, 'path', None)}
        missing = [p for p in EXPECTED_ROUTES if p not in paths]
        assert not missing, f"以下本体路由未注册: {missing}"

    def test_ontology_routes_are_readonly(self):
        """当前阶段本体面板只读，不应出现 POST/PUT/DELETE 入口。"""
        methods = set()
        for r in main.app.routes:
            if getattr(r, 'path', '').startswith('/api/ontology'):
                methods.update(getattr(r, 'methods', None) or ())
        assert methods <= {'GET', 'HEAD'}, f"出现了非只读方法: {methods - {'GET', 'HEAD'}}"


@pytest.fixture(scope='module')
def client():
    with TestClient(main.app) as c:
        yield c


class TestApiContract:
    def test_overview(self, client):
        d = client.get('/api/ontology/overview').json()
        assert d['success'] is True
        assert 'counts' in d['data'] and 'spec_source' in d['data']
        assert set(d['data']['counts']) == set(ont.ONT_TABLES)

    @requires_src
    def test_spec(self, client):
        d = client.get('/api/ontology/spec').json()
        assert d['success'] is True
        for key in ('concepts', 'relations', 'actions', 'invariants', 'rules', 'action_registry'):
            assert d['data'][key], f"spec 缺少 {key}"

    def test_claim_state_contract(self, client):
        """认领健康度：即便本体库缺失也必须 200 + 降级标记。"""
        d = client.get('/api/ontology/claim-state').json()
        assert d['success'] is True
        data = d['data']
        for key in ('watermark_ts', 'watermark', 'unclaimed_count', 'unclaimed', 'degraded'):
            assert key in data, f"claim-state 缺少 {key}"
        assert isinstance(data['unclaimed'], list)
        assert data['unclaimed_count'] == len(data['unclaimed'])

    @requires_db
    def test_claim_state_unclaimed_shape(self, client):
        """卡单条目必须带排障所需字段（状态 + 错因），否则运维看不出为什么卡。"""
        data = client.get('/api/ontology/claim-state').json()['data']
        for row in data['unclaimed']:
            for key in ('email_message_id', 'claim_status', 'claim_error'):
                assert key in row, f"卡单条目缺少 {key}"
            assert row['claim_status'] in ('pending', 'failed')

    @requires_db
    def test_instances(self, client):
        d = client.get('/api/ontology/instances').json()
        assert d['success'] is True
        for key in ('tasks', 'persons', 'emails', 'quotes', 'sessions'):
            assert isinstance(d['data'][key], list)

    @requires_src
    def test_knowledge(self, client):
        d = client.get('/api/ontology/knowledge').json()
        assert d['success'] is True
        assert d['data']['invariants']
        assert d['data']['rules']
        # 每个动作定义都要有 定义/条件/效果 三段
        for aid, spec in d['data']['actions'].items():
            assert '定义' in spec and '条件' in spec and '效果' in spec, f"{aid} 定义不完整"

    @requires_src
    def test_actions(self, client):
        d = client.get('/api/ontology/actions').json()
        assert d['success'] is True
        assert d['data']['action_registry']
        for aid, spec in d['data']['action_registry'].items():
            assert '_stats' in spec, f"{aid} 缺少执行统计"

    @requires_db
    def test_audit(self, client):
        d = client.get('/api/ontology/audit?limit=5').json()
        assert d['success'] is True
        assert len(d['data']) <= 5
        for row in d['data']:
            assert 'content_snapshot_parsed' in row

    @requires_db
    def test_tasks(self, client):
        d = client.get('/api/ontology/tasks').json()
        assert d['success'] is True
        for t in d['data']:
            # 双流状态 + 里程碑是任务列表面板的核心列
            for col in ('internal_status', 'external_status', 'milestones', 'part'):
                assert col in t

    @requires_db
    def test_task_detail_not_found(self, client):
        r = client.get('/api/ontology/tasks/NOT-EXIST')
        assert r.status_code == 404
        assert r.json()['success'] is False

    @requires_db
    def test_ledger(self, client):
        d = client.get('/api/ontology/ledger').json()
        assert d['success'] is True
        for row in d['data']:
            assert row['close_status'].upper().startswith('CLOSED')
