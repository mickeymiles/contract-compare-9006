# -*- coding: utf-8 -*-
"""数字员工（emp-009）启停与渠道配置 —— 本工程自持的极简登记表。

迁移说明
────────
原实现依赖 neuops-agent-demo 的 `app/db/employees.py`（employees / employee_skills /
employee_channels 三张表 + 数字员工管理界面）。本工程不复制那一整套员工中台，
只保留本体轨真正需要的两个语义：

  1. **启停开关**：`employees.enabled` / `employee_skills.enabled` 是「开关挂在数字
     员工身上」的生效点 —— 停用后常驻调度立即零副作用，无需改 .env、无需重启。
  2. **邮箱渠道**：`employee_channels(emp,'email')` 允许用库配置覆盖 ONT_MAIL_* 环境变量。

两者统一收敛到本体库的一张 KV 表 `o_agent_state`。行为与迁移前完全一致：
**未登记时按启用放行**（向后兼容旧库/测试库），渠道未配置时回退环境变量。
"""
import json

from . import schema

EMP_ID = "emp-009"
SKILL_ID = "skill-ont-proc-inquiry"

_K_EMP_ENABLED = "emp_enabled"
_K_SKILL_ENABLED = "skill_enabled"
_K_MAIL_CHANNEL = "mail_channel"


def _get(key: str, default=None):
    try:
        conn = schema.connect()
    except Exception:
        return default
    try:
        r = conn.execute("SELECT v FROM o_agent_state WHERE k=?", (key,)).fetchone()
        return r[0] if r else default
    except Exception:
        return default
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _set(key: str, value: str):
    conn = schema.connect()
    try:
        conn.execute("INSERT INTO o_agent_state (k, v) VALUES (?,?) "
                     "ON CONFLICT(k) DO UPDATE SET v=excluded.v", (key, value))
        conn.commit()
    finally:
        conn.close()


def employee_managed() -> bool:
    """emp-009 及其技能是否启用。未登记按启用（与迁移前默认一致）。"""
    if str(_get(_K_EMP_ENABLED, "1")) not in ("1", "true", "True"):
        return False
    if str(_get(_K_SKILL_ENABLED, "1")) not in ("1", "true", "True"):
        return False
    return True


def set_employee_enabled(enabled: bool, skill_enabled: bool = None):
    """页面/接口停用或启用数字员工。skill_enabled=None 表示不改技能开关。"""
    _set(_K_EMP_ENABLED, "1" if enabled else "0")
    if skill_enabled is not None:
        _set(_K_SKILL_ENABLED, "1" if skill_enabled else "0")
    return state()


def state() -> dict:
    return {
        "emp_id": EMP_ID,
        "skill_id": SKILL_ID,
        "emp_enabled": str(_get(_K_EMP_ENABLED, "1")) in ("1", "true", "True"),
        "skill_enabled": str(_get(_K_SKILL_ENABLED, "1")) in ("1", "true", "True"),
        "mail_channel_configured": bool(mail_channel()),
    }


def mail_channel() -> dict:
    """邮箱渠道库配置（覆盖 ONT_MAIL_*）。未配置 / 不完整返回 {}。"""
    raw = _get(_K_MAIL_CHANNEL, "")
    if not raw:
        return {}
    try:
        c = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    if not isinstance(c, dict):
        return {}
    if not (c.get("address") or "").strip() or not (c.get("password") or "").strip():
        return {}
    return c


def set_mail_channel(cfg: dict):
    _set(_K_MAIL_CHANNEL, json.dumps(cfg or {}, ensure_ascii=False))
    return mail_channel()
