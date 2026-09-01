# -*- coding: utf-8 -*-
"""本体轨存储访问层（O_* 表 CRUD，仅本轨读写；不触碰 spare_mail_task）"""
import json
import threading
import uuid
from datetime import datetime

from . import schema

_lock = threading.Lock()


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _qid(prefix="OT"):
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


def upsert_task(task: dict):
    with _lock:
        conn = schema.get_conn()
        try:
            conn.execute(
                "INSERT INTO o_task (task_id, session_id, threat_msg_id, from_email, spare_info, urgency_raw,"
                " quote_deadline, target_supplier_list, target_supplier, tracking_number, close_feedback,"
                " status, internal_status, external_status, mode, create_time, close_time, update_time) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(task_id) DO UPDATE SET status=excluded.status, spare_info=excluded.spare_info,"
                " urgency_raw=excluded.urgency_raw, quote_deadline=excluded.quote_deadline,"
                " target_supplier_list=excluded.target_supplier_list, target_supplier=excluded.target_supplier,"
                " tracking_number=excluded.tracking_number, close_feedback=excluded.close_feedback,"
                " internal_status=excluded.internal_status, external_status=excluded.external_status,"
                " close_time=excluded.close_time, update_time=excluded.update_time",
                (task.get("task_id"), task.get("session_id"), task.get("threat_msg_id", ""),
                 task.get("from_email", ""), json.dumps(task.get("spare_info") or {}, ensure_ascii=False),
                 task.get("urgency_raw", ""), task.get("quote_deadline", ""),
                 json.dumps(task.get("target_supplier_list") or [], ensure_ascii=False),
                 task.get("target_supplier", ""), task.get("tracking_number", ""),
                 task.get("close_feedback", ""), task.get("status", "INIT"),
                 task.get("internal_status", "R_INIT"), task.get("external_status", "R_SEND"),
                 task.get("mode", "ontology"),
                 task.get("create_time") or _now(), task.get("close_time"),
                 task.get("update_time") or _now()),
            )
            conn.commit()
        finally:
            conn.close()


def get_task(task_id: str):
    with _lock:
        conn = schema.get_conn()
        try:
            r = conn.execute("SELECT * FROM o_task WHERE task_id=?", (task_id,)).fetchone()
            return _row_to_task(r) if r else None
        finally:
            conn.close()


def list_tasks(limit=500):
    with _lock:
        conn = schema.get_conn()
        try:
            rows = conn.execute("SELECT * FROM o_task ORDER BY create_time DESC LIMIT ?", (limit,)).fetchall()
            return [_row_to_task(r) for r in rows]
        finally:
            conn.close()


def _row_to_task(r):
    t = dict(r)
    for k in ("spare_info", "target_supplier_list"):
        try:
            t[k] = json.loads(t.get(k) or ("{}" if k == "spare_info" else "[]"))
        except Exception:
            t[k] = {} if k == "spare_info" else []
    return t


def upsert_email(m: dict):
    """emailMessageId 幂等：存在则跳过（不重复执行业务逻辑），仅当新邮件才入库。"""
    with _lock:
        conn = schema.get_conn()
        try:
            mid = (m.get("email_message_id") or m.get("message_id") or "").strip()
            if not mid:
                return False
            cur = conn.execute("SELECT 1 FROM o_email WHERE email_message_id=?", (mid,))
            if cur.fetchone():
                return False
            conn.execute(
                "INSERT INTO o_email (email_message_id, task_id, session_id, title, body, send_time,"
                " template_type, from_email, to_json, cc_json, in_reply_to, `references`) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (mid, m.get("task_id", ""), m.get("session_id", ""), m.get("title", "") or m.get("subject", ""),
                 m.get("body", "") or m.get("mail_body_text", ""), m.get("send_time", "") or _now(),
                 m.get("template_type", ""), m.get("from_email", ""),
                 json.dumps(m.get("to_email_list") or [], ensure_ascii=False),
                 json.dumps(m.get("cc_email_list") or [], ensure_ascii=False),
                 m.get("in_reply_to", ""), m.get("references", "")),
            )
            conn.commit()
            return True
        finally:
            conn.close()


