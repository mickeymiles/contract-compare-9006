"""
合同比对系统 — FastAPI 主应用（多合同版）
端口: 9006
"""

from fastapi import FastAPI, UploadFile, File, Query, Form, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
import os, json, shutil, re, io, urllib.parse

from models import init_db, get_db, clear_contract, create_contract, delete_contract, update_contract_status
from compare_engine import run_comparison
from excel_handler import import_contract_excel, import_supplier_excel, export_report, reapply_column_mapping
from chat_handler import handle_user_message, get_messages, register_sse_listener, unregister_sse_listener

app = FastAPI(title="合同比对系统（多合同版）", version="2.0")
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, '..', 'uploads')
FRONTEND_DIR = os.path.join(BASE_DIR, '..', 'frontend')
DATASOURCE_DIR = os.path.join(BASE_DIR, '..', 'datasource')
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(DATASOURCE_DIR, exist_ok=True)

# 数据源版本元数据文件
DS_META_FILE = os.path.join(DATASOURCE_DIR, 'versions.json')

def _load_ds_meta():
    if os.path.exists(DS_META_FILE):
        with open(DS_META_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def _save_ds_meta(meta):
    with open(DS_META_FILE, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

def _ensure_table(meta, table_name):
    if table_name not in meta:
        meta[table_name] = {'versions': [], 'next_id': 1}
    return meta[table_name]


# ===================== 数据源 API =====================

@app.get("/api/datasource/tables")
def datasource_tables():
    """列出所有数据表及其最新版本摘要"""
    meta = _load_ds_meta()
    tables = []
    for tname, tdata in meta.items():
        vers = tdata.get('versions', [])
        latest = vers[0] if vers else None
        tables.append({
            'name': tname,
            'version_count': len(vers),
            'latest_id': latest['id'] if latest else None,
            'latest_time': latest['upload_time'] if latest else None,
            'latest_rows': latest['row_count'] if latest else 0,
            'latest_columns': latest['columns'] if latest else [],
        })
    return {'tables': tables}


@app.post("/api/datasource/upload")
async def datasource_upload(file: UploadFile = File(...), table_name: str = Query(...)):
    """上传原始数据表（Excel），按表名隔离版本"""
    if not file.filename.endswith(('.xlsx', '.xls')):
        return JSONResponse({'success': False, 'error': '仅支持 .xlsx / .xls 文件'})
    meta = _load_ds_meta()
    tdata = _ensure_table(meta, table_name)
    vid = tdata['next_id']
    fname = f'{table_name}_v{vid}.xlsx'
    fpath = os.path.join(DATASOURCE_DIR, fname)
    content = await file.read()
    with open(fpath, 'wb') as f:
        f.write(content)
    import openpyxl
    wb = openpyxl.load_workbook(fpath, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    headers = [str(h) for h in rows[0]] if rows else []
    row_count = len(rows) - 1
    wb.close()
    from datetime import datetime
    ver = {
        'id': vid,
        'filename': file.filename,
        'upload_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'row_count': row_count,
        'columns': headers,
        'file': fname,
    }
    tdata['versions'].insert(0, ver)
    tdata['next_id'] = vid + 1
    _save_ds_meta(meta)
    return {'success': True, 'version': ver, 'table_name': table_name}


@app.get("/api/datasource/versions")
def datasource_versions(table_name: str = Query(...)):
    """获取指定表的所有版本"""
    meta = _load_ds_meta()
    tdata = meta.get(table_name, {})
    vers = tdata.get('versions', [])
    return {'table_name': table_name, 'versions': vers, 'latest_id': vers[0]['id'] if vers else None}


@app.get("/api/datasource/latest")
def datasource_latest(table_name: str = Query(...)):
    """获取指定表最新版本的数据预览"""
    meta = _load_ds_meta()
    tdata = meta.get(table_name, {})
    vers = tdata.get('versions', [])
    if not vers:
        return {'version': None, 'headers': [], 'rows': [], 'row_count': 0}
    latest = vers[0]
    fpath = os.path.join(DATASOURCE_DIR, latest['file'])
    if not os.path.exists(fpath):
        return {'version': latest, 'headers': [], 'rows': [], 'row_count': 0, 'error': '文件丢失'}
    import openpyxl
    wb = openpyxl.load_workbook(fpath, read_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    headers = [str(h) for h in next(rows_iter, [])]
    preview_rows = []
    for i, row in enumerate(rows_iter):
        if i >= 20:
            break
        preview_rows.append([str(v) if v is not None else '' for v in row])
    wb.close()
    return {'version': latest, 'headers': headers, 'rows': preview_rows, 'row_count': latest['row_count']}


@app.delete("/api/datasource/version/{table_name}/{version_id}")
def datasource_delete_version(table_name: str, version_id: int):
    """删除指定表的指定版本"""
    meta = _load_ds_meta()
    tdata = meta.get(table_name)
    if not tdata:
        return JSONResponse({'success': False, 'error': '表不存在'}, status_code=404)
    target = None
    for v in tdata.get('versions', []):
        if v['id'] == version_id:
            target = v
            break
    if not target:
        return JSONResponse({'success': False, 'error': '版本不存在'}, status_code=404)
    fpath = os.path.join(DATASOURCE_DIR, target['file'])
    if os.path.exists(fpath):
        os.remove(fpath)
    tdata['versions'] = [v for v in tdata['versions'] if v['id'] != version_id]
    if not tdata['versions']:
        del meta[table_name]
    _save_ds_meta(meta)
    return {'success': True}


# ===================== 回款周期分析 API =====================

@app.get("/api/analysis/payment-cycle")
def analysis_payment_cycle():
    """回款周期分析：H表∪R表补充→按月累计计算"""
    import openpyxl
    from datetime import datetime, date
    meta = _load_ds_meta()
    
    # 读取 H 表（总合同表）
    htdata = meta.get('总合同表', {})
    hvers = htdata.get('versions', [])
    if not hvers:
        return {'success': True, 'data': {'source_version': 0, 'months': [], 'icid': {}, 'department': {}, 'zones': [], 'enriched_rows': []}}
    
    hfpath = os.path.join(DATASOURCE_DIR, hvers[0]['file'])
    if not os.path.exists(hfpath):
        return {'success': False, 'error': '总合同表文件丢失'}
    wb = openpyxl.load_workbook(hfpath, read_only=True)
    ws = wb.active
    hrows = list(ws.iter_rows(values_only=True))
    wb.close()
    h_headers = [str(h) if h else '' for h in hrows[0]]
    h_data = []
    for r in hrows[1:]:
        row = {}
        for i, h in enumerate(h_headers):
            row[h] = r[i] if i < len(r) else None
        h_data.append(row)
    
    # 工具函数
    def parse_date(v):
        if v is None or v == '' or v == '-': return None
        if isinstance(v, (datetime, date)): return v
        s = str(v).strip()
        if s.startswith('='): return None
        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d', '%Y%m%d']:
            try: return datetime.strptime(s, fmt)
            except: pass
        return None
    
    def safe_float(v):
        if v is None or v == '' or v == '-': return 0
        s = str(v).strip()
        if s.startswith('='): return 0
        try: return float(v)
        except: return 0
    
    def safe_str(v):
        if v is None: return ''
        s = str(v).strip()
        return '' if s.startswith('=') else s
    
    # 列名匹配
    def find_col(headers, keywords):
        for h in headers:
            hl = h.lower().replace(' ', '').replace('_', '').replace('-', '')
            for kw in keywords:
                if kw.lower().replace(' ', '').replace('_', '').replace('-', '') in hl:
                    return h
        return None
    
    h_col_no = find_col(h_headers, ['合同编号', '编号'])
    h_col_date = find_col(h_headers, ['统计日期', '签约日期', '日期'])
    h_col_dept = find_col(h_headers, ['部门', '责任部门'])
    # 修正：'部门' 可能被 '签定部门' 抢先匹配，确认真实的部门列
    if h_col_dept and '签定' in str(h_col_dept):
        for h in h_headers:
            if h == '部门':
                h_col_dept = h
                break
    h_col_amount = find_col(h_headers, ['合同金额', '金额', '合同额', '合同总金额'])
    h_col_region = find_col(h_headers, ['区域', '大区', '片区'])
    # 省份列：优先精确匹配“省”（避免被“省分”抢占）
    h_col_province = None
    for h in h_headers:
        if str(h).strip() in ('省', '省份'):
            h_col_province = h
            break
    if h_col_province is None:
        h_col_province = find_col(h_headers, ['省份'])
    
    # 读取 R 表（项目里程碑表），按合同编号建索引
    rtdata = meta.get('项目里程碑表', {})
    rvers = rtdata.get('versions', [])
    r_index = {}  # 合同编号 → [里程碑行列表]
    if rvers:
        rfpath = os.path.join(DATASOURCE_DIR, rvers[0]['file'])
        if os.path.exists(rfpath):
            wb = openpyxl.load_workbook(rfpath, read_only=True)
            ws = wb.active
            rrows = list(ws.iter_rows(values_only=True))
            wb.close()
            r_headers = [str(h) if h else '' for h in rrows[0]]
            r_col_contract = find_col(r_headers, ['合同编号'])
            for r in rrows[1:]:
                row = {}
                for i, h in enumerate(r_headers):
                    row[h] = r[i] if i < len(r) else None
                cid = str(row.get(r_col_contract, '')).strip() if r_col_contract else ''
                if cid:
                    r_index.setdefault(cid, []).append(row)
    
    # 通用：为指定年份的H表行补充回款周期数据
    def enrich_for_year(h_rows, target_year):
        """返回 enriched 列表"""
        result = []
        for row in h_rows:
            cno = safe_str(row.get(h_col_no, ''))
            sdate = parse_date(row.get(h_col_date))
            dept = safe_str(row.get(h_col_dept, ''))
            region = safe_str(row.get(h_col_region, '')) if h_col_region else ''
            province = safe_str(row.get(h_col_province, '')) if h_col_province else ''
            amount = safe_float(row.get(h_col_amount)) if h_col_amount else 0
            
            if not sdate or sdate.year != target_year:
                continue
            
            matches = r_index.get(cno, [])
            valid = []
            for m in matches:
                pdate = parse_date(m.get('计划回款时间'))
                pval = safe_float(m.get('计划产值(元)'))
                if pdate and pval != 0:
                    valid.append((pdate, pval, m))
            valid.sort(key=lambda x: x[0], reverse=True)
            
            last_payback = valid[0][0] if valid else None
            cycle_days = (last_payback - sdate).days if last_payback and sdate else 0
            years = round(cycle_days / 365, 4) if cycle_days else 0
            
            if years < 0.5: zone = '0.5以内'
            elif years < 1: zone = '0.5-1年'
            elif years < 2: zone = '1年以上'
            elif years < 3: zone = '2年以上'
            else: zone = '3年以上'
            
            result.append({
                'contract_no': cno,
                'sign_date': sdate.strftime('%Y-%m-%d') if sdate else '',
                'dept': dept,
                'region': region,
                'province': province,
                'amount': amount,
                'last_payback_date': last_payback.strftime('%Y-%m-%d') if last_payback else '',
                'cycle_days': cycle_days,
                'years': years,
                'zone': zone,
            })
        return result
    
    enriched_2026 = enrich_for_year(h_data, 2026)
    enriched_2025 = enrich_for_year(h_data, 2025)
    
    # 区域聚合（2026全年）— 含平均周期 / 有回款 / 无回款 / 金额
    region_stats = {}
    for r in enriched_2026:
        reg = r.get('region', '') or '未知'
        if reg not in region_stats:
            region_stats[reg] = {'count': 0, 'total_days': 0, 'with_payment': 0, 'no_payment': 0, 'total_amount': 0.0}
        cd = r.get('cycle_days', 0) or 0
        amt = r.get('amount', 0) or 0
        region_stats[reg]['count'] += 1
        region_stats[reg]['total_days'] += cd
        region_stats[reg]['total_amount'] += amt
        if cd > 0:
            region_stats[reg]['with_payment'] += 1
        else:
            region_stats[reg]['no_payment'] += 1
    region_agg = [{'region': k, 'count': v['count'], 'avg_days': round(v['total_days']/v['count']) if v['count']>0 else 0,
                   'with_payment': v['with_payment'], 'no_payment': v['no_payment'],
                   'amount': round(v['total_amount'])} 
                  for k, v in sorted(region_stats.items(), key=lambda x: -x[1]['count'])]

    # 省份聚合（2026全年）— 供省份着色地图
    prov_stats = {}
    for r in enriched_2026:
        pv = r.get('province', '') or '未知'
        if pv not in prov_stats:
            prov_stats[pv] = {'count': 0, 'total_days': 0, 'with_payment': 0, 'no_payment': 0, 'total_amount': 0.0}
        cd = r.get('cycle_days', 0) or 0
        amt = r.get('amount', 0) or 0
        prov_stats[pv]['count'] += 1
        prov_stats[pv]['total_days'] += cd
        prov_stats[pv]['total_amount'] += amt
        if cd > 0:
            prov_stats[pv]['with_payment'] += 1
        else:
            prov_stats[pv]['no_payment'] += 1
    province_agg = [{'province': k, 'count': v['count'], 'avg_days': round(v['total_days']/v['count']) if v['count']>0 else 0,
                     'with_payment': v['with_payment'], 'no_payment': v['no_payment'],
                     'amount': round(v['total_amount'])} 
                    for k, v in sorted(prov_stats.items(), key=lambda x: -x[1]['count'])]
    
    # 按月累计计算（6-8月）
    target_months = [(2026, 6), (2026, 7), (2026, 8)]
    
    def calc_metrics(rows, y, m):
        count = len(rows)
        total_amount = sum(r['amount'] for r in rows)
        total_cycle = sum(r['cycle_days'] for r in rows)
        avg_cycle = round(total_cycle / count, 1) if count > 0 else 0
        avg_years = round(avg_cycle / 365, 2) if avg_cycle > 0 else 0
        zones = [0, 0, 0, 0, 0]
        for r in rows:
            yrs = r['years']
            if yrs <= 0: continue
            if yrs < 0.5: zones[0] += 1
            elif yrs < 1: zones[1] += 1
            elif yrs < 2: zones[2] += 1
            elif yrs < 3: zones[3] += 1
            else: zones[4] += 1
        return {'project_count': count, 'contract_amount': round(total_amount/10000,2), 'cumulative_days': total_cycle, 'avg_days': avg_cycle, 'avg_years': avg_years, 'zones': zones}
    
    def in_month(r, yr, mo):
        if not r['sign_date']: return False
        try:
            sd = datetime.strptime(r['sign_date'], '%Y-%m-%d')
            return sd.year < yr or (sd.year == yr and sd.month <= mo)
        except: return False
    
    def filter_rows(enriched, year, month):
        return [r for r in enriched if in_month(r, year, month)]
    
    months_result = []
    icid_result = {'project_count': {}, 'cumulative_days': {}, 'avg_days': {}, 'avg_years': {}, 'contract_amount': {}}
    dept_result = {'project_count': {}, 'cumulative_days': {}, 'avg_days': {}, 'avg_years': {}, 'contract_amount': {}}
    zones_result = []
    
    for y, m in target_months:
        m_key = f'{y}-{m:02d}'
        py = 2025  # previous year
        
        cur_rows = filter_rows(enriched_2026, y, m)
        prev_rows = filter_rows(enriched_2025, py, m)
        
        cur_icid = calc_metrics(cur_rows, y, m)
        prev_icid = calc_metrics(prev_rows, py, m)
        cur_dept_rows = [r for r in cur_rows if '系统集成' in r.get('dept','')]
        prev_dept_rows = [r for r in prev_rows if '系统集成' in r.get('dept','')]
        cur_dept = calc_metrics(cur_dept_rows, y, m)
        prev_dept = calc_metrics(prev_dept_rows, py, m)
        
        months_result.append({'key': m_key, 'label': f'{y}年{m}月', 'current': f'{y}年{m}月', 'last_year': f'{py}年{m}月'})
        
        for metric in ['project_count', 'cumulative_days', 'avg_days', 'avg_years', 'contract_amount']:
            cv, pv = cur_icid[metric], prev_icid[metric]
            icid_result[metric][m_key] = {'current': cv, 'previous': pv, 'diff': round(cv-pv,2) if isinstance(cv,(int,float)) and isinstance(pv,(int,float)) else None}
        
        for metric in ['project_count', 'cumulative_days', 'avg_days', 'avg_years', 'contract_amount']:
            cv, pv = cur_dept[metric], prev_dept[metric]
            dept_result[metric][m_key] = {'current': cv, 'previous': pv, 'diff': round(cv-pv,2) if isinstance(cv,(int,float)) and isinstance(pv,(int,float)) else None}
        
        for zi in range(5):
            if len(zones_result) <= zi: zones_result.append({})
            zones_result[zi][m_key] = {'current': cur_icid['zones'][zi], 'previous': prev_icid['zones'][zi], 'diff': cur_icid['zones'][zi] - prev_icid['zones'][zi]}
    
    total_row = {}
    for m in months_result:
        mk = m['key']
        tc = sum(zones_result[zi][mk]['current'] for zi in range(5))
        tp = sum(zones_result[zi][mk]['previous'] for zi in range(5))
        total_row[mk] = {'current': tc, 'previous': tp, 'diff': tc - tp}
    zones_result.append(total_row)
    
    return {
        'success': True,
        'data': {
            'source_version': hvers[0]['id'],
            'months': months_result,
            'icid': icid_result,
            'department': dept_result,
            'zones': [{'data': z} for z in zones_result],
            'enriched_rows': enriched_2026[:500],
            'enriched_total': len(enriched_2026),
            'regions': region_agg,
            'province_stats': province_agg,
        }
    }


@app.get("/api/analysis/payment-cycle/export")
def export_payment_cycle():
    """回款周期分析结果导出 Excel"""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    from datetime import datetime, date
    import io

    # --- 复用分析逻辑 ---
    meta = _load_ds_meta()

    htdata = meta.get('总合同表', {})
    hvers = htdata.get('versions', [])
    if not hvers:
        return JSONResponse({'success': False, 'error': '无数据源'}, status_code=400)

    hfpath = os.path.join(DATASOURCE_DIR, hvers[0]['file'])
    if not os.path.exists(hfpath):
        return JSONResponse({'success': False, 'error': '总合同表文件丢失'}, status_code=400)
    wb = openpyxl.load_workbook(hfpath, read_only=True)
    ws = wb.active
    hrows = list(ws.iter_rows(values_only=True))
    wb.close()
    h_headers = [str(h) if h else '' for h in hrows[0]]
    h_data = []
    for r in hrows[1:]:
        row = {}
        for i, h in enumerate(h_headers):
            row[h] = r[i] if i < len(r) else None
        h_data.append(row)

    def parse_date(v):
        if v is None or v == '' or v == '-': return None
        if isinstance(v, (datetime, date)): return v
        s = str(v).strip()
        if s.startswith('='): return None
        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d', '%Y%m%d']:
            try: return datetime.strptime(s, fmt)
            except: pass
        return None

    def safe_float(v):
        if v is None or v == '' or v == '-': return 0
        try: return float(v)
        except: return 0

    def safe_str(v):
        if v is None: return ''
        return str(v).strip()

    def find_col(headers, keywords):
        for h in headers:
            hl = h.lower().replace(' ', '').replace('_', '').replace('-', '')
            for kw in keywords:
                if kw.lower().replace(' ', '').replace('_', '').replace('-', '') in hl:
                    return h
        return None

    h_col_no = find_col(h_headers, ['合同编号', '编号'])
    h_col_date = find_col(h_headers, ['统计日期', '签约日期', '日期'])
    h_col_dept = find_col(h_headers, ['部门', '责任部门'])
    if h_col_dept and '签定' in str(h_col_dept):
        for h in h_headers:
            if h == '部门':
                h_col_dept = h
                break
    h_col_amount = find_col(h_headers, ['合同金额', '金额', '合同额', '合同总金额'])

    rtdata = meta.get('项目里程碑表', {})
    rvers = rtdata.get('versions', [])
    r_index = {}
    if rvers:
        rfpath = os.path.join(DATASOURCE_DIR, rvers[0]['file'])
        if os.path.exists(rfpath):
            wb = openpyxl.load_workbook(rfpath, read_only=True)
            ws = wb.active
            rrows = list(ws.iter_rows(values_only=True))
            wb.close()
            r_headers = [str(h) if h else '' for h in rrows[0]]
            r_col_contract = find_col(r_headers, ['合同编号'])
            for r in rrows[1:]:
                row = {}
                for i, h in enumerate(r_headers):
                    row[h] = r[i] if i < len(r) else None
                cid = str(row.get(r_col_contract, '')).strip() if r_col_contract else ''
                if cid:
                    r_index.setdefault(cid, []).append(row)

    def enrich_for_year(h_rows, target_year):
        result = []
        for row in h_rows:
            cno = safe_str(row.get(h_col_no, ''))
            sdate = parse_date(row.get(h_col_date))
            dept = safe_str(row.get(h_col_dept, ''))
            region = safe_str(row.get(h_col_region, '')) if h_col_region else ''
            amount = safe_float(row.get(h_col_amount)) if h_col_amount else 0
            if not sdate or sdate.year != target_year:
                continue
            matches = r_index.get(cno, [])
            valid = []
            for m in matches:
                pdate = parse_date(m.get('计划回款时间'))
                pval = safe_float(m.get('计划产值(元)'))
                if pdate and pval != 0:
                    valid.append((pdate, pval, m))
            valid.sort(key=lambda x: x[0], reverse=True)
            last_payback = valid[0][0] if valid else None
            cycle_days = (last_payback - sdate).days if last_payback and sdate else 0
            years = round(cycle_days / 365, 4) if cycle_days else 0
            if years < 0.5: zone = '0.5以内'
            elif years < 1: zone = '0.5-1年'
            elif years < 2: zone = '1年以上'
            elif years < 3: zone = '2年以上'
            else: zone = '3年以上'
            result.append({
                'contract_no': cno, 'sign_date': sdate.strftime('%Y-%m-%d') if sdate else '',
                'dept': dept, 'amount': amount,
                'last_payback_date': last_payback.strftime('%Y-%m-%d') if last_payback else '',
                'cycle_days': cycle_days, 'years': years, 'zone': zone,
            })
        return result

    enriched_2026 = enrich_for_year(h_data, 2026)
    enriched_2025 = enrich_for_year(h_data, 2025)

    target_months = [(2026, 6), (2026, 7), (2026, 8)]

    def calc_metrics(rows, y, m):
        count = len(rows)
        total_amount = sum(r['amount'] for r in rows)
        total_cycle = sum(r['cycle_days'] for r in rows)
        avg_cycle = round(total_cycle / count, 1) if count > 0 else 0
        avg_years = round(avg_cycle / 365, 2) if avg_cycle > 0 else 0
        zones = [0, 0, 0, 0, 0]
        for r in rows:
            yrs = r['years']
            if yrs <= 0: continue
            if yrs < 0.5: zones[0] += 1
            elif yrs < 1: zones[1] += 1
            elif yrs < 2: zones[2] += 1
            elif yrs < 3: zones[3] += 1
            else: zones[4] += 1
        return {'project_count': count, 'contract_amount': round(total_amount/10000,2),
                'cumulative_days': total_cycle, 'avg_days': avg_cycle, 'avg_years': avg_years, 'zones': zones}

    def in_month(r, yr, mo):
        if not r['sign_date']: return False
        try:
            sd = datetime.strptime(r['sign_date'], '%Y-%m-%d')
            return sd.year < yr or (sd.year == yr and sd.month <= mo)
        except: return False

    def filter_rows(enriched, year, month):
        return [r for r in enriched if in_month(r, year, month)]

    # --- 构建 Excel ---
    out = io.BytesIO()
    xwb = openpyxl.Workbook()
    xwb.remove(xwb.active)

    header_fill = PatternFill(start_color='1a1a2e', end_color='1a1a2e', fill_type='solid')
    header_font = Font(name='Microsoft YaHei', size=10, color='00e5ff', bold=True)
    normal_font = Font(name='Microsoft YaHei', size=10, color='e0e0e0')
    cell_fill = PatternFill(start_color='0d1530', end_color='0d1530', fill_type='solid')
    alt_fill = PatternFill(start_color='111b33', end_color='111b33', fill_type='solid')
    thin_border = Border(
        left=Side(style='thin', color='1a2540'),
        right=Side(style='thin', color='1a2540'),
        top=Side(style='thin', color='1a2540'),
        bottom=Side(style='thin', color='1a2540'),
    )
    center_align = Alignment(horizontal='center', vertical='center')
    left_align = Alignment(horizontal='left', vertical='center')

    def style_cell(cell, is_header=False, is_left=False, fill_idx=0):
        cell.font = header_font if is_header else normal_font
        cell.fill = header_fill if is_header else (cell_fill if fill_idx % 2 == 0 else alt_fill)
        cell.border = thin_border
        cell.alignment = left_align if is_left else center_align

    # ===== Sheet 1: ICID整体汇总 =====
    ws1 = xwb.create_sheet('ICID整体汇总')
    metrics_labels = ['合同额（万元）', '项目个数', '当年累计回款周期（天）', '平均合同回款周期（天）', '平均合同回款周期（年）']
    metrics_keys = ['contract_amount', 'project_count', 'cumulative_days', 'avg_days', 'avg_years']

    col = 1
    ws1.cell(row=1, column=col, value='指标名称')
    style_cell(ws1.cell(row=1, column=col), is_header=True, is_left=True)
    col += 1
    for y, m in target_months:
        m_key = f'{y}-{m:02d}'
        py = 2025
        for label in [f'{y}年{m}月', f'{py}年{m}月', '增长额']:
            ws1.cell(row=1, column=col, value=label)
            style_cell(ws1.cell(row=1, column=col), is_header=True)
            col += 1

    for ri, label in enumerate(metrics_labels):
        r = ri + 2
        col = 1
        ws1.cell(row=r, column=col, value=label)
        style_cell(ws1.cell(row=r, column=col), is_left=True, fill_idx=ri)
        col += 1
        for y, m in target_months:
            m_key = f'{y}-{m:02d}'
            cur_rows = filter_rows(enriched_2026, y, m)
            prev_rows = filter_rows(enriched_2025, 2025, m)
            cur_m = calc_metrics(cur_rows, y, m)
            prev_m = calc_metrics(prev_rows, 2025, m)
            cv, pv = cur_m[metrics_keys[ri]], prev_m[metrics_keys[ri]]
            diff = round(cv - pv, 2) if isinstance(cv, (int, float)) and isinstance(pv, (int, float)) else '-'
            for v in [cv, pv, diff]:
                ws1.cell(row=r, column=col, value=v)
                style_cell(ws1.cell(row=r, column=col), fill_idx=ri)
                col += 1

    # 列宽
    ws1.column_dimensions['A'].width = 28
    for i in range(2, col):
        ws1.column_dimensions[get_column_letter(i)].width = 16

    # ===== Sheet 2: 部门汇总 =====
    ws2 = xwb.create_sheet('系统集成部门汇总')
    col = 1
    ws2.cell(row=1, column=col, value='指标名称')
    style_cell(ws2.cell(row=1, column=col), is_header=True, is_left=True)
    col += 1
    for y, m in target_months:
        py = 2025
        for label in [f'{y}年{m}月', f'{py}年{m}月', '增长额']:
            ws2.cell(row=1, column=col, value=label)
            style_cell(ws2.cell(row=1, column=col), is_header=True)
            col += 1

    for ri, label in enumerate(metrics_labels):
        r = ri + 2
        col = 1
        ws2.cell(row=r, column=col, value=label)
        style_cell(ws2.cell(row=r, column=col), is_left=True, fill_idx=ri)
        col += 1
        for y, m in target_months:
            m_key = f'{y}-{m:02d}'
            cur_rows = filter_rows(enriched_2026, y, m)
            prev_rows = filter_rows(enriched_2025, 2025, m)
            cur_dept_rows = [x for x in cur_rows if '系统集成' in x.get('dept', '')]
            prev_dept_rows = [x for x in prev_rows if '系统集成' in x.get('dept', '')]
            cur_m = calc_metrics(cur_dept_rows, y, m)
            prev_m = calc_metrics(prev_dept_rows, 2025, m)
            cv, pv = cur_m[metrics_keys[ri]], prev_m[metrics_keys[ri]]
            diff = round(cv - pv, 2) if isinstance(cv, (int, float)) and isinstance(pv, (int, float)) else '-'
            for v in [cv, pv, diff]:
                ws2.cell(row=r, column=col, value=v)
                style_cell(ws2.cell(row=r, column=col), fill_idx=ri)
                col += 1

    ws2.column_dimensions['A'].width = 28
    for i in range(2, col):
        ws2.column_dimensions[get_column_letter(i)].width = 16

    # ===== Sheet 3: 分区明细 =====
    ws3 = xwb.create_sheet('回款周期分区明细')
    zone_labels = ['0.5以内', '0.5-1年', '1年以上', '2年以上', '3年以上', '总计']
    col = 1
    ws3.cell(row=1, column=col, value='回款周期分区')
    style_cell(ws3.cell(row=1, column=col), is_header=True, is_left=True)
    col += 1
    for y, m in target_months:
        py = 2025
        for label in [f'{y}年{m}月', f'{py}年{m}月', '差值']:
            ws3.cell(row=1, column=col, value=label)
            style_cell(ws3.cell(row=1, column=col), is_header=True)
            col += 1

    # 先算各区数据
    zones_data = []
    for y, m in target_months:
        cur_rows = filter_rows(enriched_2026, y, m)
        prev_rows = filter_rows(enriched_2025, 2025, m)
        cur_m = calc_metrics(cur_rows, y, m)
        prev_m = calc_metrics(prev_rows, 2025, m)
        zones_data.append((cur_m['zones'], prev_m['zones']))
    # 总计
    totals = []
    for y, m in target_months:
        cur_rows = filter_rows(enriched_2026, y, m)
        prev_rows = filter_rows(enriched_2025, 2025, m)
        totals.append((len(cur_rows), len(prev_rows)))

    for zi, zlabel in enumerate(zone_labels):
        r = zi + 2
        col = 1
        ws3.cell(row=r, column=col, value=zlabel)
        style_cell(ws3.cell(row=r, column=col), is_left=True, fill_idx=zi)
        for mi in range(len(target_months)):
            if zi < 5:
                cv, pv = zones_data[mi][0][zi], zones_data[mi][1][zi]
            else:
                cv, pv = totals[mi]
            diff = cv - pv
            for v in [cv, pv, diff]:
                ws3.cell(row=r, column=col, value=v)
                style_cell(ws3.cell(row=r, column=col), fill_idx=zi)
                col += 1

    ws3.column_dimensions['A'].width = 20
    for i in range(2, col):
        ws3.column_dimensions[get_column_letter(i)].width = 14

    # ===== Sheet 4: 补充数据表 =====
    ws4 = xwb.create_sheet('补充数据表(2026年)')
    # 按回款周期降序
    enriched_2026.sort(key=lambda x: x['cycle_days'] or 0, reverse=True)
    headers4 = ['合同编号', '签约日期', '部门', '最后一笔回款日期', '回款周期(天)', '年', '分区']
    for ci, h in enumerate(headers4):
        ws4.cell(row=1, column=ci + 1, value=h)
        style_cell(ws4.cell(row=1, column=ci + 1), is_header=True)

    red_font = Font(name='Microsoft YaHei', size=10, color='ff5252', bold=True)
    for ri, row in enumerate(enriched_2026):
        r = ri + 2
        vals = [row['contract_no'], row['sign_date'], row['dept'],
                row['last_payback_date'], row['cycle_days'], row['years'], row['zone']]
        for ci, v in enumerate(vals):
            cell = ws4.cell(row=r, column=ci + 1, value=v if v != '' else '-')
            style_cell(cell, fill_idx=ri)
            if ci == 4 and isinstance(v, (int, float)) and v > 500:
                cell.font = red_font

    col_widths4 = [22, 14, 14, 20, 16, 10, 14]
    for ci, w in enumerate(col_widths4):
        ws4.column_dimensions[get_column_letter(ci + 1)].width = w

    # 保存到 bytes
    xwb.save(out)
    out.seek(0)

    from fastapi.responses import StreamingResponse
    from urllib.parse import quote
    filename = quote('回款周期分析报告.xlsx')
    return StreamingResponse(
        out,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f"attachment; filename*=UTF-8''{filename}"}
    )


@app.on_event("startup")
def startup():
    init_db()


# ===================== 供应商列名 =====================
# 供应商列不再做删减过滤，比对结果/版本详情均展示全部原始列


@app.get("/")
def index():
    return FileResponse(os.path.join(FRONTEND_DIR, 'index.html'))


@app.get("/common.css")
def common_css():
    return FileResponse(os.path.join(FRONTEND_DIR, 'common.css'))


@app.get("/gross")
def gross_page():
    return FileResponse(os.path.join(FRONTEND_DIR, 'gross.html'))

@app.get("/china.json")
def china_map_data():
    return FileResponse(os.path.join(FRONTEND_DIR, 'china.json'))

# ===================== 合同管理 =====================

@app.get("/api/contracts")
def list_contracts(keyword: str = Query(None), status: str = Query(None)):
    """全部合同列表（首页）"""
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


@app.post("/api/contracts")
async def create_new_contract(name: str = Query(...), no: str = Query(''), sign_date: str = Query('')):
    cid = create_contract(name, no, sign_date)
    return JSONResponse({'success': True, 'contract_id': cid})


@app.put("/api/contracts/{contract_id}")
async def update_contract(contract_id: int):
    """更新合同元信息（通过form data）"""
    from fastapi import Form
    # Simple update via query params for now
    return JSONResponse({'success': True})


@app.delete("/api/contracts/{contract_id}")
def remove_contract(contract_id: int):
    delete_contract(contract_id)
    return JSONResponse({'success': True})


# ===================== 合同基准管理 =====================

@app.post("/api/contract/{contract_id}/upload")
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


@app.get("/api/contract/{contract_id}/items")
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


# ===================== 供应商版本管理 =====================

@app.post("/api/contract/{contract_id}/supplier/upload")
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


@app.get("/api/contract/{contract_id}/supplier/versions")
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


@app.get("/api/contract/{contract_id}/supplier/items")
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


@app.delete("/api/contract/{contract_id}/supplier/versions/{version_id}")
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


# ===================== 比对引擎 =====================

@app.post("/api/contract/{contract_id}/compare/run")
def run_compare(contract_id: int, version_id: int = Query(...)):
    try:
        result = run_comparison(contract_id, version_id)
        update_contract_status(contract_id)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e)}, status_code=400)


