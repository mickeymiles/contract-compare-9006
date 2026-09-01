# -*- coding: utf-8 -*-
"""本体轨邮件模板渲染（emp-009，独立于现轨 routes_procurement_agent）。

复用 skill-proc-mail-inquiry 的 A-G 模板（DB `proc_templates` 优先覆盖现轨自定义），
提供：安全 format 渲染、原文引用（=== 分隔，比 `>` 在 webmail 更稳定）、
内外流收件人/Reply-All 辅助。只读复用，不改动现轨文件。
"""
import re
from datetime import datetime


def load_templates():
    """加载 A-G 邮件模板：DB `proc_templates` 覆盖 skill；再从 skill JSON 文件兜底补全缺失宏模板。"""
    tpls = {}
    try:
        from .skills import load_skill
        sk = load_skill("skill-proc-mail-inquiry") or {}
        skill_def = sk.get("skill") or {}
        tpls = dict(skill_def.get("templates") or {}) or dict(sk.get("templates") or {})
    except Exception:
        tpls = {}
    # 兜底：直接读 skill JSON 文件，确保 A-G 齐全（部分装载源可能缺宏模板 G）
    for want in ("A", "B", "C", "D", "E", "F", "G"):
        if want in tpls:
            continue
        try:
            import json
            import os
            p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "skills", "skill-proc-mail-inquiry.json")
            with open(os.path.normpath(p), encoding="utf-8") as f:
                fj = json.load(f)
            ptpl = ((fj.get("skill") or {}).get("templates") or {}) or (fj.get("templates") or {})
            if want in ptpl:
                tpls[want] = ptpl[want]
        except Exception:
            pass
    # 最高优先级：本工程「邮件模板」页面维护的自定义模板（procurement_mail_template）
    # 只覆盖非空字段 —— subject/body 留空的模板仍用 skill 默认，避免发出空邮件
    try:
        from . import party_config as p9
        page_tpls = p9.load_mail_templates() or {}
        if page_tpls:
            merged = dict(tpls)
            for k, v in page_tpls.items():
                base = dict(merged.get(k) or {})
                if v.get("subject"):
                    base["subject"] = v["subject"]
                if v.get("body"):
                    base["body"] = v["body"]
                merged[k] = base
            tpls = merged
    except Exception:
        pass
    return tpls or {}


def _safe_format(template: str, args: dict) -> str:
    if not template:
        return ""
    try:
        return template.format(**args)
    except (KeyError, ValueError):
        def _repl(m):
            k = m.group(1)
            return str(args.get(k, ""))
        return re.sub(r"\{(\w+)\}", _repl, template)


def quote_orig(body: str, max_chars: int = 3000) -> str:
    """将原邮件正文以 === 引用分隔块追加到回复末尾，避免无限嵌套截断。"""
    body = str(body or "").strip()
    if not body:
        return ""
    lines = [ln for ln in body.splitlines()
             if not ln.strip().startswith(">") and not ln.strip().startswith("---")
             and "原始邮件" not in ln]
    content = "\n".join(lines).strip()
    if not content:
        return ""
    if len(content) > max_chars:
        content = content[:max_chars] + "\n……（引用过长已截断）"
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"\n\n{'=' * 40}\n【引用】以下为 {ts} 的被回复邮件原文\n{'=' * 40}\n{content}\n{'=' * 40}\n"


def _supplier_name_map():
    """构建 {email: 名称} 映射，供邮件正文显示供应商实名。

    优先「供应商」页维护的主数据（procurement_supplier）；
    取不到再回退 ONT_SUPPLIERS 环境变量（"名称:邮箱,名称:邮箱"）。"""
    try:
        from . import party_config as p9
        m = p9.supplier_name_map() or {}
        if m:
            return m
    except Exception:
        pass
    try:
        from .config import ONT_SUPPLIERS
        m = {}
        for item in (ONT_SUPPLIERS or "").split(","):
            item = (item or "").strip()
            if not item:
                continue
            if ":" in item:
                name, _, email_ = item.partition(":")
            elif "@" in item:
                name, email_ = item, item
            else:
                continue
            if email_.strip():
                m[email_.strip().lower()] = name.strip()
        return m
    except Exception:
        return {}


