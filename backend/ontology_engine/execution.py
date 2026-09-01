# -*- coding: utf-8 -*-
"""动作执行器 + 治理开关（阶段 B）。
动作真正的执行（发信/建 O_Task/更新状态）都在此；是否真的发信/落库由 Governor 决定。
Governor 默认 'off'（不接管、不执行任何变更，零影响现轨）；灰度测试时再置 'split/all'。
默认全程 dry_run=False 但 Governor 未开时禁止执行。

数据来源：mail_gateway（本轨独立邮箱收发）、审批人/供应商主数据（只读，见 party_config）。
"""
import os
import time

from . import store, mail_tpl
from .config import settlement_enabled

# 治理：本轨默认 off（不接管、不执行变更，零影响现轨，本体轨暂停改走传统状态机）。
# 需要时可用 ONT_MODE / ONT_EXEC / ONT_LLM 开启。
_GOV = {"mode": os.getenv("ONT_MODE", "off"), "roll": float(os.getenv("ONT_ROLL", "0")),
        "exec": os.getenv("ONT_EXEC", "0") == "1", "llm": os.getenv("ONT_LLM", "0") == "1"}

# 本体轨数字员工实体（与 agent_registry.py 保持一致）
_EMP_ID = "emp-009"
_SKILL_ID = "skill-ont-proc-inquiry"


def set_governor(mode: str = "off", roll: float = 0.0, exec_enabled=False, llm: bool = None):
    """mode: off|legacy|ontology|split。roll∈[0,1]=分给本体轨比例。exec_enabled=允许真实发信/落库。
    llm=None 保持现值；True→LLM 决策接管并执行；False→规则驱动(可开影子对齐)。"""
    if mode not in ("off", "legacy", "ontology", "split"):
        raise ValueError("mode must be off|legacy|ontology|split")
    g = {"mode": mode, "roll": max(0.0, min(1.0, roll)), "exec": bool(exec_enabled)}
    if llm is not None:
        g["llm"] = bool(llm)
    _GOV.update(g)
    return dict(_GOV)


def governor():
    return dict(_GOV)


def _employee_managed() -> bool:
    """数字员工 emp-009 及其关联技能在 DB 中是否启用。

    这是「开关在数字员工身上」的真实生效点：把开关置否，
    运行时即停止执行（无需改 .env / 脚本 / 重启）。

    向后兼容：状态尚未登记（新库/测试库）时按历史默认放行。
    """
    try:
        from . import agent_registry
        return agent_registry.employee_managed()
    except Exception:
        # 本体库不可达等异常按历史默认放行（与迁移前 employees 表缺失时一致）
        return True


def _is_managed() -> bool:
    return _GOV["mode"] in ("ontology", "split") and _GOV["exec"] and _employee_managed()


def needs_exec(force: bool = False) -> bool:
    if force:
        return True
    return _is_managed()


def _deadline(urgent_raw: str):
    """时长换算（DET-R-01 确定性代码，不交 LLM）：xHH/xMN/xD 或 latest xh/x天。失败兜底24h。"""
    s = (urgent_raw or "").strip().lower()
    try:
        if not s:
            return int(time.time()) + 24 * 3600
        num = int(re_num(s))
        if "d" in s or "天" in s:
            return int(time.time()) + num * 86400
        if "mn" in s or "min" in s or "分" in s:
            return int(time.time()) + num * 60
        if "h" in s or "小" in s:
            return int(time.time()) + num * 3600
        return int(time.time()) + num * 3600
    except Exception:
        return int(time.time()) + 24 * 3600


import re as _re
def re_num(s):
    m = _re.search(r"\d+", s)
    return m.group(0) if m else "1"


def _suppliers_from_config(cfg_leak):
    return cfg_leak or []


