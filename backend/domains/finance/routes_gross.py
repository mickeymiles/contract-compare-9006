"""财经域 · 毛利率指标 (R2 split from main.py)."""
from typing import Optional, Any, List, Dict, Tuple, Union
import io
import os
import json
from collections import defaultdict
from datetime import datetime, date, timedelta
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from common.datasource_meta import _load_ds_meta, _ds_latest_path
from common.privacy import is_privacy_header, filter_privacy_headers
from models import get_db

router = APIRouter(prefix="", tags=["finance-gross"])

@router.get("/api/gross/metrics")
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

    # 部门 × 区域 二维热力图数据
    dr_rows = [r for r in rows if r['dim_type'] == 'dept_region']
    dr_dept_region_year = defaultdict(lambda: defaultdict(dict))
    for r in dr_rows:
        extra = json.loads(r['extra_json'] or '{}')
        dept = extra.get('dept') or r['dim_value'].split('|')[0]
        region = extra.get('region') or r['dim_value'].split('|')[1]
        dr_dept_region_year[dept][region][r['year']] = r

    dr_depts = sorted({d for d, _ in dr_dept_region_year.items()})
    dr_regions = sorted({r for _, rd in dr_dept_region_year.items() for r in rd.keys()})

    def _cell(r26, r25):
        if r26 is None:
            return {'rate': None, 'diff': None, 'hasData': False}
        return {
            'rate': round(r26['gross_rate'], 6),
            'diff': round((r26['gross_rate'] - (r25['gross_rate'] if r25 else 0)) * 100, 2) if r25 else None,
            'hasData': True,
        }

    cells = {}
    total_by_dept = {}
    total_by_region = {}
    for dept in dr_depts:
        cells[dept] = {}
        dept_amt_26 = dept_amt_25 = 0.0
        dept_gross_26 = dept_gross_25 = 0.0
        for region in dr_regions:
            yd = dr_dept_region_year[dept].get(region, {})
            m26 = yd.get('2026')
            m25 = yd.get('2025')
            cells[dept][region] = _cell(m26, m25)
            if m26:
                dept_amt_26 += m26['contract_amt']
                dept_gross_26 += m26['gross_profit']
            if m25:
                dept_amt_25 += m25['contract_amt']
                dept_gross_25 += m25['gross_profit']
        total_by_dept[dept] = {
            'rate': round(dept_gross_26 / dept_amt_26, 6) if dept_amt_26 else None,
            'diff': round((dept_gross_26 / dept_amt_26 - dept_gross_25 / dept_amt_25) * 100, 2) if (dept_amt_26 and dept_amt_25) else None,
            'hasData': dept_amt_26 > 0,
        }

    for region in dr_regions:
        reg_amt_26 = reg_amt_25 = 0.0
        reg_gross_26 = reg_gross_25 = 0.0
        for dept in dr_depts:
            yd = dr_dept_region_year[dept].get(region, {})
            m26 = yd.get('2026')
            m25 = yd.get('2025')
            if m26:
                reg_amt_26 += m26['contract_amt']
                reg_gross_26 += m26['gross_profit']
            if m25:
                reg_amt_25 += m25['contract_amt']
                reg_gross_25 += m25['gross_profit']
        total_by_region[region] = {
            'rate': round(reg_gross_26 / reg_amt_26, 6) if reg_amt_26 else None,
            'diff': round((reg_gross_26 / reg_amt_26 - reg_gross_25 / reg_amt_25) * 100, 2) if (reg_amt_26 and reg_amt_25) else None,
            'hasData': reg_amt_26 > 0,
        }

    dept_region_rows = {
        'regions': dr_regions,
        'depts': dr_depts,
        'cells': cells,
        'totals': {'byDept': total_by_dept, 'byRegion': total_by_region},
    }

    return {
        'success': True,
        'summary': summary,
        'year_rows': year_list,
        'region_rows': region_list,
        'dept_rows': dept_list,
        'dept_region_rows': dept_region_rows,
    }
