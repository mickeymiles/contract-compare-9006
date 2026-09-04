# -*- coding: utf-8 -*-
"""本体可观测（Ontology）数据网关 — 为 /api/ontology/* 提供只读数据。

迁移说明（本体可观测整体迁入本工程）
──────────────────────────────────
迁移前：本体轨住在 neuops-agent-demo(9007)，本模块是个**跨工程外挂视图** ——
ABox 直读对方工程目录下的 `neuops_ontology.db`，TBox 走 HTTP 打 9007 的 `/spec`，
9007 没起时还要退化到 AST 解析对方源码。对方一挂，可观测页就只剩空壳。

迁移后：引擎（TBox + 规则 + 动作 + 邮件 + 常驻循环）已在本工程 `ontology_engine/`，
本体库也由本工程自建自写（工程根 `contract_ontology.db`）。因此本模块简化为：
  1. ABox（实例事实）：只读打开本工程自己的本体库（mode=ro，与引擎的 WAL 写入不冲突）。
  2. TBox（本体定义）：**进程内直接取** ontology_engine 的模块字面量，
     不再有 HTTP 往返、TTL 缓存与 AST 回落这三层脚手架。

当前只提供只读查询。写入口预留见文件末尾「编辑扩展预留」一节。
"""

import copy
import json
import os
import sqlite3
import time

from ontology_engine import schema as _ont_schema

# 本体库路径：与引擎写入端同一个文件（引擎侧 ONT_DB_PATH 可覆盖，这里跟随）
ONT_DB_PATH = _ont_schema.ONT_DB_PATH

# o_* 表清单：概览页统计用
ONT_TABLES = ["o_task", "o_person", "o_email", "o_supplier_quote",
              "o_session", "o_audit_log", "o_alignment"]

# 视为「终态」的任务状态：台账只收这些
_CLOSED_STATUS = ("CLOSED", "CLOSED_ABORT", "CLOSED_MANUAL")

# 本体库不可用时的降级标记（供概览页展示，不抛 500）
_DB_ERR = {"missing": False, "error": ""}


