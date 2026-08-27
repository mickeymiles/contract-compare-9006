"""neuops 智能体网关（跨域共享）：触发 emp-008 采购询比价。"""
import httpx
import os

NEUOPS_BASE = os.getenv("NEUOPS_BASE", "http://127.0.0.1:9007")


def trigger_neuops(path: str, payload: dict, timeout: float = 15.0) -> dict:
    """调用 neuops 智能体 trigger API。失败不阻断主流程，返回 trigger 结果。"""
    import copy
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