@app.get("/api/contract/{contract_id}/compare/results")
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


@app.get("/api/contract/{contract_id}/column-mapping")
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


@app.post("/api/contract/{contract_id}/column-mapping")
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


@app.post("/api/compare/{result_id}/confirm")
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


# ===================== 统计（多合同版） =====================

@app.get("/api/contract/{contract_id}/stats")
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


# ===================== 全局统计（首页） =====================

@app.get("/api/stats")
def get_global_stats():
    """全局聚合统计（已废弃，用 /api/contracts 代替）"""
    conn = get_db()
    stats = {
        'total': conn.execute("SELECT COUNT(*) FROM contracts").fetchone()[0],
        'total_amount': conn.execute("SELECT COALESCE(SUM(total_amount), 0) FROM contracts").fetchone()[0],
    }
    conn.close()
    return JSONResponse({'stats': stats, 'versions': []})


# ===================== 报告导出 =====================

@app.get("/api/contract/{contract_id}/export/report")
def download_report(contract_id: int, version_id: int = Query(...)):
    try:
        filepath = export_report(version_id)
        return FileResponse(filepath,
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            filename=os.path.basename(filepath))
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e)}, status_code=400)


# ===================== 聊天 API =====================

from fastapi.responses import StreamingResponse
from fastapi import Form
import asyncio, json

