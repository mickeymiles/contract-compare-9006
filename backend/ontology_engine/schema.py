# -*- coding: utf-8 -*-
"""本体轨（ABox）数据库 schema —— 本工程自持。

迁移说明
────────
原库文件是 neuops-agent-demo 工程根下的 `neuops_ontology.db`，由 9007 进程建库并写入，
本工程只能只读外挂。本体可观测整体迁入后，库改为**本工程自己建、自己写**：

    工程根/contract_ontology.db      （可用 ONT_DB_PATH 覆盖）

与主库 `contract_compare.db` 分文件存放：本体轨常驻循环会持续写 o_email / o_audit_log，
分开可避免与主库业务查询争 SQLite 写锁（WAL 下也仍是单写者）。
两者都在工程根、都被 .gitignore 忽略，备份时一起打包即可。

表清单：o_session / o_task / o_person / o_email / o_scan_state /
        o_supplier_quote / o_audit_log / o_alignment / o_agent_state
"""
import os
import sqlite3
import threading

# backend/ontology_engine/schema.py -> ontology_engine -> backend -> 工程根
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ONT_DB_PATH = os.getenv("ONT_DB_PATH", os.path.join(_REPO_ROOT, "contract_ontology.db"))
_lock = threading.Lock()
_inited = False


def get_conn():
    conn = sqlite3.connect(ONT_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def connect():
    """建库后的连接（供 agent_registry 等使用；保证表已存在）。

    首次调用才跑 DDL，之后直接连库——本体轨每轮循环会读多次开关，
    每次都跑一遍 DDL 是无谓开销。
    """
    if not _inited:
        ensure_core_tables()
    return get_conn()


_DDL = [
    # 预会话：立项前临时实体（多轮补齐）
    """CREATE TABLE IF NOT EXISTS o_session (
        session_id TEXT PRIMARY KEY,
        initiator_person_id TEXT,
        thread_id TEXT,
        status TEXT DEFAULT 'PRE_CHECK',
        create_time TEXT,
        update_time TEXT,
        abandon_reason TEXT,
        auto_abandon_threshold_hours INTEGER DEFAULT 24
    )""",
    # 任务：业务根实体（独立于 spare_mail_task）
    """CREATE TABLE IF NOT EXISTS o_task (
        task_id TEXT PRIMARY KEY,
        session_id TEXT,
        threat_msg_id TEXT DEFAULT '',
        from_email TEXT DEFAULT '',
        spare_info TEXT DEFAULT '{}',
        urgency_raw TEXT DEFAULT '',
        quote_deadline TEXT DEFAULT '',
        target_supplier_list TEXT DEFAULT '[]',
        target_supplier TEXT DEFAULT '',
        tracking_number TEXT DEFAULT '',
        close_feedback TEXT DEFAULT '',
        status TEXT DEFAULT 'INIT',
        internal_status TEXT DEFAULT 'R_INIT',
        external_status TEXT DEFAULT 'R_SEND',
        mode TEXT DEFAULT 'ontology',
        create_time TEXT,
        close_time TEXT,
        update_time TEXT
    )""",
    # 人员：映射业务主数据
    """CREATE TABLE IF NOT EXISTS o_person (
        person_id TEXT PRIMARY KEY,
        name TEXT DEFAULT '',
        email TEXT DEFAULT '',
        role TEXT DEFAULT ''
    )""",
    # 邮件：emailMessageId 幂等唯一键
    # claim_status 两阶段消费标记（防丢单）：
    #   pending = 已登记但业务处理（建任务）未完成 → 下轮必须重试
    #   done    = 业务处理已完成 → 永久跳过
    #   failed  = 处理异常，保留现场，下轮仍重试
    """CREATE TABLE IF NOT EXISTS o_email (
        email_message_id TEXT PRIMARY KEY,
        task_id TEXT DEFAULT '',
        session_id TEXT DEFAULT '',
        title TEXT DEFAULT '',
        body TEXT DEFAULT '',
        send_time TEXT DEFAULT '',
        template_type TEXT DEFAULT '',
        from_email TEXT DEFAULT '',
        to_json TEXT DEFAULT '[]',
        cc_json TEXT DEFAULT '[]',
        in_reply_to TEXT DEFAULT '',
        `references` TEXT DEFAULT '',
        claim_status TEXT DEFAULT '',
        claim_error TEXT DEFAULT ''
    )""",
    # 扫描水位：记录上次成功扫描完成的时刻。
    # 用途是「防漏」而非「防重」——防重由 email_message_id 唯一键负责。
    # 服务停机超过固定窗口（原写死 48h）时，靠水位把扫描下界前移，避免停机期间邮件永久漏单。
    """CREATE TABLE IF NOT EXISTS o_scan_state (
        scan_key TEXT PRIMARY KEY,
        last_ts INTEGER DEFAULT 0,
        update_time TEXT DEFAULT ''
    )""",
    # 报价：独立生命周期
    """CREATE TABLE IF NOT EXISTS o_supplier_quote (
        quote_id TEXT PRIMARY KEY,
        task_id TEXT DEFAULT '',
        supplier_person_id TEXT DEFAULT '',
        quote_raw_text TEXT DEFAULT '',
        unit_price TEXT DEFAULT '',
        receive_time TEXT DEFAULT '',
        is_timeout INTEGER DEFAULT 0,
        is_valid INTEGER DEFAULT 1,
        invalid_reason TEXT DEFAULT ''
    )""",
    # 审计：仅追加，禁止修改/删除
    """CREATE TABLE IF NOT EXISTS o_audit_log (
        audit_log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        biz_type TEXT,
        biz_id TEXT,
        action TEXT,
        operator TEXT,
        operate_time TEXT,
        content_snapshot TEXT DEFAULT '{}',
        remark TEXT DEFAULT ''
    )""",
    # 阶段A只读对照：本体轨推断动作 vs 现轨实际
    """CREATE TABLE IF NOT EXISTS o_alignment (
        alignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT,
        legacy_external TEXT,
        legacy_internal TEXT,
        proposed_action TEXT,
        proposed_external TEXT,
        proposed_internal TEXT,
        aligned INTEGER,
        diff TEXT DEFAULT '',
        create_time TEXT
    )""",
    # 数字员工（emp-009）启停与渠道配置。
    # 迁移前这些状态在 neuops 的 employees / employee_skills / employee_channels 三张表里，
    # 本工程不复制员工中台，只留本体轨真正需要的 KV（详见 agent_registry.py）。
    """CREATE TABLE IF NOT EXISTS o_agent_state (
        k TEXT PRIMARY KEY,
        v TEXT DEFAULT ''
    )""",
]


def init():
    global _inited
    with _lock:
        conn = get_conn()
        try:
            for ddl in _DDL:
                conn.execute(ddl)
            # 幂等迁移：老库补 internal/external 状态列
            cols = [r[1] for r in conn.execute("PRAGMA table_info(o_task)").fetchall()]
            if "internal_status" not in cols:
                conn.execute("ALTER TABLE o_task ADD COLUMN internal_status TEXT DEFAULT 'R_INIT'")
            if "external_status" not in cols:
                conn.execute("ALTER TABLE o_task ADD COLUMN external_status TEXT DEFAULT 'R_SEND'")
            # 幂等迁移：老库补两阶段认领列。
            # 存量行 claim_status 为空——视同 'done'（历史邮件早已建过任务），避免升级后重扫重建。
            ecols = [r[1] for r in conn.execute("PRAGMA table_info(o_email)").fetchall()]
            if "claim_status" not in ecols:
                conn.execute("ALTER TABLE o_email ADD COLUMN claim_status TEXT DEFAULT ''")
                conn.execute("UPDATE o_email SET claim_status='done' WHERE IFNULL(claim_status,'')=''")
            if "claim_error" not in ecols:
                conn.execute("ALTER TABLE o_email ADD COLUMN claim_error TEXT DEFAULT ''")
            conn.commit()
            _inited = True
        finally:
            conn.close()


def ensure_core_tables():
    init()