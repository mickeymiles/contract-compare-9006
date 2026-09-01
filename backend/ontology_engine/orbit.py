# -*- coding: utf-8 -*-
"""本体轨自走编排：SEEN 认领 + 入向回复归集 + 决策与执行（阶段 B/C）。
只有 Governor 放行（ontology/split + exec）才真正驱动；否则仅诊断。
状态与数据全部落在 O_*（独立于现轨 spare_mail_task）。
"""
import os
import re
import time
import json

from . import store, execution
from .config import settlement_enabled

_TERMINAL = ("CLOSED_ABORT", "CLOSED_MANUAL", "R_SETTLE")
_APPROVE_KW = ("确认", "采购", "同意", "采纳", "就选")
_REJECT_KW = ("拒绝", "不同意", "不选", "不采纳", "否决", "驳回", "不采购")
_CLOSE_KW = ("完成", "测试完毕", "更换完成", "采购结束")
_SHIP_KW = ("单号", "快递单号", "物流单号", "运单")
_REMIND_WINDOW = 3600  # 临期提醒窗口（秒）：截止前 1 小时主动催报价


# ── 截止时间（对齐现役轨 routes_procurement_agent.py:2700-2728 的口径）──
# 关键：基准取「邮件头 Date（发送方声明时间）」，不是扫描时刻。
# 用 time.time() 会让截止时间随轮询时机漂移，且任务重跑时结果不一致。
def _urgent_to_seconds(urgent: str) -> int:
    """紧急时长换算：5min / 2h / 3天 → 秒。无法识别兜底 24h。"""
    s = (urgent or "").strip().lower()
    m = re.search(r"(\d+)\s*(分钟?|min|m|小时?|h|天|d)", s)
    if not m:
        return 24 * 3600
    n = int(m.group(1))
    unit = m.group(2)
    if unit in ("分钟", "分", "min", "m"):
        return n * 60
    if unit in ("小时", "时", "h"):
        return n * 3600
    if unit in ("天", "d"):
        return n * 24 * 3600
    return n * 3600


def _mail_date_ts(mail: dict) -> int:
    """从邮件头 Date 取发送方声明时间；缺失时回退 receive_timestamp / now。"""
    d = (mail or {}).get("date") or (mail or {}).get("date_raw") or ""
    if d:
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(d)
            if dt.tzinfo is None:
                import datetime as _dt
                dt = dt.replace(tzinfo=_dt.timezone.utc)
            return int(dt.timestamp())
        except Exception:
            pass
    ts = int((mail or {}).get("receive_timestamp") or 0)
    return ts or int(time.time())


def _inquiry_deadline(mail: dict, urgent: str) -> str:
    """报价截止时间 = 邮件头 Date（发送时间）+ 紧急时长。"""
    from datetime import datetime
    base_ts = _mail_date_ts(mail)
    return datetime.fromtimestamp(base_ts + _urgent_to_seconds(urgent)).strftime("%Y-%m-%d %H:%M:%S")


def _deadline_passed(meta: dict) -> bool:
    """到点判定（现役轨:3435 同口径：all_replied or now >= deadline）。"""
    from datetime import datetime
    dl = (meta or {}).get("quote_deadline") or ""
    if not dl:
        return False
    try:
        return int(time.time()) >= int(datetime.strptime(dl, "%Y-%m-%d %H:%M:%S").timestamp())
    except Exception:
        return False


def config():
    """读本体轨参与者配置：供应商 + 审批人。

    权威来源 = 本工程页面维护的 contract_compare.db（本轨只读）：
      - 供应商：procurement_supplier（「供应商」页）
      - 审批人：procurement_approver（「审批人」页，替代 ONT_APPROVERS 环境变量）
    页面未配置某一项时，该项才回退旧链路（env → skill JSON），并打 WARNING。
    """
    suppliers, approvers = [], []
    try:
        from . import party_config as p9
        suppliers = p9.load_suppliers() or []
        approvers = p9.load_approvers() or []
    except Exception:
        suppliers, approvers = [], []
    if suppliers and approvers:
        return {"suppliers": suppliers, "approvers": approvers}
    # 页面尚未配齐 → 缺项回退旧链路，并告警（上线前请在 9006 页面维护，之后不再触发）
    try:
        import logging
        logging.getLogger(__name__).warning(
            "[ont-config] 页面配置不完整：供应商 %d / 审批人 %d，"
            "缺项暂回退旧配置链路，请在「供应商」「审批人」页面维护",
            len(suppliers), len(approvers))
    except Exception:
        pass
    legacy = _legacy_config()
    return {
        "suppliers": suppliers or (legacy.get("suppliers") or []),
        "approvers": approvers or (legacy.get("approvers") or []),
    }


def _load_global_cc():
    """系统配置抄送：「抄送」页维护的全局抄送列表（只读，取不到返回 []）。"""
    try:
        from . import party_config as p9
        return p9.load_global_cc() or []
    except Exception:
        return []


def _legacy_config():
    """旧配置链路（仅供 config() 回退）：env → skill JSON。

    迁移说明：原链路中间一级是现轨 neuops 的 `spare_mail_config.proc_participants`，
    迁入本工程后无对应数据源（权威来源已是上面的 procurement_supplier/approver 页面），故移除。
    """
    suppliers, approvers = [], []

    # ① 本体轨独立配置：ONT_SUPPLIERS="名称:邮箱,名称:邮箱" / ONT_APPROVERS="邮箱,邮箱"
    try:
        from .config import ONT_SUPPLIERS, ONT_APPROVERS
        for item in (ONT_SUPPLIERS or "").split(","):
            item = (item or "").strip()
            if not item:
                continue
            if ":" in item:
                name, _, email_ = item.partition(":")
                if email_.strip():
                    suppliers.append({"name": name.strip(), "email": email_.strip()})
            elif "@" in item:
                suppliers.append({"name": item, "email": item})
        approvers = [e.strip() for e in (ONT_APPROVERS or "").split(",") if e.strip()]
    except Exception:
        pass
    if suppliers and approvers:
        return {"suppliers": suppliers, "approvers": approvers}

    # ② 兜底：skill JSON
    if not suppliers or not approvers:
        try:
            from .skills import load_skill
            sk = load_skill("skill-proc-mail-inquiry") or {}
            comp = (sk.get("compose") or {}).get("participants") or (sk.get("participants") or {})
            if not suppliers:
                suppliers = [s for s in (comp.get("default_suppliers") or [])
                             if isinstance(s, dict) and s.get("email")]
            if not approvers:
                approvers = [e for e in (comp.get("approver_emails") or []) if e]
        except Exception:
            pass
    return {"suppliers": suppliers, "approvers": approvers}


def _mids_of(task):
    meta = task.get("spare_info") or {}
    mids = [(task.get("threat_msg_id") or "").strip()]
    mids += [m for m in (meta.get("b_msg_ids") or []) if m]
    for k in ("d_msg_id", "e_msg_id"):
        if meta.get(k):
            mids.append(meta[k])
    return {m.strip() for m in mids if m and m.strip()}


def _price(body):
    m = re.search(r"(?:单价|价格|报价)[：:\s]*([0-9]+(?:\.[0-9]+)?)", body)
    return m.group(1) if m else ""


# 货期/成色 关键词（报价结构化抽取用）
_DELIVERY_KW = ("货期", "交货期", "交期", "到货", "发货")
_CONDITION_KW = ("全新原装", "全新", "原厂翻新", "翻新", "拆机二手", "拆机", "二手", "原装")


def _parse_quote(body):
    """从供应商报价正文抽取结构化字段：单价/货期/成色/数量。

    连单价都识别不出 → 返回 None，交由 unparseable 分支催补（不再丢字段）。
    """
    s = body or ""
    m = re.search(r"(?:单价|价格|报价|每台|每件)[：:\s]*([0-9]+(?:\.[0-9]+)?)\s*(?:元|块|RMB|rmb|¥|￥)?", s)
    if not m:
        return None
    unit_price = m.group(1)
    # 货期：优先「货期：x天」，否则匹配「x天内交货」式
    delivery = ""
    for kw in _DELIVERY_KW:
        dm = re.search(kw + r"[：:\s]*([0-9]+\s*(?:天|工作日|周|月|日|小时))", s)
        if dm:
            delivery = dm.group(1).strip()
            break
    if not delivery:
        dm = re.search(r"([0-9]+\s*(?:天|工作日|周|月|日|小时))(?:\s*(?:内|左右)?\s*(?:交货|发货|到货))?", s)
        delivery = dm.group(1).strip() if dm else ""
    # 成色：最长匹配优先（"全新原装" 优先于 "全新"）
    condition = ""
    for kw in _CONDITION_KW:
        if kw in s:
            condition = kw
            break
    # 数量
    qty = ""
    qm = re.search(r"(?:数量|台数|件数)[：:\s]*([0-9]+(?:\.[0-9]+)?)", s)
    if qm:
        qty = qm.group(1)
    return {"unit_price": unit_price, "delivery": delivery, "condition": condition, "quantity": qty}


def _supplier_mentioned_in(body, suppliers):
    """审批正文中若显式点名某供应商（邮箱或名称），返回其邮箱；否则 None。"""
    bl = (body or "").lower()
    for s in (suppliers or []):
        email = str(s.get("email") or "").strip().lower()
        name = str(s.get("name") or "").strip().lower()
        if (email and email in bl) or (name and name in bl):
            return s.get("email")
    return None


def _strip_quoted(body):
    """去掉回复中引用的历史邮件（以 > 开头的行），只保留发件人自己新写的内容。

    真实邮件客户端『携带原文回复』时，引用的旧邮件里可能含有供应商名/价格/关键词，
    若不过滤会被误判（如审批人引用了含两供应商名称的 D 邮件，导致选错供应商）。
    """
    if not body:
        return ""
    return "\n".join(ln for ln in (body or "").splitlines()
                     if not ln.lstrip().startswith(">"))


def _thread_match(inrep, known):
    """判断邮件是否归属某任务的已知线程。known 为 message_id/refs 集合（去 <> 后匹配）。"""
    if not inrep or not known:
        return False
    for x in known:
        xs = x.strip().strip("<>")
        if not xs:
            continue
        if xs in inrep or x.strip() in inrep:
            return True
    return False


def ctx_from_task(task):
    meta = task.get("spare_info") or {}
    quotes = meta.get("quotes") or []
    approvers = meta.get("approver_emails") or []
    target_list = meta.get("suppliers") or config()["suppliers"]
    valid = [q for q in quotes if q.get("email")]
    lowest = min(valid, key=lambda q: float(q.get("unit_price") or 10 ** 12)) if valid else None
    deadline_passed = meta.get("deadline_passed", False)
    # 智能体固定规则：比价后选最低价（agent_selected_supplier）；
    # target_supplier 仅在下单前由审批人确认/覆盖后写入，避免绕过审批门。
    target_supplier = meta.get("target_supplier") or ""
    approval_rejected = bool(meta.get("approval_rejected"))
    lowest_email = lowest["email"] if (valid and lowest) else ""
    internal = "R_CLOSED" if meta.get("engineer_close") else task.get("internal_status")
    ctx = {
        "project_no": meta.get("project_no"), "project_name": meta.get("project_name"),
        "part_type": meta.get("part_type"), "brand": meta.get("brand"), "pn": meta.get("pn"),
        "spec": meta.get("spec"), "condition": meta.get("condition"), "count": meta.get("count"),
        "address": meta.get("address"), "urgent": meta.get("urgent"),
        "from_email": task.get("from_email"), "approver_emails": approvers,
        # 初始询价 A 的抄送人（运维工程师在发 A 时抄送的观察者），须透传到后续所有邮件
        "inquiry_cc": list((meta.get("inquiry_reply_from") or {}).get("cc_email_list") or []),
        # 系统配置抄送（9006「抄送」页维护的全局抄送），与 A 抄送叠加，两路都要携带
        "global_cc": _load_global_cc(),
        "internal_status": internal, "external_status": task.get("external_status"),
        "target_supplier_list": [s.get("email") for s in target_list],
        "valid_quotes": valid, "valid_quote_count": len(valid), "raw_quote_count": len(quotes),
        "valid_supplier_emails": [q.get("email") for q in valid],
        "target_supplier": target_supplier,
        "approval_rejected": approval_rejected,
        "lowest_supplier": lowest_email,
        "agent_selected_supplier": meta.get("agent_selected_supplier") or lowest_email,
        "approval_choice": target_supplier,
        "tracking_number_candidate": meta.get("tracking_no", ""),
        "collection_done": bool(deadline_passed or (valid and len(quotes) >= len(target_list) and target_list)),
        "deadline_passed": bool(deadline_passed),
        "unparseable_supplier_emails": list(meta.get("unparseable_replies") or []),
    }
    return ctx


# ── SEEN 认领：新工程师发起邮件 → 归本体轨并标记已读 ──────────────
def claim_inquiries(mg, mode="off", roll=0.0):
    claimed = []
    if mode not in ("ontology", "split"):
        return claimed
    try:
        from .ingest import fetch_new_inquiry_facts
        from .config import ONT_SCAN_HOURS as _scan_hours
    except Exception:
        _scan_hours = 48
    try:
        facts = fetch_new_inquiry_facts(mg, hours=_scan_hours, store=store)
    except Exception:
        return claimed
    for it in facts:
        fields = it["fields"]
        fid = fields.get("message_id") or ""
        # split：按消息指纹滚
        if mode == "split":
            import hashlib
            h = int(hashlib.sha256(fid.encode()).hexdigest(), 16) % 1000 / 1000.0
            if h > roll:
                continue
        tid = f"OT-{_shake(fid)}"
        mail = it.get("mail") or {}
        try:
            into = {**fields, "suppliers": config()["suppliers"],
                    "approver_emails": config()["approvers"],
                    "quotes": [], "received_reply_ids": []}
            # 携带工程师原始采购申请（A）原文与线程元数据：供 D/F 回复同一线程并携带原文
            into["inquiry_raw"] = (fields.get("mail_body") or fields.get("body")
                                   or mail.get("mail_body_text") or mail.get("body") or "")
            into["inquiry_mid"] = fid
            into["inquiry_refs"] = (mail.get("references") or "").strip()
            into["inquiry_reply_from"] = {
                "from_email": fields.get("from_email", ""),
                "to_email_list": mail.get("to_email_list") or [],
                "cc_email_list": mail.get("cc_email_list") or [],
            }
            # 报价截止时间：建任务路径走 claim_inquiries（不经过 execute_action("createTask")），
            # 原先 execution._deadline() 根本没机会被调用，导致 quote_deadline 恒为空、
            # deadline_passed 永假、超时中止成死代码。此处按现役轨口径补齐：
            #   基准 = 邮件头 Date（发送方声明时间），而非扫描时刻
            #   时长 = 紧急程度换算（_urgent_to_seconds）
            into["quote_deadline"] = _inquiry_deadline(mail, fields.get("urgent", ""))
            into["deadline_passed"] = False
            task = {"task_id": tid, "session_id": tid + "-S", "threat_msg_id": fid,
                    "from_email": fields.get("from_email", ""), "urgency_raw": fields.get("urgent", ""),
                    "internal_status": "R_INIT", "external_status": "R_SEND", "status": "INIT",
                    "mode": "ontology", "spare_info": into}
            store.upsert_task(task)
            store.audit("Task", tid, "claim", operator="emp-009",
                        snapshot={"from": fields.get("from_email")})
            # 建任务成功后才置 done：两阶段消费，中途崩溃下轮会重试而不是永久丢单
            store.mark_email_claimed(fid, tid)
            try:
                mg.mark_seen_by_message_id(fid)  # SEEN 认领握手：现轨 UNSEEN 不再处理
            except Exception:
                pass  # 主去重是 o_email 账本，SEEN 失败不影响正确性
            claimed.append(tid)
        except Exception as e:
            # 单封认领失败不得中断整批（原先异常会冒泡出函数，后面的邮件全都不处理）
            try:
                store.mark_email_failed(fid, f"{type(e).__name__}: {e}")
                store.audit("Email", fid, "claim_failed", operator="emp-009",
                            remark=f"{type(e).__name__}: {e}")
            except Exception:
                pass
            continue
    return claimed