@app.post("/api/chat/send")
async def chat_send(message: str = Form(...), contract_id: int = Form(0)):
    """接收网页聊天消息 → 存储 + 飞书转发"""
    try:
        msg = handle_user_message(contract_id, message)
        return JSONResponse({'success': True, 'message': msg})
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e)}, status_code=400)


@app.get("/api/chat/messages")
def chat_messages(contract_id: int = Query(0), since_id: int = Query(0)):
    """获取聊天历史"""
    msgs = get_messages(contract_id, since_id)
    return JSONResponse({'messages': msgs})


@app.get("/api/chat/stream")
async def chat_stream(contract_id: int = Query(0)):
    """SSE 实时消息流"""
    q = []
    register_sse_listener(q)

    async def event_generator():
        try:
            while True:
                if q:
                    msg = q.pop(0)
                    yield f"data: {json.dumps(msg, default=str)}\n\n"
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            pass
        finally:
            unregister_sse_listener(q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


# ===================== 资金占用分析 API =====================

FUND_DATA_DIR = os.path.join(BASE_DIR, '..', 'fund_data')
os.makedirs(FUND_DATA_DIR, exist_ok=True)


@app.get("/api/fund/status")
def fund_status():
    """查询付款/收款明细在数据源中的上传状态"""
    result = {}
    meta = _load_ds_meta()
    for key, tname in [('payment', '付款明细表'), ('collection', '收款明细表')]:
        vers = meta.get(tname, {}).get('versions', [])
        if vers:
            result[key] = f'{tname} v{vers[0]["id"]}'
    return result


@app.post("/api/fund/upload")
async def fund_upload(file: UploadFile = File(...), type: str = Form(...)):
    """上传付款明细/收款明细/计算规则"""
    if type not in ('payment', 'collection', 'rule'):
        return {'success': False, 'error': '无效的文件类型'}
    name_map = {'payment': 'payment_details.xlsx',
                'collection': 'collection_details.xlsx',
                'rule': 'fund_rule.xlsx'}
    fname = name_map[type]
    fpath = os.path.join(FUND_DATA_DIR, fname)
    content = await file.read()
    with open(fpath, 'wb') as f:
        f.write(content)
    return {'success': True, 'filename': fname}


# FIFO 垫资片段全局缓存
fund_segments_cache = {}
fund_flows_cache = {}


def _save_snapshot(job_key, result_dict):
    """保存分析结果快照到 SQLite（持久化，替代内存缓存）"""
    import json as _json
    from models import init_db
    init_db()
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO analysis_snapshots (job_key, result_json)
        VALUES (?,?)
        ON CONFLICT(job_key) DO UPDATE SET result_json=excluded.result_json, updated_at=datetime('now','localtime')
    """, (job_key, _json.dumps(result_dict, ensure_ascii=False, default=str)))
    conn.commit()
    conn.close()


def _load_snapshot(job_key):
    """读取分析结果快照"""
    import json as _json
    conn = get_db()
    c = conn.cursor()
    row = c.execute("SELECT result_json FROM analysis_snapshots WHERE job_key=?", (job_key,)).fetchone()
    conn.close()
    if row:
        return _json.loads(row['result_json'])
    return None

@app.post("/api/fund/analyze")
def fund_analyze():
    """FIFO 先进先出资金占用计算"""
    import openpyxl
    from datetime import datetime, date
    from collections import defaultdict

    global fund_segments_cache, fund_flows_cache

    # 从数据源读「付款明细表」「收款明细表」最新版本（统一数据源），回退到 fund_data 旧目录
    def ds_latest_file(table_name):
        try:
            meta = _load_ds_meta()
            vers = meta.get(table_name, {}).get('versions', [])
            if vers:
                p = os.path.join(DATASOURCE_DIR, vers[0]['file'])
                if os.path.exists(p):
                    return p
        except Exception:
            pass
        return None

    pay_path = ds_latest_file('付款明细表') or os.path.join(FUND_DATA_DIR, 'payment_details.xlsx')
    coll_path = ds_latest_file('收款明细表') or os.path.join(FUND_DATA_DIR, 'collection_details.xlsx')

    if not os.path.exists(pay_path):
        return {'success': False, 'error': '请先上传付款明细表'}
    if not os.path.exists(coll_path):
        return {'success': False, 'error': '请先上传收款明细表'}

    # ── 工具函数 ──
    def safe_float(v):
        if v is None or v == '' or v == '-': return 0.0
        try: return float(v)
        except: return 0.0

    def parse_date(v):
        if v is None or v == '' or v == '-': return None
        if isinstance(v, (datetime, date)): return v
        s = str(v).strip()
        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d', '%Y%m%d']:
            try: return datetime.strptime(s, fmt)
            except: pass
        return None

    def safe_str(v):
        if v is None: return ''
        return str(v).strip()

    def find_col(headers, keywords):
        for h in headers:
            hl = str(h).lower().replace(' ', '').replace('_', '').replace('-', '')
            for kw in keywords:
                if kw.lower().replace(' ', '').replace('_', '').replace('-', '') in hl:
                    return h
        return None

    def read_excel(path):
        wb = openpyxl.load_workbook(path, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        wb.close()
        headers = [str(h) if h else '' for h in rows[0]]
        data = []
        for r in rows[1:]:
            row = {}
            for i, h in enumerate(headers):
                row[h] = r[i] if i < len(r) else None
            data.append(row)
        return headers, data

    # ── 系统参数 ──
    REPORT_CUTOFF = datetime(2026, 8, 12)
    ANNUAL_COST_RATE = 0.03

    # ── 读取数据并透视 ──
    pay_headers, pay_data = read_excel(pay_path)
    col_pay_no = find_col(pay_headers, ['合同编号', '编号'])
    col_pay_date = find_col(pay_headers, ['实际支付时间', '支付时间', '付款日期'])
    col_pay_amount = find_col(pay_headers, ['实际支付金额', '支付金额'])
    col_contract_amt = find_col(pay_headers, ['合同额', '合同金额'])
    col_customer = find_col(pay_headers, ['主合同客户名称', '客户名称', '客户'])
    col_project = find_col(pay_headers, ['项目名称', '项目描述'])

    coll_headers, coll_data = read_excel(coll_path)
    col_coll_no = find_col(coll_headers, ['合同号', '合同编号', '编号'])
    col_coll_date = find_col(coll_headers, ['回款日期', '收款日期', '回款时间'])
    col_coll_amount = find_col(coll_headers, ['到款金额', '回款金额', '收款金额'])
    col_coll_customer = find_col(coll_headers, ['客户名称', '客户'])

    # 合同基础信息
    contract_info = {}
    for row in pay_data:
        cno = safe_str(row.get(col_pay_no, ''))
        if not cno or cno in contract_info: continue
        contract_info[cno] = {
            '合同额': safe_float(row.get(col_contract_amt)) if col_contract_amt else 0,
            '客户名称': safe_str(row.get(col_customer, '')),
            '项目名称': safe_str(row.get(col_project, '')),
        }

    # ── 透视聚合 ──
    pay_pivot = defaultdict(lambda: defaultdict(float))
    flow_idx = 0
    for row in pay_data:
        cno = safe_str(row.get(col_pay_no, ''))
        if not cno: continue
        dt = parse_date(row.get(col_pay_date))
        amt = safe_float(row.get(col_pay_amount))
        if dt and amt > 0:
            date_key = dt.strftime('%Y-%m-%d')
            pay_pivot[cno][date_key] += amt
            flow_idx += 1
        if cno not in contract_info:
            contract_info[cno] = {
                '合同额': safe_float(row.get(col_contract_amt)) if col_contract_amt else 0,
                '客户名称': safe_str(row.get(col_customer, '')),
                '项目名称': safe_str(row.get(col_project, '')),
            }

    coll_pivot = defaultdict(lambda: defaultdict(float))
    for row in coll_data:
        cno = safe_str(row.get(col_coll_no, ''))
        if not cno: continue
        dt = parse_date(row.get(col_coll_date))
        amt = safe_float(row.get(col_coll_amount))
        if dt and amt > 0:
            date_key = dt.strftime('%Y-%m-%d')
            coll_pivot[cno][date_key] += amt
            flow_idx += 1
        if cno not in contract_info:
            contract_info[cno] = {
                '合同额': 0,
                '客户名称': safe_str(row.get(col_coll_customer, '')),
                '项目名称': '',
            }

    all_contracts = set(list(pay_pivot.keys()) + list(coll_pivot.keys()))

    # ── 清空全局缓存 ──
    fund_segments_cache = {}
    fund_flows_cache = {}

    # ── FIFO 计算 ──
    summary_rows = []

    for cno in all_contracts:
        # 构建付款列表
        payments = []
        p_idx = 0
        for date_key in sorted(pay_pivot.get(cno, {}).keys()):
            dt = parse_date(date_key)
            amt = pay_pivot[cno][date_key]
            if dt and amt > 0:
                p_idx += 1
                payments.append({
                    'flow_id': f'{cno}-PAY-{p_idx:03d}',
                    'occur_date': dt,
                    'amount': amt,
                })

        # 构建回款列表
        collections = []
        c_idx = 0
        for date_key in sorted(coll_pivot.get(cno, {}).keys()):
            dt = parse_date(date_key)
            amt = coll_pivot[cno][date_key]
            if dt and amt > 0:
                c_idx += 1
                collections.append({
                    'flow_id': f'{cno}-REC-{c_idx:03d}',
                    'occur_date': dt,
                    'amount': amt,
                })

        payments.sort(key=lambda x: x['occur_date'])
        collections.sort(key=lambda x: x['occur_date'])

        # 保存原始流水 + 现金流序列
        _pay_flows = [{'flow_id': p['flow_id'], 'flow_type': 'PAY', 'occur_date': p['occur_date'].strftime('%Y-%m-%d'), 'amount': p['amount']} for p in payments]
        _coll_flows = [{'flow_id': c['flow_id'], 'flow_type': 'RECEIVE', 'occur_date': c['occur_date'].strftime('%Y-%m-%d'), 'amount': c['amount']} for c in collections]

        # 现金流序列（逐笔：付款为负/回款为正，按日期排序，累计净现金余额）
        _events = []
        for p in payments:
            _events.append((p['occur_date'], 'PAY', -p['amount'], p['flow_id']))
        for c in collections:
            _events.append((c['occur_date'], 'RECEIVE', c['amount'], c['flow_id']))
        _events.sort(key=lambda x: (x[0], 1 if x[1] == 'RECEIVE' else 0))  # 同日先付后收
        _cashflow = []
        _balance = 0
        for _d, _t, _amt, _fid in _events:
            _balance += _amt
            _cashflow.append({
                'flow_id': _fid, 'date': _d.strftime('%Y-%m-%d'), 'type': _t,
                'amount': round(_amt), 'balance': round(_balance),
            })
        # 按月汇总（每月付款/回款/净现金流/月末累计余额）
        _monthly = {}
        for _d, _t, _amt, _fid in _events:
            _mk = _d.strftime('%Y-%m')
            _m = _monthly.setdefault(_mk, {'month': _mk, 'pay_amount': 0, 'recv_amount': 0})
            if _t == 'PAY':
                _m['pay_amount'] += _amt
            else:
                _m['recv_amount'] += _amt
        _cashflow_monthly = []
        _mbalance = 0
        for _mk in sorted(_monthly.keys()):
            _m = _monthly[_mk]
            _mbalance += _m['recv_amount'] + _m['pay_amount']
            _cashflow_monthly.append({
                'month': _mk, 'pay_amount': round(_m['pay_amount']),
                'recv_amount': round(_m['recv_amount']),
                'net': round(_m['recv_amount'] + _m['pay_amount']), 'balance': round(_mbalance),
            })

        fund_flows_cache[cno] = {
            'payments': _pay_flows,
            'collections': _coll_flows,
            'cashflow': _cashflow,
            'cashflow_monthly': _cashflow_monthly,
        }

        # 无付款 → 纯收款合同，占用为0
        if not payments:
            total_receive = round(sum(c['amount'] for c in collections))
            info = contract_info.get(cno, {})
            fund_segments_cache[cno] = []
            summary_rows.append({
                '合同编号': cno,
                '客户名称': info.get('客户名称', ''),
                '项目名称': info.get('项目名称', ''),
                '合同额': round(info.get('合同额', 0)),
                '累计付款': 0,
                '累计收款': total_receive,
                '当前资金占用': 0,
                '元天合计': 0,
                '周期起始日': '-',
                '周期总天数': 0,
                '平均资金占用': 0,
                '预估资金成本': 0,
                '年化成本率': f'{ANNUAL_COST_RATE*100:.0f}%',
                '片段数': 0,
                '已结清片段': 0,
                '占用中片段': 0,
            })
            continue

        # 第一步：预收款
        first_pay_date = payments[0]['occur_date']
        pre_receipts = [c for c in collections if c['occur_date'] < first_pay_date]
        regular_collections = [c for c in collections if c['occur_date'] >= first_pay_date]
        pre_receipt_balance = sum(c['amount'] for c in pre_receipts)

        # 第二步：垫资池（预收款冲抵时生成片段）
        advance_pool = []
        segments = []
        for p in payments:
            remaining = p['amount']
            if pre_receipt_balance > 0:
                offset = min(pre_receipt_balance, remaining)
                remaining -= offset
                pre_receipt_balance -= offset
                if offset > 0:
                    segments.append({
                        'contract_id': cno,
                        'origin_flow_id': p['flow_id'],
                        'pay_occur_date': p['occur_date'].strftime('%Y-%m-%d'),
                        'segment_status': 'PRESETTLED',
                        'segment_amount': round(offset),
                        'end_date': p['occur_date'].strftime('%Y-%m-%d'),
                        'occupy_days': 0,
                        'amount_day': 0,
                    })
            if remaining > 0:
                advance_pool.append({
                    'flow_id': p['flow_id'],
                    'pay_date': p['occur_date'],
                    'origin_amount': p['amount'],
                    'remain_amount': remaining,
                })

        # 第三步：回款 FIFO
        for c in regular_collections:
            receive_left = c['amount']
            receive_date = c['occur_date']
            while receive_left > 0 and advance_pool:
                item = advance_pool[0]
                days = (receive_date - item['pay_date']).days
                if days < 0: days = 0
                if item['remain_amount'] <= receive_left:
                    segments.append({
                        'contract_id': cno,
                        'origin_flow_id': item['flow_id'],
                        'pay_occur_date': item['pay_date'].strftime('%Y-%m-%d'),
                        'segment_status': 'SETTLED',
                        'segment_amount': round(item['remain_amount']),
                        'end_date': receive_date.strftime('%Y-%m-%d'),
                        'occupy_days': days,
                        'amount_day': round(item['remain_amount'] * days),
                    })
                    receive_left -= item['remain_amount']
                    advance_pool.pop(0)
                else:
                    segments.append({
                        'contract_id': cno,
                        'origin_flow_id': item['flow_id'],
                        'pay_occur_date': item['pay_date'].strftime('%Y-%m-%d'),
                        'segment_status': 'SETTLED',
                        'segment_amount': round(receive_left),
                        'end_date': receive_date.strftime('%Y-%m-%d'),
                        'occupy_days': days,
                        'amount_day': round(receive_left * days),
                    })
                    item['remain_amount'] -= receive_left
                    receive_left = 0

        # 第四步：剩余 → OCCUPYING
        for item in advance_pool:
            days = (REPORT_CUTOFF - item['pay_date']).days
            if days < 0: days = 0
            segments.append({
                'contract_id': cno,
                'origin_flow_id': item['flow_id'],
                'pay_occur_date': item['pay_date'].strftime('%Y-%m-%d'),
                'segment_status': 'OCCUPYING',
                'segment_amount': round(item['remain_amount']),
                'end_date': REPORT_CUTOFF.strftime('%Y-%m-%d'),
                'occupy_days': days,
                'amount_day': round(item['remain_amount'] * days),
            })

        fund_segments_cache[cno] = segments

        # 第五步：聚合
        total_pay = round(sum(p['amount'] for p in payments))
        total_receive = round(sum(c['amount'] for c in collections))
        current_occupy = round(sum(s['segment_amount'] for s in segments if s['segment_status'] == 'OCCUPYING'))
        sum_amount_day = round(sum(s['amount_day'] for s in segments))
        cycle_start = payments[0]['occur_date']
        cycle_days = (REPORT_CUTOFF - cycle_start).days
        if cycle_days <= 0: cycle_days = 0
        avg_occupy = round(sum_amount_day / cycle_days) if cycle_days > 0 else 0
        estimate_cost = round(sum_amount_day * (ANNUAL_COST_RATE / 365))

        info = contract_info.get(cno, {})

        summary_rows.append({
            '合同编号': cno,
            '客户名称': info.get('客户名称', ''),
            '项目名称': info.get('项目名称', ''),
            '合同额': round(info.get('合同额', 0)),
            '累计付款': total_pay,
            '累计收款': total_receive,
            '净现金流': total_receive - total_pay,
            '当前资金占用': current_occupy,
            '元天合计': sum_amount_day,
            '周期起始日': cycle_start.strftime('%Y-%m-%d'),
            '周期总天数': cycle_days,
            '平均资金占用': avg_occupy,
            '预估资金成本': estimate_cost,
            '年化成本率': f'{ANNUAL_COST_RATE*100:.0f}%',
            '片段数': len(segments),
            '已结清片段': sum(1 for s in segments if s['segment_status'] == 'SETTLED'),
            '占用中片段': sum(1 for s in segments if s['segment_status'] == 'OCCUPYING'),
        })

    # 排序：纯付款 → 有付有收 → 纯收款，组内按资金占用降序
    def sort_key(row):
        pay = row['累计付款']
        recv = row['累计收款']
        if pay > 0 and recv == 0:
            cat = 0  # 纯付款
        elif pay > 0 and recv > 0:
            cat = 1  # 有付有收
        else:
            cat = 2  # 纯收款
        return (cat, -row['当前资金占用'])
    # 过滤纯收款合同（无付款、无占用）
    summary_rows = [r for r in summary_rows if r['累计付款'] > 0]
    summary_rows.sort(key=sort_key)

    n = len(summary_rows)
    grand_pay = sum(r['累计付款'] for r in summary_rows)
    grand_recv = sum(r['累计收款'] for r in summary_rows)
    grand_occupy = sum(r['当前资金占用'] for r in summary_rows)
    grand_amount_day = sum(r['元天合计'] for r in summary_rows)
    grand_cost = sum(r['预估资金成本'] for r in summary_rows)

    summary = {
        '合同总数': f'{n}个',
        '累计付款总额': f'¥{grand_pay:,}',
        '累计收款总额': f'¥{grand_recv:,}',
        '净现金流总额': f'¥{grand_recv - grand_pay:,}',
        '当前资金占用总额': f'¥{grand_occupy:,}',
        '总加权资金占用': f'{grand_amount_day:,}',
        '预估资金成本': f'¥{grand_cost:,}',
        '年化成本率': f'{ANNUAL_COST_RATE*100:.0f}%',
        '报表截止日': REPORT_CUTOFF.strftime('%Y-%m-%d'),
    }

    columns = ['合同编号', '客户名称', '项目名称', '累计付款', '累计收款', '净现金流',
               '当前资金占用', '平均资金占用', '预估资金成本', '周期总天数', '片段数']

    result = {
        'success': True,
        'message': f'分析完成：{n}个合同，当前资金占用 ¥{grand_occupy:,}',
        'data': {
            'summary': summary,
            'columns': columns,
            'rows': summary_rows,
        }
    }
    # 写资金占用宽表（fund_metrics，每合同一行）
    try:
        conn_w = get_db()
        cw = conn_w.cursor()
        cw.execute("DELETE FROM fund_metrics")
        def _num(row, key):
            v = row.get(key, 0)
            if v is None or v == '-' or v == '': return 0
            if isinstance(v, (int, float)): return v
            try: return float(str(v).replace('¥', '').replace(',', '').replace('%', '').strip())
            except: return 0
        for row in summary_rows:
            cw.execute("""INSERT INTO fund_metrics
                (contract_no, customer_name, project_name, contract_amount, total_pay, total_recv,
                 current_occupy, amount_day, cycle_start, cycle_days, avg_occupy, est_cost,
                 annual_rate, segment_count, settled_segments, occupying_segments)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (row.get('合同编号', ''), row.get('客户名称', ''), row.get('项目名称', ''),
                 _num(row, '合同额'), _num(row, '累计付款'), _num(row, '累计收款'),
                 _num(row, '当前资金占用'), _num(row, '元天合计'), str(row.get('周期起始日', '')),
                 int(_num(row, '周期总天数')), _num(row, '平均资金占用'), _num(row, '预估资金成本'),
                 str(row.get('年化成本率', '')), int(_num(row, '片段数')),
                 int(_num(row, '已结清片段')), int(_num(row, '占用中片段'))))
        conn_w.commit()
        conn_w.close()
    except Exception as e:
        print(f"[fund宽表] 写入失败: {e}")

    _save_snapshot('fund-occupancy', result)
    return result


