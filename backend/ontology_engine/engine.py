# -*- coding: utf-8 -*-
"""决策循环调度（DRV-R-01）：读事实→选动作→规则校验→记录对齐/审计。
Stage A：dry_run=True（默认），只推理与记录，不执行发信等副作用。
"""
from . import knowledge, store
from .decision import build_fact_context, propose_action


def decide_action(ctx, use_llm: bool = False, task: dict = None):
    """统一决策入口：LLM 提议(读ABox+语义规则)+规则校验(KNO-R-02)，或规则式基线。返回 (action, reason, via_llm)。"""
    if use_llm:
        from .llm import llm_decide_action
        return llm_decide_action(ctx, task=task)
    aid, ex, inn, reason = propose_action(ctx)
    return aid, reason or "", False


def _legacy_desc(task):
    return {
        "internal_status": task.get("internal_status"),
        "external_status": task.get("external_status"),
        "latest_step": (task.get("latest_step") or "")[:60],
    }


def evaluate_task(task: dict, dry_run: bool = True):
    """对一个现轨 task 做本体轨只读对照评估。返回结果 dict；dry_run=True 不写任何业务态。"""
    ctx = build_fact_context(task)
    action_id, next_ext, next_int, reason = propose_action(ctx)
    pre_ok, failed = knowledge.check_target(action_id, ctx)

    res = {
        "task_id": task.get("task_id"),
        "legacy": _legacy_desc(task),
        "proposed_action": action_id,
        "next_external": next_ext,
        "next_internal": next_int,
        "reason": reason,
        "preconditions_ok": pre_ok,
        "preconditions_failed": failed,
        "aligned": pre_ok,
        "dry_run": dry_run,
    }
    # 终态一致性：现轨已 CLOSED/DONE 且动作也应达成终态
    legacy_status = str(task.get("status") or "")
    if legacy_status.upper() in ("DONE",) or str(task.get("internal_status")) in ("R_CLOSED",):
        res["aligned"] = (next_ext in ("CLOSED_ABORT",) or next_int == "R_CLOSED"
                          or legacy_status.upper() == "DONE")

    if task.get("task_id"):
        # 审计本体轨的"决策"（诊断性，不修改现轨业务数据）
        store.audit("Task", task.get("task_id"), f"propose:{action_id}",
                    operator="emp-009", snapshot=res["legacy"],
                    remark="stage-A read-only alignment")
    return res


def run_alignment(tasks, dry_run: bool = True):
    """对批任务做只读对照，并记录 o_alignment。返回汇总。"""
    records = []
    aligned = 0
    for t in tasks:
        r = evaluate_task(t, dry_run=dry_run)
        store.record_alignment(
            r["task_id"], r["legacy"].get("external_status"), r["legacy"].get("internal_status"),
            r["proposed_action"], r["next_external"], r["next_internal"], r["aligned"],
            diff=(r["reason"] if not r["preconditions_ok"] else r["next_external"] or ""))
        records.append(r)
        if r["aligned"]:
            aligned += 1
    total = len(records)
    return {
        "total": total,
        "aligned": aligned,
        "ratio": round(aligned / total, 4) if total else 1.0,
        "records": records,
    }