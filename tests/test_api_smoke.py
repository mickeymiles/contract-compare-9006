"""关键 API 冒烟测试（直连 9006 服务，验证端点连通 + 返回结构）

说明：本测试依赖本地/CI 已启动的 9006 服务。CI 环境中若无服务运行，
则整体跳过（集成冒烟不作为单元测试阻断项）；本地有服务时跑真实校验。
"""
# 规格编号: CC-001 合同管理 / CC-006 资金占用 / CC-007 ETL 调度
import requests

import pytest

BASE = "http://127.0.0.1:9006"

# 服务可达性预检：9006 未监听则跳过全部冒烟用例（避免 CI 无服务时 ConnectionRefused）
try:
    _probe = requests.get(BASE + "/", timeout=2)
    _service_up = _probe.status_code < 500
except Exception:
    _service_up = False

pytestmark = pytest.mark.skipif(
    not _service_up,
    reason="9006 服务未运行，跳过集成冒烟测试（CI 无服务时自动跳过）",
)


def _get(path, **params):
    return requests.get(BASE + path, params=params, timeout=15)


class TestContractAPI:
    def test_contracts(self):
        r = _get('/api/contracts')
        assert r.status_code == 200
        d = r.json()
        assert 'contracts' in d and 'stats' in d

    def test_stats(self):
        r = _get('/api/stats')
        assert r.status_code == 200
        assert 'stats' in r.json()


class TestFundAPI:
    def test_fund_status(self):
        r = _get('/api/fund/status')
        assert r.status_code == 200

    def test_fund_metrics(self):
        r = _get('/api/fund/metrics')
        assert r.status_code == 200
        d = r.json()
        assert d.get('success') is True
        assert 'data' in d


class TestETLAPI:
    def test_etl_jobs(self):
        r = _get('/api/etl/jobs')
        assert r.status_code == 200
        assert 'jobs' in r.json()

    def test_etl_metrics(self):
        r = _get('/api/etl/metrics')
        assert r.status_code == 200
        assert 'metrics' in r.json()


class TestGrossAPI:
    def test_gross_metrics(self):
        r = _get('/api/gross/metrics')
        assert r.status_code == 200
        d = r.json()
        assert 'summary' in d and 'year_rows' in d


class TestMCPOntologyAPI:
    def test_tables(self):
        r = _get('/api/mcp/ontology/tables')
        assert r.status_code == 200
        d = r.json()
        assert 'tables' in d and len(d['tables']) > 0

    def test_schema(self):
        r = _get('/api/mcp/ontology/schema', table_name='总合同表')
        assert r.status_code == 200

    def test_query(self):
        r = _get('/api/mcp/ontology/query', table_name='总合同表', limit=5)
        assert r.status_code == 200
