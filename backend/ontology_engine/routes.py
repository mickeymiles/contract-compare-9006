# -*- coding: utf-8 -*-
"""本体轨（NO-012 emp-009）HTTP 路由：健康/对齐 tick/查询/emp-009 展示。
独立 FastAPI router；挂载到 main.py，与现轨 /api/procurement-agent/* 并存。
"""
from fastapi import APIRouter, Request
import asyncio
import threading

from . import store, actions as act, engine
from .decision import build_fact_context, propose_action

router = APIRouter(prefix="/api/ontology-emp009", tags=["ontology-emp009"])

# 进程级串行锁：run-full（可能含 LLM 决定）在 async 事件循环中经 to_thread 执行，串行化防并发重复发信。
# 【修复】原用 asyncio.Lock：它在模块导入时绑定到当时的事件循环，
# 而请求处理发生在 uvicorn 的运行期循环，导致
# "Task got Future attached to a different loop" → 500。
# 改用 threading.Lock（不绑定 loop），且在工作线程内部获取，不阻塞事件循环。
_RUN_LOCK = threading.Lock()


@router.get("/health")
def health():
    return {"service": "emp-009", "rotor": "ontology", "status": "ok",
            "tables": ["o_session", "o_task", "o_person", "o_email",
                       "o_supplier_quote", "o_audit_log", "o_alignment"]}


@router.get("/actions")
def list_actions():
    return {"total": len(act.list_action_ids()), "actions": act.ACTION_REGISTRY}


@router.get("/rules")
def list_rules():
    return {"total": len(knowledge_rules()), "rules": knowledge_rules()}


@router.get("/spec")
def spec():
    """导出本体定义（TBox）为 JSON，供「本体可观测」页只读展示。

    CONCEPTS / RELATIONS / ACTIONS / INVARIANTS 在 ontology.py，RULES 在 knowledge.py，
    ACTION_REGISTRY 在 actions.py —— 都是 Python 字面量、不落库，故只能由本端点导出。
    迁移后 TBox 与本端点同进程，可观测页直接进程内取用（见 ontology_gateway.spec）。
    """
    from . import knowledge, ontology
    return {
        "success": True,
        "service": "emp-009",
        "concepts": ontology.CONCEPTS,
        "relations": ontology.RELATIONS,
        "actions": ontology.ACTIONS,
        "invariants": ontology.INVARIANTS,
        "rules": knowledge.RULES,
        "action_registry": act.ACTION_REGISTRY,
    }


def knowledge_rules():
    from . import knowledge
    return knowledge.RULES


@router.get("/propose/{task_id}")
def propose(task_id: str):
    """对一个现轨任务做本体轨只读提议（不执行）。

    现轨任务源已从 neuops 的 spare_mail_task 迁到本工程的 procurement_task
    （字段映射见 legacy_track.py）。"""
    from .legacy_track import get_task
    task = get_task(task_id)
    if not task:
        return {"success": False, "error": "task not found"}
    ctx = build_fact_context(task)
    action_id, next_ext, next_int, reason = propose_action(ctx)
    return {"success": True, "task_id": task_id, "proposed_action": action_id,
            "next_external": next_ext, "next_internal": next_int, "reason": reason}


