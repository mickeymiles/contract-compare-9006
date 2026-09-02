"""主数据域 core API：/api/core/*."""
import os
import tempfile
import json

from fastapi import APIRouter, Query, UploadFile, File
from fastapi.responses import JSONResponse

from core import project as core
from core.import_total_contract import read_total_contract_xlsx, upsert_total_contracts
from core import finance_import

router = APIRouter(prefix="", tags=["core-master"])


@router.post("/api/core/projects/import")
async def api_core_import_contracts(file: UploadFile = File(...)):
    """导入总合同表 Excel：按 TOTAL_CONTRACT_COLUMN_MAP 裁剪映射存 core_project。"""
    suffix = os.path.splitext(file.filename or '')[-1] or '.xlsx'
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        tmp.write(await file.read())
        tmp.close()
        rows = read_total_contract_xlsx(tmp.name)
        r = upsert_total_contracts(rows)
        if r.get('success'):
            # 主数据变更后清掉指标快照，强制下次访问重算（避免读到导入前的空快照）
            try:
                pm.invalidate_metric_snapshots()
            except Exception:
                pass
            return JSONResponse({
                'success': True, 'rows': len(rows),
                'imported': r.get('imported', 0), 'created': r.get('created', 0),
                'updated': r.get('updated', 0), 'errors': r.get('errors', 0),
            })
        return JSONResponse({'success': False, 'error': '导入失败'})
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e)})
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


@router.get("/api/core/projects")
def api_core_list_projects(keyword: str = ''):
    return JSONResponse({'success': True, 'data': core.list_projects(keyword=keyword)})


@router.post("/api/core/projects")
def api_core_create_project(body: dict):
    r = core.create_project(body)
    return JSONResponse(r, status_code=200 if r.get('success') else 409)


@router.get("/api/core/projects/{project_id}")
def api_core_get_project(project_id: int):
    p = core.get_project(project_id)
    if not p:
        return JSONResponse({'success': False, 'error': 'not found'}, status_code=404)
    return JSONResponse({'success': True, 'data': p})


@router.put("/api/core/projects/{project_id}")
def api_core_update_project(project_id: int, body: dict):
    r = core.update_project(project_id, body)
    return JSONResponse(r, status_code=200 if r.get('success') else 409)


@router.delete("/api/core/projects/{project_id}")
def api_core_delete_project(project_id: int):
    core.delete_project(project_id)
    return JSONResponse({'success': True})


# ── 财经 · 收款表/付款表（导入 + 列表，落 finance_detail）──
@router.post("/api/core/finance/import")
async def api_core_finance_import(kind: str = 'pay', file: UploadFile = File(...)):
    """导入收款/付款明细 Excel：kind=pay|recv，按 FINANCE_COLUMN_MAP 裁剪映射存 finance_detail。"""
    kind = 'recv' if kind == 'recv' else 'pay'
    suffix = os.path.splitext(file.filename or '')[-1] or '.xlsx'
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        tmp.write(await file.read())
        tmp.close()
        r = finance_import.import_finance_xlsx(tmp.name, kind)
        # 收付款明细变更后清掉资金相关指标快照，强制下次访问重算
        try:
            pm.invalidate_metric_snapshots()
        except Exception:
            pass
        return JSONResponse(r)
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e)})
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


@router.get("/api/core/finance")
def api_core_finance_list(kind: str = 'pay', keyword: str = ''):
    """查询收款/付款明细列表：GET /api/core/finance?kind=pay|recv&keyword=，按 occur_date 倒序。"""
    kind = 'recv' if kind == 'recv' else 'pay'
    return JSONResponse({'success': True, 'data': finance_import.list_finance(kind, keyword)})


# ── 财经分析（资金运作：回款周期 / 资金占用 / 毛利率）──
# 三个聚合指标均基于当前库真实数据计算（core_project 主数据、
# finance_detail 收付款明细、plm_milestone 里程碑），GET 轻量 JSON 供
# /finance-cycle、/finance-fund 独立页直接渲染。口径见 core.project_metrics。
#
# 快照缓存：每个指标的 GET 默认读 analysis_snapshots 快照（秒级，见
# pm.snapshot_get/snapshot_put，key='metrics:payment-cycle'|'fund'|'gross'），
# 响应附带 updated_at 与 from_cache；显式 ?refresh=1 才强制全量重算并更新快照。
from core.project_metrics import payment_cycle_all, fund_occupancy_all, gross_margin_all, cost_warning_all  # noqa: E402
from core import project_metrics as pm  # noqa: E402


def _snapshot_response(cache_key, compute_fn, refresh):
    """通用快照读写封装：读快照 → 命中直接返；?refresh=1 或未命中 → compute_fn() 重算并落库。"""
    def _wrap(result):
        result['updated_at'] = pm.snapshot_put(cache_key, result)
        result['from_cache'] = False
        return result
    if not refresh:
        cached = pm.snapshot_get(cache_key)
        if cached is not None:
            cached['payload']['updated_at'] = cached['updated_at']
            cached['payload']['from_cache'] = True
            return JSONResponse(cached['payload'])
    return JSONResponse(_wrap(compute_fn()))


@router.get("/api/core/metrics/payment-cycle")
def api_core_metrics_payment_cycle(refresh: int = Query(0)):
    """回款周期全量：主数据 sign_date + 里程碑回款时间点 → cycle_days；汇总来源/NaN。
    GET 默认读快照（秒级）；?refresh=1 强制全量重算并更新快照。
    同时返回旧门户 /api/analysis/payment-cycle 的富结构（months/icid/department/zones/
    enriched_rows/regions/province_stats），供独立页 1:1 复刻渲染。"""
    return _snapshot_response('metrics:payment-cycle', pm.payment_cycle_result_full, refresh)


