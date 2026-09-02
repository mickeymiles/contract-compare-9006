"""
备品备件采购询比价智能体 — 数据模型与数据库初始化
SQLite, 6 张表:
  procurement_task              询比价任务
  procurement_ledger           采购业务台账（闭环凭证）
  procurement_op_log           操作日志
  procurement_supplier         供应商主数据（名称/邮箱/供货能力，独立 CRUD，资源池）
  procurement_contract          合同主数据（合同名/编号/项目经理/项目经理邮箱）
  procurement_mail_cc          全局邮件抄送配置
  procurement_spare_part       备品备件主数据（编码/名称/规格/品牌/单位/分类）
字段定义依据: .trae/documents/备品备件采购询比价智能体设计文档.md
状态枚举依据: 同文档第 3.2 节
"""

import sqlite3
import os
import json
import time
import uuid
from datetime import datetime, timezone, timedelta

# 复用现有 models.py 的 DB 路径（同一 SQLite 文件）
DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
DB_PATH = os.path.join(DB_DIR, 'contract_compare.db')

# 时区：本系统业务在国内，统一用 +08:00
CN_TZ = timezone(timedelta(hours=8))


def get_db():
    """获取数据库连接（与 models.py 一致风格）"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _now_iso():
    """当前时间的 ISO 字符串（北京时区）"""
    return datetime.now(CN_TZ).strftime('%Y-%m-%d %H:%M:%S')


def _ts():
    """当前时间的 unix 时间戳（秒）"""
    return int(time.time())


def _table_columns(c, table):
    """返回某表当前的列名集合（用于幂等判断列是否存在）"""
    rows = c.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


def _ensure_columns(c, table, cols):
    """幂等补列：列不存在才 ALTER TABLE ADD COLUMN（TEXT DEFAULT ''）"""
    existing = _table_columns(c, table)
    for col in cols:
        if col not in existing:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT DEFAULT ''")


# ===================== 表 1: 询比价任务 =====================

TASK_STATUS_ENUM = (
    '询比价进行中', '已选型确认', '供应商发货中', '待收货测试', '流程闭环',  # 正常
    '部分供应商超时', '全部供应商超时', '收货测试失败', '任务已取消',  # 异常
)

EMERGENCY_LEVEL_ENUM = ('2h', '4h', '5h')

# 紧急等级 → 截止时长（秒）
EMERGENCY_SECONDS = {
    '2h': 2 * 3600,
    '4h': 4 * 3600,
    '5h': 5 * 3600,
}

TEST_RESULT_ENUM = (None, '通过', '失败')


def init_procurement_db():
    """初始化备件采购 6 张表（幂等，已存在不重建）"""
    conn = get_db()
    c = conn.cursor()

    # 1. 询比价任务表
    c.execute("""
        CREATE TABLE IF NOT EXISTS procurement_task (
            task_id TEXT PRIMARY KEY,
            contract_no TEXT DEFAULT '',
            spare_part_model TEXT NOT NULL,
            purchase_qty REAL NOT NULL,
            emergency_level TEXT NOT NULL,
            reply_deadline TEXT NOT NULL,
            inquiry_supplier_list TEXT DEFAULT '[]',
            replied_supplier_quotes TEXT DEFAULT '[]',
            no_reply_supplier TEXT DEFAULT '[]',
            selected_supplier TEXT DEFAULT '{}',
            deal_unit_price REAL DEFAULT 0,
            delivery_time TEXT DEFAULT '',
            logistics_no TEXT DEFAULT '',
            test_result TEXT DEFAULT '',
            task_status TEXT NOT NULL DEFAULT '询比价进行中',
            cancel_reason TEXT DEFAULT '',
            ledger_written INTEGER DEFAULT 0,
            creator TEXT DEFAULT '',
            create_time TEXT NOT NULL,
            updated_at TEXT DEFAULT ''
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_proc_task_status ON procurement_task(task_status)")

    # 1b. 幂等补列：为 procurement_task 补上「双流 + 审批 + 备件明细 + 邮件」列（TEXT DEFAULT ''）。
    #     internal_status / external_status = 双流（内部: R_INIT→R_APPROVAL→R_CLOSED；外部: R_SEND→R_WAIT_QUOTES→R_DECIDING→R_ORDER→R_WAIT_SHIPPING→R_CLOSED）
    #     source = 任务来源（页面 / Agent对话 / 邮件），供详情页展示
    _ensure_columns(c, 'procurement_task', [
        # 双流
        'internal_status', 'external_status',
        # 审批
        'approval_state', 'approval_result', 'approver_email', 'target_supplier',
        # 备件明细（页面 / 邮件 / 智能体三入口携带）
        'project_no', 'project_name', 'spec', 'condition', 'pn', 'address',
        'urgent', 'inquiry_deadline',
        # 邮件来源
        'brand', 'latest_ship_time', 'from_email', 'mail_archive_json',
        'source',
    ])

    # 2. 采购业务台账表（闭环自动写入，结算凭证）
    c.execute("""
        CREATE TABLE IF NOT EXISTS procurement_ledger (
            ledger_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            contract_no TEXT DEFAULT '',
            spare_part_model TEXT DEFAULT '',
            purchase_qty REAL DEFAULT 0,
            selected_supplier_name TEXT DEFAULT '',
            deal_unit_price REAL DEFAULT 0,
            delivery_time TEXT DEFAULT '',
            logistics_no TEXT DEFAULT '',
            test_result TEXT DEFAULT '',
            task_close_time TEXT DEFAULT '',
            remark TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_proc_ledger_task ON procurement_ledger(task_id)")

    # 3. 操作日志表
    c.execute("""
        CREATE TABLE IF NOT EXISTS procurement_op_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            operator TEXT DEFAULT '',
            action TEXT NOT NULL,
            action_time TEXT DEFAULT (datetime('now','localtime')),
            remark TEXT DEFAULT ''
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_proc_oplog_task ON procurement_op_log(task_id)")

    # 4. 供应商主数据（资源池，不绑定合同）
    c.execute("""
        CREATE TABLE IF NOT EXISTS procurement_supplier (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            capability TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_proc_supplier_email ON procurement_supplier(email)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_proc_supplier_name ON procurement_supplier(name)")

    # 初始化 3 条示例供应商（只在表空时写入）
    c.execute("SELECT COUNT(*) FROM procurement_supplier")
    if c.fetchone()[0] == 0:
        seed_suppliers = [
            ('东软供应商',    'biquanzhi3@163.com', '擅长网络设备、企业级路由器/交换机主板、光模块供货，7×24 响应，支持上门安装调试。'),
            ('华为总代 星辰设备', 'biquanzhi2@163.com', '华为数通/安全产品金牌总代，AR/NetEngine/S 系列主板/整机现货，可走原厂 RMA 流程。'),
            ('智联信息科技',    'biquanzhi@163.com',  '数据中心通用电源、风扇、SFP/QSFP 光模块现货供应商，支持小批量快发。'),
        ]
        c.executemany("""
            INSERT INTO procurement_supplier(name, email, capability) VALUES (?,?,?)
        """, seed_suppliers)

    # 4.1 审批人配置（备件采购智能体 emp-009 用；页面维护，逐步替代 ONT_APPROVERS 环境变量）
    c.execute("""
        CREATE TABLE IF NOT EXISTS procurement_approver (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_proc_approver_email ON procurement_approver(email)")

    # 4.3 智能体已处理邮件去重表（业务化执行链路用）
    #     取代本体轨 o_email：以 email_message_id 唯一键防重复认领，
    #     是「不靠时间水位、只靠唯一键」去重策略的落点。
    c.execute("""
        CREATE TABLE IF NOT EXISTS procurement_mail_seen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_message_id TEXT NOT NULL,
            task_id TEXT DEFAULT '',
            direction TEXT DEFAULT 'in',
            subject TEXT DEFAULT '',
            from_email TEXT DEFAULT '',
            claim_status TEXT DEFAULT 'claimed',
            claim_error TEXT DEFAULT '',
            received_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_proc_mail_seen_mid "
              "ON procurement_mail_seen(email_message_id)")

    # 4.4 智能体运行状态（扫描水位等键值；业务化执行链路用）
    c.execute("""
        CREATE TABLE IF NOT EXISTS procurement_agent_state (
            state_key TEXT PRIMARY KEY,
            state_value TEXT DEFAULT '',
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    # 4.5 业务化执行链路所需列（幂等补列，已存在不重复添加）
    #     spare_info 承载智能体运行时上下文（邮件线程 id、报价、抄送名单等），
    #     业务字段单独映射到同名列供页面展示，整体再存一份供流程回读还原。
    _ensure_columns(c, "procurement_task", (
        "spare_info", "session_id", "threat_msg_id",
        "close_feedback", "mode", "close_time", "status",
    ))

    # 4.6 发起人白名单（智能体只处理白名单内发件人的询价邮件）
    c.execute("""
        CREATE TABLE IF NOT EXISTS procurement_requester (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT DEFAULT '',
            email TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_proc_requester_email "
              "ON procurement_requester(email)")

    # 4.2 智能体邮件模板配置（A-G；页面可改措辞。subject/body 留空则回退 skill 默认模板，避免发空邮件）
    c.execute("""
        CREATE TABLE IF NOT EXISTS procurement_mail_template (
            tpl_key TEXT PRIMARY KEY,
            name TEXT DEFAULT '',
            subject TEXT DEFAULT '',
            body TEXT DEFAULT '',
            enabled INTEGER DEFAULT 1,
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    _tpl_keys = [
        ("A", "工程师询价回执"),
        ("B", "向供应商发起询价"),
        ("C", "催报价"),
        ("D", "报价汇总待审批"),
        ("E", "订货确认"),
        ("F", "快递单号/中止通知"),
        ("G", "采购结束结算"),
    ]
    c.executemany("""
        INSERT OR IGNORE INTO procurement_mail_template(tpl_key, name) VALUES (?,?)
    """, _tpl_keys)

    # 5. 合同主数据表（核心实体，不再关联项目）
    c.execute("""
        CREATE TABLE IF NOT EXISTS procurement_contract (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contract_no   TEXT NOT NULL,
            contract_name TEXT DEFAULT '',
            pm_name       TEXT DEFAULT '',
            pm_email      TEXT DEFAULT '',
            receiver_name TEXT DEFAULT '',
            receiver_phone TEXT DEFAULT '',
            receiver_address TEXT DEFAULT '',
            created_at    TEXT DEFAULT (datetime('now','localtime')),
            updated_at    TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(contract_no)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_proc_contract_name ON procurement_contract(contract_name)")
    # 老库迁移：补充 收件人/联系方式/邮寄地址 三列（报错则说明已存在，忽略）
    for _col in ('receiver_name', 'receiver_phone', 'receiver_address'):
        try:
            c.execute(f"ALTER TABLE procurement_contract ADD COLUMN {_col} TEXT DEFAULT ''")
        except Exception:
            pass

    # 初始化 4 条示例合同
    c.execute("SELECT COUNT(*) FROM procurement_contract")
    if c.fetchone()[0] == 0:
        seed_contracts = [
            ('IDZB2607070A', '示范项目A期-IT基础设施扩容合同',  '张启明', 'rich-miles@163.com',
             '张启明', '13800001111', '北京市朝阳区望京街10号 望京SOHO塔1-1902'),
            ('CSZB2512210A', '运维节点B期扩容-服务器配件采购合同','李慧敏', 'biquanzhi3@163.com',
             '李慧敏', '13800002222', '上海市浦东新区张江高科技园区祖冲之路887弄 中心大厦B座'),
            ('CGZB2605112B', '核心机房光模块集中采购框架合同',  '王大伟',  'biquanzhi2@163.com',
             '王大伟', '13800003333', '广州市天河区体育西路103号 维多利广场A塔'),
            ('QTZB2603080C', '园区交换机备件及年度维保合同',     '周晓峰',  'biquanzhi@163.com',
             '周晓峰', '13800004444', '深圳市南山区科技园南区 深湾科技园T2栋'),
        ]
        c.executemany("""
            INSERT INTO procurement_contract(contract_no, contract_name, pm_name, pm_email,
                                             receiver_name, receiver_phone, receiver_address)
            VALUES (?,?,?,?,?,?,?)
        """, seed_contracts)

    # 6. 全局邮件抄送配置：所有发给供应商的邮件自动抄送这些人
    c.execute("""
        CREATE TABLE IF NOT EXISTS procurement_mail_cc (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name   TEXT NOT NULL,
            email  TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(email)
        )
    """)
    c.execute("SELECT COUNT(*) FROM procurement_mail_cc")
    if c.fetchone()[0] == 0:
        c.executemany("INSERT INTO procurement_mail_cc(name, email) VALUES (?,?)", [
            ('项目管理（张启明）', 'rich-miles@163.com'),
            ('运维结算组',         'biquanzhi@163.com'),
        ])

    # 7. 备品备件主数据（基础数据，不绑定合同）
    c.execute("""
        CREATE TABLE IF NOT EXISTS procurement_spare_part (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            part_code    TEXT UNIQUE NOT NULL,
            part_name    TEXT NOT NULL,
            spec_model   TEXT DEFAULT '',
            brand        TEXT DEFAULT '',
            unit         TEXT DEFAULT '个',
            category     TEXT DEFAULT '通用',
            condition    TEXT DEFAULT '',
            remark       TEXT DEFAULT '',
            created_at   TEXT DEFAULT (datetime('now','localtime')),
            updated_at   TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_proc_sparepart_code ON procurement_spare_part(part_code)")
    # 老库迁移：补充「成色」列（报错则说明已存在，忽略）
    try:
        c.execute("ALTER TABLE procurement_spare_part ADD COLUMN condition TEXT DEFAULT ''")
    except Exception:
        pass

    # 初始化几条示例备件
    c.execute("SELECT COUNT(*) FROM procurement_spare_part")
    if c.fetchone()[0] == 0:
        c.executemany("""
            INSERT INTO procurement_spare_part(part_code, part_name, spec_model, brand, unit, category, condition, remark)
            VALUES (?,?,?,?,?,?,?,?)
        """, [
            ('SP-0001', '内存条', 'DDR4 32GB 3200MHz', '三星/Samsung', '条', '服务器配件', '全新', 'Dell R740/R760 通用'),
            ('SP-0002', '固态硬盘', '2.5寸 960GB SATA', '希捷/Seagate', '块', '存储配件', '全新', '服务器通用'),
            ('SP-0003', '电源模块', '铂金 800W 80PLUS', '台达/Delta', '个', '电源配件', '全新', 'Dell R740 原装'),
            ('SP-0004', '光模块', '10G SFP+ 多模 850nm', '华为/Huawei', '个', '网络配件', '全新', '交换机通用'),
            ('SP-0005', '服务器风扇', '120mm 20000RPM', '建准/Sunon', '个', '散热配件', '九成新', 'Dell R740/R760'),
            ('SP-0006', '网线', 'CAT6A 10米', '安普/AMP', '根', '网络配件', '全新', '机房布线常用'),
            ('SP-0007', '磁盘阵列卡缓存', '2GB NVMe', 'LSI/Broadcom', '个', '存储配件', '全新', '9361-8i 通用'),
            ('SP-0008', '电池模块', 'UPS 铅酸 12V 9Ah', '施耐德/Schneider', '块', '电源配件', '九成新', 'UPS 备用电源'),
        ])

    # 8. 备件邮件询价（mail_inquiry_task）——只读观察表。
    #    该表由 neuops 引擎（neuops-agent-demo/app/db/contract_mail.py）upsert 写入，
    #    9006 仅初始化（幂等）+ 只读查询，不在此写入任何数据。
    #    DDL 与 neuops 侧保持一致。
    c.execute("""
        CREATE TABLE IF NOT EXISTS mail_inquiry_task (
            task_id TEXT PRIMARY KEY,
            project_no TEXT DEFAULT '',
            project_name TEXT DEFAULT '',
            part_type TEXT DEFAULT '',
            brand TEXT DEFAULT '',
            pn TEXT DEFAULT '',
            spec TEXT DEFAULT '',
            `condition` TEXT DEFAULT '',
            `count` TEXT DEFAULT '',
            address TEXT DEFAULT '',
            urgent TEXT DEFAULT '',
            inquiry_deadline TEXT DEFAULT '',
            suppliers_json TEXT DEFAULT '[]',
            quotes_json TEXT DEFAULT '[]',
            lowest_supplier TEXT DEFAULT '',
            lowest_quote TEXT DEFAULT '',
            approval_state TEXT DEFAULT '',
            approval_result TEXT DEFAULT '',
            approver_email TEXT DEFAULT '',
            target_supplier TEXT DEFAULT '',
            internal_status TEXT DEFAULT '',
            external_status TEXT DEFAULT '',
            status TEXT DEFAULT '',
            shipped_no TEXT DEFAULT '',
            latest_step TEXT DEFAULT '',
            thread_msg_id TEXT DEFAULT '',
            from_email TEXT DEFAULT '',
            mail_archive_json TEXT DEFAULT '[]',
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_mail_inq_status ON mail_inquiry_task(status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_mail_inq_updated ON mail_inquiry_task(updated_at)")

    # ---- 老 schema 迁移：DROP 已废弃的表 + ALTER DROP 老字段（失败不阻断主流程）----
    # 废弃表：procurement_master_data / procurement_project / procurement_contract_supplier / procurement_contract_spare_part
    # 废弃字段：procurement_task.project_id、procurement_contract.project_id
    # 注意：必须先 DROP 引用 project_id 的索引，否则 ALTER DROP COLUMN 会因索引引用而失败
    for ddl in (
        "DROP TABLE IF EXISTS procurement_master_data",
        "DROP TABLE IF EXISTS procurement_project",
        "DROP TABLE IF EXISTS procurement_contract_supplier",
        "DROP TABLE IF EXISTS procurement_contract_spare_part",
        "DROP INDEX IF EXISTS idx_proc_task_project",
        "DROP INDEX IF EXISTS idx_proc_contract_project",
    ):
        try:
            c.execute(ddl)
        except Exception:
            pass
    # 老 SQLite (<3.35) 不支持 DROP COLUMN，用 try/except 兜底；不影响主流程
    # 注意：procurement_task 的 project_name 现在是新功能需要的列（备件明细），不能 DROP；
    #       只对任务表 DROP 废弃的 project_id；台账表两条废弃字段均可 DROP。
    for col in ('project_id',):
        try:
            c.execute(f"ALTER TABLE procurement_task DROP COLUMN {col}")
        except Exception:
            pass
    for col in ('project_id', 'project_name'):
        try:
            c.execute(f"ALTER TABLE procurement_ledger DROP COLUMN {col}")
        except Exception:
            pass
    try:
        c.execute("ALTER TABLE procurement_contract DROP COLUMN project_id")
    except Exception:
        pass

    conn.commit()
    conn.close()


# ===================== Task CRUD =====================

def create_task(*, contract_no, spare_part_model,
                purchase_qty, emergency_level, inquiry_supplier_list=None, creator='',
                project_no='', project_name='', brand='', pn='', spec='', condition='',
                count=None, address='', urgent='', inquiry_deadline='',
                target_supplier='', approver_email='', approval_result='',
                from_email='', latest_ship_time='', source='', **kwargs):
    """创建询比价任务实例（Skill-01 / 页面 / Agent对话 / 工程师邮件 统一入口。

    只要传 business 字段就走标准 create_task，同时支持三入口写同一张 procurement_task：
      - internal_status 默认 'R_INIT'，external_status 默认 'R_SEND'（双流初始化）
      - task_status 仍默认 '询比价进行中'（向后兼容旧读方）
    可选 kwargs（无则用空串）：project_no / project_name / brand / pn / spec / condition /
    count(数量别名，与 purchase_qty 二选一) / address / urgent / inquiry_deadline /
    target_supplier / approver_email / from_email / latest_ship_time / source。
    source 缺省自动推导：有 from_email → '邮件'；creator in ('agent','Agent') → 'Agent对话'；否则 '页面'。
    若未指定 inquiry_supplier_list，自动从供应商资源池全量带出
    """
    if emergency_level not in EMERGENCY_LEVEL_ENUM:
        raise ValueError(f"非法 emergency_level: {emergency_level}")
    # count 作为数量别名：邮件/页面入口可能只传 count 不传 purchase_qty
    if purchase_qty in (None, 0) and count not in (None, ''):
        try:
            purchase_qty = float(count)
        except (TypeError, ValueError):
            purchase_qty = 0
    purchase_qty = float(purchase_qty or 0)
    if not source:
        if from_email:
            source = '邮件'
        elif creator in ('agent', 'Agent', 'Agent对话'):
            source = 'Agent对话'
        else:
            source = '页面'
    now = _now_iso()
    deadline_ts = _ts() + EMERGENCY_SECONDS[emergency_level]
    reply_deadline = datetime.fromtimestamp(deadline_ts, CN_TZ).strftime('%Y-%m-%d %H:%M:%S')
    task_id = f"PROC-{datetime.now(CN_TZ).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
    # 未指定询价供应商 → 自动从资源池全量带
    if not inquiry_supplier_list:
        all_sup = list_suppliers()
        inquiry_supplier_list = [
            {'id': s['id'], 'name': s['name'], 'email': s['email']}
            for s in all_sup
        ]
    # 【修复 2026-08-24】兜底：对显式传入的 inquiry_supplier_list，按 email 反查资源池补 id。
    # 场景：前端正确传了 poolId，但后端 SupplierItem 缺少 id 声明（已修）、或其他调用方（API/Agent）
    # 只传了 name+email。保证最终落库的 JSON 里，资源池供应商一定带 id，flow-02 才能正确标记
    # _is_temp=False（资源池） vs True（临时）。
    try:
        sup_all = list_suppliers()
        sup_by_email = {str(s.get('email', '')).lower().strip(): s for s in sup_all if s.get('email')}
    except Exception:
        sup_by_email = {}
    if inquiry_supplier_list and sup_by_email:
        for s in inquiry_supplier_list:
            if not isinstance(s, dict):
                continue
            if s.get('id'):
                continue  # 已有 id，跳过
            em = str(s.get('email', '')).lower().strip()
            hit = sup_by_email.get(em)
            if hit and hit.get('id'):
                s['id'] = hit['id']
    suppliers_json = json.dumps(inquiry_supplier_list, ensure_ascii=False)
    no_reply_json = json.dumps(inquiry_supplier_list, ensure_ascii=False)
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO procurement_task
        (task_id, contract_no, spare_part_model, purchase_qty,
         emergency_level, reply_deadline, inquiry_supplier_list, no_reply_supplier,
         task_status, creator, create_time, updated_at,
         internal_status, external_status, source,
         approval_state, approval_result, approver_email, target_supplier,
         project_no, project_name, spec, condition, pn, address, urgent, inquiry_deadline,
         brand, latest_ship_time, from_email, mail_archive_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, '询比价进行中', ?, ?, ?,
                'R_INIT', 'R_SEND', ?, '', '', '', '',
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]')
    """, (task_id, contract_no, spare_part_model, purchase_qty,
          emergency_level, reply_deadline, suppliers_json, no_reply_json,
          creator, now, now,
          source,
          project_no, project_name, spec, condition, pn, address, urgent, inquiry_deadline,
          brand, latest_ship_time, from_email))
    _add_op_log(c, task_id, creator, 'create_inquiry', f'发起询价，紧急等级 {emergency_level}')
    conn.commit()
    conn.close()
    return get_task(task_id)


def get_task(task_id):
    """按 task_id 查询任务详情"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM procurement_task WHERE task_id=?", (task_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return _row_to_task(row)


_SOURCE_ALIAS = {
    # 别名 -> 落库标准值（与 create_task 自动推导一致）
    'page': '页面', '页面': '页面',
    'agent': 'Agent对话', 'agent对话': 'Agent对话',
    'email': '邮件', 'mail': '邮件', '邮件': '邮件',
}


def _normalize_source(source):
    """把来源参数归一为落库标准值（页面 / Agent对话 / 邮件）；未识别则原样返回"""
    s = (source or '').strip()
    if not s:
        return s
    return _SOURCE_ALIAS.get(s) or _SOURCE_ALIAS.get(s.lower()) or s


def list_tasks(*, status=None, source=None, keyword=None, limit=200):
    """列出任务（可按 状态 / 来源 / 关键词 过滤，全部默认不过滤）"""
    conn = get_db()
    c = conn.cursor()
    sql = "SELECT * FROM procurement_task"
    where, params = [], []
    if status:
        where.append("task_status=?")
        params.append(status)
    if source:
        where.append("source=?")
        params.append(_normalize_source(source))
    if keyword:
        like = f"%{keyword}%"
        where.append("(task_id LIKE ? OR spare_part_model LIKE ? OR project_name LIKE ?"
                     " OR pn LIKE ? OR spec LIKE ? OR brand LIKE ? OR from_email LIKE ?)")
        params.extend([like] * 7)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY create_time DESC LIMIT ?"
    params.append(limit)
    c.execute(sql, params)
    rows = c.fetchall()
    conn.close()
    return [_row_to_task(r) for r in rows]


def update_task_quote(*, task_id, replied_supplier_quotes, no_reply_supplier, all_replied=False):
    """回填报价（Skill-03 调用），并刷新未回复清单。

    合并策略：若原 replied_supplier_quotes 中某供应商 is_manual=True（人工录入），
    则本次自动解析回来的报价不再覆盖它，保留用户人工录入内容。
    """
    conn = get_db()
    c = conn.cursor()
    now = _now_iso()

    # 取出旧报价，按 email 合并 is_manual 条目
    old = c.execute("SELECT replied_supplier_quotes FROM procurement_task WHERE task_id=?", (task_id,)).fetchone()
    existing = []
    if old and old[0]:
        try:
            existing = json.loads(old[0])
        except Exception:
            existing = []
    manual_map = {
        (x.get("email") or "").lower(): x
        for x in existing if x.get("is_manual")
    }
    merged = []
    for new_q in replied_supplier_quotes:
        key = (new_q.get("email") or "").lower()
        merged.append(manual_map.pop(key, new_q))
    # 可能有人工录入后、本次 IMAP 还没有扫描到这个供应商邮件的情况 → 保留
    for remain in manual_map.values():
        merged.append(remain)

    c.execute("""
        UPDATE procurement_task
        SET replied_supplier_quotes=?, no_reply_supplier=?, updated_at=?
        WHERE task_id=?
    """, (json.dumps(merged, ensure_ascii=False),
          json.dumps(no_reply_supplier, ensure_ascii=False), now, task_id))
    if all_replied:
        c.execute("UPDATE procurement_task SET task_status='询比价进行中' WHERE task_id=?", (task_id,))
    conn.commit()
    conn.close()
    return get_task(task_id)


def manual_update_supplier_quote(*, task_id, reply_index, payload, operator='frontend:user'):
    """前端人工录入/修改指定供应商报价。

    reply_index 为当前 replied_supplier_quotes 数组的索引；
    payload 允许字段: unit_price / total_price / lead_time / brand / model；
    保存后 is_manual=True，后续 IMAP 复解析会保留人工数据。
    """
    conn = get_db()
    c = conn.cursor()
    row = c.execute("SELECT replied_supplier_quotes FROM procurement_task WHERE task_id=?", (task_id,)).fetchone()
    if not row or not row[0]:
        conn.close()
        raise ValueError(f"任务 {task_id} 不存在或尚无报价记录")
    try:
        quotes = json.loads(row[0])
    except Exception as e:
        conn.close()
        raise ValueError(f"replied_supplier_quotes JSON 解析失败: {e}")
    try:
        idx = int(reply_index)
    except Exception:
        conn.close()
        raise ValueError("reply_index 必须是整数")
    if idx < 0 or idx >= len(quotes):
        conn.close()
        raise ValueError(f"reply_index 越界: {idx}，当前报价 {len(quotes)} 条")
    q = quotes[idx]
    for k in ("unit_price", "total_price", "lead_time", "brand", "model"):
        if k in payload and payload[k] not in (None, ""):
            if k in ("unit_price", "total_price"):
                try:
                    q[k] = float(payload[k])
                except (TypeError, ValueError):
                    conn.close()
                    raise ValueError(f"{k} 必须是数字")
            else:
                q[k] = str(payload[k]).strip()
    q["is_manual"] = True
    q["parse_strategy"] = "manual_entry"
    q["note"] = (payload.get("note") or "").strip() or q.get("note", "") or "人工录入报价"

    now = _now_iso()
    c.execute(
        "UPDATE procurement_task SET replied_supplier_quotes=?, updated_at=? WHERE task_id=?",
        (json.dumps(quotes, ensure_ascii=False), now, task_id),
    )
    _add_op_log(
        c, task_id, operator, "manual_edit_quote",
        f"人工修改第 {idx} 号供应商（{q.get('email') or q.get('name')}）报价："
        f"单价 {q.get('unit_price')} 总价 {q.get('total_price')} 货期 {q.get('lead_time')}"
    )
    conn.commit()
    conn.close()
    return get_task(task_id)


def update_task_status_on_deadline(*, task_id, has_replied, all_timeout):
    """截止时间到达的状态跳转（scheduler 调用）"""
    if all_timeout:
        new_status = '全部供应商超时'
    elif has_replied:
        new_status = '部分供应商超时'
    else:
        return get_task(task_id)  # 不该走到这
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE procurement_task SET task_status=?, updated_at=? WHERE task_id=?",
              (new_status, _now_iso(), task_id))
    _add_op_log(c, task_id, 'system:scheduler', 'deadline_reach',
                f'截止到达，状态置为 {new_status}')
    conn.commit()
    conn.close()
    return get_task(task_id)


def confirm_selection(*, task_id, selected_supplier, deal_unit_price, operator=''):
    """选型确认（Skill-05 调用）：状态 → 已选型确认"""
    conn = get_db()
    c = conn.cursor()
    now = _now_iso()
    c.execute("""
        UPDATE procurement_task
        SET selected_supplier=?, deal_unit_price=?, task_status='已选型确认', updated_at=?
        WHERE task_id=?
    """, (json.dumps(selected_supplier, ensure_ascii=False), deal_unit_price, now, task_id))
    _add_op_log(c, task_id, operator, 'confirm_selection',
                f"选中供应商 {selected_supplier.get('name','')}, 成交单价 {deal_unit_price}")
    conn.commit()
    conn.close()
    return get_task(task_id)


def update_task_delivery(*, task_id, delivery_time, logistics_no, operator='system:mail'):
    """回填发货信息（Skill-06 调用）：状态 → 供应商发货中"""
    conn = get_db()
    c = conn.cursor()
    now = _now_iso()
    c.execute("""
        UPDATE procurement_task
        SET delivery_time=?, logistics_no=?, task_status='供应商发货中', updated_at=?
        WHERE task_id=?
    """, (delivery_time, logistics_no, now, task_id))
    _add_op_log(c, task_id, operator, 'delivery_update',
                f"发货时间 {delivery_time}, 物流 {logistics_no}")
    conn.commit()
    conn.close()
    return get_task(task_id)


def input_test_result(*, task_id, test_result, remark='', operator=''):
    """测试结果录入（Skill-07 调用）
    通过 → 状态 流程闭环 + 触发台账写入；失败 → 收货测试失败
    """
    if test_result not in ('通过', '失败'):
        raise ValueError(f"非法 test_result: {test_result}")
    new_status = '流程闭环' if test_result == '通过' else '收货测试失败'
    conn = get_db()
    c = conn.cursor()
    now = _now_iso()
    c.execute("""
        UPDATE procurement_task SET test_result=?, task_status=?, updated_at=? WHERE task_id=?
    """, (test_result, new_status, now, task_id))
    _add_op_log(c, task_id, operator, 'input_test_result',
                f"测试结果 {test_result} 备注 {remark}")
    task_row = c.execute("SELECT * FROM procurement_task WHERE task_id=?", (task_id,)).fetchone()
    conn.commit()
    conn.close()
    if test_result == '通过':
        write_ledger(task_id)  # 闭环自动写台账
    return _row_to_task(task_row)


def cancel_task(*, task_id, cancel_reason, operator=''):
    """任务取消（Skill-09 调用）：状态 → 任务已取消，不写台账"""
    conn = get_db()
    c = conn.cursor()
    now = _now_iso()
    c.execute("""
        UPDATE procurement_task
        SET task_status='任务已取消', cancel_reason=?, updated_at=? WHERE task_id=?
    """, (cancel_reason, now, task_id))
    _add_op_log(c, task_id, operator, 'cancel_task', f"取消原因: {cancel_reason}")
    conn.commit()
    conn.close()
    return get_task(task_id)


# ===================== 台账 =====================

def write_ledger(task_id):
    """任务闭环写入采购业务台账（Skill-08 调用）
    幂等：ledger_written=1 则不再写
    """
    task = get_task(task_id)
    if not task:
        raise ValueError(f"task_id 不存在: {task_id}")
    if task['ledger_written']:
        return None
    ledger_id = f"LED-{datetime.now(CN_TZ).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
    sel = task['selected_supplier'] or {}
    remark = ''
    if task['task_status'] == '任务已取消':
        remark = f"任务取消: {task['cancel_reason']}"
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO procurement_ledger
        (ledger_id, task_id, contract_no,
         spare_part_model, purchase_qty, selected_supplier_name, deal_unit_price,
         delivery_time, logistics_no, test_result, task_close_time, remark)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (ledger_id, task_id, task['contract_no'],
          task['spare_part_model'], task['purchase_qty'], sel.get('name', ''), task['deal_unit_price'],
          task['delivery_time'], task['logistics_no'], task['test_result'],
          _now_iso(), remark))
    c.execute("UPDATE procurement_task SET ledger_written=1, updated_at=? WHERE task_id=?",
              (_now_iso(), task_id))
    _add_op_log(c, task_id, 'system:ledger', 'write_ledger', f'台账写入 {ledger_id}')
    conn.commit()
    conn.close()
    return {'ledger_id': ledger_id, 'task_id': task_id}


def list_ledger(*, contract_no=None, limit=200):
    conn = get_db()
    c = conn.cursor()
    sql = "SELECT * FROM procurement_ledger"
    params = []
    if contract_no:
        sql += " WHERE contract_no=?"
        params.append(contract_no)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    c.execute(sql, params)
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ===================== 操作日志 =====================

def _add_op_log(c, task_id, operator, action, remark=''):
    """内部：往 op_log 写一条日志（c 是已打开的 cursor，不单独 commit）"""
    c.execute("""
        INSERT INTO procurement_op_log (task_id, operator, action, remark)
        VALUES (?, ?, ?, ?)
    """, (task_id, operator, action, remark))


def list_op_logs(task_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM procurement_op_log WHERE task_id=? ORDER BY id DESC", (task_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ===================== 行转 dict + JSON 字段反序列化 =====================

def _row_to_task(row):
    if not row:
        return None
    d = dict(row)
    # JSON 字段反序列化
    for k in ('inquiry_supplier_list', 'replied_supplier_quotes', 'no_reply_supplier', 'mail_archive_json'):
        try:
            d[k] = json.loads(d.get(k) or '[]')
        except Exception:
            d[k] = []
    try:
        d['selected_supplier'] = json.loads(d.get('selected_supplier') or '{}')
    except Exception:
        d['selected_supplier'] = {}
    d['ledger_written'] = bool(d.get('ledger_written'))
    return d


# ============================================================
# 供应商主数据 CRUD (5 个接口级函数)
# ============================================================

def list_suppliers(*, keyword=None, limit=500):
    """供应商列表：支持按 名称/邮箱/供货能力 关键词模糊搜索"""
    conn = get_db()
    c = conn.cursor()
    sql = "SELECT * FROM procurement_supplier"
    params = []
    if keyword:
        sql += " WHERE name LIKE ? OR email LIKE ? OR capability LIKE ?"
        like = f"%{keyword}%"
        params = [like, like, like]
    sql += " ORDER BY id ASC LIMIT ?"
    params.append(limit)
    c.execute(sql, params)
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_supplier(supplier_id):
    """查询单个供应商"""
    conn = get_db()
    c = conn.cursor()
    s = c.execute("SELECT * FROM procurement_supplier WHERE id=?", (supplier_id,)).fetchone()
    conn.close()
    return dict(s) if s else None


def create_supplier(*, name, email, capability=''):
    """新增供应商：email 唯一，重复抛出 ValueError"""
    if not name or not email:
        raise ValueError("供应商名称与邮箱必填")
    conn = get_db()
    c = conn.cursor()
    dup = c.execute("SELECT id FROM procurement_supplier WHERE email=?", (email,)).fetchone()
    if dup:
        conn.close()
        raise ValueError(f"邮箱已被供应商『{dup['id']}』占用，每个供应商一个邮箱")
    c.execute("""
        INSERT INTO procurement_supplier(name, email, capability) VALUES (?,?,?)
    """, (name.strip(), email.strip(), capability))
    new_id = c.lastrowid
    conn.commit()
    conn.close()
    return get_supplier(new_id)


def update_supplier(*, supplier_id, name=None, email=None, capability=None):
    """编辑供应商"""
    conn = get_db()
    c = conn.cursor()
    existing = c.execute("SELECT id FROM procurement_supplier WHERE id=?", (supplier_id,)).fetchone()
    if not existing:
        conn.close()
        return None
    sets, params = [], []
    if name is not None:
        sets.append("name=?"); params.append(name.strip())
    if email is not None:
        # 唯一性约束：不能改成别人在用的邮箱
        email = email.strip()
        dup = c.execute("SELECT id FROM procurement_supplier WHERE email=? AND id<>?",
                        (email, supplier_id)).fetchone()
        if dup:
            conn.close()
            raise ValueError(f"邮箱已被其它供应商『{dup['id']}』占用")
        sets.append("email=?"); params.append(email)
    if capability is not None:
        sets.append("capability=?"); params.append(capability)
    if not sets:
        conn.close(); return get_supplier(supplier_id)
    sets.append("updated_at=datetime('now','localtime')")
    params.append(supplier_id)
    c.execute(f"UPDATE procurement_supplier SET {', '.join(sets)} WHERE id=?", params)
    conn.commit()
    conn.close()
    return get_supplier(supplier_id)


def delete_supplier(supplier_id):
    """删除供应商；如该供应商已出现在任何采购台账/任务中，则不允许删除，抛 ValueError"""
    conn = get_db()
    c = conn.cursor()
    s = c.execute("SELECT name FROM procurement_supplier WHERE id=?", (supplier_id,)).fetchone()
    if not s:
        conn.close()
        return {'ok': True, 'deleted': 0, 'msg': '供应商不存在，跳过'}
    # 已被引用检查
    name = s['name']
    l1 = c.execute("SELECT COUNT(*) FROM procurement_ledger WHERE selected_supplier_name=?", (name,)).fetchone()[0]
    l2 = c.execute("SELECT COUNT(*) FROM procurement_task"
                   " WHERE json_extract(selected_supplier, '$.name')=?"
                   " OR EXISTS (SELECT 1 FROM json_each(inquiry_supplier_list)"
                   "              WHERE json_extract(value,'$.name')=?)",
                   (name, name)).fetchone()[0]
    if (l1 + l2) > 0:
        conn.close()
        raise ValueError(f"供应商『{name}』已出现在 {l1} 条台账 / {l2} 条任务中，为保留审计线索不允许物理删除。")
    c.execute("DELETE FROM procurement_supplier WHERE id=?", (supplier_id,))
    rows = c.rowcount
    conn.commit()
    conn.close()
    return {'ok': True, 'deleted': rows, 'name': name}


# ============================================================
# 合同主数据表 CRUD（合同名 / 编号 / 项目经理 / 项目经理邮箱）
# ============================================================

def list_contracts(*, keyword=None, limit=500):
    """合同主数据列表：支持 合同编号/合同名/项目经理名/邮箱 关键词搜索"""
    conn = get_db()
    c = conn.cursor()
    sql = "SELECT * FROM procurement_contract"
    params = []
    if keyword:
        sql += " WHERE contract_no LIKE ? OR contract_name LIKE ? OR pm_name LIKE ? OR pm_email LIKE ?"
        like = f"%{keyword}%"
        params = [like, like, like, like]
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    c.execute(sql, params)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_contract(contract_id=None, contract_no=None):
    """按 id 或 contract_no 查询单个合同"""
    if not (contract_id or contract_no):
        return None
    conn = get_db()
    c = conn.cursor()
    if contract_id is not None:
        r = c.execute("SELECT * FROM procurement_contract WHERE id=?", (contract_id,)).fetchone()
    else:
        r = c.execute("SELECT * FROM procurement_contract WHERE contract_no=?", (contract_no,)).fetchone()
    conn.close()
    return dict(r) if r else None


def create_contract(*, contract_no, contract_name='', pm_name='', pm_email='',
                    receiver_name='', receiver_phone='', receiver_address=''):
    """新增合同：contract_no 唯一，重复抛 ValueError"""
    if not contract_no:
        raise ValueError("合同编号必填")
    conn = get_db()
    c = conn.cursor()
    dup = c.execute("SELECT id FROM procurement_contract WHERE contract_no=?", (contract_no,)).fetchone()
    if dup:
        conn.close()
        raise ValueError(f"合同编号 {contract_no} 已存在，不允许重复")
    c.execute("""
        INSERT INTO procurement_contract(contract_no, contract_name, pm_name, pm_email,
                                         receiver_name, receiver_phone, receiver_address)
        VALUES (?,?,?,?,?,?,?)
    """, (contract_no.strip(), contract_name.strip(), (pm_name or '').strip(), (pm_email or '').strip(),
          (receiver_name or '').strip(), (receiver_phone or '').strip(), (receiver_address or '').strip()))
    new_id = c.lastrowid
    conn.commit()
    conn.close()
    return get_contract(contract_id=new_id)


def update_contract(*, contract_id, contract_no=None, contract_name=None,
                    pm_name=None, pm_email=None,
                    receiver_name=None, receiver_phone=None, receiver_address=None):
    """编辑合同"""
    conn = get_db()
    c = conn.cursor()
    exist = c.execute("SELECT * FROM procurement_contract WHERE id=?", (contract_id,)).fetchone()
    if not exist:
        conn.close(); return None
    sets, params = [], []
    if contract_no is not None:
        contract_no = contract_no.strip()
        dup = c.execute("SELECT id FROM procurement_contract WHERE contract_no=? AND id<>?",
                        (contract_no, contract_id)).fetchone()
        if dup:
            conn.close()
            raise ValueError(f"新合同编号 {contract_no} 已被其它合同占用")
        # 注意：改了 contract_no 之后，关联表 task/ledger 里的旧编号都要同步
        old_no = exist['contract_no']
        if old_no != contract_no:
            try:
                c.execute("UPDATE procurement_task SET contract_no=?, updated_at=datetime('now','localtime') WHERE contract_no=?",
                          (contract_no, old_no))
                c.execute("UPDATE procurement_ledger SET contract_no=? WHERE contract_no=?",
                          (contract_no, old_no))
            except Exception as e:
                conn.close()
                raise ValueError(f"合同编号改后联动失败：{e}")
        sets.append("contract_no=?"); params.append(contract_no)
    if contract_name is not None:
        sets.append("contract_name=?"); params.append(contract_name.strip())
    if pm_name is not None:
        sets.append("pm_name=?"); params.append((pm_name or '').strip())
    if pm_email is not None:
        sets.append("pm_email=?"); params.append((pm_email or '').strip())
    if receiver_name is not None:
        sets.append("receiver_name=?"); params.append((receiver_name or '').strip())
    if receiver_phone is not None:
        sets.append("receiver_phone=?"); params.append((receiver_phone or '').strip())
    if receiver_address is not None:
        sets.append("receiver_address=?"); params.append((receiver_address or '').strip())
    if not sets:
        conn.close(); return get_contract(contract_id=contract_id)
    sets.append("updated_at=datetime('now','localtime')")
    params.append(contract_id)
    c.execute(f"UPDATE procurement_contract SET {', '.join(sets)} WHERE id=?", params)
    conn.commit()
    conn.close()
    return get_contract(contract_id=contract_id)


def delete_contract(contract_id):
    """删除合同：如果合同关联了任务/台账，则不允许物理删除"""
    conn = get_db()
    c = conn.cursor()
    ex = c.execute("SELECT * FROM procurement_contract WHERE id=?", (contract_id,)).fetchone()
    if not ex:
        conn.close(); return {'ok': True, 'deleted': 0, 'msg': '合同不存在，跳过'}
    no = ex['contract_no']
    cnt1 = c.execute("SELECT COUNT(*) FROM procurement_ledger WHERE contract_no=?", (no,)).fetchone()[0]
    cnt2 = c.execute("SELECT COUNT(*) FROM procurement_task WHERE contract_no=?", (no,)).fetchone()[0]
    if (cnt1 + cnt2) > 0:
        conn.close()
        raise ValueError(f"合同『{no}』已被 {cnt1} 条台账 / {cnt2} 条任务引用，为保留审计线索不允许物理删除。")
    c.execute("DELETE FROM procurement_contract WHERE id=?", (contract_id,))
    rows = c.rowcount
    conn.commit(); conn.close()
    return {'ok': True, 'deleted': rows, 'contract_no': no}


# ============================================================
# 全局邮件抄送配置（所有供应商邮件自动 CC 这些人）
# ============================================================

def list_mail_cc(*, keyword=None, limit=500):
    """抄送列表：按名字/邮箱搜索"""
    conn = get_db()
    c = conn.cursor()
    sql = "SELECT * FROM procurement_mail_cc"
    params = []
    if keyword:
        sql += " WHERE name LIKE ? OR email LIKE ?"
        like = f"%{keyword}%"
        params = [like, like]
    sql += " ORDER BY id ASC LIMIT ?"
    params.append(limit)
    c.execute(sql, params)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def create_mail_cc(*, name, email):
    """新增一条抄送：邮箱唯一（名字重复没关系）"""
    if not name or not email:
        raise ValueError("名字和邮箱必填")
    email = email.strip()
    conn = get_db()
    c = conn.cursor()
    dup = c.execute("SELECT id FROM procurement_mail_cc WHERE email=?", (email,)).fetchone()
    if dup:
        conn.close(); raise ValueError(f"邮箱 {email} 已经加入抄送列表，不能重复添加")
    c.execute("INSERT INTO procurement_mail_cc(name, email) VALUES (?,?)", (name.strip(), email))
    new_id = c.lastrowid
    conn.commit(); conn.close()
    return list(row for row in list_mail_cc() if row['id'] == new_id)[0] if new_id else None


def delete_mail_cc(cc_id):
    """删除一条抄送"""
    conn = get_db()
    c = conn.cursor()
    r = c.execute("SELECT name, email FROM procurement_mail_cc WHERE id=?", (cc_id,)).fetchone()
    if not r:
        conn.close(); return {'ok': True, 'deleted': 0, 'msg': '记录不存在，跳过'}
    c.execute("DELETE FROM procurement_mail_cc WHERE id=?", (cc_id,))
    rows = c.rowcount
    conn.commit(); conn.close()
    return {'ok': True, 'deleted': rows, 'name': r['name'], 'email': r['email']}


def get_all_cc_emails():
    """给 neuops 邮件发送层调用：一次性返回 [(name, email)] 列表，所有发给供应商的邮件统一抄送这些人"""
    rows = list_mail_cc()
    return [(r.get('name') or '', r.get('email')) for r in rows]


# ============================================================
# 备品备件主数据 CRUD
# ============================================================

def list_spare_parts(*, keyword=None, category=None, limit=500):
    """备品备件列表：支持 编码/名称/规格/品牌 关键词搜索 + 分类过滤"""
    conn = get_db()
    c = conn.cursor()
    sql = "SELECT * FROM procurement_spare_part"
    params = []
    where = []
    if keyword:
        sql += " WHERE part_code LIKE ? OR part_name LIKE ? OR spec_model LIKE ? OR brand LIKE ?"
        like = f"%{keyword}%"
        params = [like, like, like, like]
    if category:
        if where:
            sql += " AND category LIKE ?"
        else:
            sql += " WHERE category LIKE ?"
        params.append(f"%{category}%")
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    c.execute(sql, params)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_spare_part(part_id):
    """按 ID 查单个备件"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM procurement_spare_part WHERE id=?", (part_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def create_spare_part(*, part_code, part_name, spec_model='', brand='',
                      unit='个', category='通用', condition='', remark=''):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute("""
            INSERT INTO procurement_spare_part(part_code, part_name, spec_model, brand, unit, category, condition, remark)
            VALUES (?,?,?,?,?,?,?,?)
        """, (part_code.strip(), part_name.strip(), spec_model, brand, unit, category, condition, remark))
        new_id = c.lastrowid
        conn.commit()
        return get_spare_part(new_id)
    except Exception as e:
        conn.close()
        if 'UNIQUE' in str(e):
            raise ValueError(f"备件编码 {part_code} 已存在")
        raise
    finally:
        if conn:
            conn.close()


def update_spare_part(part_id, **fields):
    """更新备件信息"""
    allowed = ('part_code', 'part_name', 'spec_model', 'brand', 'unit', 'category', 'condition', 'remark')
    sets, params = [], []
    for k in allowed:
        if k in fields and fields[k] is not None:
            sets.append(f"{k}=?")
            params.append(fields[k])
    if not sets:
        return get_spare_part(part_id)
    sets.append("updated_at=datetime('now','localtime')")
    params.append(part_id)
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute(f"UPDATE procurement_spare_part SET {','.join(sets)} WHERE id=?", params)
        conn.commit()
        return get_spare_part(part_id)
    except Exception as e:
        if 'UNIQUE' in str(e):
            raise ValueError("备件编码已被其他记录占用")
        raise
    finally:
        conn.close()


def delete_spare_part(part_id):
    """删除备件"""
    conn = get_db()
    c = conn.cursor()
    r = c.execute("SELECT part_code, part_name FROM procurement_spare_part WHERE id=?", (part_id,)).fetchone()
    if not r:
        conn.close(); return {'ok': True, 'deleted': 0, 'msg': '记录不存在'}
    c.execute("DELETE FROM procurement_spare_part WHERE id=?", (part_id,))
    rows = c.rowcount
    conn.commit(); conn.close()
    return {'ok': True, 'deleted': rows, 'part_code': r['part_code'], 'part_name': r['part_name']}


def list_spare_part_categories():
    """列出所有备件分类（下拉筛选用）"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT DISTINCT category FROM procurement_spare_part WHERE category IS NOT NULL AND category != '' ORDER BY category")
    rows = [r[0] for r in c.fetchall()]
    conn.commit()
    conn.close()


# ============================================================
# 备件邮件询价（mail_inquiry_task）——只读观察
# 数据由 neuops 引擎 upsert 写入，本模块只读查询，不做任何写操作
# ============================================================

# JSON 序列化字段（下钻时反序列化为 list）
_MAIL_TASK_JSON_COLS = ('suppliers_json', 'quotes_json', 'mail_archive_json')


def _row_to_mail_task(row):
    """mail_inquiry_task 行 → dict，JSON 字段反序列化"""
    if row is None:
        return None
    d = dict(row)
    for k in _MAIL_TASK_JSON_COLS:
        try:
            d[k] = json.loads(d.get(k) or '[]')
        except Exception:
            d[k] = []
    return d


def get_mail_inquiry_task(task_id):
    """按 task_id 查询单个备件邮件询价任务（只读）"""
    conn = get_db()
    r = conn.execute("SELECT * FROM mail_inquiry_task WHERE task_id=?", (task_id,)).fetchone()
    conn.close()
    return _row_to_mail_task(r)


def list_mail_inquiry_tasks(filter=None, page_size=200):
    """备件邮件询价任务列表（只读）。
    filter 支持 status / keyword；keyword 会对 项目名/料号/备件类型/品牌/最低报价供应商/目标供应商
    做模糊匹配。默认按更新时间倒序。
    """
    filter = filter or {}
    conn = get_db()
    c = conn.cursor()
    sql = "SELECT * FROM mail_inquiry_task WHERE 1=1"
    params = []
    st = (filter.get('status') or '').strip()
    if st:
        sql += " AND status=?"
        params.append(st)
    kw = (filter.get('keyword') or '').strip()
    if kw:
        like = f"%{kw}%"
        sql += (" AND (project_name LIKE ? OR pn LIKE ? OR part_type LIKE ? OR brand LIKE ?"
                " OR lowest_supplier LIKE ? OR target_supplier LIKE ?)")
        params.extend([like, like, like, like, like, like])
    sql += " ORDER BY updated_at DESC LIMIT ?"
    params.append(max(1, int(page_size or 200)))
    c.execute(sql, params)
    rows = c.fetchall()
    conn.close()
    return [_row_to_mail_task(r) for r in rows]


# ============================================================
# 采购台账列表（多条件过滤 + 直接返回 总价/验收时间）
# ============================================================

def list_ledger_advanced(*, contract_no=None, supplier_name=None,
                         from_date=None, to_date=None, limit=500):
    """采购台账（业务正式账，对台账页、财务结算可见）
    返回字段：ledger_id, task_id, contract_no,
              selected_supplier_name (哪个供应商),
              delivery_time (供货时间),
              spare_part_model (供了什么货),
              purchase_qty (数量),
              deal_unit_price (单价),
              total_price (总价 = 单价 * 数量),
              acceptance_time (验收时间 = task_close_time),
              logistics_no, test_result, remark, created_at
    """
    conn = get_db()
    c = conn.cursor()
    sql = """
        SELECT
          ledger_id, task_id, contract_no,
          spare_part_model, purchase_qty,
          selected_supplier_name,
          deal_unit_price,
          (CASE WHEN deal_unit_price IS NULL THEN 0 ELSE deal_unit_price END) *
          (CASE WHEN purchase_qty   IS NULL THEN 0 ELSE purchase_qty   END) AS total_price,
          delivery_time AS delivery_time,
          logistics_no,
          test_result,
          task_close_time AS acceptance_time,
          remark,
          created_at
        FROM procurement_ledger
    """
    where, params = [], []
    if contract_no:
        where.append("contract_no=?"); params.append(contract_no)
    if supplier_name:
        where.append("selected_supplier_name LIKE ?"); params.append(f"%{supplier_name}%")
    if from_date:
        where.append("date(created_at) >= date(?)"); params.append(from_date)
    if to_date:
        where.append("date(created_at) <= date(?)"); params.append(to_date)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at DESC, ledger_id DESC LIMIT ?"
    params.append(limit)
    c.execute(sql, params)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


# ============================================================
# 审批人配置（备件采购智能体 emp-009 用，页面维护）
# ============================================================

def list_approvers(*, keyword=None, only_enabled=False, limit=500):
    """审批人列表：支持按 名称/邮箱 模糊搜索"""
    conn = get_db()
    c = conn.cursor()
    sql = "SELECT * FROM procurement_approver"
    params, conds = [], []
    if keyword:
        conds.append("(name LIKE ? OR email LIKE ?)")
        like = f"%{keyword}%"
        params += [like, like]
    if only_enabled:
        conds.append("enabled=1")
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY id ASC LIMIT ?"
    params.append(limit)
    c.execute(sql, params)
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_approver(approver_id):
    conn = get_db()
    c = conn.cursor()
    r = c.execute("SELECT * FROM procurement_approver WHERE id=?", (approver_id,)).fetchone()
    conn.close()
    return dict(r) if r else None


def create_approver(*, name, email, enabled=1):
    """新增审批人：email 唯一"""
    if not name or not email:
        raise ValueError("审批人姓名与邮箱必填")
    conn = get_db()
    c = conn.cursor()
    dup = c.execute("SELECT id FROM procurement_approver WHERE email=?", (email,)).fetchone()
    if dup:
        conn.close()
        raise ValueError(f"邮箱已被审批人『{dup['id']}』占用，每个审批人一个邮箱")
    c.execute("""
        INSERT INTO procurement_approver(name, email, enabled) VALUES (?,?,?)
    """, (name.strip(), email.strip(), 1 if enabled else 0))
    new_id = c.lastrowid
    conn.commit()
    conn.close()
    return get_approver(new_id)


def update_approver(*, approver_id, name=None, email=None, enabled=None):
    conn = get_db()
    c = conn.cursor()
    existing = c.execute("SELECT id FROM procurement_approver WHERE id=?", (approver_id,)).fetchone()
    if not existing:
        conn.close()
        return None
    sets, params = [], []
    if name is not None:
        sets.append("name=?"); params.append(name.strip())
    if email is not None:
        email = email.strip()
        dup = c.execute("SELECT id FROM procurement_approver WHERE email=? AND id<>?",
                        (email, approver_id)).fetchone()
        if dup:
            conn.close()
            raise ValueError(f"邮箱已被其它审批人『{dup['id']}』占用")
        sets.append("email=?"); params.append(email)
    if enabled is not None:
        sets.append("enabled=?"); params.append(1 if enabled else 0)
    if not sets:
        conn.close(); return get_approver(approver_id)
    sets.append("updated_at=datetime('now','localtime')")
    params.append(approver_id)
    c.execute(f"UPDATE procurement_approver SET {', '.join(sets)} WHERE id=?", params)
    conn.commit()
    conn.close()
    return get_approver(approver_id)


def delete_approver(approver_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM procurement_approver WHERE id=?", (approver_id,))
    n = c.rowcount
    conn.commit()
    conn.close()
    if n == 0:
        raise ValueError("审批人不存在")
    return {"deleted": n, "id": approver_id}


def get_all_approver_emails():
    """给智能体用：返回启用中的审批人邮箱列表"""
    return [r["email"] for r in list_approvers(only_enabled=True) if r.get("email")]


# ============================================================
# 智能体邮件模板配置（A-G，页面可改措辞）
# ============================================================

def list_mail_templates():
    """返回**当前生效**的 A–G 模板（页面自定义 ∪ 系统默认）。

    页面自定义库只保存被改过的字段（留空表示沿用默认），直接读表会看到
    "空白"，用户无从判断实际会发出什么。这里以系统默认内容为基线，
    用自定义的非空字段覆盖，再标注 is_custom 供页面提示。
    """
    try:
        from mail_tpl_default import DEFAULT_MAIL_TEMPLATES
    except Exception:
        try:
            from .mail_tpl_default import DEFAULT_MAIL_TEMPLATES
        except Exception:
            DEFAULT_MAIL_TEMPLATES = {}

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM procurement_mail_template")
    custom = {r["tpl_key"]: dict(r) for r in c.fetchall()}
    conn.close()

    out = []
    for key in (sorted(DEFAULT_MAIL_TEMPLATES.keys()) or sorted(custom.keys())):
        base = dict(DEFAULT_MAIL_TEMPLATES.get(key) or {"name": "", "subject": "", "body": ""})
        row = custom.get(key) or {}
        eff = {
            "tpl_key": key,
            "name": row.get("name") or base.get("name") or key,
            "subject": row.get("subject") or base.get("subject") or "",
            "body": row.get("body") or base.get("body") or "",
            "enabled": row.get("enabled", 1),
        }
        eff["default_subject"] = base.get("subject") or ""
        eff["default_body"] = base.get("body") or ""
        eff["is_custom"] = bool(
            (row.get("subject") and row.get("subject") != base.get("subject"))
            or (row.get("body") and row.get("body") != base.get("body"))
        )
        eff["updated_at"] = row.get("updated_at") or ""
        out.append(eff)
    return out


def get_mail_template(tpl_key):
    conn = get_db()
    c = conn.cursor()
    r = c.execute("SELECT * FROM procurement_mail_template WHERE tpl_key=?", (tpl_key,)).fetchone()
    conn.close()
    return dict(r) if r else None


def update_mail_template(*, tpl_key, name=None, subject=None, body=None, enabled=None):
    conn = get_db()
    c = conn.cursor()
    existing = get_mail_template(tpl_key)
    if not existing:
        conn.close()
        return None
    sets, params = [], []
    if name is not None:
        sets.append("name=?"); params.append(name)
    if subject is not None:
        sets.append("subject=?"); params.append(subject)
    if body is not None:
        sets.append("body=?"); params.append(body)
    if enabled is not None:
        sets.append("enabled=?"); params.append(1 if enabled else 0)
    if not sets:
        conn.close(); return existing
    sets.append("updated_at=datetime('now','localtime')")
    params.append(tpl_key)
    c.execute(f"UPDATE procurement_mail_template SET {', '.join(sets)} WHERE tpl_key=?", params)
    conn.commit()
    conn.close()
    return get_mail_template(tpl_key)


def reset_mail_template(tpl_key):
    """清空自定义内容，回退到 skill 默认模板"""
    return update_mail_template(tpl_key=tpl_key, subject="", body="")


def get_mail_templates_map():
    """给智能体用：{模板键: {subject, body}}，仅含启用且内容非空者（空则回退默认模板）"""
    out = {}
    for r in list_mail_templates():
        if not r.get("enabled"):
            continue
        subj = (r.get("subject") or "").strip()
        body = (r.get("body") or "").strip()
        if not subj and not body:
            continue
        out[r["tpl_key"]] = {"subject": subj, "body": body}
    return out


# ============================================================
# 主数据种子（仅当各主数据表为空时插入 1-2 条示例，便于首次启动演示）
# 遵循约束：主数据由页面输入，数据库中仅保留 1-2 条测试数据
# ============================================================

def seed_procurement_master():
    """首次启动时为各主数据表注入极少量示例数据（幂等：表非空则跳过）"""
    conn = get_db()
    c = conn.cursor()

    # 供应商资源池（1 条示例）
    if c.execute("SELECT COUNT(*) AS n FROM procurement_supplier").fetchone()['n'] == 0:
        c.execute(
            "INSERT INTO procurement_supplier(name,email,capability) VALUES(?,?,?)",
            ('示例供应商-A', 'supplier-a@example.com', '通用备件/紧急供货')
        )

    # 合同主数据（1 条示例）
    if c.execute("SELECT COUNT(*) AS n FROM procurement_contract").fetchone()['n'] == 0:
        c.execute(
            "INSERT INTO procurement_contract(contract_no,contract_name,pm_name,pm_email) VALUES(?,?,?,?)",
            ('HT-2026-0001', '示例合同-备件框架采购', '张三', 'pm-zhangsan@example.com')
        )

    # 备品备件主数据（1 条示例）
    if c.execute("SELECT COUNT(*) AS n FROM procurement_spare_part").fetchone()['n'] == 0:
        c.execute(
            "INSERT INTO procurement_spare_part(part_code,part_name,spec_model,brand,unit,category) VALUES(?,?,?,?,?,?)",
            ('SP-0001', '示例备件-继电器', 'JL-12-AC220V', 'XX品牌', '个', '电气类')
        )

    # 全局邮件抄送（1 条示例）
    if c.execute("SELECT COUNT(*) AS n FROM procurement_mail_cc").fetchone()['n'] == 0:
        c.execute(
            "INSERT INTO procurement_mail_cc(name,email) VALUES(?,?)",
            ('采购监督', 'audit@example.com')
        )

    conn.commit()
    conn.close()


# ============================================================
# 发起人白名单（procurement_requester）
#   智能体只处理白名单内发件人的询价邮件，避免广告/垃圾邮件被误认领。
#   支持整邮箱（a@b.com）与域名（@b.com）两种写法。
#   **列表为空 = 不限制**（与 9007 _requester_allowed 的行为保持一致）。
# ============================================================

def list_requesters(*, keyword=None, only_enabled=False, limit=500):
    conn = get_db()
    c = conn.cursor()
    sql = "SELECT * FROM procurement_requester"
    params, conds = [], []
    if keyword:
        conds.append("(name LIKE ? OR email LIKE ?)")
        like = f"%{keyword}%"
        params += [like, like]
    if only_enabled:
        conds.append("enabled=1")
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY id ASC LIMIT ?"
    params.append(limit)
    rows = c.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_requester(requester_id):
    conn = get_db()
    c = conn.cursor()
    r = c.execute("SELECT * FROM procurement_requester WHERE id=?", (requester_id,)).fetchone()
    conn.close()
    return dict(r) if r else None


def create_requester(*, name="", email="", enabled=1):
    if not (email or "").strip():
        raise ValueError("邮箱不能为空")
    email = email.strip()
    if "@" not in email:
        raise ValueError("请填写完整邮箱（a@b.com）或域名（@b.com）")
    conn = get_db()
    c = conn.cursor()
    dup = c.execute("SELECT id FROM procurement_requester WHERE lower(email)=lower(?)",
                    (email,)).fetchone()
    if dup:
        conn.close()
        raise ValueError(f"白名单中已存在：{email}")
    cur = c.execute(
        "INSERT INTO procurement_requester(name, email, enabled) VALUES (?,?,?)",
        (name.strip(), email, 1 if enabled else 0))
    rid = cur.lastrowid
    conn.commit()
    conn.close()
    return {"id": rid, "name": name.strip(), "email": email, "enabled": 1 if enabled else 0}


def update_requester(requester_id, **fields):
    allowed = ("name", "email", "enabled")
    sets, params = [], []
    for k, v in fields.items():
        if k in allowed and v is not None:
            if k == "email":
                v = (v or "").strip()
                if not v:
                    raise ValueError("邮箱不能为空")
            sets.append(f"{k}=?")
            params.append(v)
    if not sets:
        return get_requester(requester_id)
    params.append(requester_id)
    conn = get_db()
    c = conn.cursor()
    c.execute(f"UPDATE procurement_requester SET {', '.join(sets)},"
              f" updated_at=datetime('now','localtime') WHERE id=?", params)
    conn.commit()
    conn.close()
    return get_requester(requester_id)


def delete_requester(requester_id):
    conn = get_db()
    c = conn.cursor()
    cur = c.execute("DELETE FROM procurement_requester WHERE id=?", (requester_id,))
    n = cur.rowcount
    conn.commit()
    conn.close()
    return {"deleted": n}


def get_all_requester_emails(*, only_enabled=True):
    """给智能体用：返回启用中的白名单条目（邮箱或域名）。"""
    conn = get_db()
    c = conn.cursor()
    sql = "SELECT email FROM procurement_requester"
    if only_enabled:
        sql += " WHERE enabled=1"
    sql += " ORDER BY id ASC"
    rows = [r["email"] for r in c.execute(sql).fetchall() if (r["email"] or "").strip()]
    conn.close()
    return rows