@app.get("/api/fund/metrics")
def fund_metrics():
    """资金占用宽表查询：读 fund_metrics 宽表（ETL 结果），页面直接渲染"""
    conn = get_db()
    c = conn.cursor()
    rows = [dict(r) for r in c.execute("SELECT * FROM fund_metrics ORDER BY current_occupy DESC").fetchall()]
    conn.close()
    if not rows:
        return {'success': False, 'error': '资金占用宽表为空，请先执行「资金占用指标计算」定时任务'}

    n = len(rows)
    grand_pay = sum(r['total_pay'] for r in rows)
    grand_recv = sum(r['total_recv'] for r in rows)
    grand_occupy = sum(r['current_occupy'] for r in rows)
    grand_amount_day = sum(r['amount_day'] for r in rows)
    grand_cost = sum(r['est_cost'] for r in rows)
    annual_rate = rows[0]['annual_rate'] if rows else ''

    summary = {
        '合同总数': f'{n}个',
        '累计付款总额': f'¥{grand_pay:,.0f}',
        '累计收款总额': f'¥{grand_recv:,.0f}',
        '净现金流总额': f'¥{grand_recv - grand_pay:,.0f}',
        '当前资金占用总额': f'¥{grand_occupy:,.0f}',
        '总加权资金占用': f'{grand_amount_day:,.0f}',
        '预估资金成本': f'¥{grand_cost:,.0f}',
        '年化成本率': annual_rate,
    }

    # 每合同明细（列名对齐前端 renderFundResult）
    detail_rows = [{
        '合同编号': r['contract_no'],
        '客户名称': r['customer_name'],
        '项目名称': r['project_name'],
        '累计付款': r['total_pay'],
        '累计收款': r['total_recv'],
        '净现金流': r['total_recv'] - r['total_pay'],
        '当前资金占用': r['current_occupy'],
        '平均资金占用': r['avg_occupy'],
        '预估资金成本': r['est_cost'],
        '周期总天数': r['cycle_days'],
        '片段数': r['segment_count'],
    } for r in rows]

    columns = ['合同编号', '客户名称', '项目名称', '累计付款', '累计收款', '净现金流',
               '当前资金占用', '平均资金占用', '预估资金成本', '周期总天数', '片段数']

    return {'success': True, 'data': {'summary': summary, 'columns': columns, 'rows': detail_rows}}


