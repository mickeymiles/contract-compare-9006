# -*- coding: utf-8 -*-
"""本体轨邮件网关（独立邮箱）。

【为什么要自实现】
原实现直接复用现轨 `mcp_tools` 的 tool_send_mail / tool_read_inbox_mail
（SKL-R-01 只读约束），导致两套共用同一个收件箱：现轨按 UNSEEN 增量扫描，
本体轨会 mark_seen 认领，共用邮箱必然互相漏单。

双轨并行要求本体轨走独立邮箱（ONT_MAIL_*），故此处自实现一套 IMAP/SMTP。
返回结构与现轨保持一致，上层 orbit / ingest 无需改动。

163 注意点：login 后必须立即发 IMAP ID 命令，否则 SELECT 报 "Unsafe Login"；
imaplib 不认 ID 命令，需先给 Commands 打补丁，再用 _simple_command 发送。
"""
import time
import email as _email_pkg
from email.header import decode_header as _decode_header


def _ont_mail_cfg(emp_id: str = "emp-009") -> dict:
    """本体轨邮件配置（按数字员工实体读取）。

    优先级：本体库 o_agent_state.mail_channel 库配置 > ONT_MAIL_* 环境变量兜底。
    这样 emp-009 的邮箱（b4）可在运行期改配置、无需改 .env / 脚本 / 重启；
    未配置时回退环境变量。（迁移前该配置在 neuops 的 employee_channels 表。）
    """
    # 1) 库配置优先：本体库中登记的邮箱渠道
    try:
        from . import agent_registry
        c = agent_registry.mail_channel()
        if c:
            addr = (c.get("address") or "").strip()
            pwd = (c.get("password") or "").strip()
            if addr and pwd:
                return {
                    "mail_username": addr,
                    "mail_password": pwd,
                    "imap_host": c.get("imap_host") or "imap.163.com",
                    "imap_port": int(c.get("imap_port") or 993),
                    "smtp_host": c.get("smtp_host") or "smtp.163.com",
                    "smtp_port": int(c.get("smtp_port") or 465),
                    "display_name": c.get("display_name") or "采购智能体",
                }
    except Exception:
        pass
    # 2) 环境变量兜底（首次部署 / 库未配置时）
    from .config import (ONT_MAIL_USERNAME, ONT_MAIL_PASSWORD,
                         ONT_MAIL_IMAP_HOST, ONT_MAIL_IMAP_PORT,
                         ONT_MAIL_SMTP_HOST, ONT_MAIL_SMTP_PORT,
                         ONT_MAIL_DISPLAY_NAME)
    return {
        "mail_username": ONT_MAIL_USERNAME,
        "mail_password": ONT_MAIL_PASSWORD,
        "imap_host": ONT_MAIL_IMAP_HOST,
        "imap_port": ONT_MAIL_IMAP_PORT,
        "smtp_host": ONT_MAIL_SMTP_HOST,
        "smtp_port": ONT_MAIL_SMTP_PORT,
        "display_name": ONT_MAIL_DISPLAY_NAME,
    }


def _decode_mime(s: str) -> str:
    """解码 MIME 头（主题、发件人昵称可能带编码）。"""
    if not s:
        return ""
    try:
        out = []
        for text, charset in _decode_header(s):
            if isinstance(text, bytes):
                out.append(text.decode(charset or "utf-8", "ignore"))
            else:
                out.append(text)
        return "".join(out).strip()
    except Exception:
        return str(s)


def _norm_mid(m) -> str:
    """RFC Message-ID 规范化：剥掉前后尖括号，便于 In-Reply-To / References 比较。"""
    if not m:
        return ""
    s = str(m).strip()
    while s.startswith("<"):
        s = s[1:]
    while s.endswith(">"):
        s = s[:-1]
    return s.strip()


def _extract_addr(v: str) -> str:
    """从 '名称 <a@b.com>' 或 'a@b.com' 提取邮箱地址。"""
    v = (v or "").strip()
    if "<" in v and ">" in v:
        return v[v.find("<") + 1:v.find(">")].strip()
    return v


def _addr_list(msg, *headers) -> list:
    """取 To / Cc 的邮箱列表（逗号分隔，可能有多个）。"""
    out = []
    for h in headers:
        for chunk in (msg.get(h) or "").split(","):
            addr = _extract_addr(chunk)
            if addr and "@" in addr:
                out.append(addr.lower())
    return list(dict.fromkeys(out))


