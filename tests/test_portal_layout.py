"""
CC-009 门户双分区导航 + CC-010 前端资源交付 — 结构冒烟测试

前端无自动化 UI 框架，这里对静态资源做结构断言（分区归属、页面注册表唯一性、
PLM 页面与脚本可访问、菜单树而非 Tab 页），行为级验证由 Playwright 手工截图完成。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

FRONTEND = os.path.join(os.path.dirname(__file__), '..', 'frontend')
TEST_DB = os.path.join(os.path.dirname(__file__), '..', 'contract_compare_plm_test.db')


def _read(name):
    with open(os.path.join(FRONTEND, name), encoding='utf-8') as f:
        return f.read()


@pytest.fixture(scope='module')
def html():
    return _read('index.html')


@pytest.fixture(scope='module')
def css():
    return _read('common.css')


@pytest.fixture(scope='module')
def plm_html():
    return _read('plm.html')


@pytest.fixture(scope='module')
def plm_js():
    return _read('plm.app.js')


# ===================== CC-009 FR-1 双分区 =====================

def test_portal_has_two_zones(html):
    """# CC-009 FR-1 门户存在「经营管理」「运维管理」两个分区。"""
    assert 'class="zone zone-biz"' in html
    assert 'class="zone zone-ops"' in html
    assert html.count('zh-title') >= 2
    assert '经营管理' in html and '运维管理' in html


def test_zone_order_and_datasource_above(html):
    """# CC-009 FR-1 数据源横条位于两个分区之上，经营管理先于运维管理。"""
    portal = html.split('<!-- 门户首页 -->')[1].split('<!-- 资金占用分析页 -->')[0]
    assert portal.index('ds-panel') < portal.index('zone-biz') < portal.index('zone-ops')


def test_ops_zone_only_contains_procurement(html):
    """# CC-009 FR-1 运维管理分区仅含备品备件采购询比价，经营类卡片不混入。"""
    portal = html.split('<!-- 门户首页 -->')[1].split('<!-- 资金占用分析页 -->')[0]
    ops = portal.split('class="zone zone-ops"')[1]
    biz = portal.split('class="zone zone-biz"')[1].split('class="zone zone-ops"')[0]
    assert '备品备件采购询比价' in ops and "/procurement" in ops
    for name in ['回款周期分析', '资金占用', '签单毛利率', '采购合同比对', '项目全生命周期管理']:
        assert name in biz, name
        assert name not in ops, name


def test_biz_zone_card_count(html):
    """# CC-009 FR-1 经营管理分区 6 张业务卡（含 1 张大模块卡）。"""
    portal = html.split('<!-- 门户首页 -->')[1].split('<!-- 资金占用分析页 -->')[0]
    biz = portal.split('class="zone zone-biz"')[1].split('class="zone zone-ops"')[0]
    assert biz.count('class="portal-card') == 7          # 6 业务卡 + 1 占位卡
    assert biz.count('portal-card add') == 1
    assert biz.count('portal-card feature') == 1


# ===================== CC-009 FR-2 大模块入口 =====================

def test_feature_card_links_plm_with_children(html):
    """# CC-009 FR-2 大模块卡跨列呈现并列出子模块，点击进入 /plm。"""
    assert 'portal-card feature' in html
    assert "location.href='/plm'" in html
    for chip in ['售前商机与概算', '四算基线管控', 'PMO 双维度进度', '人力池与工时',
                 '项目全景视图', '多维风险预警']:
        assert chip in html, chip
    css = _read('common.css')
    assert '.portal-card.feature' in css
    assert 'grid-column:span 2' in css
    assert '@media (max-width:980px)' in css          # 窄屏降级为单列


# ===================== CC-009 FR-3/FR-4 单活动页面不变式 =====================

def test_page_ids_defined_once(html):
    """# CC-009 FR-4 页 ID 字面量集合仅 ALL_PAGES 一处定义。"""
    assert html.count("'page-portal','page-home','page-workspace'") == 1
    assert 'const ALL_PAGES=' in html
    assert 'function showPage(' in html


def test_all_page_switch_paths_use_showpage(html):
    """# CC-009 FR-3 六条页面切换路径统一走 showPage。"""
    for call in ["showPage('page-portal')", "showPage('page-home')", "showPage('page-workspace')",
                 "showPage('page-datasource')", "showPage('page-payment-cycle')",
                 "showPage('page-fund-occupancy')"]:
        assert call in html, call


