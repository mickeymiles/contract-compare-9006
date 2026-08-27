"""采购域 · 合同硬件对比 contrast (R2 split from main.py)."""
from typing import Optional, Any, List, Dict, Union
import io, os, json, re, shutil
from datetime import datetime, date
from fastapi import APIRouter, Query, File, UploadFile, Form, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse, Response
from common.paths import UPLOAD_DIR, FRONTEND_DIR, DATASOURCE_DIR, BASE_DIR
from models import get_db, create_contract, delete_contract, update_contract_status
from compare_engine import run_comparison
from excel_handler import import_contract_excel, import_supplier_excel, export_report, reapply_column_mapping

router = APIRouter(prefix="", tags=["procurement-contrast"])

@router.get("/api/contracts")
def list_contracts_legacy(keyword: str = Query(None), status: str = Query(None)):
    """全部合同列表（首页）——【旧合同管理】Python 函数加 _legacy 避免与 procurement_models 导入的同名函数冲突"""
    conn = get_db()
    where = ["1=1"]
    params = []
    if keyword:
        where.append("(contract_name LIKE ? OR contract_no LIKE ?)")
        params.extend([f"%{keyword}%", f"%{keyword}%"])
    if status and status != '全部':
        where.append("status = ?")
        params.append(status)

    contracts = [dict(r) for r in conn.execute(
        f"""SELECT c.*, COALESCE(v.progress, 0) as progress, COALESCE(v.supplier_name, '') as latest_supplier,
                   (SELECT COUNT(DISTINCT supplier_name) FROM versions WHERE contract_id = c.id AND supplier_name != '') as supplier_count
            FROM contracts c
            LEFT JOIN (
                SELECT contract_id, MAX(id) as max_id FROM versions GROUP BY contract_id
            ) latest ON c.id = latest.contract_id
            LEFT JOIN versions v ON v.id = latest.max_id
            WHERE {' AND '.join(where)}
            ORDER BY c.id DESC""", params
    ).fetchall()]

    # 统计
    stats = {
        'total': conn.execute("SELECT COUNT(*) FROM contracts").fetchone()[0],
        'closed': conn.execute("SELECT COUNT(*) FROM contracts WHERE status = '已闭环(100%)'").fetchone()[0],
        'active': conn.execute("SELECT COUNT(*) FROM contracts WHERE status != '已闭环(100%)' AND status != '未上传基准'").fetchone()[0],
        'total_amount': conn.execute("SELECT COALESCE(SUM(total_amount), 0) FROM contracts").fetchone()[0],
    }
    conn.close()
    return JSONResponse({'contracts': contracts, 'stats': stats})

@router.post("/api/contracts")
async def create_new_contract(name: str = Query(...), no: str = Query(''), sign_date: str = Query('')):
    """CC-001 FR-1 新建合同（合同比对域）。create_contract 现为 models.py 的实现。"""
    if not (name or '').strip():
        return JSONResponse({'success': False, 'error': '合同名称不能为空'}, status_code=400)
    cid = create_contract(name.strip(), no or '', sign_date or '')
    return JSONResponse({'success': True, 'contract_id': cid})

@router.put("/api/contracts/{contract_id}")
async def update_contract_legacy(contract_id: int):
    """更新合同元信息（通过form data）- 函数加 _legacy 避免与采购模块同名冲突"""
    # Simple update via query params for now
    return JSONResponse({'success': True})

@router.delete("/api/contracts/{contract_id}")
def remove_contract(contract_id: int):
    """CC-001 FR-3 删除合同并级联清理（合同比对域）。"""
    delete_contract(contract_id)
    return JSONResponse({'success': True})

@router.post("/api/contract/{contract_id}/upload")
async def upload_contract(contract_id: int, file: UploadFile = File(...)):
    filepath = os.path.join(UPLOAD_DIR, f'contract_{contract_id}_基准.xlsx')
    with open(filepath, 'wb') as f:
        shutil.copyfileobj(file.file, f)
    try:
        result = import_contract_excel(contract_id, filepath)
        # 更新合同总金额
        conn = get_db()
        total = conn.execute(
            "SELECT COALESCE(SUM(contract_amount), 0) FROM contract_items WHERE contract_id = ?",
            (contract_id,)
        ).fetchone()[0]
        conn.execute("UPDATE contracts SET total_amount = ?, status = '比对进行中' WHERE id = ?",
                     (total, contract_id))
        conn.commit(); conn.close()
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e)}, status_code=400)