@app.get("/api/fund/segments/{contract_id}")
def fund_segments(contract_id: str):
    segments = fund_segments_cache.get(contract_id, [])
    flows = fund_flows_cache.get(contract_id, {'payments': [], 'collections': []})
    return {
        'success': True,
        'contract_id': contract_id,
        'segments': segments,
        'flows': flows,
        'cashflow': flows.get('cashflow', []),
        'cashflow_monthly': flows.get('cashflow_monthly', []),
        'local_summary': {
            'sum_amount_day': sum(s['amount_day'] for s in segments),
            'current_occupy': sum(s['segment_amount'] for s in segments if s['segment_status'] == 'OCCUPYING'),
            'total_segments': len(segments),
        }
    }


@app.get("/api/fund/analyze/export")
def fund_analyze_export():
    """导出资金占用分析结果"""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from datetime import datetime

    # 先执行分析
    result = fund_analyze()
    if not result['success']:
        return result

    data = result['data']
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = '资金占用分析'

    # 标题行
    ws.merge_cells('A1:E1')
    ws['A1'] = f'资金占用分析报告（{datetime.now().strftime("%Y-%m-%d %H:%M")}）'
    ws['A1'].font = Font(bold=True, size=14)

    # 汇总指标
    row_idx = 3
    for k, v in data['summary'].items():
        ws.cell(row=row_idx, column=1, value=k).font = Font(bold=True)
        ws.cell(row=row_idx, column=2, value=v)
        row_idx += 1

    # 明细表
    row_idx += 1
    headers = data['columns']
    for ci, h in enumerate(headers, 1):
        cell = ws.cell(row=row_idx, column=ci, value=h)
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill(start_color='165DFF', end_color='165DFF', fill_type='solid')
        cell.alignment = Alignment(horizontal='center')
    row_idx += 1

    for row in data['rows']:
        for ci, h in enumerate(headers, 1):
            v = row.get(h, '')
            cell = ws.cell(row=row_idx, column=ci, value=v)
            cell.alignment = Alignment(horizontal='center')
            if isinstance(v, (int, float)) and v < 0:
                cell.font = Font(color='FF0000')
        row_idx += 1

    # 列宽
    for ci in range(1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(ci)].width = 18

    import io
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f'资金占用分析_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    encoded = urllib.parse.quote(filename)
    return StreamingResponse(
        output,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename*=UTF-8\'{encoded}'}
    )


