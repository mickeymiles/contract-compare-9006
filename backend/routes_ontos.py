"""本体拓扑（v4 业务域）独立页与 API。

数据源（全部动态，无静态快照）：
- TBox 定义：ontos submodule，``ontos.domain_business.to_spec()``。
- 物理字段：``datasource/datasource_meta.json`` 中「总合同表」(208 列)、
  「项目里程碑表」(77 列) 的最新版本列清单。

设计要点：
- to_spec() 每次请求实时执行，改 ontos 代码后刷新页面即生效（TBox 不落库）。
- ontos 不可用时返回 503 + 明确原因，不静默降级为旧数据（避免"看到的是假的"）。
"""
import os
import sys
import json

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))            # backend/
REPO_ROOT = os.path.abspath(os.path.join(BASE_DIR, '..'))
FRONTEND_DIR = os.path.join(REPO_ROOT, 'frontend')
DATASOURCE_META = os.path.join(REPO_ROOT, 'datasource', 'datasource_meta.json')
ONTOS_ROOT = os.path.join(REPO_ROOT, 'ontos')                    # submodule 根（内含 ontos/ 包）

router = APIRouter(tags=['ontos-topology'])

# 实体 → 权威物理数据集（用户确认：合同表最全，作属性参考基准）
ENTITY_DATASET = {
    'Contract': '总合同表',
    'Project': '总合同表',
    'Receipt': '总合同表',
    'Payment': '总合同表',
    'Milestone': '项目里程碑表',
}

# 列分组规则：按序匹配首个命中关键词归组，未命中落入「其他」。
# 顺序敏感——越具体的语义放前面（如「回款」先于「金额」，避免被泛化吞掉）。
COLUMN_GROUP_RULES = [
    ('标识与主数据', ('编号', '号', '名称', '客户', '甲方', '最终用户', '部门', '区域',
                 '省', '行业', '业务线', '业务类型', '客户分类', '责任人', '签定人',
                 '签署地', '标识', '说明', '备注', '描述', '状态', '是否', '币种',
                 '统计日期', '模板', '组织', '方向', '产品', '版本', '形态')),
    ('时间与周期', ('周期', '日期', '时间', '年份', '月')),
    ('回款与欠款', ('回款', '收款', '欠款', '核销', '退免税', '到账', '流入')),
    ('成本与费用', ('成本', '费用', '分包', '集成费', '实施费', '出厂价', '培训费',
                '附加费', '税金', '结算', '采购', '结转', '完工', '下单')),
    ('毛利与利润', ('毛利', '利润', '毛利率')),
    ('额度与产值', ('合同额', '金额', '产值', '生效', '分劈', '差异', '比例')),
]


_COLUMN_FIELD_CACHE = {'loaded': False, 'mapping': {}, 'provider': None}


def _cn_to_field_mapping():
    """中文列名 → 物理字段名的映射（用于标出"已被本体声明"的物理列）。

    取自 backend/core/import_total_contract.py（总合同表 v2 → core_project）。
    该文件 import 了 core.project，故用 try/except 兜底：拿不到映射时仅丢失
    高亮能力，不影响列清单本身（页面仍可正常浏览 208 列）。
    """
    if _COLUMN_FIELD_CACHE['loaded']:
        return _COLUMN_FIELD_CACHE['mapping']
    _COLUMN_FIELD_CACHE['loaded'] = True
    try:
        from core.import_total_contract import TOTAL_CONTRACT_COLUMN_MAP
        _COLUMN_FIELD_CACHE['mapping'] = dict(TOTAL_CONTRACT_COLUMN_MAP)
        _COLUMN_FIELD_CACHE['provider'] = 'core.import_total_contract'
    except Exception:
        _COLUMN_FIELD_CACHE['mapping'] = {}
        _COLUMN_FIELD_CACHE['provider'] = None
    return _COLUMN_FIELD_CACHE['mapping']


def _group_columns(columns):
    """把列清单按语义分组，返回 [(组名, [列名...]), ...]（保持原顺序）。"""
    groups = []
    index = {}
    for gname, _ in COLUMN_GROUP_RULES:
        index[gname] = []
        groups.append((gname, index[gname]))
    other = []
    for col in columns:
        hit = None
        for gname, keywords in COLUMN_GROUP_RULES:
            if any(k in col for k in keywords):
                hit = gname
                break
        (index[hit] if hit else other).append(col)
    result = [(g, v) for g, v in groups if v]
    if other:
        result.append(('其他', other))
    return result