@router.get("/api/contract/{contract_id}/items")
def list_contract_items(contract_id: int):
    conn = get_db()
    items = [dict(r) for r in conn.execute(
        "SELECT * FROM contract_items WHERE contract_id = ? ORDER BY id", (contract_id,)
    ).fetchall()]
    all_headers = []
    for item in items:
        try:
            raw = json.loads(item.get('raw_columns', '{}'))
            for k in raw:
                if k not in all_headers: all_headers.append(k)
        except: pass
    conn.close()
    return JSONResponse({'items': items, 'total': len(items), 'headers': all_headers})

@router.post("/api/contract/{contract_id}/supplier/upload")
async def upload_supplier(contract_id: int, file: UploadFile = File(...),
                          supplier_name: str = Query('')):
    if not supplier_name.strip():
        return JSONResponse({'success': False, 'error': '请填写供应商名称'}, status_code=400)
    filepath = os.path.join(UPLOAD_DIR, f'supplier_{contract_id}_{supplier_name}_{file.filename}')
    with open(filepath, 'wb') as f:
        shutil.copyfileobj(file.file, f)
    try:
        result = import_supplier_excel(contract_id, filepath, supplier_name.strip())
        update_contract_status(contract_id)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e)}, status_code=400)

@router.get("/api/contract/{contract_id}/supplier/versions")
def list_versions(contract_id: int, supplier_name: str = Query(None)):
    """版本列表，可按供应商筛选"""
    conn = get_db()
    where = "contract_id = ?"
    params = [contract_id]
    if supplier_name:
        where += " AND supplier_name = ?"
        params.append(supplier_name)
    versions = [dict(r) for r in conn.execute(
        f"SELECT * FROM versions WHERE {where} ORDER BY id DESC", params
    ).fetchall()]

    # 该合同下有哪些供应商
    suppliers = [dict(r) for r in conn.execute(
        "SELECT supplier_name, COUNT(*) as version_count, MAX(id) as latest_id FROM versions WHERE contract_id = ? AND supplier_name != '' GROUP BY supplier_name ORDER BY latest_id DESC",
        (contract_id,)
    ).fetchall()]
    conn.close()
    return JSONResponse({'versions': versions, 'suppliers': suppliers})

@router.get("/api/contract/{contract_id}/supplier/items")
def list_supplier_items(contract_id: int, version_id: int = Query(...)):
    conn = get_db()
    items = [dict(r) for r in conn.execute(
        "SELECT * FROM supplier_items WHERE contract_id = ? AND version_id = ? ORDER BY id",
        (contract_id, version_id)
    ).fetchall()]
    # 提取供应商全部原始列名（保持顺序，不删减）
    all_headers = []
    for item in items:
        try:
            raw = json.loads(item.get('raw_columns', '{}'))
            for k in raw:
                if k not in all_headers:
                    all_headers.append(k)
        except Exception:
            pass
    conn.close()
    return JSONResponse({'items': items, 'total': len(items), 'headers': all_headers})

@router.delete("/api/contract/{contract_id}/supplier/versions/{version_id}")
def delete_version(contract_id: int, version_id: int):
    """删除供应商版本，级联删除 comparison_results 和 supplier_items"""
    conn = get_db()
    c = conn.cursor()

    # 获取版本信息用于后续处理
    v = c.execute(
        "SELECT supplier_name FROM versions WHERE id = ? AND contract_id = ?",
        (version_id, contract_id)
    ).fetchone()
    if not v:
        conn.close()
        return JSONResponse({'success': False, 'error': '版本不存在'}, status_code=404)

    supplier_name = v['supplier_name']

    # 级联删除
    c.execute("DELETE FROM comparison_results WHERE version_id = ?", (version_id,))
    c.execute("DELETE FROM supplier_items WHERE version_id = ?", (version_id,))
    c.execute("DELETE FROM versions WHERE id = ?", (version_id,))

    # 如果该供应商还有其他版本，让最新的一个变活跃
    if supplier_name:
        latest = c.execute("""
            SELECT id FROM versions
            WHERE contract_id = ? AND supplier_name = ?
            ORDER BY id DESC LIMIT 1
        """, (contract_id, supplier_name)).fetchone()
        if latest:
            c.execute("UPDATE versions SET is_active = 1 WHERE id = ?", (latest[0],))

    conn.commit()
    conn.close()

    update_contract_status(contract_id)
    return JSONResponse({'success': True})

@router.post("/api/contract/{contract_id}/compare/run")
def run_compare(contract_id: int, version_id: int = Query(...)):
    try:
        result = run_comparison(contract_id, version_id)
        update_contract_status(contract_id)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e)}, status_code=400)