def try_claim_email(m: dict):
    """两阶段认领登记（防丢单）。

    与 `upsert_email` 的区别：upsert_email 是「见过即消费」——一旦入库就永久跳过。
    若入库成功后建任务失败（进程崩溃/异常），这封询价将永久丢失且无任何告警。
    本函数把「登记」与「消费」拆开：

      返回 True  → 需要处理（新邮件，或上次 pending/failed 的重试）
      返回 False → claim_status='done'，业务已闭环，永久跳过

    处理成功后必须由调用方回调 `mark_email_claimed(mid, task_id)` 才置 done。
    """
    with _lock:
        conn = schema.get_conn()
        try:
            mid = (m.get("email_message_id") or m.get("message_id") or "").strip()
            if not mid:
                return False
            row = conn.execute(
                "SELECT claim_status FROM o_email WHERE email_message_id=?", (mid,)).fetchone()
            if row is not None:
                # 已登记：仅 done 跳过；pending/failed 交还调用方重试
                return (row["claim_status"] or "") != "done"
            conn.execute(
                "INSERT INTO o_email (email_message_id, task_id, session_id, title, body, send_time,"
                " template_type, from_email, to_json, cc_json, in_reply_to, `references`, claim_status)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'pending')",
                (mid, m.get("task_id", ""), m.get("session_id", ""),
                 m.get("title", "") or m.get("subject", ""),
                 m.get("body", "") or m.get("mail_body_text", ""),
                 m.get("send_time", "") or _now(), m.get("template_type", ""),
                 m.get("from_email", ""),
                 json.dumps(m.get("to_email_list") or [], ensure_ascii=False),
                 json.dumps(m.get("cc_email_list") or [], ensure_ascii=False),
                 m.get("in_reply_to", ""), m.get("references", "")),
            )
            conn.commit()
            return True
        finally:
            conn.close()


def mark_email_claimed(mid: str, task_id: str = ""):
    """认领闭环：业务处理（建任务）成功后才置 done。"""
    mid = (mid or "").strip()
    if not mid:
        return False
    with _lock:
        conn = schema.get_conn()
        try:
            conn.execute("UPDATE o_email SET claim_status='done', claim_error='', task_id=?"
                         " WHERE email_message_id=?", (task_id or "", mid))
            conn.commit()
            return True
        finally:
            conn.close()


def mark_email_failed(mid: str, err: str = ""):
    """认领失败：留 failed 现场，下轮重试（不置 done，保证不丢单）。"""
    mid = (mid or "").strip()
    if not mid:
        return False
    with _lock:
        conn = schema.get_conn()
        try:
            conn.execute("UPDATE o_email SET claim_status='failed', claim_error=?"
                         " WHERE email_message_id=?", (str(err or "")[:500], mid))
            conn.commit()
            return True
        finally:
            conn.close()


def list_unclaimed_emails(limit=100):
    """未闭环的认领邮件（pending/failed），供可观测页与告警使用。"""
    with _lock:
        conn = schema.get_conn()
        try:
            rows = conn.execute(
                "SELECT email_message_id, title, from_email, send_time, claim_status, claim_error"
                " FROM o_email WHERE IFNULL(claim_status,'') IN ('pending','failed')"
                " ORDER BY send_time DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def pending_claim_mails(limit=100):
    """把未闭环（pending/failed）的邮件还原成 mail 形状，供认领重试。

    重试不依赖 IMAP 扫描窗口——邮件正文已在登记时落库，
    因此即使窗口早已滑过，pending 邮件仍能被重新处理，不会丢单。
    """
    with _lock:
        conn = schema.get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM o_email WHERE IFNULL(claim_status,'') IN ('pending','failed')"
                " ORDER BY send_time ASC LIMIT ?", (limit,)).fetchall()
        finally:
            conn.close()
    out = []
    for r in rows:
        d = dict(r)
        def _j(v, dflt):
            try:
                return json.loads(v or dflt)
            except Exception:
                return json.loads(dflt)
        out.append({
            "message_id": d.get("email_message_id") or "",
            "subject": d.get("title") or "",
            "mail_body_text": d.get("body") or "",
            "from_email": d.get("from_email") or "",
            "in_reply_to": d.get("in_reply_to") or "",
            "references": d.get("references") or "",
            "to_email_list": _j(d.get("to_json"), "[]"),
            "cc_email_list": _j(d.get("cc_json"), "[]"),
            "receive_timestamp": 0,
            "_retry": True,
        })
    return out