# ═══════════════════════════════════════════
# 定时 ETL 框架（轨道A：固定指标计算链路）
# 原始明细表 → 定时任务聚合 → 指标汇总宽表
# ═══════════════════════════════════════════

ETL_JOB_DEFS = [
    {
        'job_key': 'gross-margin',
        'job_name': '签单毛利指标计算',
        'description': '按年份/区域聚合签单毛利、签单毛利率',
        'schedule': '0 2 * * *',
        'calculation_logic': '数据源：总合同表（数据源管理最新版）。字段映射：「统计日期」→年份、「区域」分组、「合同总金额」+「签单毛利」求和。计算：签单毛利率 = 签单毛利 ÷ 合同总金额。产出：indicator_metrics 宽表（dim_type=year 按年份、dim_type=region 按区域×年份）。',
    },
    {
        'job_key': 'payment-cycle',
        'job_name': '回款周期指标计算',
        'description': '按合同聚合回款周期指标',
        'schedule': '0 3 * * *',
        'calculation_logic': '数据源：总合同表 + 项目里程碑表。口径：按合同编号关联回款记录，取最后一笔回款日期；回款周期 = 最后一笔回款日 − 合同签订日（统计日期）；按合同聚合。产出：payment_cycle_metrics 宽表（每合同一行）。',
    },
    {
        'job_key': 'sign-summary',
        'job_name': '签约汇总指标计算',
        'description': '按业务线/区域聚合签约合同额',
        'schedule': '0 4 * * *',
        'calculation_logic': '数据源：总合同表。口径：按「业务线」「区域」分组，聚合当年生效合同额与签约合同数。（骨架阶段，计算逻辑待实现）',
    },
    {
        'job_key': 'fund-occupancy',
        'job_name': '资金占用指标计算',
        'description': 'FIFO 垫资冲抵，计算每个合同的资金占用、加权资金占用、资金成本',
        'schedule': '0 5 * * *',
        'calculation_logic': '数据源：付款明细表 + 收款明细表。口径：按合同编号透视（付款/收款按日期聚合）→ FIFO 先进先出冲抵 → 预收款冲抵后续付款 → 生成垫资片段（SETTLED/OCCUPYING）。计算：当前资金占用=占用中片段金额和；元天合计=片段金额×占用天数；预估资金成本=元天×日利率（年化3%）。产出：fund_metrics 宽表（每合同一行）。',
    },
]


def _register_etl_jobs():
    """注册 ETL 任务定义（幂等，UPSERT 保证计算逻辑同步）"""
    from models import init_db
    init_db()
    conn = get_db()
    c = conn.cursor()
    for job in ETL_JOB_DEFS:
        c.execute("""
            INSERT INTO etl_jobs (job_key, job_name, description, calculation_logic, schedule)
            VALUES (?,?,?,?,?)
            ON CONFLICT(job_key) DO UPDATE SET
                job_name=excluded.job_name,
                description=excluded.description,
                calculation_logic=excluded.calculation_logic,
                schedule=excluded.schedule
        """, (job['job_key'], job['job_name'], job['description'], job['calculation_logic'], job['schedule']))
    conn.commit()
    conn.close()


def _ds_latest_path(table_name):
    """获取数据源某表最新版本的文件路径"""
    try:
        meta = _load_ds_meta()
        vers = meta.get(table_name, {}).get('versions', [])
        if vers:
            p = os.path.join(DATASOURCE_DIR, vers[0]['file'])
            if os.path.exists(p):
                return p
    except Exception:
        pass
    return None