# ─────────────────────────────────────────────────────────────
# 基础工具
# ─────────────────────────────────────────────────────────────
def _conn():
    """只读连接本体库。文件不存在时显式抛错，由 _rows 捕获降级为空结果。

    引擎会在应用启动期建库（见 main.py 的 startup），所以正常运行时文件必然存在；
    这里保留存在性校验，避免 sqlite3 在路径配错时静默创建空库。
    """
    if not os.path.exists(ONT_DB_PATH):
        raise sqlite3.OperationalError(f"本体库不存在: {ONT_DB_PATH}")
    conn = sqlite3.connect(f"file:{ONT_DB_PATH}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def _rows(sql, params=()):
    """执行查询；本体库缺失/锁表/表不存在时一律降级为空列表，绝不抛 500。"""
    try:
        conn = _conn()
    except Exception as e:
        _DB_ERR["missing"] = True
        _DB_ERR["error"] = f"{type(e).__name__}: {e}"
        return []
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    except sqlite3.Error as e:
        _DB_ERR["error"] = f"{type(e).__name__}: {e}"
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _load_json(raw, default):
    """把库里的 JSON 文本列解析成对象，坏了不抛异常。"""
    if raw in (None, ""):
        return default
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return default


def _meta(task):
    """任务的 spare_info（备件属性 / 报价 / 审批选择全在里面）。"""
    return _load_json(task.get("spare_info"), {})


def _supplier_of(task, meta):
    """选中供应商：o_task 列为空时退回 spare_info（9007 部分路径只写了 JSON）。"""
    return (task.get("target_supplier")
            or meta.get("target_supplier")
            or meta.get("approval_choice")
            or "")


def _tracking_of(task, meta):
    """快递单号：库里存的是供应商发货原文，取『快递单号：』那一段，没有就截断原文。"""
    import re
    raw = (meta.get("tracking_no") or task.get("tracking_number") or "").strip()
    if not raw:
        return ""
    m = re.search(r"快递单号[:：]\s*([^\s，,。]+)", raw)
    if m:
        return m.group(1)
    first = next((ln.strip() for ln in raw.splitlines() if ln.strip()), "")
    return first[:40]


# ─────────────────────────────────────────────────────────────
# TBox：本体定义（进程内直取）
# ─────────────────────────────────────────────────────────────
# CONCEPTS / RELATIONS / ACTIONS / INVARIANTS / RULES / ACTION_REGISTRY 都是
# Python 字面量、不落库。迁移后它们与本模块同进程，直接 import 即可 ——
# 不再需要 HTTP 转发、TTL 缓存与 AST 源码解析这三层跨进程脚手架。


def _empty_spec():
    """引擎模块异常时的空 TBox，保证可观测页始终能渲染（不 500）。"""
    return {"success": True, "service": "emp-009",
            "concepts": {}, "relations": {}, "actions": {},
            "invariants": [], "rules": [], "action_registry": {},
            "fetched_at": "", "source": "unavailable"}


def spec(force: bool = False):
    """取本体定义。返回 (data, source)；source ∈ local | unavailable。

    `force` 参数保留（前端「刷新」按钮会传）但已无实际作用：进程内直取本就是实时的。
    引擎模块导入异常时降级为 unavailable 空 TBox，不向上抛错导致 500——
    可观测页是「只读业务呈现」，缺失时显示空概念即可。
    """
    try:
        from ontology_engine import actions as _acts
        from ontology_engine import knowledge as _know
        from ontology_engine import ontology as _onto
        data = {
            "success": True, "service": "emp-009",
            "concepts": _onto.CONCEPTS, "relations": _onto.RELATIONS,
            "actions": _onto.ACTIONS, "invariants": _onto.INVARIANTS,
            "rules": _know.RULES, "action_registry": _acts.ACTION_REGISTRY,
        }
        source = "local"
    except Exception:
        data, source = _empty_spec(), "unavailable"
    data["fetched_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return data, source


# ─────────────────────────────────────────────────────────────
# 概览
# ─────────────────────────────────────────────────────────────
def overview():
    counts = {}
    try:
        conn = _conn()
        try:
            for t in ONT_TABLES:
                try:
                    counts[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                except sqlite3.Error:
                    counts[t] = None  # 表不存在（老库）不算致命错误
        finally:
            conn.close()
        db_ok = True
        db_error = ""
    except Exception as e:
        counts = {t: None for t in ONT_TABLES}
        db_ok = False
        db_error = f"{type(e).__name__}: {e}"

    try:
        _, spec_source = spec()
        spec_ok = True
        spec_error = ""
    except Exception as e:
        spec_source = "unavailable"
        spec_ok = False
        spec_error = f"{type(e).__name__}: {e}"

    # 引擎运行态：治理开关 + 数字员工启停 —— 迁移后引擎同进程，概览页可直接展示
    engine = {"governor": {}, "agent": {}, "error": ""}
    try:
        from ontology_engine import agent_registry as _reg
        from ontology_engine import execution as _exec
        engine["governor"] = _exec.governor()
        engine["agent"] = _reg.state()
    except Exception as e:
        engine["error"] = f"{type(e).__name__}: {e}"

    return {
        "db_path": ONT_DB_PATH,
        "db_ok": db_ok,
        "db_error": db_error,
        "db_mtime": (time.strftime("%Y-%m-%d %H:%M:%S",
                                   time.localtime(os.path.getmtime(ONT_DB_PATH)))
                     if os.path.exists(ONT_DB_PATH) else ""),
        "counts": counts,
        "spec_source": spec_source,
        "spec_ok": spec_ok,
        "spec_error": spec_error,
        # 本体轨已迁入本工程、与本服务同进程，不再有外部 neuops 依赖
        "engine": "local",
        "engine_state": engine,
    }


# ─────────────────────────────────────────────────────────────
# 认领健康度：扫描水位 + 未闭环邮件（运维告警面板）
# ─────────────────────────────────────────────────────────────
def claim_state():
    """本体轨邮件认领是否有卡单。

    `unclaimed` 是已登记但任务未建成的邮件（claim_status=pending/failed），
    下一轮扫描会自动重试；数量长期不降说明存在稳定失败，需人工介入。
    `watermark` 是引擎上次成功扫完收件箱的时刻，用于停机后补扫防漏单。
    老库无 o_scan_state / claim_status 时降级为空值，不报错。
    """
    watermark_ts, unclaimed = 0, []
    degraded = []
    try:
        rows = _rows("SELECT last_ts FROM o_scan_state WHERE scan_key='inquiry'")
        watermark_ts = int((rows[0] or {}).get("last_ts") or 0) if rows else 0
    except Exception:
        degraded.append("o_scan_state")
    try:
        unclaimed = _rows(
            "SELECT email_message_id, title, from_email, send_time, claim_status, claim_error"
            " FROM o_email WHERE IFNULL(claim_status,'') IN ('pending','failed')"
            " ORDER BY send_time DESC LIMIT 100")
    except Exception:
        degraded.append("o_email.claim_status")
    return {
        "watermark_ts": watermark_ts,
        "watermark": (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(watermark_ts))
                      if watermark_ts else ""),
        "unclaimed_count": len(unclaimed),
        "unclaimed": unclaimed,
        "degraded": degraded,
    }


# ─────────────────────────────────────────────────────────────
# ABox：实例（实体与关系面板）
# ─────────────────────────────────────────────────────────────
def instances(task_limit: int = 50, email_limit: int = 50, quote_limit: int = 100):
    tasks = _rows("SELECT * FROM o_task ORDER BY create_time DESC LIMIT ?", (task_limit,))
    for t in tasks:
        meta = _meta(t)
        t["spare_info_parsed"] = {
            "project_no": meta.get("project_no", ""),
            "project_name": meta.get("project_name", ""),
            "part_type": meta.get("part_type", ""),
            "brand": meta.get("brand", ""),
            "pn": meta.get("pn", ""),
            "spec": meta.get("spec", ""),
            "condition": meta.get("condition", ""),
            "count": meta.get("count", ""),
            "urgent": meta.get("urgent", ""),
            "address": meta.get("address", ""),
            "suppliers": meta.get("suppliers", []),
            "approver_emails": meta.get("approver_emails", []),
            "pm_emails": meta.get("pm_emails", []),
            "quotes": meta.get("quotes", []),
            # 定标模式：True=自动轨（A 声明「无特殊要求，最低价中标」，AI 比价后直送审批）；
            # False=人工轨（先交项目经理定标，PM 线下比选后自行送审批）。
            # 缺省 False：旧任务无该字段，按人工轨展示（与 orbit.ctx_from_task 口径一致）。
            "auto_award": bool(meta.get("auto_award")),
            # 人工轨已向项目经理发出定标请求的时间戳（空=尚未发出）
            "pm_notified_at": meta.get("pm_notified_at", ""),
        }
        t["target_supplier_list"] = _load_json(t.get("target_supplier_list"), [])
    return {
        "tasks": tasks,
        "persons": _rows("SELECT * FROM o_person LIMIT 200"),
        "emails": _rows("SELECT email_message_id, task_id, session_id, title, template_type,"
                        " from_email, send_time, in_reply_to FROM o_email"
                        " ORDER BY send_time DESC LIMIT ?", (email_limit,)),
        "quotes": _rows("SELECT * FROM o_supplier_quote ORDER BY receive_time DESC LIMIT ?",
                        (quote_limit,)),
        "sessions": _rows("SELECT * FROM o_session ORDER BY create_time DESC LIMIT 100"),
    }


# ─────────────────────────────────────────────────────────────
# 知识：动作定义 + 全局不变量 + 规则集
# ─────────────────────────────────────────────────────────────
def knowledge():
    data, source = spec()
    return {
        "source": source,
        "actions": data.get("actions", {}),
        "invariants": data.get("invariants", []),
        "rules": data.get("rules", []),
    }


# ─────────────────────────────────────────────────────────────
# 动作：注册表 + 执行历史
# ─────────────────────────────────────────────────────────────
def actions():
    data, source = spec()
    # 必须深拷贝：迁移后 spec() 返回的是**引擎模块里的活字典**（ACTION_REGISTRY），
    # 下面会往每个动作里塞 _stats 统计字段。若直接改，统计结果会永久污染引擎的注册表，
    # 并从 /spec、/knowledge 等其它端点漏出去。（迁移前数据来自 HTTP JSON，每次都是新对象，
    # 所以原代码就地修改是安全的 —— 这是「跨进程改同进程」必须补的一刀。）
    registry = copy.deepcopy(data.get("action_registry", {}))
    # o_audit_log 里的 action 带前缀（align: / noop:），归一化后统计真实动作调用次数
    hist = _rows("SELECT action, COUNT(*) AS n, MAX(operate_time) AS last_time"
                 " FROM o_audit_log GROUP BY action")
    stats = {}
    for h in hist:
        raw = h["action"] or ""
        kind, name = ("exec", raw) if ":" not in raw else raw.split(":", 1)
        s = stats.setdefault(name, {"exec": 0, "align": 0, "noop": 0, "last_time": ""})
        s[kind] = s.get(kind, 0) + h["n"]
        if (h["last_time"] or "") > s["last_time"]:
            s["last_time"] = h["last_time"] or ""
    for a in registry.values():
        a.setdefault("_stats", {"exec": 0, "align": 0, "noop": 0, "last_time": ""})
    for name, s in stats.items():
        registry.setdefault(name, {"desc": "(仅见于审计流水，未在本体注册表中声明)"})
        registry[name]["_stats"] = s
    return {"source": source, "action_registry": registry}


def audit(action: str = "", biz_id: str = "", keyword: str = "", limit: int = 200):
    where, params = ["1=1"], []
    if action:
        where.append("action LIKE ?")
        params.append(f"%{action}%")
    if biz_id:
        where.append("biz_id LIKE ?")
        params.append(f"%{biz_id}%")
    if keyword:
        where.append("(operator LIKE ? OR remark LIKE ? OR content_snapshot LIKE ?)")
        params.extend([f"%{keyword}%"] * 3)
    rows = _rows(f"SELECT * FROM o_audit_log WHERE {' AND '.join(where)}"
                 f" ORDER BY audit_log_id DESC LIMIT ?", (*params, limit))
    for r in rows:
        # content_snapshot 是 JSON 文本，前端要按对象展示
        r["content_snapshot_parsed"] = _load_json(r.get("content_snapshot"), {})
    return rows


# ─────────────────────────────────────────────────────────────
# 任务列表
# ─────────────────────────────────────────────────────────────
def tasks(status: str = "", keyword: str = "", limit: int = 200):
    where, params = ["1=1"], []
    if status:
        where.append("(status = ? OR internal_status = ? OR external_status = ?)")
        params.extend([status] * 3)
    if keyword:
        where.append("(task_id LIKE ? OR from_email LIKE ? OR spare_info LIKE ?"
                     " OR target_supplier LIKE ?)")
        params.extend([f"%{keyword}%"] * 4)
    rows = _rows(f"SELECT * FROM o_task WHERE {' AND '.join(where)}"
                 f" ORDER BY create_time DESC LIMIT ?", (*params, limit))
    out = []
    for t in rows:
        meta = _meta(t)
        supplier = _supplier_of(t, meta)
        suppliers = meta.get("suppliers") or []
        quotes = meta.get("quotes") or []
        valid_quotes = [q for q in quotes if q.get("email") and q.get("unit_price")]
        out.append({
            "task_id": t.get("task_id"),
            "session_id": t.get("session_id"),
            "from_email": t.get("from_email"),
            "status": t.get("status"),
            "internal_status": t.get("internal_status"),
            "external_status": t.get("external_status"),
            "mode": t.get("mode"),
            "quote_deadline": t.get("quote_deadline"),
            "urgency_raw": t.get("urgency_raw"),
            "target_supplier": supplier,
            "tracking_number": _tracking_of(t, meta),
            "create_time": t.get("create_time"),
            "update_time": t.get("update_time"),
            "close_time": t.get("close_time"),
            "part": {k: meta.get(k, "") for k in
                     ("project_no", "project_name", "part_type", "brand", "pn",
                      "spec", "condition", "count", "address", "urgent")},
            "suppliers": suppliers,
            "supplier_count": len(suppliers),
            "quote_count": len(quotes),
            "valid_quote_count": len(valid_quotes),
            # 双流关键节点：是否已发询价 B / 定标请求 P / 审批 D / 订货 E / 结算 G
            # P 仅人工轨有（A 未声明「无特殊要求，最低价中标」时发项目经理定标）。
            "milestones": {
                "inquiry_sent": bool(meta.get("b_msg_ids")),
                "pm_decision_sent": bool(meta.get("p_msg_id")),
                "approval_sent": bool(meta.get("d_msg_id")),
                "order_sent": bool(meta.get("e_msg_id")),
                "settled": bool(meta.get("g_msg_id")),
                "tracking_no": bool(meta.get("tracking_no")),
                "engineer_close": bool(meta.get("engineer_close")),
            },
            # 定标模式：True=自动轨（AI 比价直送审批）/ False=人工轨（先交项目经理定标）
            "auto_award": bool(meta.get("auto_award")),
        })
    return out


def task_detail(task_id: str):
    rows = _rows("SELECT * FROM o_task WHERE task_id = ?", (task_id,))
    if not rows:
        return None
    t = rows[0]
    meta = _meta(t)
    return {
        "task": {k: v for k, v in t.items() if k != "spare_info"},
        "spare_info": meta,
        "target_supplier_list": _load_json(t.get("target_supplier_list"), []),
        "audit": _rows("SELECT * FROM o_audit_log WHERE biz_id = ?"
                       " ORDER BY audit_log_id DESC LIMIT 300", (task_id,)),
        "emails": _rows("SELECT email_message_id, title, template_type, from_email,"
                        " send_time, in_reply_to FROM o_email"
                        " WHERE task_id = ? OR session_id = ? ORDER BY send_time",
                        (task_id, t.get("session_id") or "")),
        "quotes": _rows("SELECT * FROM o_supplier_quote WHERE task_id = ?", (task_id,)),
    }


# ─────────────────────────────────────────────────────────────
# 台账：结算 / 闭环记录
# ─────────────────────────────────────────────────────────────
def ledger(limit: int = 200):
    """本体轨没有独立的结算表，闭环记录由「终态任务 + 审计流水」推导。

    一条台账 = 一个已闭环的 o_task：供应商取 target_supplier，单价取该供应商在
    spare_info.quotes 里的报价，数量取备件 count，闭环时间取 engineerFinalClose
    审计时间（缺则退回任务 update_time）。
    """
    rows = _rows("SELECT * FROM o_task ORDER BY create_time DESC")
    settle_time = {}
    for r in _rows("SELECT biz_id, MAX(operate_time) AS t FROM o_audit_log"
                   " WHERE action LIKE '%engineerFinalClose%' GROUP BY biz_id"):
        settle_time[r["biz_id"]] = r["t"]

    out = []
    for t in rows:
        status = (t.get("status") or "").upper()
        if status not in _CLOSED_STATUS:
            continue
        meta = _meta(t)
        supplier = _supplier_of(t, meta)
        unit_price = ""
        for q in (meta.get("quotes") or []):
            if q.get("email") == supplier:
                unit_price = q.get("unit_price", "")
                break
        try:
            amount = round(float(unit_price) * float(meta.get("count") or 0), 2)
        except (TypeError, ValueError):
            amount = None
        out.append({
            "task_id": t.get("task_id"),
            "project_no": meta.get("project_no", ""),
            "project_name": meta.get("project_name", ""),
            "part": " ".join(x for x in (meta.get("brand", ""), meta.get("pn", "")) if x),
            "spec": meta.get("spec", ""),
            "count": meta.get("count", ""),
            "supplier": supplier,
            "unit_price": unit_price,
            "amount": amount,
            "tracking_no": _tracking_of(t, meta),
            "close_status": status,
            "close_time": settle_time.get(t.get("task_id")) or t.get("close_time") or t.get("update_time") or "",
            "close_feedback": meta.get("engineer_close") or t.get("close_feedback") or "",
        })
    out.sort(key=lambda r: r["close_time"] or "", reverse=True)
    return out[:limit]


# ─────────────────────────────────────────────────────────────
# 编辑扩展预留（当前未接入任何路由）
# ─────────────────────────────────────────────────────────────
# 后续要支持编辑时，在这下面补写入函数（UPDATE/INSERT + 写 o_audit_log），
# 再到 main.py 挂 POST/PUT 路由即可。注意两条约束：
#   1. o_audit_log 是仅追加表，任何修改都要补一条审计，不要 UPDATE/DELETE；
#   2. 本体库的写入端是同进程的 ontology_engine（常驻循环）。要写请复用
#      `ontology_engine.store` 的写函数，不要在这里另开可写连接 ——
#      两个写者争 SQLite 写锁容易 database is locked，且绕过 store 就绕过了审计。
#
# def update_task_field(task_id: str, field: str, value, operator: str = 'web'):
#     raise NotImplementedError('本体可观测当前为只读面板')
