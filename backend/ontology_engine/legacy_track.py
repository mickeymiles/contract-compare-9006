# -*- coding: utf-8 -*-
"""现轨（传统状态机）任务只读适配层 —— 供本体轨做「影子对齐」用。

迁移说明
────────
原实现依赖 neuops-agent-demo 的 `app/db/spare_mail.py`（表 `spare_mail_task`）。
本体可观测迁入本工程后，现轨任务的落地表是本工程主库的 `procurement_task`。
两张表字段命名不同，故这里做一层**只读字段映射**，把 procurement_task 的行
翻译成本体轨决策器（decision.build_fact_context）期望的形状：

    procurement_task            →  本体轨事实字段
    ─────────────────────────────────────────────
    spare_part_model            →  part_type
    purchase_qty                →  count
    inquiry_supplier_list       →  suppliers_json
    replied_supplier_quotes     →  quotes_json
    logistics_no                →  shipped_no
    task_status                 →  status
    （project_no / project_name / brand / pn / spec / condition / address /
      urgent / internal_status / external_status / target_supplier / from_email 同名直通）

只读、全程容错：表不存在或库不可达时返回空，不抛异常、不阻断可观测页渲染。
"""
import json
import sqlite3

from .party_config import db_path

# procurement_task 列名 → 本体轨事实字段名
_FIELD_MAP = {
    "spare_part_model": "part_type",
    "purchase_qty": "count",
    "inquiry_supplier_list": "suppliers_json",
    "replied_supplier_quotes": "quotes_json",
    "logistics_no": "shipped_no",
    "task_status": "status",
}


def _connect():
    conn = sqlite3.connect(f"file:{db_path()}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def _adapt(row) -> dict:
    """把一行 procurement_task 翻译成本体轨事实字段（保留原列名，额外补别名）。"""
    d = dict(row)
    for src, dst in _FIELD_MAP.items():
        if src in d and dst not in d:
            d[dst] = d[src]
    # 现轨 JSON 列在库里是文本，decision 侧两种都吃，这里统一解析一次便于对齐比较
    for k in ("suppliers_json", "quotes_json"):
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            try:
                d[k] = json.loads(v)
            except ValueError:
                d[k] = []
    # procurement_task 无「最近步骤」文本列；本体轨仅用它做关键词判断，缺失按空串处理
    d.setdefault("latest_step", "")
    return d


def get_task(task_id: str):
    """按 task_id 取单条现轨任务；不存在 / 不可读返回 None。"""
    task_id = str(task_id or "").strip()
    if not task_id:
        return None
    try:
        conn = _connect()
    except Exception:
        return None
    try:
        r = conn.execute("SELECT * FROM procurement_task WHERE task_id=?", (task_id,)).fetchone()
        return _adapt(r) if r else None
    except sqlite3.Error:
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def list_tasks(filter: dict = None, page_size: int = 100) -> list:
    """现轨任务列表。filter 支持 status / keyword；不可读时返回 []。"""
    filter = filter or {}
    try:
        conn = _connect()
    except Exception:
        return []
    try:
        sql = "SELECT * FROM procurement_task WHERE 1=1"
        params = []
        status = filter.get("status")
        if status:
            sql += " AND task_status=?"
            params.append(status)
        keyword = filter.get("keyword")
        if keyword:
            sql += (" AND (project_name LIKE ? OR pn LIKE ?"
                    " OR target_supplier LIKE ? OR selected_supplier LIKE ?)")
            params.extend([f"%{keyword}%"] * 4)
        sql += " ORDER BY create_time DESC LIMIT ?"
        params.append(int(page_size))
        return [_adapt(r) for r in conn.execute(sql, params).fetchall()]
    except sqlite3.Error:
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass
