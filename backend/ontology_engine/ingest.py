# -*- coding: utf-8 -*-
"""邮箱事实采集：读 IMAP 新邮件 → 幂等入 o_email → 解析为事实上下文 → 新询价建 O_Task。
本体轨用邮箱作为唯一事实源（同现轨），但落 O_* 独立表。
"""
import re
import time


def _clean(v):
    return (v or "").strip().replace("\r", "")


def _field(body, *labels):
    """按标签行提取字段值：'品牌：Seagate' 或 '品牌: Seagate'。"""
    for lb in labels:
        m = re.search(rf"{lb}[：:\s]+([^\n，,；;]+)", body)
        if m:
            return _clean(m.group(1))
    return ""


def _ship_time(body: str) -> str:
    """最晚发货时间：抽取并统一成 YYYY-MM-DD。

    不能直接用 _field 的通用取值，因为日期有多种写法（2026/09/20、2026年9月20日），
    需要归一化后再交给模板 B/E 的 {latest_ship_time}。
    口径与现役轨 routes_procurement_agent.py:3024-3025 保持一致。
    """
    m = re.search(r"(?:最晚发货(?:时间)?\s*[:：]?\s*)(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?)", body or "")
    if not m:
        return ""
    return (m.group(1).replace("/", "-").replace("年", "-")
            .replace("月", "-").replace("日", ""))


def parse_inquiry_fields(body: str, subject: str = "") -> dict:
    """从工程师询价邮件正文/主题抽取本体轨事实字段（确定性，不交 LLM）。"""
    text = body or ""
    pno = _field(text, "项目编号", "项目号")
    if not pno:
        m = re.search(r"P(RJ|RJ-)?[A-Z0-9]*-?[0-9A-Z-]+", text + "\n" + subject)
        pno = m.group(0).strip() if m else ""
    return {
        "project_no": pno,
        "project_name": _field(text, "项目名称"),
        "part_type": _field(text, "类型", "备件类型"),
        "brand": _field(text, "品牌"),
        "pn": _field(text, "PN", "PN号", "型号", "料号"),
        "spec": _field(text, "规格"),
        "condition": _field(text, "成色", "新旧"),
        "count": _field(text, "数量"),
        "address": _field(text, "收货地址", "地址"),
        "urgent": _field(text, "紧急程度", "紧急", "时限"),
        # 最晚发货时间：模板 B（对外询价）与 E（订货）都会渲染 {latest_ship_time}，
        # 原先未解析导致邮件里「最晚发货」一栏为空。
        "latest_ship_time": _ship_time(text),
        "receiver_name": _field(text, "联系人", "收货人"),
        "receiver_phone": _field(text, "电话", "手机"),
    }


def _requester_allowed(from_email: str, allow: list) -> bool:
    """发起人白名单校验。allow 为空 = 不限制（向后兼容）。

    支持整邮箱（a@b.com）与域名（@b.com）两种写法。
    """
    if not allow:
        return True
    fe = (from_email or "").strip().lower()
    if not fe:
        return False
    for item in allow:
        it = (item or "").strip().lower()
        if not it:
            continue
        if it.startswith("@"):
            if fe.endswith(it):
                return True
        elif fe == it:
            return True
    return False


def is_inquiry(mail: dict, allow_senders=None, self_email: str = "") -> bool:
    """发起判据：非回复(无 in_reply_to/references)、主题非 Re:、含询价关键词。

    额外两道闸（都可关闭，保持向后兼容）：
      - self_email：排除智能体自己发出的邮件，避免同域回投时自我认领建任务；
      - allow_senders：发起人白名单。「采购」是极常见词，不设白名单时
        广告/垃圾邮件会被误认领建任务。
    """
    subject = (mail.get("subject") or "")
    body = (mail.get("mail_body_text") or "") or (mail.get("body") or "")
    if mail.get("in_reply_to") or mail.get("references"):
        return False
    from_email = (mail.get("from_email") or "").strip().lower()
    if self_email and from_email == (self_email or "").strip().lower():
        return False
    if not _requester_allowed(from_email, allow_senders or []):
        return False
    sl = subject.lower()
    if sl.startswith("re:") or sl.startswith("回复") or sl.startswith("re :"):
        return False
    flat = re.sub(r"\s+", "", body + subject)
    return any(kw in flat for kw in ("询价", "采购", "备件", "购买"))


SCAN_KEY = "inquiry"
_SCAN_OVERLAP = 3600  # 水位回退缓冲：容忍投递延迟与时钟漂移