def _self_email():
    """本体轨自身发件邮箱（用于 Reply-All 排除）。

    必须取本体轨自己的邮箱（ONT_MAIL_*，即 b4）；若仍取现轨的 b3，
    Reply-All 时不会把 b4 自己排除，智能体会给自己发信造成自激循环。
    """
    try:
        from .mail_gateway import _ont_mail_cfg
        return (_ont_mail_cfg() or {}).get("mail_username") or ""
    except Exception:
        return ""


def _send_tpl(mg, tpl_key, ctx, task, *, to, cc=None, reply_to=None, refs=None,
              original_body=None, reply_all_from=None):
    """按模板渲染并发信；携带原文（===）、线程头（In-Reply-To/References）、可选 Reply-All。
    返回 (ok, detail, sent_r)。"""
    subj, body = mail_tpl.render(tpl_key, ctx, task)
    if original_body:
        body += mail_tpl.quote_orig(original_body)
    if reply_all_from:
        to, cc = mail_tpl.reply_recipients(reply_all_from, to, cc=cc, self_email=_self_email())
    r = mg.send_mail(to=to, subject=subj, body_text=body, cc=cc or None,
                     reply_to_mail_id=reply_to or None, reply_refs_chain=refs or None)
    return True, f"mail {tpl_key} sent", (r or {})


def _sel_quote(meta, target):
    """按选中供应商邮箱取对应报价（含 msg_id/refs/raw/reply_all）。"""
    for q in (meta.get("quotes") or []):
        if str(q.get("email") or "").strip().lower() == str(target or "").strip().lower():
            return q or {}
    return {}