def get_scan_ts(key: str = "inquiry") -> int:
    """读扫描水位（上次成功扫完的时刻，unix 秒）。无记录返回 0。"""
    conn = schema.get_conn()
    try:
        row = conn.execute("SELECT last_ts FROM o_scan_state WHERE scan_key=?", (key,)).fetchone()
        return int(row["last_ts"] or 0) if row else 0
    except Exception:
        return 0
    finally:
        conn.close()


def set_scan_ts(ts: int, key: str = "inquiry"):
    """写扫描水位。只在一轮扫描完整跑完后调用。"""
    with _lock:
        conn = schema.get_conn()
        try:
            conn.execute(
                "INSERT INTO o_scan_state (scan_key, last_ts, update_time) VALUES (?,?,?)"
                " ON CONFLICT(scan_key) DO UPDATE SET last_ts=excluded.last_ts,"
                " update_time=excluded.update_time",
                (key, int(ts or 0), _now()))
            conn.commit()
            return True
        finally:
            conn.close()


def audit(biz_type, biz_id, action, operator=None, snapshot=None, remark=""):
    with _lock:
        conn = schema.get_conn()
        try:
            conn.execute(
                "INSERT INTO o_audit_log (biz_type, biz_id, action, operator, operate_time, content_snapshot, remark) "
                "VALUES (?,?,?,?,?,?,?)",
                (biz_type, biz_id, action, operator, _now(),
                 json.dumps(snapshot or {}, ensure_ascii=False), remark),
            )
            conn.commit()
        finally:
            conn.close()


def list_audit(biz_type=None, biz_id=None, limit=200):
    with _lock:
        conn = schema.get_conn()
        try:
            sql = "SELECT * FROM o_audit_log WHERE 1=1"
            args = []
            if biz_type:
                sql += " AND biz_type=?"; args.append(biz_type)
            if biz_id:
                sql += " AND biz_id=?"; args.append(biz_id)
            sql += " ORDER BY audit_log_id DESC LIMIT ?"; args.append(limit)
            return [dict(r) for r in conn.execute(sql, args).fetchall()]
        finally:
            conn.close()


def record_alignment(task_id, legacy_ext, legacy_int, proposed_action, proposed_ext, proposed_int, aligned, diff=""):
    with _lock:
        conn = schema.get_conn()
        try:
            conn.execute(
                "INSERT INTO o_alignment (task_id, legacy_external, legacy_internal, proposed_action,"
                " proposed_external, proposed_internal, aligned, diff, create_time) VALUES (?,?,?,?,?,?,?,?,?)",
                (task_id, legacy_ext, legacy_int, proposed_action, proposed_ext, proposed_int, 1 if aligned else 0,
                 diff, _now()),
            )
            conn.commit()
        finally:
            conn.close()


def list_alignment(limit=200):
    with _lock:
        conn = schema.get_conn()
        try:
            rows = conn.execute("SELECT * FROM o_alignment ORDER BY alignment_id DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def person_map():
    """Person 映射：优先业务主数据（procurement_supplier 等），暂无则从邮件注册。"""
    out = {}
    # TODO: 阶段 B 接入业务主数据源；当前为空实现，调用方需显式注册
    return out


def register_person(name, email, role):
    with _lock:
        conn = schema.get_conn()
        try:
            person_id = f"P-{uuid.uuid4().hex[:6].upper()}"
            conn.execute(
                "INSERT OR IGNORE INTO o_person (person_id, name, email, role) VALUES (?,?,?,?)",
                (person_id, name, email or "", role or ""),
            )
            conn.commit()
            return person_id
        finally:
            conn.close()