# -*- coding: utf-8 -*-
"""LLM 决策回路（KNO-R-02 v2，本体知识层 azone）。
LLM 读取「本体 ABox 事实 + 动作定义/条件/不变量 + 全局不变量」，自主提议下一步动作并给理由；
由 ontology.validate_action 基于 ABox 事实裁决可执行性，不合法则带原因重问；不可用则回退规则式。

LLM 只做选择与编排（读本体语义做决策）；计算/持久化/邮件网关不交 LLM（DET-R-01）。
"""
import json
import os

from . import ontology as onto
from .decision import propose_action


def _fallback(ctx, note="LLM不可用/未收敛，回退规则式"):
    aid, ex, inn, reason = propose_action(ctx)
    return aid, reason or note, False


def _facts_prompt(abox: dict) -> str:
    return json.dumps(abox, ensure_ascii=False, default=str)


def build_system_prompt() -> str:
    """把体知识层（概念/关系/动作规范/不变量）序列化为 LLM 系统指令。"""
    act_lines = []
    for aid, spec in onto.ACTIONS.items():
        act_lines.append(
            f"- {aid}：{spec.get('定义','')}\n"
            f"    条件(必须全部满足才能选): {spec.get('条件')}\n"
            f"    效果: {spec.get('效果','')}\n"
            f"    不变量: {spec.get('不变量') or '无'}")
    inv_lines = "\n".join(f"  - {i['id']}: {i['desc']}" for i in onto.INVARIANTS)
    return (
        "你是本体化备件询价智能体 emp-009 的决策核心。当前是一个可执行动作集合，你必须：\n"
        "1) 依据给定的『当前任务事实(ABox)』自主判断下一步该执行哪个动作并给出一句话理由；\n"
        "2) 只能输出 JSON：{\"action\": \"<动作id>\", \"reason\": \"一句话理由\"}，不要多余文字/代码块；\n"
        "3) 选的动作必须『条件』全部满足、且不违反任何『不变量』/全局不变量；\n"
        "4) 拿不准就选最保守、不产生新动作、不重复的动作；宁可等待也不要乱发信。\n\n"
        "【动作注册表(含业务定义/条件/效果/不变量)】\n" + "\n".join(act_lines) +
        "\n【全局不变量(恒成立，任何动作不得违反)】\n" + inv_lines +
        "\n【本体概念/关系参考】\n" + json.dumps(onto.CONCEPTS, ensure_ascii=False) +
        "\n" + json.dumps(onto.RELATIONS, ensure_ascii=False)
    )


def _ask_llm_action(allowed: list, sys_prompt: str, user_msg: str, rejections: list):
    """调用 DeepSeek 让其从 allowed 中继续选择动作；失败返回 None。"""
    try:
        from .config import (load_deepseek_key, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL)
    except Exception:
        return None
    key = load_deepseek_key()
    if not key:
        return None
    import httpx
    messages = [{"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_msg}]
    if rejections:
        messages.append({"role": "assistant", "content": "（系统提示）以下动作被校验拒绝，请换一个："
                           + json.dumps(rejections, ensure_ascii=False)})
    try:
        r = httpx.post(
            f"{DEEPSEEK_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": DEEPSEEK_MODEL, "messages": messages, "temperature": 0.1},
            timeout=40)
        content = r.json()["choices"][0]["message"]["content"]
        s, e = content.find("{"), content.rfind("}")
        obj = json.loads(content[s:e + 1]) if s >= 0 and e > s else {}
        action = str(obj.get("action") or "").strip()
        if action in allowed:
            return {"action": action, "reason": str(obj.get("reason") or "").strip()}
    except Exception:
        pass
    return None


def llm_decide_action(ctx: dict, task: dict = None, max_tries: int = 3):
    """LLM 提议(读ABox+语义规则) → ontology.validate_action 裁决 → 带原因重问 → 兜底规则。
    返回 (action_id, reason, via_llm)。"""
    use_llm = os.getenv("ONT_USE_LLM", "1") == "1"
    if not use_llm:
        return _fallback(ctx)
    abox = onto.build_abox(task) if task else _abox_from_ctx(ctx)
    allowed = onto.list_action_ids()
    sys_prompt = build_system_prompt()
    user_msg = "当前任务事实(ABox)：\n" + _facts_prompt(abox)
    rejections = []
    for _ in range(max_tries):
        cand = _ask_llm_action(allowed, sys_prompt, user_msg, rejections)
        if not cand:
            break
        ok, why = onto.validate_action(cand["action"], abox)
        if ok:
            return cand["action"], cand["reason"], True
        rejections.append({"action": cand["action"], "rejected": why})
    return _fallback(ctx)


def _abox_from_ctx(ctx: dict) -> dict:
    """没有 task dict 时，从 ctx 构造最小 ABox（兼容独立调用）。"""
    return {
        "task_id": ctx.get("task_id") or "OT-?",
        "status": "INIT",
        "from_email": ctx.get("from_email") or "",
        "internal_status": ctx.get("internal_status"),
        "external_status": ctx.get("external_status"),
        "part": {"pn": ctx.get("pn"), "count": ctx.get("count"), "brand": ctx.get("brand"),
                 "part_type": ctx.get("part_type"), "condition": ctx.get("condition"),
                 "project_no": ctx.get("project_no"), "project_name": ctx.get("project_name"),
                 "spec": ctx.get("spec"), "address": ctx.get("address"), "urgent": ctx.get("urgent")},
        "quote_count": ctx.get("valid_quote_count", 0),
        "quotes": ctx.get("valid_quotes") or [],
        "target_supplier_list": ctx.get("target_supplier_list") or [],
        "inquiry_sent": ctx.get("external_status") in ("INVITE_QUOTE", "R_WAIT_QUOTES"),
        "approval_sent": ctx.get("internal_status") in ("R_APPROVAL",),
        "target_supplier_set": bool(ctx.get("target_supplier") or ctx.get("approval_choice")),
        "order_sent": ctx.get("external_status") in ("ORDER_CONFIRM", "R_WAIT_SHIPPING"),
        "tracking_number": ctx.get("tracking_number_candidate") or "",
        "engineer_feedback_finished": bool(ctx.get("engineer_close")),
        "deadline_passed": bool(ctx.get("deadline_passed")),
    }