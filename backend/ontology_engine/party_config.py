# -*- coding: utf-8 -*-
"""本体轨(emp-009)参与方与模板配置：直读本工程主库 contract_compare.db。

迁移说明：原为 neuops-agent-demo 的 `app/db/proc_9006_config.py`（跨工程远程读 9006）。
本体可观测整体迁入本工程后，这里读的就是**自己的库**，不再有跨工程路径依赖。

页面维护入口（均在本工程）：
  - 「供应商」  → procurement_supplier      （资源池主数据）
  - 「审批人」  → procurement_approver      （替代 ONT_APPROVERS 环境变量）
  - 「邮件模板」→ procurement_mail_template （A-G，可改措辞）
  - 「抄送」    → procurement_mail_cc       （全局抄送，系统配置）

引擎侧**只读**：所有函数容错，表不存在 / 未配置时返回空，
不抛异常、不阻断主流程（由调用方决定如何降级）。
"""
import os
import sqlite3

# backend/ontology_engine/party_config.py -> ontology_engine -> backend -> 工程根
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 与 backend/models.py、backend/procurement_models.py 的 DB_PATH 指向同一文件
_DEFAULT_DB = os.path.join(_REPO_ROOT, "contract_compare.db")


def db_path() -> str:
    return os.getenv("CONTRACT_DB_PATH", _DEFAULT_DB)


def _connect():
    # 先校验存在性：sqlite3.connect 会在文件缺失时静默创建空库，
    # 路径配错时会污染出一个垃圾 db 文件。
    p = db_path()
    if not p or not os.path.exists(p):
        raise FileNotFoundError("主库不存在: %s" % p)
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(c, name: str) -> bool:
    try:
        r = c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
        return bool(r)
    except Exception:
        return False


def load_suppliers():
    """[{'name':..,'email':..}, ...] 读不到/未配置返回 []"""
    try:
        conn = _connect()
        c = conn.cursor()
        if not _table_exists(c, "procurement_supplier"):
            conn.close()
            return []
        rows = c.execute("SELECT name, email FROM procurement_supplier ORDER BY id ASC").fetchall()
        conn.close()
    except Exception:
        return []
    out = []
    for r in rows:
        email = (r["email"] or "").strip()
        if email:
            out.append({"name": (r["name"] or "").strip() or email, "email": email})
    return out


def load_approvers():
    """['a@b.com', ...] 仅启用中的审批人"""
    try:
        conn = _connect()
        c = conn.cursor()
        if not _table_exists(c, "procurement_approver"):
            conn.close()
            return []
        rows = c.execute(
            "SELECT email FROM procurement_approver WHERE enabled=1 ORDER BY id ASC").fetchall()
        conn.close()
    except Exception:
        return []
    return [(r["email"] or "").strip() for r in rows if (r["email"] or "").strip()]


def load_global_cc():
    """['a@b.com', ...] 9006「抄送」页维护的全局抄送（系统配置）"""
    try:
        conn = _connect()
        c = conn.cursor()
        if not _table_exists(c, "procurement_mail_cc"):
            conn.close()
            return []
        rows = c.execute("SELECT email FROM procurement_mail_cc ORDER BY id ASC").fetchall()
        conn.close()
    except Exception:
        return []
    return [(r["email"] or "").strip() for r in rows if (r["email"] or "").strip()]


def load_mail_templates():
    """{'A': {'subject':..,'body':..}, ...} 仅启用且内容非空者；空 dict 表示全部用默认模板"""
    try:
        conn = _connect()
        c = conn.cursor()
        if not _table_exists(c, "procurement_mail_template"):
            conn.close()
            return {}
        rows = c.execute(
            "SELECT tpl_key, subject, body FROM procurement_mail_template WHERE enabled=1").fetchall()
        conn.close()
    except Exception:
        return {}
    out = {}
    for r in rows:
        subj = (r["subject"] or "").strip()
        body = (r["body"] or "").strip()
        if not subj and not body:
            continue  # 留空 => 回退 skill 默认模板，避免发出空邮件
        key = (r["tpl_key"] or "").strip().upper()
        if key:
            out[key] = {"subject": subj, "body": body}
    return out


def supplier_name_map():
    """{email.lower(): name} 供邮件正文显示供应商实名"""
    return {s["email"].lower(): s["name"] for s in load_suppliers() if s.get("email")}