def run_etl_gross_margin():
    """签单毛利 ETL：读总合同表 → 按年份/区域聚合 → 写指标宽表"""
    import openpyxl
    from datetime import datetime
    from collections import defaultdict

    h_fpath = _ds_latest_path('总合同表')
    if not h_fpath:
        return {'success': False, 'error': '总合同表未上传'}

    def safe_float(v):
        if v is None or v == '' or v == '-': return 0.0
        try: return float(v)
        except: return 0.0

    def find_col(headers, keywords):
        for h in headers:
            hl = str(h).lower().replace(' ', '').replace('_', '').replace('-', '')
            for kw in keywords:
                if kw.lower().replace(' ', '').replace('_', '').replace('-', '') in hl:
                    return h
        return None

    wb = openpyxl.load_workbook(h_fpath, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    headers = [str(h) if h is not None else '' for h in rows[0]]
    col_idx = {h: i for i, h in enumerate(headers)}

    col_amt = find_col(headers, ['合同总金额'])
    col_gross = find_col(headers, ['签单毛利'])
    col_region = find_col(headers, ['区域'])
    col_date = find_col(headers, ['统计日期'])
    col_dept = find_col(headers, ['部门', '责任部门'])

    def parse_year(v):
        if isinstance(v, datetime): return v.year
        if hasattr(v, 'year'): return v.year
        try: return int(str(v)[:4])
        except: return None

    year_agg = defaultdict(lambda: {'amt': 0.0, 'gross': 0.0})
    region_year_agg = defaultdict(lambda: defaultdict(lambda: {'amt': 0.0, 'gross': 0.0}))
    dept_year_agg = defaultdict(lambda: defaultdict(lambda: {'amt': 0.0, 'gross': 0.0}))
    for r in rows[1:]:
        if r is None: continue
        amt = safe_float(r[col_idx[col_amt]]) if col_amt else 0.0
        gross = safe_float(r[col_idx[col_gross]]) if col_gross else 0.0
        region = str(r[col_idx[col_region]]).strip() if col_region and r[col_idx[col_region]] else ''
        dept = str(r[col_idx[col_dept]]).strip() if col_dept and r[col_idx[col_dept]] else ''
        y = parse_year(r[col_idx[col_date]]) if col_date else None
        if y is not None:
            year_agg[y]['amt'] += amt
            year_agg[y]['gross'] += gross
            if region:
                region_year_agg[region][y]['amt'] += amt
                region_year_agg[region][y]['gross'] += gross
            if dept:
                dept_year_agg[dept][y]['amt'] += amt
                dept_year_agg[dept][y]['gross'] += gross

    def rate(g, a): return round(g / a, 6) if a else 0.0

    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM indicator_metrics WHERE job_key='gross-margin'")
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    n = 0
    for y, v in year_agg.items():
        c.execute("INSERT INTO indicator_metrics (job_key, metric_name, dim_type, dim_value, year, contract_amt, gross_profit, gross_rate, calc_time) VALUES (?,?,?,?,?,?,?,?,?)",
                  ('gross-margin', '签单毛利率', 'year', str(y), str(y), v['amt'], v['gross'], rate(v['gross'], v['amt']), now))
        n += 1
    for region, yd in region_year_agg.items():
        for y, v in yd.items():
            c.execute("INSERT INTO indicator_metrics (job_key, metric_name, dim_type, dim_value, year, contract_amt, gross_profit, gross_rate, calc_time) VALUES (?,?,?,?,?,?,?,?,?)",
                      ('gross-margin', '签单毛利率', 'region', region, str(y), v['amt'], v['gross'], rate(v['gross'], v['amt']), now))
            n += 1
    for dept, yd in dept_year_agg.items():
        for y, v in yd.items():
            c.execute("INSERT INTO indicator_metrics (job_key, metric_name, dim_type, dim_value, year, contract_amt, gross_profit, gross_rate, calc_time) VALUES (?,?,?,?,?,?,?,?,?)",
                      ('gross-margin', '签单毛利率', 'dept', dept, str(y), v['amt'], v['gross'], rate(v['gross'], v['amt']), now))
            n += 1
    conn.commit()
    conn.close()
    return {'success': True, 'rows': n}


@app.get("/api/gross/metrics")
def gross_metrics():
    """签单毛利宽表查询：读 indicator_metrics 宽表（ETL 结果），页面直接渲染，不重复计算"""
    from collections import defaultdict
    conn = get_db()
    c = conn.cursor()
    rows = [dict(r) for r in c.execute("SELECT * FROM indicator_metrics WHERE job_key='gross-margin' ORDER BY id").fetchall()]
    conn.close()
    if not rows:
        return {'success': False, 'error': '指标宽表为空，请先执行「签单毛利指标计算」定时任务'}

    year_rows = [r for r in rows if r['dim_type'] == 'year']
    region_rows = [r for r in rows if r['dim_type'] == 'region']
    dept_rows = [r for r in rows if r['dim_type'] == 'dept']

    by_year = {r['year']: r for r in year_rows}
    def rate(y):
        m = by_year.get(str(y))
        return m['gross_rate'] if m else None
    def amt(y):
        m = by_year.get(str(y))
        return m['contract_amt'] if m else 0

    r26, r25 = rate(2026), rate(2025)
    summary = {
        '2026签单毛利率': f"{r26*100:.2f}%" if r26 is not None else '-',
        '2025签单毛利率': f"{r25*100:.2f}%" if r25 is not None else '-',
        '同比增减': f"{(r26-r25)*100:+.2f}个百分点" if (r26 is not None and r25 is not None) else '-',
        '2026合同额(万)': round(amt(2026)/10000, 2),
    }

    year_list = [{
        '年份': r['year'],
        '合同额(万)': round(r['contract_amt']/10000, 2),
        '签单毛利(万)': round(r['gross_profit']/10000, 2),
        '签单毛利率': r['gross_rate'],
    } for r in sorted(year_rows, key=lambda x: x['year'])]

    region_map = defaultdict(dict)
    for r in region_rows:
        region_map[r['dim_value']][r['year']] = r
    region_list = []
    for region, yd in sorted(region_map.items()):
        m26 = yd.get('2026'); m25 = yd.get('2025')
        r26_rate = m26['gross_rate'] if m26 else None
        r25_rate = m25['gross_rate'] if m25 else None
        diff = round((r26_rate - r25_rate)*100, 2) if (r26_rate is not None and r25_rate is not None) else None
        region_list.append({
            '区域': region,
            '2026合同额(万)': round(m26['contract_amt']/10000, 2) if m26 else 0,
            '2026签单毛利率': r26_rate,
            '2025合同额(万)': round(m25['contract_amt']/10000, 2) if m25 else 0,
            '2025签单毛利率': r25_rate,
            '同比(百分点)': diff,
        })

    dept_map = defaultdict(dict)
    for r in dept_rows:
        dept_map[r['dim_value']][r['year']] = r
    dept_list = []
    for dept, yd in sorted(dept_map.items()):
        m26 = yd.get('2026'); m25 = yd.get('2025')
        dept_list.append({
            '部门': dept,
            '2026合同额(万)': round(m26['contract_amt']/10000, 2) if m26 else 0,
            '2026签单毛利率': m26['gross_rate'] if m26 else None,
            '2025合同额(万)': round(m25['contract_amt']/10000, 2) if m25 else 0,
            '2025签单毛利率': m25['gross_rate'] if m25 else None,
        })

    return {
        'success': True,
        'summary': summary,
        'year_rows': year_list,
        'region_rows': region_list,
        'dept_rows': dept_list,
    }


def run_etl_payment_cycle():
    """回款周期 ETL：读总合同表 + 项目里程碑表 → 算每合同回款周期 → 写宽表"""
    import openpyxl
    from datetime import datetime, date

    h_fpath = _ds_latest_path('总合同表')
    r_fpath = _ds_latest_path('项目里程碑表')
    if not h_fpath:
        return {'success': False, 'error': '总合同表未上传'}

    def parse_date(v):
        if v is None or v == '' or v == '-': return None
        if isinstance(v, (datetime, date)): return v
        s = str(v).strip()
        if s.startswith('='): return None
        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d', '%Y%m%d']:
            try: return datetime.strptime(s, fmt)
            except: pass
        return None

    def safe_float(v):
        if v is None or v == '' or v == '-': return 0.0
        try: return float(v)
        except: return 0.0

    def find_col(headers, keywords):
        for h in headers:
            hl = str(h).lower().replace(' ', '').replace('_', '').replace('-', '')
            for kw in keywords:
                if kw.lower().replace(' ', '').replace('_', '').replace('-', '') in hl:
                    return h
        return None

    # 读总合同表
    wb = openpyxl.load_workbook(h_fpath, data_only=True)
    ws = wb.active
    hrows = list(ws.iter_rows(values_only=True))
    wb.close()
    h_headers = [str(h) if h else '' for h in hrows[0]]
    h_col_no = find_col(h_headers, ['合同编号'])
    h_col_date = find_col(h_headers, ['统计日期', '签约日期'])
    h_col_amt = find_col(h_headers, ['合同总金额', '合同金额', '合同额'])
    h_idx = {h: i for i, h in enumerate(h_headers)}
    contracts = {}
    for r in hrows[1:]:
        if r is None: continue
        cno = str(r[h_idx[h_col_no]]).strip() if h_col_no and h_idx.get(h_col_no) is not None else ''
        if not cno: continue
        cdate = parse_date(r[h_idx[h_col_date]]) if h_col_date and h_idx.get(h_col_date) is not None else None
        amt = safe_float(r[h_idx[h_col_amt]]) if h_col_amt and h_idx.get(h_col_amt) is not None else 0.0
        contracts[cno] = {'date': cdate, 'amount': amt}

    # 读项目里程碑表，找每合同的最后一笔回款日期
    last_pay = {}
    if r_fpath:
        wb = openpyxl.load_workbook(r_fpath, data_only=True)
        ws = wb.active
        rrows = list(ws.iter_rows(values_only=True))
        wb.close()
        r_headers = [str(h) if h else '' for h in rrows[0]]
        r_col_no = find_col(r_headers, ['合同编号'])
        r_col_pay_date = find_col(r_headers, ['回款时间', '回款日期', '到款时间'])
        r_idx = {h: i for i, h in enumerate(r_headers)}
        for r in rrows[1:]:
            if r is None: continue
            cno = str(r[r_idx[r_col_no]]).strip() if r_col_no and r_idx.get(r_col_no) is not None else ''
            if not cno: continue
            pdate = parse_date(r[r_idx[r_col_pay_date]]) if r_col_pay_date and r_idx.get(r_col_pay_date) is not None else None
            if pdate and (cno not in last_pay or pdate > last_pay[cno]):
                last_pay[cno] = pdate

    # 算回款周期，写宽表
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM payment_cycle_metrics")
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    n = 0
    for cno, info in contracts.items():
        cdate = info['date']
        pdate = last_pay.get(cno)
        cycle_days = 0
        if cdate and pdate:
            cycle_days = (pdate - cdate).days
            if cycle_days < 0: cycle_days = 0
        c.execute("INSERT INTO payment_cycle_metrics (contract_no, contract_date, last_payment_date, cycle_days, amount, calc_time) VALUES (?,?,?,?,?,?)",
                  (cno, cdate.strftime('%Y-%m-%d') if cdate else '', pdate.strftime('%Y-%m-%d') if pdate else '', cycle_days, info['amount'], now))
        n += 1
    conn.commit()
    conn.close()
    return {'success': True, 'rows': n}


@app.get("/api/payment-cycle/metrics")
def payment_cycle_metrics():
    """回款周期宽表查询：读 payment_cycle_metrics 宽表（ETL 结果），页面直接渲染"""
    conn = get_db()
    c = conn.cursor()
    rows = [dict(r) for r in c.execute("SELECT * FROM payment_cycle_metrics ORDER BY cycle_days DESC").fetchall()]
    conn.close()
    if not rows:
        return {'success': False, 'error': '回款周期宽表为空，请先执行「回款周期指标计算」定时任务'}

    # 统计：平均回款周期、分布
    total = len(rows)
    has_pay = [r for r in rows if r['cycle_days'] > 0]
    avg_days = round(sum(r['cycle_days'] for r in has_pay) / len(has_pay)) if has_pay else 0
    buckets = {'0-90天': 0, '91-180天': 0, '181-365天': 0, '365天以上': 0}
    for r in has_pay:
        d = r['cycle_days']
        if d <= 90: buckets['0-90天'] += 1
        elif d <= 180: buckets['91-180天'] += 1
        elif d <= 365: buckets['181-365天'] += 1
        else: buckets['365天以上'] += 1

    summary = {
        '合同总数': f'{total}个',
        '已回款合同': f'{len(has_pay)}个',
        '平均回款周期': f'{avg_days}天',
        '回款周期分布': buckets,
    }

    detail_rows = [{
        '合同编号': r['contract_no'],
        '合同签订日期': r['contract_date'],
        '最后一笔回款日期': r['last_payment_date'],
        '回款周期(天)': r['cycle_days'],
        '合同额': r['amount'],
    } for r in rows[:200]]

    columns = ['合同编号', '合同签订日期', '最后一笔回款日期', '回款周期(天)', '合同额']

    return {'success': True, 'data': {'summary': summary, 'columns': columns, 'rows': detail_rows, 'total': total}}


@app.get("/api/etl/jobs")
def etl_jobs():
    """ETL 任务列表（供 9007 长期任务关联）"""
    conn = get_db()
    c = conn.cursor()
    jobs = [dict(r) for r in c.execute("SELECT * FROM etl_jobs ORDER BY id").fetchall()]
    conn.close()
    return {'jobs': jobs}


def _record_execution(job_key, result):
    """记录一次执行到 etl_executions 表"""
    from datetime import datetime
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ok = bool(result.get('success'))
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO etl_executions (job_key, run_time, status, detail, rows_written) VALUES (?,?,?,?,?)",
              (job_key, now, 'success' if ok else 'failed', result.get('error', ''), result.get('rows', 0)))
    c.execute("UPDATE etl_jobs SET last_run=?, last_result=? WHERE job_key=?",
              (now, '成功' if ok else result.get('error', '失败'), job_key))
    conn.commit()
    conn.close()