@router.post("/scheduler/tick")
async def tick(request: Request):
    """Stage A：只读对照——对现轨活动任务做本体轨决策对比，不执行副作用。"""
    body = {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    dry_run = bool(body.get("dry_run", True))
    from .legacy_track import list_tasks as legacy_list_tasks
    tasks = legacy_list_tasks(page_size=500)
    active = [t for t in tasks if (t.get("status") or "") not in ("REJECTED",)]
    summary = engine.run_alignment(active, dry_run=dry_run)
    return {"success": True, "mode": "stage-A-read-only", "summary": summary}


@router.get("/alignment")
def alignment(limit: int = 100):
    return {"success": True, "records": store.list_alignment(limit=limit)}


@router.get("/audit")
def audit(biz_type: str = "", biz_id: str = "", limit: int = 100):
    return {"success": True, "records": store.list_audit(biz_type=biz_type or None,
                                                          biz_id=biz_id or None, limit=limit)}


@router.get("/tasks")
def list_tasks():
    return {"success": True, "tasks": store.list_tasks()}


@router.get("/claim-state")
def claim_state():
    """认领健康度：扫描水位 + 未闭环邮件。

    `unclaimed` 非空说明有询价邮件已登记但任务未建成（pending/failed）——
    这些下一轮会自动重试；若数量长期不降，说明存在稳定失败，需人工介入。
    `watermark` 是上次成功扫描完成的时刻，用于停机后把扫描下界前移、防漏单。
    """
    import time as _t

    from .ingest import SCAN_KEY, scan_window
    ts = store.get_scan_ts(SCAN_KEY)
    from .config import ONT_SCAN_HOURS as _h
    unclaimed = store.list_unclaimed_emails()
    return {
        "success": True,
        "watermark_ts": ts,
        "watermark": (_t.strftime("%Y-%m-%d %H:%M:%S", _t.localtime(ts)) if ts else ""),
        "scan_hours": _h,
        "next_scan_since": _t.strftime("%Y-%m-%d %H:%M:%S", _t.localtime(scan_window(_h))),
        "unclaimed_count": len(unclaimed),
        "unclaimed": unclaimed,
    }


@router.post("/tasks/{task_id}/close")
async def close_task(task_id: str, request: Request):
    """操作员手动关闭/取消本体轨任务（不进邮件链路）。供经营管理平台「台账/任务列表」调用。"""
    from . import execution
    body = {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    task = store.get_task(task_id)
    if not task:
        return {"success": False, "error": "task not found"}
    ctx = {"operator": body.get("operator", "web"),
           "manual_close_reason": body.get("reason", "")}
    # force=True：显式人工动作不受 governor 灰度开关限制
    ok, detail = execution.execute_action("manualCloseTask", task, ctx, force=True)
    return {"success": ok, "task_id": task_id, "detail": detail}


# ── 阶段 B 治理 / 受控执行 ──────────────────────────────────────────

@router.get("/governor")
def get_governor():
    from . import execution
    return {"success": True, "governor": execution.governor()}


@router.post("/governor")
async def set_governor(request: Request):
    body = await request.json()
    from . import execution
    llm_val = body.get("llm")
    try:
        g = execution.set_governor(mode=body.get("mode", "off"),
                                   roll=float(body.get("roll", 0)),
                                   exec_enabled=bool(body.get("exec_enabled", False)),
                                   llm=(llm_val if llm_val is None else bool(llm_val)))
        return {"success": True, "governor": g}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/run")
async def run_managed(request: Request):
    """受控执行：在 governor 放行下，采集新工程师询价→建 O_Task→发询价B。
    use_llm=true 走 LLM 决策。默认仅能力演示，governor=off 时不产生任何变更。"""
    body = await request.json()
    use_llm = bool(body.get("use_llm", False))
    from .ingest import fetch_new_inquiry_facts
    from . import mail_gateway as mg, execution, store
    from .engine import decide_action
    try:
        facts = fetch_new_inquiry_facts(mg, hours=int(body.get("hours", 2)), store=store)
    except Exception as e:
        return {"success": False, "error": f"inbox scan failed: {e}"}
    created, executed = [], []
    for it in facts:
        fields = it["fields"]
        ctx = dict(fields)
        aid, reason, via_llm = decide_action(ctx, use_llm=use_llm)
        # 建任务占位（O_Task）
        tid = f"OT-{shake(fields.get('message_id'))}"
        task = {"task_id": tid, "from_email": fields.get("from_email", ""),
                "threat_msg_id": fields.get("message_id", ""), "urgency_raw": fields.get("urgent", ""),
                "status": "PRE", "mode": "ontology", "spare_info": fields,
                "internal_status": "R_INIT", "external_status": "R_SEND"}
        created.append({"task_id": tid, "proposed_action": aid, "reason": reason, "via_llm": via_llm})
        if execution.needs_exec():
            ok, detail = execution.execute_action(aid, task, ctx, mg=mg, force=False)
            executed.append({"task_id": tid, "ok": ok, "detail": detail})
        elif fields.get("from_email"):
            # 未放行时也建 O_Task 占位（仅诊断，不触发真实发信）
            execution.execute_action("createTask", task, ctx, mg=mg, force=True)
    return {"success": True, "facts": len(facts), "created": created, "executed": executed,
            "governor": execution.governor()}


@router.post("/run-full")
async def run_full(request: Request):
    """本体轨全流程自走：SEEN 认领新询价 + 入向回复归集 + LLM/规则决策执行。
    仅 governor=ontology/split 且 exec=True 时真正发信/落库；否则零副作用。

    注意：决策可能调用 LLM（阻塞式 http），故放到线程池执行，避免冻结 async 事件循环；
    并用进程级锁串行化，防止「定时调度 + 手动触发」并发对同一任务重复发信。"""
    body = await request.json()
    use_llm = bool(body.get("use_llm", False))
    from . import orbit, mail_gateway as mg, execution
    if not execution.needs_exec():
        # 未放行两类原因：① governor 未开（ONT_MODE/ONT_EXEC/ONT_LLM）；
        # ② 数字员工 emp-009 在「数字员工配置」中被停用。两者都会让常驻调度零副作用。
        return {"success": True, "note": "governor 未放行或数字员工已停用",
                "claim": [], "replies": [], "drive": [], "governor": execution.governor(),
                "employee_managed": execution._employee_managed()}
    def _locked_run():
        # 锁在线程内部获取：既串行化，又不会因等锁而阻塞 async 事件循环
        with _RUN_LOCK:
            return orbit.run_full(mg, use_llm=use_llm)
    try:
        r = await asyncio.to_thread(_locked_run)
        return {"success": True, **r}
    except Exception as e:
        return {"success": False, "error": str(e)}


def shake(s: str) -> str:
    import hashlib
    return hashlib.md5((s or "x").encode()).hexdigest()[:8].upper()