"""财经域 · 回款周期宽表 (R2 split from main.py)."""
import io, os, json
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from common.datasource_meta import _load_ds_meta, _ds_latest_path
from common.privacy import is_privacy_header, filter_privacy_headers
from models import get_db

router = APIRouter(prefix="", tags=["finance-payment"])

@router.get("/api/payment-cycle/metrics")
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
