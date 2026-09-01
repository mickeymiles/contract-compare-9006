"""基础支撑域 · ETL 调度 (R2 split from main.py)."""
import asyncio
import time
import json
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from models import get_db
from services.etl import ETL_JOB_DEFS, _register_etl_jobs, run_etl_gross_margin, run_etl_fund_multidim, run_etl_payment_cycle

router = APIRouter(prefix="", tags=["foundation-etl"])

@router.get("/api/etl/jobs")
def etl_jobs():
    """ETL 任务列表（供 9007 长期任务关联）"""
    conn = get_db()
    c = conn.cursor()
    jobs = [dict(r) for r in c.execute("SELECT * FROM etl_jobs ORDER BY id").fetchall()]
    conn.close()
    return {'jobs': jobs}

@router.post("/api/etl/run/{job_key}")
def etl_run(job_key: str):
    """手动触发 ETL 任务"""
    if job_key == 'gross-margin':
        result = run_etl_gross_margin()
    elif job_key == 'fund-occupancy':
        from main import fund_analyze
        result = fund_analyze()
        if result.get('success'):
            result['rows'] = len(result.get('data', {}).get('rows', []))
    elif job_key == 'fund-multidim':
        result = run_etl_fund_multidim()
    elif job_key == 'payment-cycle':
        result = run_etl_payment_cycle()
    else:
        result = {'success': False, 'error': '该任务的计算逻辑尚未实现（骨架阶段）'}
    from main import _record_execution
    _record_execution(job_key, result)
    return result

@router.post("/api/etl/jobs/{job_key}/start")
def etl_start(job_key: str):
    """启动任务（进入自动调度）"""
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE etl_jobs SET status='running' WHERE job_key=?", (job_key,))
    conn.commit()
    conn.close()
    return {'success': True, 'job_key': job_key, 'status': 'running'}

@router.post("/api/etl/jobs/{job_key}/stop")
def etl_stop(job_key: str):
    """停止任务（退出自动调度）"""
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE etl_jobs SET status='stopped' WHERE job_key=?", (job_key,))
    conn.commit()
    conn.close()
    return {'success': True, 'job_key': job_key, 'status': 'stopped'}

@router.get("/api/etl/jobs/{job_key}")
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

@router.get("/api/etl/metrics")
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