# ── 入向回复归集：报价/审批/运单/工程师完成 ───────────────────────
def process_replies(mg):
    updates = []
    raw = mg.read_inbox(since_timestamp=int(time.time()) - 48 * 3600)
    mails = (raw or {}).get("mails", []) if isinstance(raw, dict) else (raw or [])
    tasks = {t["task_id"]: t for t in store.list_tasks()
             if (t.get("mode") == "ontology") and (t.get("status") not in _TERMINAL)}
    fresh = {}  # 逐任务最新工作副本，避免同任务多条回复互相覆盖
    for m in mails:
        inrep = (m.get("in_reply_to") or "") + " " + (m.get("references") or "")
        owner = None
        for tid, t in tasks.items():
            known = _mids_of(t)
            if known and _thread_match(inrep, known):
                owner = t
                break
        if not owner:
            continue
        tid = owner["task_id"]
        cur = fresh.get(tid) or dict(owner)
        mid = (m.get("message_id") or "").strip()
        meta = dict(cur.get("spare_info") or {})
        rec = list(meta.get("received_reply_ids") or [])
        if mid in rec:
            continue
        rec.append(mid)
        body = (m.get("mail_body_text") or "")
        body_new = _strip_quoted(body)  # 仅看发件人新写内容，忽略引用的历史邮件
        from_e = (m.get("from_email") or "").lower().strip()
        # 该邮件线程元数据（Reply-All 用）：原邮件 To/Cc/From 排除系统自身由 send 端处理
        mail_meta = {"from_email": (m.get("from_email") or "").strip(),
                     "to_email_list": m.get("to_email_list") or [],
                     "cc_email_list": m.get("cc_email_list") or []}
        emit = None
        if (from_e == str(cur.get("from_email") or "").lower().strip()
                and any(k in body_new for k in _CLOSE_KW)
                and settlement_enabled()):
            # 结算闭环开关（ONT_SETTLEMENT_ENABLED）：关闭时工程师「更换完成」邮件不触发闭环，
            # 仅保留在收件箱、任务维持已发货待确认状态——预留后续启用。
            meta["engineer_close"] = body_new[:500]
            meta["engineer_close_mid"] = mid
            meta["engineer_close_refs"] = (m.get("references") or "").strip()
            meta["engineer_close_reply_from"] = mail_meta
            emit = "engineer_close"
        elif from_e in [a.lower() for a in (meta.get("approver_emails") or [])]:
            if any(k in body_new for k in _REJECT_KW):
                # 审批驳回：显式中止，不再无限重发审批 D
                meta["approval_rejected"] = True
                meta["target_supplier"] = ""
                meta["approval_choice"] = ""
                emit = "approval_reject"
            elif any(k in body_new for k in _APPROVE_KW):
                # 智能体固定规则：比价后选最低价。审批人「确认采购」→ 沿用最低价；
                # 仅当审批人「显式点名其他供应商」(且确已报价) 才覆盖。
                qq = [q for q in (meta.get("quotes") or []) if q.get("email") and q.get("unit_price")]
                low = min(qq, key=lambda q: float(q.get("unit_price") or 10 ** 12)) if qq else None
                low_email = low["email"] if low else ""
                named = _supplier_mentioned_in(body_new, config()["suppliers"])
                # 覆盖条件：点名存在、确已报价、且与最低价不同
                if named and named != low_email and any(str(q.get("email")) == named for q in qq):
                    chosen = named
                else:
                    # 确认采购 / 未点名 / 点名即最低价 → 沿用智能体固定规则选的最低价
                    chosen = low_email
                meta["agent_selected_supplier"] = low_email  # 记录智能体比价结论
                meta["target_supplier"] = chosen
                meta["approval_choice"] = chosen
                meta["approval_rejected"] = False
                emit = "approval"
        elif any(k in body_new for k in _SHIP_KW):
            mn = re.search(r"([A-Za-z]{0,6}[\d]{6,})", body_new)
            meta["tracking_no"] = mn.group(1) if mn else body[:80]
            meta["ship_raw"] = body
            meta["ship_mid"] = mid
            meta["ship_reply_from"] = mail_meta
            emit = "shipping"
        elif _parse_quote(body_new):
            q = _parse_quote(body_new)
            q.update({"email": from_e, "raw": body, "msg_id": mid,
                      "refs": (m.get("references") or "").strip(),
                      "reply_all": mail_meta,
                      "receive_time": time.strftime("%Y-%m-%d %H:%M:%S")})
            quotes = meta.get("quotes") or []
            # 同供应商按邮箱 upsert（手动改价 is_manual 的保留，不被邮件覆盖）
            has_manual = any(str(xq.get("email") or "").strip().lower() == from_e and xq.get("is_manual")
                             for xq in quotes)
            if not has_manual:
                replaced = False
                for i, ex in enumerate(quotes):
                    if str(ex.get("email") or "").strip().lower() == from_e and not ex.get("is_manual"):
                        quotes[i] = q
                        replaced = True
                        break
                if not replaced:
                    quotes.append(q)
            meta["quotes"] = quotes
            # 智能体固定规则：每次报价后重算并保存「比价选最低价」结论
            low2 = min([x for x in quotes if x.get("email") and x.get("unit_price")],
                       key=lambda q: float(q.get("unit_price") or 10 ** 12), default=None)
            meta["agent_selected_supplier"] = low2["email"] if low2 else ""
            # 已给有效报价 → 从"解析失败"清单移除
            un = list(meta.get("unparseable_replies") or [])
            if from_e in un:
                un.remove(from_e)
                meta["unparseable_replies"] = un
            emit = "quote"
        elif meta.get("b_msg_ids"):  # 收到线程回复但未识别为报价/运单/审批/完成 → 报价解析失败
            un = list(meta.get("unparseable_replies") or [])
            if from_e not in un:
                un.append(from_e)
                meta["unparseable_replies"] = un
            emit = "unparseable"
        meta["received_reply_ids"] = rec
        cur = {**cur, "spare_info": meta}
        store.upsert_task(cur)
        fresh[tid] = cur
        tasks[tid] = cur
        updates.append({"task_id": tid, "kind": emit})
    return updates