@router.get("/api/contract/{contract_id}/compare/results")
def get_results(contract_id: int, version_id: int = Query(None),
                status: str = Query(None), keyword: str = Query(None)):
    conn = get_db()
    where = ["r.contract_id = ?"]
    params = [contract_id]

    if version_id:
        where.append("r.version_id = ?"); params.append(version_id)
    else:
        latest = conn.execute(
            "SELECT MAX(id) FROM versions WHERE contract_id = ?", (contract_id,)
        ).fetchone()[0]
        if latest:
            where.append("r.version_id = ?"); params.append(latest)

    if status and status != '全部':
        where.append("r.match_status = ?"); params.append(status)

    query = f"""
        SELECT r.*, ct.device_name as ct_name, ct.device_model as ct_model,
            ct.specs_full as ct_specs, ct.contract_qty, ct.contract_unit,
            ct.raw_columns as ct_raw,
            sp.device_name as sp_name, sp.device_model as sp_model,
            sp.specs_full as sp_specs, sp.quote_qty, sp.quote_unit,
            sp.raw_columns as sp_raw
        FROM comparison_results r
        LEFT JOIN contract_items ct ON r.contract_item_id = ct.id
        LEFT JOIN supplier_items sp ON r.supplier_item_id = sp.id
        WHERE {' AND '.join(where)} ORDER BY r.match_status, ct.device_name
    """
    results = [dict(r) for r in conn.execute(query, params).fetchall()]

    # 收集合同和供应商的原始列名（取第一个有数据的）
    ct_headers = []
    sp_headers_raw = []
    for r in results:
        if not ct_headers and r.get('ct_raw'):
            try: ct_headers = list(json.loads(r['ct_raw']).keys())
            except: pass
        if not sp_headers_raw and r.get('sp_raw'):
            try: sp_headers_raw = list(json.loads(r['sp_raw']).keys())
            except: pass
        if ct_headers and sp_headers_raw: break

    # 供应商列保留全部原始列，不删减
    sp_headers = sp_headers_raw
    conn.close()

    if keyword:
        kw = keyword.lower()
        results = [r for r in results if kw in str(r.get('ct_name','')).lower()
                   or kw in str(r.get('ct_model','')).lower()
                   or kw in str(r.get('sp_name','')).lower()
                   or kw in str(r.get('anomaly_detail','')).lower()]

    for r in results:
        try: r['anomaly_types_list'] = json.loads(r.get('anomaly_types', '[]'))
        except: r['anomaly_types_list'] = []

    return JSONResponse({'results': results, 'total': len(results), 'ct_headers': ct_headers, 'sp_headers': sp_headers})

@router.get("/api/contract/{contract_id}/column-mapping")
def get_column_mapping(contract_id: int, version_id: int = Query(None)):
    """返回主合同列 ↔ 供应商列 的对齐关系"""
    conn = get_db()
    if not version_id:
        latest = conn.execute("SELECT MAX(id) FROM versions WHERE contract_id=?", (contract_id,)).fetchone()[0]
        version_id = latest
    row = conn.execute("SELECT column_mapping FROM versions WHERE id=?", (version_id,)).fetchone()
    conn.close()
    if row and row['column_mapping']:
        try:
            cm = json.loads(row['column_mapping'])
            cm['version_id'] = version_id
            return JSONResponse(cm)
        except Exception:
            pass
    return JSONResponse({'version_id': version_id})

@router.post("/api/contract/{contract_id}/column-mapping")
async def save_column_mapping(contract_id: int, request: Request):
    """保存手动调整的列对齐，重提供应商数据并重新比对"""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({'success': False, 'error': '请求体不是合法 JSON'}, status_code=400)
    version_id = body.get('version_id')
    mapping = body.get('mapping', {})
    if not version_id:
        return JSONResponse({'success': False, 'error': '缺少 version_id'}, status_code=400)

    conn = get_db()
    c = conn.cursor()
    row = c.execute("SELECT column_mapping FROM versions WHERE id=?", (version_id,)).fetchone()
    if not row:
        conn.close()
        return JSONResponse({'success': False, 'error': '版本不存在'}, status_code=404)
    try:
        cm = json.loads(row['column_mapping'] or '{}')
    except Exception:
        cm = {}
    cm['mapping'] = mapping
    c.execute("UPDATE versions SET column_mapping=? WHERE id=?",
              (json.dumps(cm, ensure_ascii=False), version_id))
    conn.commit()
    conn.close()

    try:
        result = reapply_column_mapping(contract_id, version_id, mapping, cm.get('contract_semantics', {}))
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e)}, status_code=400)
    update_contract_status(contract_id)
    result['column_mapping'] = cm
    return JSONResponse(result)

