"""总合同表 v2（205 列）→ 主数据 core_project 导入/映射模块。

- TOTAL_CONTRACT_COLUMN_MAP：中文列表名 → core_project 字段（只裁剪主数据关注的列）。
- read_total_contract_xlsx(path)：openpyxl 读取首表，按映射只提取存在的列。
- upsert_total_contracts(rows)：按 contract_no 去重/更新到 core_project（project_no 缺省取 contract_no）。
"""
from typing import Dict, List, Any, Optional
import os

from core import project as project_core

# 数值类型字段（从 Excel 读取后做浮点归一化；其余按原样存 TEXT）
NUMERIC_FIELDS = {
    'sign_amount', 'hardware_est', 'software_est', 'service_est',
    'accum_cost_est', 'accum_cost_actual', 'sign_gross_profit', 'gross_rate',
    'gross_rate_est', 'contract_profit', 'payback_profit', 'accum_received',
    'payback_cycle', 'cycle',
}

# 中文列表名 → core_project 字段（同时收真实总合同表 v2 列名与其简化别名）
TOTAL_CONTRACT_COLUMN_MAP: Dict[str, str] = {
    # 识别 + 三号（v2 列名 + 别名）
    '合同编号': 'contract_no', '合同号': 'contract_no',
    '部门内部项目号': 'project_no', '项目号': 'project_no',
    '商机号': 'opportunity_no',
    '项目描述': 'name', '项目名称': 'name',
    # 客户（v2: 客户简称 / 甲方名称 / 最终用户）
    '客户简称': 'customer_key', '客户名称': 'customer_key', '客户标识': 'customer_key',
    '甲方名称': 'party_a', '最终用户': 'party_a',
    # 金额（v2: 合同总金额）
    '合同总金额': 'sign_amount', '合同金额': 'sign_amount',
    # 毛利
    '签单毛利': 'sign_gross_profit',
    '综合毛利率': 'gross_rate', '预估综合毛利率': 'gross_rate_est',
    '合同毛利': 'contract_profit', '回款毛利': 'payback_profit',
    # 回款
    '累计总回款': 'accum_received', '往年回款合计': 'accum_received',
    '回款周期-删NA': 'payback_cycle', '回款周期': 'payback_cycle',
    '最后一笔回款日期': 'last_received_date',
    # 成本概算
    '硬件预估成本': 'hardware_est',
    '软件预估实施费': 'software_est',
    '服务预估成本': 'service_est',
    '累计实施成本预估': 'accum_cost_est', '累计实施成本实际': 'accum_cost_actual',
    # 部门 / 区域 / 时间 / 状态
    '区域': 'region', '省分': 'province', '省': 'province',
    '签订行业': 'industry', '行业': 'industry',
    '业务类型': 'biz_type', '客户分类': 'customer_cls', '业务线': 'biz_line',
    '年份': 'stat_year', '统计日期': 'stat_year',
    '签定部门': 'dept', '部门': 'dept',
    '合同签定时间': 'sign_date', '签订日期': 'sign_date',
    '合同状态': 'status', '状态': 'status',
    '合同签定人': 'owner_ref', '责任人': 'owner_ref',
}
# 中文列名 → 目标字段 反向（供调试/报告）
FIELD_TO_CN = {v: k for k, v in TOTAL_CONTRACT_COLUMN_MAP.items()}


def _header_key(h: Any) -> str:
    return str(h or '').strip()


def _to_float(v: Any) -> Optional[float]:
    if v is None or v == '' or v == '-':
        return None
    if isinstance(v, bool):
        return None
    try:
        f = float(str(v).strip().replace(',', ''))
        return f
    except (ValueError, TypeError):
        return None


def _clean_value(field: str, v: Any) -> Any:
    if field in NUMERIC_FIELDS:
        return _to_float(v)
    if v is None:
        return ''
    return str(v).strip()


def read_total_contract_xlsx(path: str) -> List[Dict[str, Any]]:
    """读取总合同表首表，返回在映射中出现的列构成的 dict 列表（仅提取原生中文列头命中的列）。

    project_no 缺省时在 upsert 阶段取 contract_no；本函数不做兜底，保留原始识别列。
    """
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows:
        return []
    headers = [_header_key(h) for h in rows[0]]
    # 取命中的列：中文头为键
    col_index = {cn: i for i, cn in enumerate(headers) if cn in TOTAL_CONTRACT_COLUMN_MAP}
    result: List[Dict[str, Any]] = []
    for r in rows[1:]:
        if not any(c is not None and str(c).strip() != '' for c in r):
            continue
        item: Dict[str, Any] = {}
        for cn, idx in col_index.items():
            val = r[idx] if idx < len(r) else None
            item[TOTAL_CONTRACT_COLUMN_MAP[cn]] = _clean_value(TOTAL_CONTRACT_COLUMN_MAP[cn], val)
        # 只保留该行有 contract_no 或 project_no 的，避免空行垃圾
        if not (str(item.get('contract_no') or '').strip()
                or str(item.get('project_no') or '').strip()):
            continue
        result.append(item)
    return result


def upsert_total_contracts(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """把 read_total_contract_xlsx 的行按 contract_no 去重/更新到 core_project。

    多条同 contract_no 时后者覆盖前者；project_no 缺省取 contract_no。
    返回 {'success', 'imported', 'created', 'updated', 'errors'}。
    """
    created = updated = errors = 0
    dedup: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        cno = str(row.get('contract_no') or '').strip()
        key = cno or str(row.get('project_no') or '').strip() or '_noname'
        dedup[key] = dict(row)  # 后者覆盖
    used = set()
    for key, row in dedup.items():
        if key == '_noname':
            errors += 1
            continue
        if key in used:
            continue
        used.add(key)
        res = project_core.upsert_project(row)
        if res.get('success'):
            if res.get('mode') == 'created':
                created += 1
            else:
                updated += 1
        else:
            errors += 1
    return {'success': True, 'imported': len(used), 'created': created,
            'updated': updated, 'errors': errors}