def build_fields(ctx: dict, task: dict, supplier_names: dict = None) -> dict:
    """把任务事实（ctx/task）映射为模板占位符取值。
    supplier_names：可选 {email: 实名} 映射（如 中软国际/神州数码），缺省回退 ONT_SUPPLIERS 解析。"""
    sname = supplier_names if isinstance(supplier_names, dict) else _supplier_name_map()
    meta = task.get("spare_info") or {}
    quotes = [q for q in (meta.get("quotes") or []) if q.get("unit_price")]
    target = str(ctx.get("target_supplier") or meta.get("target_supplier") or "")
    lowest = min(quotes, key=lambda q: float(q.get("unit_price") or 1e18)) if quotes else None
    target_quote = next((q for q in quotes if str(q.get("email") or "") == target), None)
    def _sn(email):
        return sname.get(str(email or "").strip().lower(), email or "")
    suppliers_str = "\n".join(
        f"{i + 1}. {_sn(q.get('email', ''))}（{q.get('email', '')}）  单价 {q.get('unit_price', '')}元"
        for i, q in enumerate(quotes)) or "（暂无）"
    condition = ctx.get("condition") or meta.get("condition") or ""
    cond_disp = {"全新": "全新原装", "原厂翻新": "原厂翻新（带保修）",
                 "拆机二手": "拆机二手（无保修）"}.get(condition, condition)
    deadline = meta.get("quote_deadline") or ctx.get("quote_deadline") or ""
    approvers = ctx.get("approver_emails") or meta.get("approver_emails") or []
    base = {
        "project_no": meta.get("project_no") or ctx.get("project_no") or "",
        "project_name": meta.get("project_name") or ctx.get("project_name") or "",
        "part_type": meta.get("part_type") or ctx.get("part_type") or "",
        "brand": meta.get("brand") or ctx.get("brand") or "",
        "pn": meta.get("pn") or ctx.get("pn") or "",
        "spec": meta.get("spec") or ctx.get("spec") or "",
        "condition": condition, "condition_display": cond_disp,
        "count": meta.get("count") or ctx.get("count") or "",
        "address": meta.get("address") or ctx.get("address") or "",
        "urgent": meta.get("urgent") or meta.get("urgency_raw") or ctx.get("urgent") or "",
        "inquiry_dur": meta.get("urgent") or meta.get("urgency_raw") or ctx.get("urgent") or "",
        "latest_ship_time": meta.get("latest_ship_time") or ctx.get("latest_ship_time") or "",
        "deadline": deadline,
        "task_no": task.get("task_id") or "",
        "supplier": _sn(target),
        "suppliers": suppliers_str,
        "suppliers_count": len(quotes),
        "lowest_quote": f"¥{lowest.get('unit_price')}" if lowest else "",
        "lowest_supplier": _sn((lowest or {}).get("email", "")) if lowest else "",
        "approver_emails": "、".join(approvers),
        "quote": (target_quote or {}).get("unit_price", "") or (lowest or {}).get("unit_price", "") or "",
        "receiver_name": "运维部", "receiver_phone": "（请回复本会话提供）",
        "stop_reason": ctx.get("stop_reason") or "无供应商报价且已到询价截止",
        "body_placeholder": "",
    }
    return base


def render(key: str, ctx: dict, task: dict, supplier_names: dict = None):
    """渲染某模板，返回 (subject, body)。supplier_names 见 build_fields。"""
    tpl = (load_templates() or {}).get(key) or {}
    fields = build_fields(ctx, task, supplier_names=supplier_names)
    subj = _safe_format(tpl.get("subject") or "", fields)
    body = _safe_format(tpl.get("body") or "", fields)
    return subj, body


def reply_recipients(reply_from: dict, to, cc=None, self_email=""):
    """Reply-All：合并原邮件 To+Cc+From（排除系统自身），去重后返回 (to, cc)。
    用于外部流在供应商回复线程上全员回复。"""
    _self = {str(self_email or "").lower().strip()}
    cands = []
    cands += list((reply_from or {}).get("to_email_list") or [])
    cands += list((reply_from or {}).get("cc_email_list") or [])
    from_e = str((reply_from or {}).get("from_email") or "").lower().strip()
    if from_e and "@" in from_e:
        cands.append(from_e)
    cands = [a for a in dict.fromkeys(cands) if a and a.strip().lower() not in _self]
    to_extra = [a for a in cands if a not in [str(x).strip() for x in (to or [])]]
    final_to = list(dict.fromkeys([str(a).strip() for a in (to or [])] + to_extra))
    cc_list = list(dict.fromkeys([str(a).strip() for a in (cc or []) if a]))
    return final_to, cc_list