@app.post("/api/etl/run/{job_key}")
def etl_run(job_key: str):
    """手动触发 ETL 任务"""
    if job_key == 'gross-margin':
        result = run_etl_gross_margin()
    elif job_key == 'fund-occupancy':
        result = fund_analyze()
        if result.get('success'):
            result['rows'] = len(result.get('data', {}).get('rows', []))
    elif job_key == 'payment-cycle':
        result = run_etl_payment_cycle()
    else:
        result = {'success': False, 'error': '该任务的计算逻辑尚未实现（骨架阶段）'}
    _record_execution(job_key, result)
    return result


@app.post("/api/etl/jobs/{job_key}/start")
def etl_start(job_key: str):
    """启动任务（进入自动调度）"""
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE etl_jobs SET status='running' WHERE job_key=?", (job_key,))
    conn.commit()
    conn.close()
    return {'success': True, 'job_key': job_key, 'status': 'running'}


@app.post("/api/etl/jobs/{job_key}/stop")
def etl_stop(job_key: str):
    """停止任务（退出自动调度）"""
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE etl_jobs SET status='stopped' WHERE job_key=?", (job_key,))
    conn.commit()
    conn.close()
    return {'success': True, 'job_key': job_key, 'status': 'stopped'}


@app.get("/api/etl/jobs/{job_key}")
def etl_job_detail(job_key: str):
    """任务详情（含计算逻辑 + 执行记录）"""
    conn = get_db()
    c = conn.cursor()
    job = c.execute("SELECT * FROM etl_jobs WHERE job_key=?", (job_key,)).fetchone()
    if not job:
        conn.close()
        return JSONResponse({'error': '任务不存在'}, status_code=404)
    job_dict = dict(job)
    exes = [dict(r) for r in c.execute("SELECT * FROM etl_executions WHERE job_key=? ORDER BY id DESC LIMIT 20", (job_key,)).fetchall()]
    conn.close()
    job_dict['executions'] = exes
    return job_dict


@app.get("/api/etl/metrics")
def etl_metrics(job_key: str = '', metric_name: str = '', dim_type: str = ''):
    """查询指标汇总宽表（指标数据集MCP 基础，只读）"""
    conn = get_db()
    c = conn.cursor()
    sql = "SELECT * FROM indicator_metrics WHERE 1=1"
    params = []
    if job_key:
        sql += " AND job_key=?"
        params.append(job_key)
    if metric_name:
        sql += " AND metric_name=?"
        params.append(metric_name)
    if dim_type:
        sql += " AND dim_type=?"
        params.append(dim_type)
    sql += " ORDER BY id"
    rows = [dict(r) for r in c.execute(sql, params).fetchall()]
    conn.close()
    return {'metrics': rows}


# ═══════════════════════════════════════════
# 原子本体 MCP（本体明细网关，只读）
# 对外暴露原始明细访问通道，不做大规模聚合
# ═══════════════════════════════════════════

@app.get("/api/mcp/ontology/tables")
def mcp_ontology_tables():
    """列出原始本体表（只读）"""
    meta = _load_ds_meta()
    return {'tables': [{'name': k, 'version_count': len(v.get('versions', []))} for k, v in meta.items()]}


@app.get("/api/mcp/ontology/schema")
def mcp_ontology_schema(table_name: str):
    """获取数据表结构（原子只读）：返回所有列名及示例值，供智能体了解字段含义。"""
    import openpyxl
    fpath = _ds_latest_path(table_name)
    if not fpath:
        return {'success': False, 'error': f'表「{table_name}」未上传'}
    wb = openpyxl.load_workbook(fpath, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    headers = [str(h) if h is not None else '' for h in rows[0]]
    s1 = rows[1] if len(rows) > 1 else None
    s2 = rows[2] if len(rows) > 2 else None
    columns = []
    for i, h in enumerate(headers):
        ex = []
        if s1 is not None and i < len(s1) and s1[i] is not None:
            ex.append(str(s1[i])[:24])
        if s2 is not None and i < len(s2) and s2[i] is not None:
            ex.append(str(s2[i])[:24])
        columns.append({'name': h, 'example': ex})
    return {'table_name': table_name, 'columns': columns, 'column_count': len(columns)}


@app.get("/api/mcp/ontology/query")
def mcp_ontology_query(table_name: str, keyword: str = '', time_column: str = '',
                       start_date: str = '', end_date: str = '', columns: str = '', limit: int = 100):
    """查询原始明细（原子只读）：关键词模糊匹配、时间范围过滤、列投影。columns 为逗号分隔列名，空则返回全部列。"""
    import openpyxl
    from datetime import datetime, timedelta
    fpath = _ds_latest_path(table_name)
    if not fpath:
        return {'success': False, 'error': f'表「{table_name}」未上传'}
    wb = openpyxl.load_workbook(fpath, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    headers = [str(h) if h is not None else '' for h in rows[0]]
    col_idx = {h: i for i, h in enumerate(headers)}

    selected = [c.strip() for c in columns.split(',') if c.strip()] if columns else []

    def parse_date(v):
        if v is None or v == '': return None
        if isinstance(v, datetime): return v
        s = str(v).strip()
        try: return datetime.strptime(s[:10], '%Y-%m-%d')
        except Exception: pass
        try:
            n = float(s)
            if 20000 < n < 80000:
                return datetime(1899, 12, 30) + timedelta(days=int(n))
        except Exception: pass
        return None

    start = parse_date(start_date)
    end = parse_date(end_date)
    tc = col_idx.get(time_column) if time_column else None

    kw = keyword.strip().lower()
    data_rows = []
    for r in rows[1:]:
        if r is None: continue
        if kw:
            hit = any(kw in str(v).lower() for v in r if v is not None)
            if not hit: continue
        if tc is not None:
            dt = parse_date(r[tc] if tc < len(r) else None)
            if dt is None: continue
            if start and dt < start: continue
            if end and dt > end: continue
        data_rows.append([str(v) if v is not None else '' for v in r])
        if len(data_rows) >= limit: break

    if selected:
        sel_idx = [col_idx[c] for c in selected if c in col_idx]
        out_headers = [headers[i] for i in sel_idx]
        out_rows = [[row[i] if i < len(row) else '' for i in sel_idx] for row in data_rows]
    else:
        out_headers = headers
        out_rows = data_rows

    return {'table_name': table_name, 'headers': out_headers, 'rows': out_rows, 'count': len(out_rows)}




# ═══════════════════════════════════════════
# 后台调度（轨道A 定时任务自动执行）
# ═══════════════════════════════════════════

import threading as _threading
import time as _time


def _cron_should_run(schedule, last_run, now):
    """简单 cron 匹配（仅支持「分 时」字段，每天执行一次）"""
    try:
        parts = schedule.split()
        if len(parts) < 2:
            return False
        minute = int(parts[0]); hour = int(parts[1])
    except Exception:
        return False
    today = now.strftime('%Y-%m-%d')
    if last_run and last_run.startswith(today):
        return False
    if (now.hour > hour) or (now.hour == hour and now.minute >= minute):
        return True
    return False


def _scheduler_loop():
    """后台调度：每 60 秒检查 running 任务，按 schedule 每天执行"""
    while True:
        try:
            from datetime import datetime
            now = datetime.now()
            conn = get_db()
            jobs = [dict(r) for r in conn.execute("SELECT * FROM etl_jobs WHERE status='running'").fetchall()]
            conn.close()
            for job in jobs:
                if _cron_should_run(job.get('schedule', ''), job.get('last_run', ''), now):
                    print(f"[ETL调度] 触发 {job['job_key']} @ {now.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
                    try:
                        if job['job_key'] == 'gross-margin':
                            result = run_etl_gross_margin()
                        elif job['job_key'] == 'fund-occupancy':
                            result = fund_analyze()
                            if result.get('success'):
                                result['rows'] = len(result.get('data', {}).get('rows', []))
                        elif job['job_key'] == 'payment-cycle':
                            result = run_etl_payment_cycle()
                        else:
                            result = {'success': False, 'error': '计算逻辑尚未实现（骨架阶段）'}
                    except Exception as e:
                        result = {'success': False, 'error': str(e)}
                    _record_execution(job['job_key'], result)
        except Exception as e:
            print(f"[ETL调度] 异常: {e}", flush=True)
        _time.sleep(60)


def _start_scheduler():
    t = _threading.Thread(target=_scheduler_loop, daemon=True, name='etl-scheduler')
    t.start()
    print("[ETL调度] 已启动，每 60 秒检查一次 running 任务", flush=True)


# 启动时注册 ETL 任务（幂等）
_register_etl_jobs()

# 启动后台调度线程
_start_scheduler()


if __name__ == '__main__':
    import os
    import uvicorn
    port = int(os.environ.get('CC_PORT', '9006'))
    uvicorn.run(app, host='0.0.0.0', port=port)