def _ont_participants():
    """读白名单与自身邮箱（配置缺失时静默降级为不限制）。"""
    allow, self_email = [], ""
    try:
        from .config import ONT_REQUESTERS, ONT_MAIL_USERNAME
        allow = [e.strip() for e in (ONT_REQUESTERS or "").split(",") if e.strip()]
        self_email = (ONT_MAIL_USERNAME or "").strip()
    except Exception:
        pass
    return allow, self_email


def scan_window(hours: int, now_ts: int = None, st=None) -> int:
    """计算本轮扫描下界（unix 秒）。

    去重**不靠**时间窗口——那是 o_email.email_message_id 唯一键的职责。
    窗口只负责「别漏」，所以取两者中更早的一个：
      ① now - hours          固定窗口（常态）
      ② 水位 - 1h 缓冲        上次扫完的时刻（停机补扫）
    服务停机 5 天后重启，② 会把下界拉回停机时刻，停机期间的询价不会漏。
    """
    now_ts = int(now_ts or time.time())
    floor_ts = now_ts - max(1, int(hours or 1)) * 3600
    try:
        if st is None:
            from . import store as st
        wm = int(st.get_scan_ts(SCAN_KEY) or 0)
    except Exception:
        wm = 0
    if wm > 0:
        return min(floor_ts, wm - _SCAN_OVERLAP)
    return floor_ts


def fetch_new_inquiry_facts(mail_gateway, hours: int = 2, store=None, log=print):
    """读新邮件 + 重试未闭环邮件，两阶段登记，返回 [ {mail, fields} ] 供建任务。

    去重三层（互相独立，任一层生效即不会重复建任务）：
      ① o_email.email_message_id 唯一键（持久账本，本函数）
      ② IMAP \\Seen 认领握手（orbit.claim_inquiries）
      ③ task_id = OT-{md5(message_id)}，同一封邮件恒等于同一个 task_id（upsert 覆盖而非新增）
    因此**不需要**「某时刻前的邮件都已处理」这类时间水位来防重；
    水位在此只用于扩大扫描下界以防漏（见 scan_window）。
    """
    from . import store as st
    from . import schema
    schema.ensure_core_tables()
    allow, self_email = _ont_participants()

    # ① 先重试未闭环的（pending/failed）——不依赖 IMAP 窗口，窗口滑过也能救回
    mails = list(st.pending_claim_mails())
    retry_ids = {(m.get("message_id") or "").strip() for m in mails}

    # ② 再扫 IMAP 新邮件；下界由水位参与计算
    scan_started = int(time.time())
    since_ts = scan_window(hours, now_ts=scan_started, st=st)
    scan_ok = True
    try:
        raw = mail_gateway.read_inbox(since_timestamp=since_ts)
        if isinstance(raw, dict) and raw.get("success") is False:
            scan_ok = False
        fresh = (raw or {}).get("mails", []) if isinstance(raw, dict) else (raw or [])
    except Exception as e:
        scan_ok, fresh = False, []
        try:
            log(f"[ont-ingest] read_inbox 失败，本轮不推进水位: {e}")
        except Exception:
            pass
    for m in fresh:
        if (m.get("message_id") or "").strip() not in retry_ids:
            mails.append(m)

    out = []
    for m in mails:
        is_retry = bool(m.get("_retry"))
        # 重试项已通过判据登记过，不再重复过判据（白名单可能在期间收紧）
        if not is_retry and not is_inquiry(m, allow_senders=allow, self_email=self_email):
            continue
        need = st.try_claim_email({
            "email_message_id": m.get("message_id"),
            "title": m.get("subject"),
            "body": m.get("mail_body_text") or m.get("body"),
            "from_email": m.get("from_email"),
            "to_email_list": m.get("to_email_list") or [],
            "cc_email_list": m.get("cc_email_list") or [],
            "in_reply_to": m.get("in_reply_to"),
            "references": m.get("references"),
            "template_type": "A",
        })
        if not need:
            continue  # claim_status='done'，业务已闭环
        fields = parse_inquiry_fields(m.get("mail_body_text") or "", m.get("subject") or "")
        fields["message_id"] = (m.get("message_id") or "").strip()
        fields["from_email"] = (m.get("from_email") or "").strip()
        fields["receive_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
        out.append({"mail": m, "fields": fields})

    # 仅在 IMAP 扫描成功时推进水位；失败则保持旧水位，下轮从更早处补扫
    if scan_ok:
        try:
            st.set_scan_ts(scan_started, SCAN_KEY)
        except Exception:
            pass
    return out