def _body_of(msg) -> str:
    """取纯文本正文（multipart 时取第一个 text/plain）。"""
    try:
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        for enc in ("utf-8", "gb18030", "latin-1"):
                            try:
                                return payload.decode(enc)
                            except Exception:
                                continue
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                for enc in ("utf-8", "gb18030", "latin-1"):
                    try:
                        return payload.decode(enc)
                    except Exception:
                        continue
    except Exception:
        pass
    return ""


def read_inbox(since_timestamp: int = 0, filter_sender_email_list=None,
               exclude_sender_email_list=None, use_unseen: bool = False,
               match_in_reply_to_msg_ids=None):
    """读本体轨邮箱收件箱（独立 IMAP）。

    返回结构与现轨 tool_read_inbox_mail 一致：
    {"tool", "success", "total", "mails": [{mail_id, message_id, in_reply_to, references,
    subject, from_email, from_name, to_email_list, cc_email_list, reply_all_candidates,
    mail_body_text, receive_timestamp}]}
    """
    import imaplib
    from email.utils import parsedate_to_datetime

    _mc = _ont_mail_cfg()
    if not _mc["mail_username"] or not _mc["mail_password"]:
        return {"tool": "ont_read_inbox", "success": False,
                "error": "ONT_MAIL_USERNAME / ONT_MAIL_PASSWORD 未配置", "mails": []}

    filter_set = {str(e).lower().strip() for e in (filter_sender_email_list or []) if e}
    exclude_set = {str(e).lower().strip() for e in (exclude_sender_email_list or []) if e}
    match_set = {_norm_mid(m) for m in (match_in_reply_to_msg_ids or []) if m}

    try:
        imap = imaplib.IMAP4_SSL(_mc["imap_host"], int(_mc["imap_port"] or 993))
        imap.login(_mc["mail_username"], _mc["mail_password"])
        # 163 要求 login 后立即发 IMAP ID，否则 SELECT 报 "Unsafe Login"
        imaplib.Commands["ID"] = ("AUTH",)
        try:
            imap._simple_command(
                "ID", '("name" "NeuOps-Ont" "version" "1.0.0" "vendor" "NeuOps" '
                      '"support-email" "' + _mc["mail_username"] + '")')
        except Exception:
            pass
        sel_status, sel_data = imap.select("INBOX")
        if sel_status != "OK":
            return {"tool": "ont_read_inbox", "success": False,
                    "error": f"IMAP select INBOX 失败: {sel_status} {sel_data}", "mails": []}

        if use_unseen:
            status, data = imap.search(None, "UNSEEN")
        else:
            from datetime import datetime
            ts = since_timestamp or int(time.time()) - 86400
            imap_date = datetime.fromtimestamp(ts).strftime("%d-%b-%Y")
            status, data = imap.search(None, f"SINCE {imap_date}")
        if status != "OK":
            return {"tool": "ont_read_inbox", "success": False,
                    "error": f"IMAP search 失败: {status}", "mails": []}

        out = []
        for mid in (data[0] or b"").split():
            status, msg_data = imap.fetch(mid, "(RFC822)")
            if status != "OK" or not msg_data or not msg_data[0]:
                continue
            msg = _email_pkg.message_from_bytes(msg_data[0][1])
            from_full = _decode_mime(msg.get("From", ""))
            from_email = _extract_addr(from_full).lower()
            if filter_set and from_email not in filter_set:
                continue
            if exclude_set and from_email in exclude_set:
                continue
            in_reply_to = _norm_mid(msg.get("In-Reply-To", ""))
            refs = msg.get("References", "") or ""
            if match_set:
                hit = (in_reply_to in match_set) or any(
                    _norm_mid(r) in match_set for r in refs.split())
                if not hit:
                    continue
            rc_to = _addr_list(msg, "To")
            rc_cc = _addr_list(msg, "Cc")
            try:
                recv_ts = int(parsedate_to_datetime(msg.get("Date", "")).timestamp())
            except Exception:
                recv_ts = int(time.time())
            out.append({
                "mail_id": mid.decode() if isinstance(mid, bytes) else str(mid),
                "message_id": _norm_mid(msg.get("Message-ID", "")),
                "in_reply_to": in_reply_to,
                "references": refs,
                "subject": _decode_mime(msg.get("Subject", "")),
                "from_email": from_email,
                "from_name": from_full.replace(f"<{from_email}>", "").strip().strip('"'),
                "to_email_list": rc_to,
                "cc_email_list": rc_cc,
                "reply_all_candidates": list(dict.fromkeys(rc_to + rc_cc)),
                "mail_body_text": _body_of(msg)[:5000],
                "receive_timestamp": recv_ts,
                # 邮件头 Date 原始字符串：报价截止时间的计算基准。
                # 现役轨 _inquiry_deadline() 用「发送方声明时间」而非扫描时刻，
                # 本体轨必须对齐这个口径，否则截止时间会随轮询时机漂移。
                "date": msg.get("Date", "") or "",
            })
        try:
            imap.close()
        except Exception:
            pass
        imap.logout()
        return {"tool": "ont_read_inbox", "success": True, "total": len(out), "mails": out}
    except Exception as e:
        return {"tool": "ont_read_inbox", "success": False,
                "error": f"{type(e).__name__}: {e}", "mails": []}


