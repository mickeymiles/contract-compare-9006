"""运维域 · 备件询价 ops (R2 split from main.py)."""
from typing import Optional, Any, List, Dict, Union
import io, os, json, re
from datetime import datetime, date
from fastapi import APIRouter, Query, File, UploadFile, Form, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse, Response
from pydantic import BaseModel, Field
from models import get_db
from common.neuops import trigger_neuops
from common.paths import UPLOAD_DIR, FRONTEND_DIR, DATASOURCE_DIR
from procurement_models import (create_task, get_task, list_tasks, update_task_quote,
   update_task_status_on_deadline, update_task_delivery, list_ledger, list_suppliers, get_supplier,
   create_supplier, update_supplier, delete_supplier, list_contracts, get_contract,
   create_contract as proc_create_contract, update_contract as proc_update_contract, delete_contract as proc_delete_contract,
   list_mail_cc, create_mail_cc, delete_mail_cc, list_spare_parts, get_spare_part,
   create_spare_part, update_spare_part, delete_spare_part, list_ledger_advanced)
import procurement_models as pm

router = APIRouter(prefix="", tags=["ops"])

class SupplierItem(BaseModel):
    """询价供应商条目（前端页面 -> 9006 API -> DB）。
    【修复 2026-08-24】显式声明 id 字段（资源池供应商有id，临时供应商无id）。
    之前未声明时，Pydantic 默认 extra='ignore' 会静默丢弃前端传入的 data-pool-id，
    导致 flow-02 中 s.id 恒为 None，全部被误标记为 _is_temp=True。"""
    model_config = {"extra": "allow"}  # 允许额外字段（如 flow-02 回写的下划线字段透传）
    id: int | None = None
    name: str
    email: str

class AgentNewTaskBody(BaseModel):
    """智能体创建任务（对话入口）：直接传业务字段，走标准 create_task + trigger_neuops"""
    contract_no: str
    spare_part_model: str
    purchase_qty: float
    emergency_level: str
    inquiry_supplier_list: List[Dict[str, str]] = []  # 可空，空则自动带池子
    creator: str = 'agent'

class SelectBody(BaseModel):
    selected_supplier: SupplierItem
    deal_unit_price: float
    # source 标记：card_callback 表示从飞书卡片按钮触发；web(默认) 表示从前端页面手动选型
    source: str = 'web'

class TestResultBody(BaseModel):
    test_result: str
    remark: str = ''
    source: str = 'web'

class CancelBody(BaseModel):
    cancel_reason: str
    source: str = 'web'

class ManualQuoteBody(BaseModel):
    reply_index: int
    unit_price: Optional[float] = None
    total_price: Optional[float] = None
    lead_time: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    note: Optional[str] = None

