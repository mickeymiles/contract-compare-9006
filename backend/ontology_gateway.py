# -*- coding: utf-8 -*-
"""本体可观测（Ontology）数据网关 — 为 9006 的 /api/ontology/* 提供只读数据。

数据来源两路，互不干扰：
  1. ABox（实例事实）：直读 neuops-agent-demo 的 `neuops_ontology.db`（o_* 七张表）。
     只读模式打开（mode=ro），与 9007 的 WAL 写入不冲突，9007 挂掉时仍可看历史数据。
  2. TBox（本体定义）：CONCEPTS / RELATIONS / ACTIONS / INVARIANTS / RULES /
     ACTION_REGISTRY 都是 Python 字面量、不落库，只能从 9007 取。优先走
     `/api/ontology-emp009/spec` HTTP 转发并按 TTL 缓存；9007 未启动时回落到
     直接 AST 解析 9007 源码目录（同机部署时才可用），仍失败则向上抛错由路由层兜底。

当前只提供只读查询。写入口预留见文件末尾「编辑扩展预留」一节。
"""

import ast
import json
import os
import sqlite3
import time

import httpx

# trust_env=False：9007 在本机，若继承 shell 的 HTTP_PROXY 会被代理拦成 502，必须绕开
_HTTP = httpx.Client(trust_env=False, timeout=5)

# ── 9007 侧位置配置（可用环境变量覆盖，便于换机器/容器部署）──
ONT_9007_DIR = os.getenv("ONT_9007_DIR", "/Users/macbook/AI-Agent/neuops-agent-demo")
ONT_9007_DB_PATH = os.getenv("ONT_9007_DB_PATH", os.path.join(ONT_9007_DIR, "neuops_ontology.db"))
NEUOPS_BASE = os.getenv("NEUOPS_BASE", "http://127.0.0.1:9007")
# TBox 是静态定义，缓存 5 分钟足够，避免每次翻页都打 9007
_SPEC_TTL = float(os.getenv("ONT_SPEC_TTL", "300"))

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
    """只读连接本体库。文件不存在时显式抛错，由 _rows 捕获降级为空结果。"""
    if not os.path.exists(ONT_9007_DB_PATH):
        raise sqlite3.OperationalError(f"本体库不存在: {ONT_9007_DB_PATH}")
    conn = sqlite3.connect(f"file:{ONT_9007_DB_PATH}?mode=ro", uri=True, timeout=5)
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
# TBox：本体定义（HTTP 转发 + 缓存 + 源码回落）
# ─────────────────────────────────────────────────────────────
_SPEC_CACHE = {"at": 0.0, "data": None}
# AST 从源码提取的目标：模块相对路径 -> 要取的顶层变量名
_SPEC_SOURCE_TARGETS = {
    "app/ontology/ontology.py": ("CONCEPTS", "RELATIONS", "ACTIONS", "INVARIANTS"),
    "app/ontology/knowledge.py": ("RULES",),
    "app/ontology/actions.py": ("ACTION_REGISTRY",),
}


def _spec_from_http():
    r = _HTTP.get(f"{NEUOPS_BASE}/api/ontology-emp009/spec")
    r.raise_for_status()
    return r.json()


def _spec_from_source():
    """9007 未启动时，直接 AST 解析其源码取字面量定义（同机部署才可用）。

    只取顶层 `NAME = <字面量>` 赋值，不求值任何表达式，因此导入 9007 模块所需
    的依赖（app.config 等）一概不需要。
    """
    spec = {}
    for rel, names in _SPEC_SOURCE_TARGETS.items():
        path = os.path.join(ONT_9007_DIR, rel)
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=path)
        wanted = set(names)
        for node in tree.body:
            # 后续同名赋值覆盖前面的（与 Python 语义一致，如 _RULES_BY_TARGET 无关则不受影响）
            if not isinstance(node, ast.Assign):
                continue
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id in wanted:
                    spec[tgt.id] = ast.literal_eval(node.value)
    missing = [n for names in _SPEC_SOURCE_TARGETS.values() for n in names if n not in spec]
    if missing:
        raise RuntimeError(f"源码中未找到定义: {', '.join(missing)}")
    return {"success": True, "service": "emp-009",
            "concepts": spec["CONCEPTS"], "relations": spec["RELATIONS"],
            "actions": spec["ACTIONS"], "invariants": spec["INVARIANTS"],
            "rules": spec["RULES"], "action_registry": spec["ACTION_REGISTRY"]}


