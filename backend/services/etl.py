"""ETL 任务定义与注册（服务层，跨域共享）。"""
from models import get_db, init_db

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
    {
        'job_key': 'fund-multidim',
        'job_name': '资金占用多维度聚合',
        'description': '按区域/部门/业务线/客户集合/月份聚合资金占用与风险分布',
        'schedule': '30 5 * * *',
        'calculation_logic': '数据源：fund_metrics 宽表（资金占用指标计算产物）。口径：按维度列（region/dept/biz_line/industry/customer_key/project_status/contract_status/sign_year/month）分组聚合合同数、累计付款/收款、当前资金占用、回款率、占用强度、风险等级分布。产出：indicator_metrics 宽表（dim_type=fund_dim）。',
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