def execute_action(action_id: str, task: dict, ctx: dict, mg=None, force: bool = False, log=print):
    """执行一个动作。task 为 O_Task 镜像。返回 (ok, detail)。未包治理时只审计不执行。"""
    if not needs_exec(force):
        store.audit("Task", task.get("task_id"), f"block:{action_id}", operator="emp-009",
                    remark=f"governor={_GOV['mode']}/exec={_GOV['exec']}，未放行")
        return False, f"governor未放行 mode={_GOV['mode']}"

    if action_id == "createTask":
        store.upsert_task({**task, "status": "INIT", "mode": "ontology",
                           "quote_deadline": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(_deadline(ctx.get("urgent"))))})
        store.audit("Task", task["task_id"], "createTask", operator="emp-009", snapshot={"fields": ctx})
        return True, "task created"

    if action_id == "distributeInquiry" and mg:
        to = ctx.get("target_supplier_list") or []  # 已是 email 字符串列表
        b_mids = []
        by_sup = dict((task.get("spare_info") or {}).get("b_msg_by_supplier") or {})
        for email in to:
            subj, _body = mail_tpl.render("B", ctx, task)
            # B 也携带初始询价 A 的抄送观察者 + 系统配置抄送（两路都要携带）
            r = mg.send_mail(to=[email], subject=subj, body_text=_body,
                             cc=(ctx.get("inquiry_cc") or []) + (ctx.get("global_cc") or []) or None)
            _mid = (r or {}).get("message_id") or (r or {}).get("msg_id") if isinstance(r, dict) else ""
            if _mid:
                b_mids.append(_mid)
                by_sup[str(email).strip()] = _mid
        meta = dict(task.get("spare_info") or {})
        meta["b_msg_ids"] = list(dict.fromkeys(list(meta.get("b_msg_ids") or []) + b_mids))
        meta["b_msg_by_supplier"] = by_sup
        store.upsert_task({**task, "external_status": "INVITE_QUOTE", "spare_info": meta})
        store.audit("Task", task["task_id"], "distributeInquiry", operator="emp-009", snapshot={"to": to, "b_mids": b_mids})
        return True, "inquiry B sent"

    if action_id == "confirmOrderToSupplier" and mg:
        sel = str(ctx.get("target_supplier") or "").strip()
        meta = dict(task.get("spare_info") or {})
        q = _sel_quote(meta, sel)
        # E 订货：回复选中供应商报价(C)线程，携带其报价原文。
        # 主送=选中供应商，其余（发起人/审批人/观察者）一律抄送——不启用 Reply-All 的 To 合并，
        # 否则会把观察者也塞进主送。线程连续性由 reply_to/refs 保证。
        reply_to = (q.get("msg_id") or "").strip()
        refs = (q.get("refs") or "").strip() or ((meta.get("b_msg_by_supplier") or {}).get(sel) or "")
        ok, detail, r = _send_tpl(mg, "E", ctx, task, to=[sel],
                                  cc=[ctx.get("from_email")] + (ctx.get("approver_emails") or [])
                                     + (ctx.get("inquiry_cc") or []) + (ctx.get("global_cc") or []),
                                  reply_to=reply_to or None, refs=refs or None,
                                  original_body=q.get("raw"))
        meta["e_msg_id"] = ((r or {}).get("message_id") or (r or {}).get("msg_id")
                            if isinstance(r, dict) else "") or meta.get("e_msg_id", "")
        store.upsert_task({**task, "external_status": "ORDER_CONFIRM", "internal_status": "R_APPROVAL", "spare_info": meta})
        store.audit("Task", task["task_id"], "confirmOrderToSupplier", operator="emp-009",
                    snapshot={"supplier": sel, "reply_to": reply_to, "refs": refs})
        return True, "order E sent"

    if action_id == "submitApproval" and mg:
        meta = dict(task.get("spare_info") or {})
        # D 内部流：回复工程师询价(A)线程，携带原始采购申请原文；To工程师 + Cc审批人
        ok, detail, r = _send_tpl(mg, "D", ctx, task, to=[ctx.get("from_email")],
                                  cc=(ctx.get("approver_emails") or []) + (ctx.get("inquiry_cc") or [])
                         + (ctx.get("global_cc") or []),
                                  reply_to=(meta.get("inquiry_mid") or "").strip() or None,
                                  refs=((meta.get("inquiry_refs") or "") + " " +
                                        (meta.get("inquiry_mid") or "")).strip() or None,
                                  original_body=meta.get("inquiry_raw"))
        meta["d_msg_id"] = ((r or {}).get("message_id") or (r or {}).get("msg_id")
                            if isinstance(r, dict) else "") or meta.get("d_msg_id", "")
        store.upsert_task({**task, "internal_status": "R_APPROVAL", "external_status": "R_DECIDING", "spare_info": meta})
        store.audit("Task", task["task_id"], "submitApproval", operator="emp-009")
        return True, "approval D sent"

    if action_id == "receiveTrackingNumber":
        store.upsert_task({**task, "external_status": "R_WAIT_SHIPPING",
                           "tracking_number": ctx.get("tracking_number_candidate", "")})
        store.audit("Task", task["task_id"], "receiveTrackingNumber", operator="emp-009",
                    snapshot={"tracking_no": ctx.get("tracking_number_candidate", "")})
        return True, "tracking recorded"

    if action_id == "engineerFinalClose":
        meta = dict(task.get("spare_info") or {})
        # 结算闭环开关（ONT_SETTLEMENT_ENABLED，默认关闭）：不向供应商发 G 结算邮件，
        # 仅把任务标记 CLOSED（不再发送任何邮件），预留后续启用。
        if not settlement_enabled():
            store.upsert_task({**task, "external_status": "R_CLOSED", "internal_status": "R_CLOSED",
                               "status": "CLOSED", "spare_info": meta})
            store.audit("Task", task["task_id"], "engineerFinalClose", operator="emp-009",
                        snapshot={"skipped": "settlement disabled: G not sent"})
            return True, "settlement disabled: task closed without G"
        if mg:
            sup = ctx.get("target_supplier") or meta.get("target_supplier") or ""
            q = _sel_quote(meta, sup)
            # G 结算：回复选中供应商报价(C)线程，携带报价原文。
            # 主送=供应商，其余（发起人/审批人/观察者）一律抄送——不启用 Reply-All 的 To 合并。
            # 线程连续性由 reply_to/refs 保证。
            reply_to = (q.get("msg_id") or "").strip()
            refs = (q.get("refs") or "").strip()
            orig = (q.get("raw") or "") + "\n" + (meta.get("ship_raw") or "")
            ok, detail, r = _send_tpl(mg, "G", ctx, task, to=[sup] if sup else [ctx.get("from_email")],
                                      cc=[ctx.get("from_email")] + (ctx.get("approver_emails") or [])
                                     + (ctx.get("inquiry_cc") or []) + (ctx.get("global_cc") or []),
                                      reply_to=reply_to or None, refs=refs or None,
                                      original_body=orig)
            meta["g_msg_id"] = ((r or {}).get("message_id") or (r or {}).get("msg_id")
                                if isinstance(r, dict) else "") or meta.get("g_msg_id", "")
        store.upsert_task({**task, "external_status": "R_SETTLE", "internal_status": "R_CLOSED",
                           "status": "CLOSED", "spare_info": meta})
        store.audit("Task", task["task_id"], "engineerFinalClose", operator="emp-009",
                    snapshot={"tracking_number": meta.get("tracking_no", ""), "g_msg_id": meta.get("g_msg_id")})
        return True, "task closed + settlement G"

    if action_id == "abortTask":
        meta = dict(task.get("spare_info") or {})
        if mg:
            # F 中止：回复工程师询价(A)线程，携带原始采购申请原文；To工程师 + Cc审批人
            _send_tpl(mg, "F", ctx, task, to=[ctx.get("from_email")],
                      cc=(ctx.get("approver_emails") or []) + (ctx.get("inquiry_cc") or [])
                         + (ctx.get("global_cc") or []),
                      reply_to=(meta.get("inquiry_mid") or "").strip() or None,
                      refs=((meta.get("inquiry_refs") or "") + " " +
                            (meta.get("inquiry_mid") or "")).strip() or None,
                      original_body=meta.get("inquiry_raw"))
        store.upsert_task({**task, "external_status": "CLOSED_ABORT", "status": "CLOSED", "spare_info": meta})
        store.audit("Task", task["task_id"], "abortTask", operator="emp-009")
        return True, "task aborted"

    if action_id == "requestQuoteClarification" and mg:
        un = ctx.get("unparseable_supplier_emails") or []
        meta = dict(task.get("spare_info") or {})
        by_sup = meta.get("b_msg_by_supplier") or {}
        for email in un:
            bmid = (by_sup.get(str(email).strip()) or "")
            subj = "Re: 【询价】报价需补充完整后重发"
            body = ("您好，收到您的回复但未能识别出完整报价，请按以下字段重新回复：\n"
                    f"备件：{ctx.get('part_type')} {ctx.get('brand')} {ctx.get('pn')} x {ctx.get('count')}\n"
                    "请务必注明：单价、货期、成色。谢谢配合！\n"
                    f"- NeuOps 备件询价(emp-009)\n任务编号：{task.get('task_id')}")
            mg.send_mail(to=[email], subject=subj, body_text=body,
                         reply_to_mail_id=bmid or None, reply_refs_chain=bmid or None)
        store.audit("Task", task["task_id"], "requestQuoteClarification", operator="emp-009",
                    snapshot={"suppliers": un})
        return True, "clarification requested"

    if action_id == "processApprovalDecision":
        meta = dict(task.get("spare_info") or {})
        meta["target_supplier"] = ctx.get("target_supplier", "") or ctx.get("approval_choice", "")
        store.upsert_task({**task, "internal_status": "R_APPROVAL", "spare_info": meta})
        store.audit("Task", task["task_id"], "processApprovalDecision", operator="emp-009",
                    snapshot={"target_supplier": meta["target_supplier"]})
        return True, "approval decision recorded"

    if action_id == "requestMissingFields" and mg:
        # 立项阶段缺必填字段 → 给工程师回信指出缺失项（仅一次）
        meta = dict(task.get("spare_info") or {})
        if meta.get("missing_requested"):
            store.audit("Task", task["task_id"], "requestMissingFields", operator="emp-009",
                        remark="已请求过补齐，跳过重发")
            return True, "missing-fields already requested"
        try:
            from . import knowledge
            ok, failed = knowledge.check_target("createTask", ctx)
            miss = [f.get("missing") for f in (failed or []) if f.get("missing")] or ["部分必填字段"]
        except Exception:
            miss = ["部分必填字段"]
        subj = "Re: 询价信息不完整，请补充后重发"
        body = ("您好，收到您的采购询价，但以下必填信息缺失，请补全后重发：\n- "
                + "\n- ".join(miss)
                + f"\n\n任务编号：{task.get('task_id')}\n- NeuOps 备件询价(emp-009)")
        mg.send_mail(to=[ctx.get("from_email")], subject=subj, body_text=body,
                     reply_to_mail_id=meta.get("inquiry_mid") or None,
                     reply_refs_chain=meta.get("inquiry_mid") or None)
        meta["missing_requested"] = True
        store.upsert_task({**task, "internal_status": "R_FR02_MISSING_FIELDS", "spare_info": meta})
        store.audit("Task", task["task_id"], "requestMissingFields", operator="emp-009",
                    snapshot={"missing": miss})
        return True, "missing fields requested"

    if action_id == "requestTrackingNo" and mg:
        # 供应商回"已发货"但无单号 → 主动索取（仅一次）
        meta = dict(task.get("spare_info") or {})
        if meta.get("tracking_requested_at"):
            return True, "tracking no already requested"
        sup = ctx.get("target_supplier") or meta.get("target_supplier") or ""
        if not sup:
            return False, "no target supplier for tracking request"
        subj = "Re: 请回复发货快递单号"
        body = ("您好，已收到贵司发货通知，请提供快递单号以便跟踪物流。\n"
                f"任务编号：{task.get('task_id')}\n- NeuOps 备件询价(emp-009)")
        mg.send_mail(to=[sup], subject=subj, body_text=body,
                     reply_to_mail_id=meta.get("e_msg_id") or None,
                     reply_refs_chain=meta.get("e_msg_id") or None)
        meta["tracking_requested_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        store.upsert_task({**task, "spare_info": meta})
        store.audit("Task", task["task_id"], "requestTrackingNo", operator="emp-009",
                    snapshot={"supplier": sup})
        return True, "tracking no requested"

    if action_id == "receiveSupplierQuote":
        # 报价收集由 process_replies 内联完成；此处仅落审计，避免 noop 误报
        store.audit("Task", task["task_id"], "receiveSupplierQuote", operator="emp-009",
                    remark="quote already recorded in process_replies")
        return True, "quote received (recorded in process_replies)"

    if action_id == "finalizeQuoteCollection":
        store.audit("Task", task["task_id"], "finalizeQuoteCollection", operator="emp-009")
        return True, "collection finalized (no-op state)"

    if action_id == "manualCloseTask":
        # 后台操作员手动关闭/取消（不在邮件链路）：写审计 + 置终态
        meta = dict(task.get("spare_info") or {})
        meta["manual_close"] = True
        meta["manual_close_reason"] = ctx.get("manual_close_reason", "")
        meta["manual_close_operator"] = ctx.get("operator", "web")
        store.upsert_task({**task, "external_status": "CLOSED_MANUAL", "status": "CLOSED", "spare_info": meta})
        store.audit("Task", task["task_id"], "manualCloseTask", operator=ctx.get("operator", "web"),
                    snapshot={"reason": meta["manual_close_reason"]})
        return True, "task manually closed"

    store.audit("Task", task.get("task_id"), f"noop:{action_id}", operator="emp-009",
                remark="action has no executor yet")
    return False, f"no executor for {action_id}"