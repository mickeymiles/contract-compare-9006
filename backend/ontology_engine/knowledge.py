# -*- coding: utf-8 -*-
"""知识规则层（KNO-R-01）：声明式 precondition/invariant/rule + 极小表达式求解器。
一切领域逻辑以「数据+表达式」声明，不写死为函数体；LLM 决策与规则校验共用本层。
"""

# ── 极小表达式求值器（ctx: dict 提供事实）─────────────────────────────

def _path(ctx, key):
    """支持 'a.b' 取嵌套。返回 (found, value)。"""
    cur = ctx
    for part in key.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return False, None
    return True, cur


def eval_node(node, ctx):
    """递归求值。返回 (bool, 未命中字段名 or '')。"""
    if not isinstance(node, dict) or len(node) != 1:
        return True, ""
    (op, arg), = node.items()

    if op == "and":
        for it in arg:
            ok, why = eval_node(it, ctx)
            if not ok:
                return False, why
        return True, ""
    if op == "or":
        for it in arg:
            ok, _ = eval_node(it, ctx)
            if ok:
                return True, ""
        return False, ""
    if op == "not":
        ok, _ = eval_node(arg, ctx)
        return (not ok), ""

    if op == "is_present":
        found, v = _path(ctx, arg)
        return (found and v is not None), ("" if (found and v is not None) else arg)
    if op == "is_non_empty":
        found, v = _path(ctx, arg)
        ok = found and v is not None and str(v).strip() != ""
        return ok, ("" if ok else arg)
    if op == "is_empty":
        found, v = _path(ctx, arg)
        ok = (not found) or v is None or str(v).strip() == ""
        return ok, ""
    if op == "eq":
        found, v = _path(ctx, arg[0])
        return (found and str(v).strip() == str(arg[1]).strip()), ("" if (found and str(v).strip() == str(arg[1]).strip()) else arg[0])
    if op == "in":
        found, v = _path(ctx, arg[0])
        if not found:
            return False, arg[0]
        return (str(v).strip() in [str(x) for x in arg[1]]), ("" if str(v).strip() in [str(x) for x in arg[1]] else arg[0])
    if op == "count_ge":
        found, v = _path(ctx, arg[0])
        n = len(v) if (found and isinstance(v, (list, dict))) else 0
        return (n >= int(arg[1])), ("")
    if op == "in_ctx_list":
        found, v = _path(ctx, arg[0])
        _, lst = _path(ctx, arg[1])
        if not found or not isinstance(lst, list):
            return False, arg[0]
        return (str(v).strip() in [str(x) for x in lst]), ("" if str(v).strip() in [str(x) for x in lst] else arg[0])
    return True, ""


def validate(node, ctx):
    """对外入口：返回 (bool, 未命中字段描述)。"""
    ok, why = eval_node(node, ctx)
    return ok, why


# ── 声明式规则集（覆盖 NO-012 KNO-R-01 要求）──────────────────────────

def _required_fields_task(node):
    """缺字段→requestMissingFields；活跃发起邮箱才可能 createTask。"""
    return None

# 每条：{id, phase, target(action or state), check(expr), desc}
RULES = [
    {"id": "create_required", "target": "createTask",
     "check": {"and": [
         {"is_non_empty": "project_no"}, {"is_non_empty": "project_name"},
         {"is_non_empty": "part_type"}, {"is_non_empty": "brand"}, {"is_non_empty": "pn"},
         {"is_non_empty": "spec"}, {"is_non_empty": "condition"}, {"is_non_empty": "count"},
         {"is_non_empty": "address"}, {"is_non_empty": "urgent"}]},
     "desc": "createTask 需 requiredFields 齐全；缺则走 requestMissingFields（不建任务）"},
    {"id": "req_2_request_missing", "target": "requestMissingFields",
     "check": {"not": {"and": [
         {"is_non_empty": "project_no"}, {"is_non_empty": "project_name"},
         {"is_non_empty": "part_type"}, {"is_non_empty": "brand"}, {"is_non_empty": "pn"},
         {"is_non_empty": "spec"}, {"is_non_empty": "condition"}, {"is_non_empty": "count"},
         {"is_non_empty": "address"}, {"is_non_empty": "urgent"}]}},
     "desc": "任一必填缺失 → 回信指出缺项，不建任务"},
    {"id": "distribute_ready", "target": "distributeInquiry",
     "check": {"and": [{"eq": ["internal_status", "R_INIT"]}, {"count_ge": ["target_supplier_list", 1]}]},
     "desc": "Task 已建且有目标供应商 → 分发询价（外部流 R_SEND）"},
    {"id": "finalize_quote", "target": "finalizeQuoteCollection",
     "check": {"or": [{"count_ge": ["valid_quotes", 1]}, {"is_present": "deadline_passed"}]},
     "desc": "全有效报价 或 已到截止 → 收集结束，进入报价完成"},
    {"id": "no_valid_quote_abort", "target": "abortTask",
     "check": {"and": [{"eq": ["deadline_passed", True]},
                       {"eq": ["valid_quote_count", 0]},
                       {"eq": ["raw_quote_count", 0]}]},
     "desc": "到截止且无任何/无有效报价 → 任务中止"},
    {"id": "submit_approval", "target": "submitApproval",
     "check": {"and": [{"count_ge": ["valid_quotes", 1]},
                       {"eq": ["collection_done", True]}]},
     "desc": "有有效报价且收集结束 → 发 D 汇总审批（内部流 R_APPROVAL）"},
    {"id": "approval_valid", "target": "processApprovalDecision",
     "check": {"in_ctx_list": ["approval_choice", "valid_supplier_emails"]},
     "desc": "审批所选供应商必须在有效候选池；非法回信重选"},
    {"id": "order_ready", "target": "confirmOrderToSupplier",
     "check": {"and": [{"is_non_empty": "target_supplier"}, {"eq": ["internal_status", "R_APPROVAL"]}]},
     "desc": "审批合法选定 supplier → 下发订货（外部流 R_ORDER）"},
    {"id": "ship_no", "target": "receiveTrackingNumber",
     "check": {"and": [{"eq": ["external_status", "R_ORDER"]}, {"is_non_empty": "tracking_number_candidate"}]},
     "desc": "E 已发且收到快递单号 → WAIT_ENGINEER_CLOSE"},
    {"id": "ask_tracking", "target": "requestTrackingNo",
     "check": {"and": [{"eq": ["external_status", "R_ORDER"]}, {"is_empty": "tracking_number_candidate"}]},
     "desc": "供应商回发货但无单号 → 主动索取并保持 R_ORDER"},
    {"id": "close_confirm", "target": "engineerFinalClose",
     "check": {"and": [{"eq": ["internal_status", "R_CLOSED"]}, {"eq": ["external_status", "R_WAIT_ENGINEER_CLOSE"]}]},
     "desc": "工程师反馈测试完成才 CLOSED（全流程终态）"},
]

# 规则索引
_RULES_BY_TARGET = {}
for _r in RULES:
    _RULES_BY_TARGET.setdefault(_r["target"], []).append(_r)


def check_target(target, ctx):
    """校验动作 target 的所有前置规则是否满足。返回 (ok: bool, 未通过列表)。"""
    failed = []
    for r in _RULES_BY_TARGET.get(target, []):
        ok, why = validate(r["check"], ctx)
        if not ok:
            failed.append({"rule": r["id"], "desc": r["desc"], "missing": why})
    return (len(failed) == 0), failed