class SupplierUpdateBody(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    capability: Optional[str] = None

class ProcMailCCBody(BaseModel):
    name: str
    email: str
class NewTaskBody(BaseModel):
    """新建询价任务（页面入口）：合同号 + 备件 + 数量 + 紧急等级 + 询价供应商（空则自动带池子）

    备件属性全部可选，但**建议传全**：智能体按模板 B 组询价邮件时，标题与正文
    依赖 brand / pn / spec / condition / address 等变量。缺失时 LLM 只能凭合同号
    与备件型号自由发挥，出现过「SMOKE-20260830-01（）-电池模块型号备件询价邮件」
    这类失控标题（模板要求的变量为空，渲染成空括号）。

    字段命名与邮件入口的解析字段（9007 `_extract_inquiry_fields`）保持一致，
    便于「页面 / Agent对话 / 邮件」三入口后续统一。
    """
    contract_no: str
    spare_part_model: str
    purchase_qty: float
    emergency_level: str
    inquiry_supplier_list: List[SupplierItem] = []
    # ── 备件属性（可选，建议传全）──
    project_no: str = ''
    project_name: str = ''
    part_type: str = ''
    brand: str = ''
    pn: str = ''
    spec: str = ''
    condition: str = ''
    address: str = ''
    latest_ship_time: str = ''
    urgent: str = ''

class SupplierBody(BaseModel):
    name: str
    email: str
    capability: Optional[str] = ''

class ProcContractBody(BaseModel):
    contract_no: str
    contract_name: Optional[str] = ''
    pm_name: Optional[str] = ''
    pm_email: Optional[str] = ''
    receiver_name: Optional[str] = ''
    receiver_phone: Optional[str] = ''
    receiver_address: Optional[str] = ''

class ProcContractUpdateBody(BaseModel):
    contract_no: Optional[str] = None
    contract_name: Optional[str] = None
    pm_name: Optional[str] = None
    pm_email: Optional[str] = None
    receiver_name: Optional[str] = None
    receiver_phone: Optional[str] = None
    receiver_address: Optional[str] = None

class SparePartBody(BaseModel):
    part_code: str
    part_name: str
    spec_model: str = ''
    brand: str = ''
    unit: str = '个'
    category: str = '通用'
    condition: str = ''
    remark: str = ''
@router.get("/api/procurement/tasks")
def api_proc_task_list(status: Optional[str] = None, source: Optional[str] = None, keyword: Optional[str] = None):
    """列出询比价任务（支持 状态 / 来源 / 关键词 过滤）。
    source 如 ?source=email（邮件来源）/ page（页面）/ agent（Agent对话）→ 归一为 邮件/页面/Agent对话。
    2026-08-29 起「备件邮件询价」观察面板改读本端点 source=email。
    """
    return {"success": True, "data": list_tasks(status=status, source=source, keyword=keyword)}

@router.get("/api/procurement/tasks/{task_id}")
def api_proc_task_get(task_id: str):
    t = get_task(task_id)
    if not t:
        return JSONResponse({"success": False, "error": "任务不存在"}, status_code=404)
    t['_op_logs'] = list_op_logs(task_id)
    return {"success": True, "data": t}

@router.post("/api/procurement/tasks")
def api_proc_task_create(body: NewTaskBody):
    """新建询价任务：落库 + 操作日志 + 触发 neuops 智能体发询价邮件+飞书通知
    若未传 inquiry_supplier_list，create_task 会自动从供应商资源池全量带出
    """
    try:
        t = create_task(
            contract_no=body.contract_no, spare_part_model=body.spare_part_model,
            purchase_qty=body.purchase_qty, emergency_level=body.emergency_level,
            inquiry_supplier_list=[s.dict() for s in body.inquiry_supplier_list] if body.inquiry_supplier_list else None,
            creator='pm',
            # 备件属性：前端建议传全。缺失时智能体按模板 B 组询价邮件会缺变量，
            # 标题/正文由 LLM 自由发挥（历史上出现过渲染成空括号的失控标题）。
            # urgent 缺省用 emergency_level 兜底，保证询价时限始终有值。
            project_no=body.project_no, project_name=body.project_name,
            part_type=body.part_type, brand=body.brand, pn=body.pn,
            spec=body.spec, condition=body.condition, address=body.address,
            latest_ship_time=body.latest_ship_time,
            urgent=body.urgent or body.emergency_level,
        )
        # 触发 neuops emp-008：flow-proc-01(已落库) + flow-proc-02(发询价邮件+飞书通知)
        agent_r = trigger_neuops("trigger/task-created", t)
        return {"success": True, "data": t, "agent_trigger": agent_r}
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

@router.post("/api/procurement/tasks/agent")
def api_proc_task_create_agent(body: AgentNewTaskBody):
    """智能体创建任务（对话入口）：直接传业务字段，走标准 create_task + trigger_neuops。
    保证 task_id 格式、reply_deadline 自动计算、操作日志、flow-proc-01/02 触发。"""
    try:
        t = create_task(
            contract_no=body.contract_no, spare_part_model=body.spare_part_model,
            purchase_qty=body.purchase_qty, emergency_level=body.emergency_level,
            inquiry_supplier_list=body.inquiry_supplier_list or None,
            creator=body.creator,
        )
        # 触发 neuops emp-008：flow-proc-01(已落库) + flow-proc-02(发询价邮件+飞书通知)
        agent_r = trigger_neuops("trigger/task-created", t)
        return {"success": True, "data": t, "agent_trigger": agent_r}
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

@router.post("/api/procurement/tasks/{task_id}/select")
def api_proc_task_select(task_id: str, body: SelectBody):
    """选型确认：落库 + 触发 neuops 发采购确认邮件+飞书通知"""
    try:
        t = confirm_selection(
            task_id=task_id,
            selected_supplier=body.selected_supplier.dict(),
            deal_unit_price=body.deal_unit_price,
            operator='pm',
        )
        # 触发 neuops emp-008：flow-proc-05(发采购确认邮件+飞书通知)
        # 透传 source：card_callback 场景下 flow-proc-05 会跳过 confirm_purchase 新卡片通知，
        # 避免与 card-callback 返回的就地替换置灰卡片造成双卡片
        agent_r = trigger_neuops("trigger/task-selected", {
            "task": t, "selected_supplier": body.selected_supplier.dict(),
            "deal_unit_price": body.deal_unit_price,
            "source": body.source or "web",
        })
        return {"success": True, "data": t, "agent_trigger": agent_r}
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

@router.post("/api/procurement/tasks/{task_id}/test")
def api_proc_task_test(task_id: str, body: TestResultBody):
    """测试结果录入：落库 + 触发 neuops 闭环/告警+飞书通知"""
    try:
        t = input_test_result(
            task_id=task_id, test_result=body.test_result,
            remark=body.remark, operator='pm',
        )
        agent_r = trigger_neuops("trigger/test-result", {
            "task": t, "test_result": body.test_result, "remark": body.remark,
            "source": body.source or "web",
        })
        return {"success": True, "data": t, "agent_trigger": agent_r}
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

@router.post("/api/procurement/tasks/{task_id}/cancel")
def api_proc_task_cancel(task_id: str, body: CancelBody):
    """任务取消：落库 + 触发 neuops 飞书通知取消"""
    try:
        t = cancel_task(task_id=task_id, cancel_reason=body.cancel_reason, operator='pm')
        agent_r = trigger_neuops("trigger/task-canceled", {
            "task": t, "cancel_reason": body.cancel_reason,
            "source": body.source or "web",
        })
        return {"success": True, "data": t, "agent_trigger": agent_r}
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

@router.get("/api/procurement/tasks/{task_id}/logs")
def api_proc_task_logs(task_id: str):
    return {"success": True, "data": list_op_logs(task_id)}

@router.patch("/api/procurement/tasks/{task_id}/quote/manual")
def api_proc_task_quote_manual(task_id: str, body: ManualQuoteBody):
    """前端铅笔按钮：人工录入/修改某供应商报价。保存后 is_manual=True，后续 IMAP 复解析不会覆盖。"""
    try:
        t = manual_update_supplier_quote(
            task_id=task_id, reply_index=body.reply_index,
            payload={
                "unit_price": body.unit_price, "total_price": body.total_price,
                "lead_time": body.lead_time, "brand": body.brand,
                "model": body.model, "note": body.note,
            },
            operator="frontend:user",
        )
        return {"success": True, "data": t}
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

@router.get("/api/procurement/ledger")
def api_proc_ledger_list(contract_no: Optional[str] = None,
                         supplier_name: Optional[str] = None,
                         from_date: Optional[str] = None,
                         to_date: Optional[str] = None,
                         limit: int = 500):
    """采购业务台账（增强查询：合同 / 供应商 / 日期范围 / 条数上限）"""
    rows = list_ledger_advanced(contract_no=contract_no,
                                supplier_name=supplier_name,
                                from_date=from_date, to_date=to_date, limit=limit)
    return {"success": True, "data": rows}

@router.get("/api/procurement/suppliers")
def api_proc_suppliers_list(keyword: Optional[str] = None, limit: int = 500):
    """供应商主数据列表（支持 名称/邮箱/供货能力 关键词模糊搜索）"""
    return {"success": True, "data": list_suppliers(keyword=keyword, limit=limit)}

@router.get("/api/procurement/suppliers/{supplier_id}")
def api_proc_suppliers_get(supplier_id: int):
    s = get_supplier(supplier_id)
    if not s:
        return JSONResponse({"success": False, "error": "供应商不存在"}, status_code=404)
    return {"success": True, "data": s}

@router.post("/api/procurement/suppliers")
def api_proc_suppliers_create(body: SupplierBody):
    try:
        s = create_supplier(name=body.name, email=body.email,
                            capability=body.capability or '')
        return {"success": True, "data": s}
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

@router.put("/api/procurement/suppliers/{supplier_id}")
def api_proc_suppliers_update(supplier_id: int, body: SupplierUpdateBody):
    try:
        s = update_supplier(supplier_id=supplier_id, name=body.name,
                            email=body.email, capability=body.capability)
        if s is None:
            return JSONResponse({"success": False, "error": "供应商不存在"}, status_code=404)
        return {"success": True, "data": s}
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

@router.delete("/api/procurement/suppliers/{supplier_id}")
def api_proc_suppliers_delete(supplier_id: int):
    try:
        r = delete_supplier(supplier_id)
        return {"success": True, **r}
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

@router.get("/api/procurement/contracts")
def api_proc_contracts_list(keyword: Optional[str] = None, limit: int = 500):
    """合同主数据列表：按 合同编号 / 合同名 / 项目经理名 / 邮箱 搜索"""
    return {"success": True, "data": list_contracts(keyword=keyword, limit=limit)}

@router.get("/api/procurement/contracts/{contract_id}")
def api_proc_contracts_get(contract_id: int):
    s = get_contract(contract_id=contract_id)
    if not s:
        return JSONResponse({"success": False, "error": "合同不存在"}, status_code=404)
    return {"success": True, "data": s}

@router.post("/api/procurement/contracts")
def api_proc_contracts_create(body: ProcContractBody):
    try:
        c = proc_create_contract(
            contract_no=body.contract_no,
            contract_name=body.contract_name or '',
            pm_name=body.pm_name or '',
            pm_email=body.pm_email or '',
            receiver_name=body.receiver_name or '',
            receiver_phone=body.receiver_phone or '',
            receiver_address=body.receiver_address or '',
        )
        return {"success": True, "data": c}
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

@router.put("/api/procurement/contracts/{contract_id}")
def api_proc_contracts_update(contract_id: int, body: ProcContractUpdateBody):
    try:
        c = update_contract(contract_id=contract_id, contract_no=body.contract_no,
                            contract_name=body.contract_name, pm_name=body.pm_name,
                            pm_email=body.pm_email,
                            receiver_name=body.receiver_name, receiver_phone=body.receiver_phone,
                            receiver_address=body.receiver_address)
        if c is None:
            return JSONResponse({"success": False, "error": "合同不存在"}, status_code=404)
        return {"success": True, "data": c}
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

@router.delete("/api/procurement/contracts/{contract_id}")
def api_proc_contracts_delete(contract_id: int):
    try:
        r = proc_delete_contract(contract_id)
        return {"success": True, **r}
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

@router.get("/api/procurement/mail-cc")
def api_proc_mailcc_list(keyword: Optional[str] = None):
    return {"success": True, "data": list_mail_cc(keyword=keyword)}

@router.get("/api/procurement/mail-cc/emails")
def api_proc_mailcc_emails_plain():
    """给 neuops 调用的极简接口：只返回 CC 列表，不包裹 success/data。"""
    return {"cc": get_all_cc_emails()}

@router.post("/api/procurement/mail-cc")
def api_proc_mailcc_create(body: ProcMailCCBody):
    try:
        r = create_mail_cc(name=body.name, email=body.email)
        return {"success": True, "data": r}
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

@router.delete("/api/procurement/mail-cc/{cc_id}")
def api_proc_mailcc_delete(cc_id: int):
    try:
        r = delete_mail_cc(cc_id)
        return {"success": True, **r}
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

@router.get("/api/procurement/spare-parts")
def api_proc_spare_parts(keyword: str = Query(None), category: str = Query(None)):
    rows = list_spare_parts(keyword=keyword, category=category)
    return {"success": True, "data": rows, "total": len(rows)}

@router.get("/api/procurement/spare-parts/categories")
def api_proc_spare_part_categories():
    cats = list_spare_part_categories()
    return {"success": True, "data": cats}

@router.get("/api/procurement/spare-parts/{part_id}")
def api_proc_spare_part_get(part_id: int):
    r = get_spare_part(part_id)
    if not r:
        return JSONResponse({"success": False, "error": "备件不存在"}, status_code=404)
    return {"success": True, "data": r}

@router.post("/api/procurement/spare-parts")
def api_proc_spare_part_create(body: SparePartBody):
    try:
        r = create_spare_part(
            part_code=body.part_code, part_name=body.part_name,
            spec_model=body.spec_model, brand=body.brand,
            unit=body.unit, category=body.category,
            condition=body.condition, remark=body.remark)
        return {"success": True, "data": r}
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

@router.put("/api/procurement/spare-parts/{part_id}")
def api_proc_spare_part_update(part_id: int, body: SparePartBody):
    try:
        r = update_spare_part(part_id,
                              part_code=body.part_code, part_name=body.part_name,
                              spec_model=body.spec_model, brand=body.brand,
                              unit=body.unit, category=body.category,
                              condition=body.condition, remark=body.remark)
        return {"success": True, "data": r}
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

@router.delete("/api/procurement/spare-parts/{part_id}")
def api_proc_spare_part_delete(part_id: int):
    try:
        r = delete_spare_part(part_id)
        return {"success": True, **r}
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)