# ── 决策 + 执行 ───────────────────────────────────────────────────
def drive(mode="off", use_llm=False, mg=None):
    if mode not in ("ontology", "split"):
        return []
    reports = []
    g = execution.governor()
    trusted = bool(g.get("llm"))
    shadow = bool(g.get("llm") is False and os.getenv("ONT_SHADOW", "0") == "1")
    for t in store.list_tasks(limit=100):
        if t.get("mode") != "ontology" or t.get("status") in _TERMINAL:
            continue
        # 到点判定：每轮刷新 deadline_passed。
        # 此前该字段只有读取方（orbit ctx / ontology.py / decision.py）而无任何写入点，
        # 恒为初始 False → 依赖它的 abortTask（超时中止）永不触发，等于死代码。
        try:
            _meta = json.loads(t.get("spare_info") or "{}")
            if _meta.get("quote_deadline"):
                _passed = _deadline_passed(_meta)
                if _passed != _meta.get("deadline_passed"):
                    _meta["deadline_passed"] = _passed
                    store.upsert_task({**t, "spare_info": _meta})
                    t = {**t, "spare_info": _meta}
        except Exception:
            pass
        ctx = ctx_from_task(t)
        # 临期提醒（无副作用风险：仅一次、有窗口、有未报价供应商才发）
        try:
            _maybe_remind_quotes(t, ctx, mg)
        except Exception:
            pass
        # 影子/信任模式都先算规则基准（参照系）
        rule_act, rule_reason, _ = _decide(ctx, t, False)
        chosen, reason, via_llm = rule_act, rule_reason, False
        aligned = True
        llm_act, llm_reason = None, ""
        # use_llm 形参此前是死参数（从未参与判断），这里让它真正生效。
        # 影子模式：始终调 LLM 做对照记录（但执行规则动作），所以不受 use_llm 限制；
        # 信任模式：只有显式开启 use_llm 才请求大模型并采用其决策。
        if shadow or (trusted and use_llm):
            llm_act, llm_reason, via2 = _decide(ctx, t, True)
            aligned = (llm_act == rule_act)
            store.audit("Task", t["task_id"], f"align:{llm_act}",
                        operator="emp-009",
                        snapshot={"rule": rule_act, "llm": llm_act, "aligned": aligned,
                                  "llm_reason": (llm_reason or "")[:200]},
                        remark="本体知识层 LLM 决策 影子对齐")
            # 【修复】原判 via_llm（恒 False）导致 LLM 决策永远不被采用，
            # 实际生效的是规则动作，整条链退化成影子记录。改为判 via2（LLM 是否真正给出动作）。
            if trusted and use_llm and via2 and llm_act:
                chosen, reason, via_llm = llm_act, llm_reason, True
        ok, detail = execution.execute_action(chosen, t, ctx, mg=mg, force=False)
        reports.append({"task_id": t["task_id"], "action": chosen, "reason": reason[:40],
                        "via_llm": via_llm, "aligned": aligned, "ok": ok, "detail": detail})
    return reports