@router.get("/api/core/metrics/fund")
def api_core_metrics_fund(cutoff: str = '', refresh: int = Query(0)):
    """资金占用全量富数据：finance_detail 按 project_no 归集（回落 contract_no）FIFO 冲抵，
    返回 summary/columns/rows(含片段数等全列)/flows/yoy，供独立页 1:1 复刻渲染。
    GET 默认读快照；?refresh=1 强制重算并更新快照。指定 cutoff（非默认节点）时直接现算不走快照。"""
    if cutoff:
        return JSONResponse(pm.fund_result_full(cutoff))
    return _snapshot_response('metrics:fund',
                              lambda: pm.fund_result_full(cutoff or None), refresh)


@router.get("/api/core/metrics/fund/dim")
def api_core_metrics_fund_dim(dim: str = 'region'):
    """资金占用维度聚合：region|province|customer_key|sign_year。"""
    return JSONResponse(pm.fund_dim_aggregate(dim))


@router.get("/api/core/metrics/fund/drill")
def api_core_metrics_fund_drill(dim: str = 'region', value: str = ''):
    """维度穿透下钻：返回该维度桶下的合同清单。"""
    return JSONResponse(pm.fund_dim_drill(dim, value))


@router.get("/api/core/metrics/fund/risk/list")
def api_core_metrics_fund_risk_list():
    """预警清单 + 风险等级统计。"""
    return JSONResponse(pm.fund_risk_list())


@router.get("/api/core/metrics/fund/risk/trend")
def api_core_metrics_fund_risk_trend(dim: str = 'region'):
    """维度趋势预警。"""
    return JSONResponse(pm.fund_risk_trend(dim))


@router.get("/api/core/metrics/fund/risk/config")
def api_core_metrics_fund_risk_config():
    """读取风险阈值配置。"""
    cfg = pm._risk_config()
    return JSONResponse({'success': True, 'config': [{'key': k, 'value': v} for k, v in cfg.items()]})


@router.post("/api/core/metrics/fund/risk/config")
async def api_core_metrics_fund_risk_config_set(body: dict = None):
    """保存风险阈值配置（对齐旧门户「保存并重算」）。"""
    body = body or {}
    return JSONResponse(pm.save_risk_config(body))


@router.get("/api/core/metrics/fund/segments")
def api_core_metrics_fund_segments(key: str = ''):
    """资金占用详情：该归集键的 垫资片段 / 收付流水 / 现金流 / 本地汇总。"""
    if not key:
        return JSONResponse({'success': False, 'error': 'key 必填'})
    return JSONResponse(pm.fund_segments_detail(key))


@router.get("/api/core/metrics/fund-flows")
def api_core_metrics_fund_flows(key: str = ''):
    """逐笔收付流水：按归集键(project_no 优先回落 contract_no)返回该键的付款/收款明细。"""
    if not key:
        return JSONResponse({'success': False, 'error': 'key 必填'})
    from core.project_metrics import get_finance_detail
    d = get_finance_detail(key)

    def _fmt(x):
        dt = x.get('occur_date') or x.get('date') or ''
        if hasattr(dt, 'isoformat'):
            dt = dt.isoformat()
        return {'date': dt, 'amount': x.get('amount') or 0}

    return JSONResponse({'success': True, 'data': {
        'key': key,
        'pay': [_fmt(x) for x in (d.get('pay') or [])],
        'recv': [_fmt(x) for x in (d.get('recv') or [])],
    }})


@router.get("/api/core/metrics/gross")
def api_core_metrics_gross(refresh: int = Query(0)):
    """毛利率全量：主数据 sign_gross_profit / sign_amount 计算（缺省回退 gross_rate）。
    GET 默认读快照；?refresh=1 强制全量重算并更新快照。"""
    return _snapshot_response('metrics:gross',
                              lambda: {'success': True, 'data': gross_margin_all()}, refresh)


@router.get("/api/core/metrics/cost-warning")
def api_core_metrics_cost_warning(refresh: int = Query(0)):
    """成本预警全量：概算/预算（plm_baseline 四算）+ 当前成本（finance_detail 累计付款），
    计算 剩余成本/预算完成比/预警状态。GET 默认读快照；?refresh=1 强制全量重算并更新快照。"""
    return _snapshot_response('metrics:cost-warning',
                              lambda: {'success': True, 'data': cost_warning_all()}, refresh)


# ── Ops 运维域 · 项目联系人/地址 ─────────────────────────
@router.get("/api/core/ops-contacts")
def api_core_list_ops(project_id: int = Query(0)):
    pid = project_id or None
    return JSONResponse({'success': True, 'data': core.list_ops_contacts(pid)})


@router.post("/api/core/ops-contacts")
def api_core_create_ops(body: dict):
    pid = body.get('project_id')
    if not pid:
        return JSONResponse({'success': False, 'error': 'project_id 必填'}, status_code=400)
    r = core.create_ops_contact(pid, body)
    return JSONResponse(r, status_code=200 if r.get('success') else 409)


@router.delete("/api/core/ops-contacts/{contact_id}")
def api_core_delete_ops(contact_id: int):
    core.delete_ops_contact(contact_id)
    return JSONResponse({'success': True})