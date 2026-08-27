"""
CC-011 前端资源缓存策略 — 回归测试

规格：changes/2026-08-27-static-asset-cache/specs/CC-011-static-asset-cache/spec.md
锁死两件事：页面与静态资源必须每次再校验（no-cache + 304 可用），
以及动态接口不被波及。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import models as cc_models          # noqa: E402
import plm_models                   # noqa: E402
import procurement_models as pm     # noqa: E402

TEST_DB = os.path.join(os.path.dirname(__file__), '..', 'contract_compare_cache_test.db')

CACHED_PATHS = ['/', '/gross', '/plm', '/procurement', '/common.css',
                '/plm.app.js', '/procurement.app.js', '/china.json']


@pytest.fixture(scope='module', autouse=True)
def _redirect_db():
    orig = (cc_models.DB_PATH, pm.DB_PATH, plm_models.DB_PATH)
    cc_models.DB_PATH = pm.DB_PATH = plm_models.DB_PATH = TEST_DB
    cc_models.init_db()
    pm.init_procurement_db()
    plm_models.init_plm_db()
    plm_models.seed_plm_master()
    yield
    cc_models.DB_PATH, pm.DB_PATH, plm_models.DB_PATH = orig
    for suffix in ('', '-wal', '-shm'):
        p = TEST_DB + suffix
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


@pytest.fixture(scope='module')
def client():
    import main as app_main
    app_main.plm.DB_PATH = TEST_DB
    from fastapi.testclient import TestClient
    return TestClient(app_main.app)


@pytest.mark.parametrize('path', CACHED_PATHS)
def test_pages_and_assets_are_no_cache(client, path):
    """# CC-011 页面与清单内静态资源必须带 Cache-Control: no-cache。"""
    r = client.get(path)
    assert r.status_code == 200, path
    assert r.headers.get('cache-control') == 'no-cache', path
    assert 'no-store' not in (r.headers.get('cache-control') or '')


def test_etag_and_last_modified_present_for_revalidation(client):
    """# CC-011 再校验依赖文件指纹，ETag / Last-Modified 必须齐备。"""
    r = client.get('/common.css')
    assert r.headers.get('etag')
    assert r.headers.get('last-modified')


def test_conditional_request_returns_304(client):
    """# CC-011 未变更时返回 304 且不传响应体（这是不用 no-store 的理由）。"""
    first = client.get('/common.css')
    etag = first.headers['etag']
    second = client.get('/common.css', headers={'If-None-Match': etag})
    assert second.status_code == 304
    assert second.content == b''


def test_suffix_fallback_covers_unlisted_assets(client):
    """# CC-011 后缀兜底：未列入清单的 .css/.js 同样 no-cache（新增资源无需改策略）。"""
    r = client.get('/some-future-asset.js')      # 未注册路由，返回 404 但仍应带指令
    assert r.status_code == 404
    assert r.headers.get('cache-control') == 'no-cache'


def test_api_routes_not_affected(client):
    """# CC-011 动态接口不得被注入 Cache-Control，行为与变更前一致。"""
    r = client.get('/api/plm/overview')
    assert r.status_code == 200
    assert r.json()['success'] is True
    assert 'cache-control' not in r.headers


def test_middleware_registered_once(client):
    """中间件只应注册一份，避免重复包装导致响应头被叠成多值。"""
    import main as app_main
    names = [m.kwargs.get('dispatch').__name__
             for m in app_main.app.user_middleware
             if m.cls.__name__ == 'BaseHTTPMiddleware' and m.kwargs.get('dispatch')]
    assert names.count('no_cache_static_assets') == 1, names


def test_stale_etag_refetches_full_body(client):
    """# CC-011 指纹不匹配（发版后）必须回 200 + 新内容，而不是 304。"""
    r = client.get('/common.css', headers={'If-None-Match': '"deadbeef"'})
    assert r.status_code == 200
    assert len(r.content) > 1000
    assert r.headers.get('cache-control') == 'no-cache'


def test_weak_and_list_etag_match(client):
    """# CC-011 If-None-Match 支持逗号列表与 W/ 弱标记。"""
    etag = client.get('/common.css').headers['etag']
    for variant in (etag, 'W/' + etag, '"other", ' + etag):
        r = client.get('/common.css', headers={'If-None-Match': variant})
        assert r.status_code == 304, variant
        assert r.content == b''