def _decide(ctx, task, use_llm):
    from .engine import decide_action
    return decide_action(ctx, use_llm=use_llm, task=task)


def _shake(s):
    import hashlib
    return hashlib.md5((s or "x").encode()).hexdigest()[:8].upper()


def _maybe_remind_quotes(task, ctx, mg):
    """临期提醒：截止前 _REMIND_WINDOW 内、仍有供应商未报价 → 主动催报价（每任务仅一次）。"""
    meta = task.get("spare_info") or {}
    dl = (meta or {}).get("quote_deadline") or ""
    if not dl or ctx.get("deadline_passed") or ctx.get("collection_done"):
        return
    try:
        from datetime import datetime
        remain = int(datetime.strptime(dl, "%Y-%m-%d %H:%M:%S").timestamp()) - int(time.time())
    except Exception:
        return
    if remain > _REMIND_WINDOW or meta.get("reminded_at"):
        return
    quoted = {str(q.get("email") or "").lower() for q in (meta.get("quotes") or [])}
    targets = [s for s in (ctx.get("target_supplier_list") or []) if str(s).lower() not in quoted]
    if not targets or not mg:
        return
    subj = "Re: 【询价】距报价截止不足1小时，请尽快回复报价"
    body = (f"您好，以下备件询价将在 {dl} 截止，请尽快回复单价/货期/成色：\n"
            f"备件：{ctx.get('part_type')} {ctx.get('brand')} {ctx.get('pn')} x {ctx.get('count')}\n"
            f"任务编号：{task.get('task_id')}\n- NeuOps 备件询价(emp-009)")
    by_sup = meta.get("b_msg_by_supplier") or {}
    for email in targets:
        bmid = by_sup.get(str(email).strip()) or None
        try:
            mg.send_mail(to=[email], subject=subj, body_text=body,
                         reply_to_mail_id=bmid, reply_refs_chain=bmid)
        except Exception:
            pass
    meta["reminded_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    store.upsert_task({**task, "spare_info": meta})


# ── 全流程：认领 + 回复 + 驱动 ────────────────────────────────────
def run_full(mg, use_llm=False):
    g = execution.governor()
    claimed = claim_inquiries(mg, g["mode"], g["roll"])
    replies = process_replies(mg)
    reports = drive(g["mode"], use_llm=use_llm, mg=mg)
    return {"claim": claimed, "replies": replies, "drive": reports, "governor": g}