def send_mail(to, subject, body_text, cc=None, reply_to_mail_id=None,
              reply_refs_chain=None, reply_all_from=None):
    """本体轨发信（独立 SMTP）。返回结构与现轨 tool_send_mail 一致。"""
    import smtplib
    from email.mime.text import MIMEText
    from email.utils import formataddr, make_msgid

    _mc = _ont_mail_cfg()
    if not _mc["mail_password"]:
        return {"tool": "ont_send_mail", "success": False,
                "error": "ONT_MAIL_PASSWORD 未配置（163 邮箱授权码）"}
    try:
        self_email = str(_mc["mail_username"] or "").lower().strip()
        _self = {self_email} if self_email else set()

        # Reply All：把原邮件全体收件人并入候选，但排除本体轨自己（防自激循环）
        to_extra, cc_extra = [], []
        if reply_all_from and isinstance(reply_all_from, dict):
            from_e = str(reply_all_from.get("from_email") or "").lower().strip()
            if from_e and "@" in from_e and from_e not in _self:
                to_extra.append(from_e)
            cc_extra = [a for a in dict.fromkeys(
                list(reply_all_from.get("cc_email_list") or []) + list(cc or []))
                if a and a.lower() not in _self and a not in to_extra]

        final_to = [a for a in dict.fromkeys(list(to or []) + to_extra)
                    if a and a.lower() not in _self]
        final_cc = [a for a in dict.fromkeys(list(cc or []) + cc_extra)
                    if a and a.lower() not in _self and a not in final_to]
        to = final_to or [self_email]
        cc = final_cc or None

        msg = MIMEText(body_text or "", "plain", "utf-8")
        msg["Subject"] = subject or ""
        msg["From"] = formataddr((_mc["display_name"] or "备件采购智能体", _mc["mail_username"]))
        msg["To"] = ",".join(to)
        msg["Message-ID"] = make_msgid()
        if cc:
            msg["Cc"] = ",".join(cc)
        if reply_to_mail_id:
            msg["In-Reply-To"] = reply_to_mail_id
            msg["References"] = (f"{reply_refs_chain} {reply_to_mail_id}".strip()
                                 if reply_refs_chain else reply_to_mail_id)

        s = smtplib.SMTP_SSL(_mc["smtp_host"], int(_mc["smtp_port"] or 465), timeout=30)
        s.login(_mc["mail_username"], _mc["mail_password"])
        s.sendmail(_mc["mail_username"], list(to) + (cc or []), msg.as_string())
        s.quit()
        return {"tool": "ont_send_mail", "success": True,
                "message_id": msg["Message-ID"], "to": to, "cc": cc, "subject": subject}
    except Exception as e:
        return {"tool": "ont_send_mail", "success": False, "error": f"{type(e).__name__}: {e}"}


def fetch_unseen_since(hours: int = 1):
    """返回 hours 内的未读邮件。"""
    return read_inbox(since_timestamp=int(time.time()) - hours * 3600, use_unseen=True)


def mark_seen_by_message_id(msg_id: str) -> bool:
    """SEEN 认领握手：按 Message-ID 定位邮件并置 \\Seen。

    双轨分邮箱后，这只影响本体轨自己的收件箱，不会干扰现轨的 UNSEEN 增量扫描。
    """
    if not msg_id:
        return False
    import imaplib
    _mc = _ont_mail_cfg()
    if not _mc["mail_username"] or not _mc["mail_password"]:
        return False
    try:
        mid = _norm_mid(msg_id)
        c = imaplib.IMAP4_SSL(_mc["imap_host"], int(_mc["imap_port"] or 993))
        c.login(_mc["mail_username"], _mc["mail_password"])
        imaplib.Commands["ID"] = ("AUTH",)
        try:
            c._simple_command("ID", '("name" "NeuOps-Ont" "vendor" "Run")')
        except Exception:
            pass
        c.select("INBOX")
        typ, data = c.search(None, "HEADER Message-ID", mid)
        nums = (data[0] or b"").split()
        if nums:
            c.store(b",".join(nums), "+FLAGS", "\\Seen")
        c.logout()
        return bool(nums)
    except Exception:
        return False