def test_zone_counts_computed_not_hardcoded():
    """# CC-009 FR-1 分区卡片数由 DOM 统计得出。"""
    html_src = _read('index.html')
    assert 'function initZoneCounts()' in html_src
    assert "querySelectorAll('.portal-card:not(.add)')" in html_src
    assert 'initZoneCounts()' in html_src.split('goPortal();')[-1]


# ===================== CC-010 前端资源 =====================

@pytest.fixture(scope='module')
def client():
    import models as cc_models
    import plm_models as plm
    orig_plm, orig_cc = plm.DB_PATH, cc_models.DB_PATH
    plm.DB_PATH = TEST_DB
    cc_models.DB_PATH = TEST_DB
    cc_models.init_db()
    plm.init_plm_db()
    plm.seed_plm_master()
    import main as app_main
    app_main.plm.DB_PATH = TEST_DB
    from fastapi.testclient import TestClient
    yield TestClient(app_main.app)
    plm.DB_PATH, cc_models.DB_PATH = orig_plm, orig_cc


def test_plm_page_and_script_served(client):
    """# CC-010 页面与脚本可访问。"""
    assert client.get('/plm').status_code == 200
    js = client.get('/plm.app.js')
    assert js.status_code == 200
    assert b'PLM' in js.content


def test_plm_uses_accordion_not_tabs(plm_html, plm_js):
    """PMO 左栏改为统一手风琴：三组（项目管理/进度管理/人员管理），含里程碑子菜单，不再渲染旧树。"""
    # 统一手风琴壳 + 三组 section
    assert 'id="plmSidebar"' in plm_html
    assert 'renderAccordion' in plm_html
    assert '项目管理' in plm_html and '进度管理' in plm_html and '人员管理' in plm_html
    # 里程碑子菜单 + 对应视图容器
    assert "label: '里程碑'" in plm_html
    assert 'id="v-milestone"' in plm_html
    # 不再渲染旧树节点 / 横向 tab 条
    assert '<nav id="plmNav">' not in plm_html
    assert 'plm-tabs' not in plm_js
    assert 'subtab' not in plm_js
    # 视图拓扑保持可用
    assert 'var NAV = [' in plm_js
    assert 'function navClick(' in plm_js and 'function renderNav(' in plm_js


def test_plm_sections_match_leaves(plm_js):
    """每个二级叶子都要有对应的内容分区容器。"""
    for sec in ['sub-project-projects', 'sub-project-contracts', 'sub-pmo-progress',
                'sub-pmo-nodes', 'sub-labor-staff', 'sub-labor-asg', 'sub-labor-ts',
                'sub-finance-summary', 'sub-finance-ledger', 'sub-alert-center',
                'sub-alert-rules', 'sub-config-params', 'sub-config-dict', 'sub-config-logs']:
        assert sec in plm_js, sec


def test_plm_panorama_blocks_in_js(plm_html, plm_js):
    """# CC-010 FR-8 全景视图 7 个固定板块在页面文案中齐备。"""
    for blk in ['① 基础信息区', '② 四算基线区', '③ PMO 进度区', '④ 人力资源区',
                '⑤ 财经数据区', '⑥ 风险预警区', '⑦ 快捷操作区']:
        assert blk in plm_js, blk


def test_plm_page_keeps_breadcrumb_to_portal(plm_html):
    """独立页保留返回门户的面包屑（由 nav.config.js 的 renderBreadcrumb 渲染根节点）。"""
    assert '项目全生命周期管理' in plm_html          # 页面身份（<title>）
    assert 'id="breadcrumb"' in plm_html            # 面包屑容器
    assert 'renderBreadcrumb' in plm_html           # 实际挂载面包屑渲染
    assert 'PMO' in plm_html                        # 面包屑根节点（域）存在


def test_common_css_has_zone_and_plm_tokens(css):
    """样式落在全局 common.css，与既有设计语言同源。"""
    for token in ['.portal-wrap', '.zone-head', '.zh-bar', '.zh-count', '.pc-chip',
                  '.zone-ops .zh-bar']:
        assert token in css, token
