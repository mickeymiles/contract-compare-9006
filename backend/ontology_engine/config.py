# -*- coding: utf-8 -*-
"""本体轨（emp-009）引擎配置 —— contract-compare-9006 自持版。

迁移说明
────────
本模块替代原 neuops-agent-demo 的 `app/config.py` 中「本体轨」那一段。
迁移后本体可观测（TBox + ABox + 引擎 + 面板）完全住在本工程里：
  · 参与方 / 邮件模板等业务配置 → 直读本工程 `contract_compare.db`
    （见 party_config.py，页面入口：系统 → 主数据 → 本体可观测 / 采购的供应商·审批人·模板页）
  · 邮箱账号、白名单、扫描窗口等运行参数 → 环境变量（本模块）
  · 本体实例库（o_* 七张表）→ 本工程 `contract_ontology.db`（见 schema.py）

与现轨（neuops emp-008）的隔离要求不变：本体轨必须用**独立邮箱**。
两轨共用一个收件箱时，现轨按 UNSEEN 增量扫描、本体轨会 mark_seen 认领，
必然互相漏单。所以这里不再像 neuops 那样回退到 PROC_MAIL_*，
未配置 ONT_MAIL_USERNAME 时邮件动作直接不可用（引擎会跳过发信并记审计）。
"""
import os

# ── 本服务端口（runtime 自调 /run-full 用）──
PORT = int(os.getenv("PORT", "9006"))

# ── 本体轨独立邮箱（IMAP 收 + SMTP 发）──
ONT_MAIL_USERNAME = os.getenv("ONT_MAIL_USERNAME", "")
ONT_MAIL_PASSWORD = os.getenv("ONT_MAIL_PASSWORD", "")  # 163 邮箱授权码
ONT_MAIL_IMAP_HOST = os.getenv("ONT_MAIL_IMAP_HOST", "imap.163.com")
ONT_MAIL_IMAP_PORT = int(os.getenv("ONT_MAIL_IMAP_PORT", "993"))
ONT_MAIL_SMTP_HOST = os.getenv("ONT_MAIL_SMTP_HOST", "smtp.163.com")
ONT_MAIL_SMTP_PORT = int(os.getenv("ONT_MAIL_SMTP_PORT", "465"))
# 发件显示名（本体身份）。供应商/审批人邮箱里可一眼分辨来源
ONT_MAIL_DISPLAY_NAME = os.getenv("ONT_MAIL_DISPLAY_NAME", "采购智能体")

# ── 参与者兜底配置（权威来源是 contract_compare.db 的页面主数据，这里只是回退）──
# ONT_SUPPLIERS="名称:邮箱,名称:邮箱"；ONT_APPROVERS="邮箱,邮箱"
ONT_SUPPLIERS = os.getenv("ONT_SUPPLIERS", "")
ONT_APPROVERS = os.getenv("ONT_APPROVERS", "")

# ── 询价发起人白名单（逗号分隔邮箱或 @域名）。留空 = 不限制 ──
# 「采购」「备件」是极常见词，不限制时广告/垃圾邮件极易误触发建任务，生产务必配置。
ONT_REQUESTERS = os.getenv("ONT_REQUESTERS", "")

# ── 认领扫描窗口下界（小时）。实际下界 = min(now-该值, 水位-缓冲) ──
ONT_SCAN_HOURS = int(os.getenv("ONT_SCAN_HOURS", "48"))

# ── 结算闭环开关：工程师「更换完成」触发 + 向供应商发结算邮件 G ──
ONT_SETTLEMENT_ENABLED = os.getenv("ONT_SETTLEMENT_ENABLED", "0") == "1"

# ── LLM（DeepSeek）──
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")

_DEEPSEEK_KEY = ""


def settlement_enabled() -> bool:
    """结算闭环是否启用。每次读环境变量，便于运行时切换（不缓存）。"""
    return os.getenv("ONT_SETTLEMENT_ENABLED", "0") == "1"


def load_deepseek_key() -> str:
    """取 DeepSeek API Key：环境变量优先，其次 ~/.hermes/.env、其次 backend/.env。"""
    global _DEEPSEEK_KEY
    if _DEEPSEEK_KEY:
        return _DEEPSEEK_KEY
    key = os.getenv("DEEPSEEK_API_KEY", "")
    if not key:
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for p in (os.path.expanduser("~/.hermes/.env"),
                  os.path.join(backend_dir, ".env"),
                  os.path.join(os.path.dirname(backend_dir), ".env")):
            try:
                with open(p, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        line = line[7:] if line.startswith("export ") else line
                        if line.startswith("DEEPSEEK_API_KEY="):
                            key = line.split("=", 1)[1].strip().strip('"').strip("'")
                            break
            except Exception:
                pass
            if key:
                break
    _DEEPSEEK_KEY = key
    return key