@router.post("/api/compare/{result_id}/confirm")
def confirm_result(result_id: int, confirmed: int = Query(1)):
    """手动确认：判断符合/匹配异常 → 确认后变为匹配成功；取消确认恢复原状态"""
    conn = get_db()
    c = conn.cursor()
    # 获取当前状态
    cur = dict(c.execute("SELECT * FROM comparison_results WHERE id = ?", (result_id,)).fetchone())
    original_status = cur['match_status']
    
    if confirmed:
        # 确认：判断符合/匹配异常 → 匹配成功
        if original_status in ('判断符合', '匹配异常'):
            c.execute("UPDATE comparison_results SET confirmed = 1, match_status = '匹配成功' WHERE id = ?",
                      (result_id,))
    else:
        # 取消确认：匹配成功 → 恢复原状态
        # 通过 match_note 推断原状态：有推理过程说明曾是判断符合，否则是匹配异常
        if cur.get('match_note', ''):
            c.execute("UPDATE comparison_results SET confirmed = 0, match_status = '判断符合' WHERE id = ?",
                      (result_id,))
        else:
            c.execute("UPDATE comparison_results SET confirmed = 0, match_status = '匹配异常' WHERE id = ?",
                      (result_id,))
    
    # 同步更新版本统计
    r = dict(c.execute("SELECT * FROM comparison_results WHERE id = ?", (result_id,)).fetchone())
    conn.commit()
    
    vid = r['version_id']
    stats = c.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN match_status='匹配成功' THEN 1 ELSE 0 END) as matched,
            SUM(CASE WHEN match_status='判断符合' THEN 1 ELSE 0 END) as judged,
            SUM(CASE WHEN match_status='匹配异常' THEN 1 ELSE 0 END) as anomaly,
            SUM(CASE WHEN match_status='待采购' THEN 1 ELSE 0 END) as pending,
            SUM(CASE WHEN match_status='供应商增项' THEN 1 ELSE 0 END) as extra
        FROM comparison_results WHERE version_id = ?
    """, (vid,)).fetchone()
    contract_total = c.execute(
        "SELECT COUNT(*) FROM contract_items WHERE contract_id = ?", (r['contract_id'],)
    ).fetchone()[0]
    # 进度 = 匹配成功（含已确认的判断符合/异常）/ 合同总条目
    progress = round((stats['matched'] / max(contract_total, 1) * 100), 2)
    c.execute("UPDATE versions SET matched_count=?, judged_count=?, anomaly_count=?, pending_count=?, extra_count=?, progress=? WHERE id=?",
              (stats['matched'] or 0, stats['judged'] or 0, stats['anomaly'] or 0, stats['pending'] or 0, stats['extra'] or 0, progress, vid))
    conn.commit()
    conn.close()
    update_contract_status(r['contract_id'])
    return JSONResponse({'success': True, 'confirmed': bool(confirmed)})

@router.get("/api/contract/{contract_id}/stats")
def get_contract_stats(contract_id: int):
    conn = get_db()
    ct_count = conn.execute(
        "SELECT COUNT(*) FROM contract_items WHERE contract_id = ?", (contract_id,)
    ).fetchone()[0]
    ct_amount = conn.execute(
        "SELECT COALESCE(SUM(contract_amount), 0) FROM contract_items WHERE contract_id = ?",
        (contract_id,)
    ).fetchone()[0]

    stats = {'contract_total': ct_count, 'contract_amount': ct_amount}
    latest = conn.execute(
        "SELECT MAX(id) FROM versions WHERE contract_id = ?", (contract_id,)
    ).fetchone()[0]
    if latest:
        v = dict(conn.execute("SELECT * FROM versions WHERE id = ?", (latest,)).fetchone())
        stats.update({
            'version_id': v['id'], 'matched_count': v['matched_count'],
            'judged_count': v.get('judged_count', 0),
            'anomaly_count': v['anomaly_count'], 'pending_count': v['pending_count'],
            'extra_count': v['extra_count'], 'progress': v['progress'],
        })

    versions = [dict(r) for r in conn.execute(
        "SELECT id, progress FROM versions WHERE contract_id = ? ORDER BY id", (contract_id,)
    ).fetchall()]
    conn.close()
    return JSONResponse({'stats': stats, 'versions': versions})

@router.get("/api/contract/{contract_id}/export/report")
def download_report(contract_id: int, version_id: int = Query(...)):
    try:
        filepath = export_report(version_id)
        return FileResponse(filepath,
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            filename=os.path.basename(filepath))
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e)}, status_code=400)
