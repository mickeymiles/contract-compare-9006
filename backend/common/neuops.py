"""neuops 智能体网关（跨域共享）：触发 emp-008 采购询比价。"""
import httpx
import os

NEUOPS_BASE = os.getenv("NEUOPS_BASE", "http://127.0.0.1:9007")
# 一次 trigger 在 9007 侧可能包含「LLM 组邮件 + SMTP 发送 + IMAP 线程查询」，
# 原硬编码 15 秒在选型确认（flow-05）等较重的流程上必然超时：
# 表现为 9006 每次调用都要干等 15 秒，且确认邮件发不出、target_supplier 等字段回写不到。
# 默认放宽到 45 秒，可用环境变量 NEUOPS_TRIGGER_TIMEOUT 覆盖。
# （该修复源自 main 分支提交 906a6e5，合并 r2 时 r2 抽出的本模块仍为 15 秒，故在此补回）
NEUOPS_TRIGGER_TIMEOUT = float(os.getenv("NEUOPS_TRIGGER_TIMEOUT", "45"))


def trigger_neuops(path: str, payload: dict, timeout: float = None) -> dict:
    """调用 neuops 智能体 trigger API。失败不阻断主流程，返回 trigger 结果。"""
    import copy
    if timeout is None:
        timeout = NEUOPS_TRIGGER_TIMEOUT
    p = copy.deepcopy(payload)
    # 清理空 dict 字段（neuops Pydantic Optional[Model] 遇到 {} 会报 required）
    if isinstance(p, dict) and isinstance(p.get("selected_supplier"), dict) and not p["selected_supplier"]:
        p["selected_supplier"] = None
    try:
        r = httpx.post(f"{NEUOPS_BASE}/api/procurement-agent/{path}",
                       json=p, timeout=timeout)
        return r.json()
    except Exception as e:
        return {"success": False, "error": f"neuops trigger 失败: {type(e).__name__}: {e}"}