def _empty_spec():
    """9007 不可达 / 源码目录不存在时的空 TBox，保证可观测页始终能渲染（不 500）。"""
    return {"success": True, "service": "emp-009",
            "concepts": {}, "relations": {}, "actions": {},
            "invariants": [], "rules": [], "action_registry": {},
            "fetched_at": "", "source": "unavailable"}


def spec(force: bool = False):
    """取本体定义。返回 (data, source)；source ∈ http | cache | source | unavailable。

    任何失败（9007 未起、源码目录不存在、定义缺失）都降级为 unavailable 空 TBox，
    不再向上抛错导致 500——可观测页是「只读业务呈现」，缺失时显示空概念即可。
    """
    if not force and _SPEC_CACHE["data"] and (time.time() - _SPEC_CACHE["at"]) < _SPEC_TTL:
        return _SPEC_CACHE["data"], "cache"
    data, source = _empty_spec(), "unavailable"
    try:
        data = _spec_from_http()
        source = "http"
    except Exception:
        # 9007 没起：退回源码解析（同机部署才可用）
        try:
            data = _spec_from_source()
            source = "source"
        except Exception:
            data, source = _empty_spec(), "unavailable"
    data["fetched_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _SPEC_CACHE.update(at=time.time(), data=data)
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

    return {
        "db_path": ONT_9007_DB_PATH,
        "db_ok": db_ok,
        "db_error": db_error,
        "db_mtime": (time.strftime("%Y-%m-%d %H:%M:%S",
                                   time.localtime(os.path.getmtime(ONT_9007_DB_PATH)))
                     if os.path.exists(ONT_9007_DB_PATH) else ""),
        "counts": counts,
        "spec_source": spec_source,
        "spec_ok": spec_ok,
        "spec_error": spec_error,
        "neuops_base": NEUOPS_BASE,
    }


# ─────────────────────────────────────────────────────────────
# 认领健康度：扫描水位 + 未闭环邮件（运维告警面板）
# ─────────────────────────────────────────────────────────────
def claim_state():
    """本体轨邮件认领是否有卡单。

    `unclaimed` 是已登记但任务未建成的邮件（claim_status=pending/failed），
    下一轮扫描会自动重试；数量长期不降说明存在稳定失败，需人工介入。
    `watermark` 是 9007 上次成功扫完收件箱的时刻，用于停机后补扫防漏单。
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
            "quotes": meta.get("quotes", []),
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
    registry = data.get("action_registry", {})
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
            # 双流关键节点：是否已发询价 B / 审批 D / 订货 E / 结算 G
            "milestones": {
                "inquiry_sent": bool(meta.get("b_msg_ids")),
                "approval_sent": bool(meta.get("d_msg_id")),
                "order_sent": bool(meta.get("e_msg_id")),
                "settled": bool(meta.get("g_msg_id")),
                "tracking_no": bool(meta.get("tracking_no")),
                "engineer_close": bool(meta.get("engineer_close")),
            },
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
#   2. 本体库是 9007 的写入端，9006 若要写需用可写连接（去掉 mode=ro）并与
#      9007 的 WAL 锁协调，否则容易 database is locked。
#
# def update_task_field(task_id: str, field: str, value, operator: str = 'web'):
#     raise NotImplementedError('本体可观测当前为只读面板')