def _read_dataset(dataset_name):
    """读取某数据集最新版本的列清单。返回 dict 或 None（无元数据文件时）。"""
    if not os.path.exists(DATASOURCE_META):
        return None
    try:
        with open(DATASOURCE_META, 'r', encoding='utf-8') as f:
            meta = json.load(f)
    except (ValueError, OSError):
        return None
    ds = meta.get(dataset_name)
    if not ds:
        return None
    versions = ds.get('versions') or []
    if not versions:
        return None
    # 取列数最多的版本作为"最全"参考（v2 通常比 v1 全）
    latest = max(versions, key=lambda v: len(v.get('columns') or []))
    columns = list(latest.get('columns') or [])
    # 中文列 → 物理字段（仅总合同表有映射表；拿不到时为空，仅影响高亮）
    cn2field = _cn_to_field_mapping() if dataset_name == '总合同表' else {}
    field_map = {c: cn2field[c] for c in columns if c in cn2field}
    return {
        'dataset': dataset_name,
        'file': latest.get('file'),
        'uploaded_at': latest.get('uploaded_at'),
        'rows': latest.get('rows'),
        'column_count': len(columns),
        'columns': columns,
        'field_map': field_map,
        'mapped_count': len(field_map),
        'field_map_provider': _COLUMN_FIELD_CACHE.get('provider'),
        'groups': [{'name': g, 'columns': c} for g, c in _group_columns(columns)],
    }


def _load_ontos_spec():
    """动态加载 ontos 业务域 TBox。

    ontos 是 submodule，包位于 ``<repo>/ontos/ontos/``，故 sys.path 需指向
    submodule 根而非仓库根（否则会命中同名外层目录得到空命名空间包）。
    """
    if ONTOS_ROOT not in sys.path:
        sys.path.insert(0, ONTOS_ROOT)
    from ontos import domain_business as biz  # noqa: WPS433（延迟导入：submodule 可能未初始化）
    return biz.to_spec()


def _ontos_revision():
    """读取 submodule 当前 commit（便于页面显示"看到的是哪一版定义"）。"""
    gitdir = os.path.join(REPO_ROOT, '.git', 'modules', 'ontos')
    head_file = os.path.join(gitdir, 'HEAD')
    if not os.path.exists(head_file):
        return None
    try:
        with open(head_file, 'r', encoding='utf-8') as f:
            ref = f.read().strip()
        rev = None
        if ref.startswith('ref:'):
            ref_path = os.path.join(gitdir, ref.split(' ', 1)[1].strip())
            if os.path.exists(ref_path):
                with open(ref_path, 'r', encoding='utf-8') as f:
                    rev = f.read().strip()
        else:
            rev = ref
        return rev[:12] if rev else None
    except OSError:
        return None


# ─────────────────────────── 页面与静态资源 ───────────────────────────

@router.get('/ontos-topology')
def ontos_topology_page():
    """本体拓扑独立页（v4 业务域）。"""
    return FileResponse(os.path.join(FRONTEND_DIR, 'ontos-topology.html'))


@router.get('/ontos-topology.app.js')
def ontos_topology_app_js():
    return FileResponse(os.path.join(FRONTEND_DIR, 'ontos-topology.app.js'))


# ─────────────────────────── API ───────────────────────────

@router.get('/api/ontos/spec')
def api_ontos_spec():
    """v4 业务域 TBox（实时取自 ontos submodule）。

    每次请求重新执行 to_spec()，保证页面显示的就是代码里的定义。
    """
    try:
        spec = _load_ontos_spec()
    except ImportError as exc:
        return JSONResponse(status_code=503, content={
            'success': False,
            'error': 'ontos_unavailable',
            'message': f'无法导入 ontos（submodule 未初始化或未更新到含 domain_business 的版本）：{exc}',
            'hint': 'cd <repo>/ontos && git fetch <ontos主仓> main && git checkout <最新commit>',
        })
    except Exception as exc:  # pragma: no cover - 兜底，避免 500
        return JSONResponse(status_code=503, content={
            'success': False,
            'error': 'ontos_error',
            'message': f'ontos 加载失败：{exc}',
        })
    spec['success'] = True
    spec['meta'] = {
        'source': 'ontos.domain_business.to_spec()',
        'domain': 'business-v4',
        'ontos_revision': _ontos_revision(),
        'ontos_path': os.path.relpath(ONTOS_ROOT, REPO_ROOT),
    }
    return spec


@router.get('/api/ontos/columns')
def api_ontos_columns():
    """物理字段参考（总合同表 / 项目里程碑表 最新版本的列清单，按语义分组）。"""
    datasets = {}
    for name in ('总合同表', '项目里程碑表'):
        data = _read_dataset(name)
        if data:
            datasets[name] = data
    if not datasets:
        return JSONResponse(status_code=404, content={
            'success': False,
            'error': 'datasource_meta_missing',
            'message': f'未找到数据源元数据：{os.path.relpath(DATASOURCE_META, REPO_ROOT)}',
        })
    return {
        'success': True,
        'datasets': datasets,
        'entity_dataset': ENTITY_DATASET,
    }
