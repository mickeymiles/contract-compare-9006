"""
合同比对系统 — 数据模型与数据库初始化
SQLite, 5张表: contracts, contract_items, supplier_items, comparison_results, versions
支持多合同隔离 (contract_id)
"""

import sqlite3
import os

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
DB_PATH = os.path.join(DB_DIR, 'contract_compare.db')


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()

    # 0. 合同主表
    c.execute("""
        CREATE TABLE IF NOT EXISTS contracts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contract_name TEXT NOT NULL,
            contract_no TEXT DEFAULT '',
            sign_date TEXT DEFAULT '',
            total_amount REAL DEFAULT 0,
            status TEXT DEFAULT '未上传基准',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    # 1. 合同基准清单表
    c.execute("""
        CREATE TABLE IF NOT EXISTS contract_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contract_id INTEGER NOT NULL,
            device_name TEXT DEFAULT '',
            device_model TEXT DEFAULT '',
            specs_full TEXT DEFAULT '',
            specs_cpu TEXT DEFAULT '',
            specs_memory TEXT DEFAULT '',
            specs_disk TEXT DEFAULT '',
            specs_other TEXT DEFAULT '',
            contract_qty REAL DEFAULT 0,
            contract_unit TEXT DEFAULT '',
            contract_unit_price REAL DEFAULT 0,
            contract_amount REAL DEFAULT 0,
            remark TEXT DEFAULT '',
            raw_columns TEXT DEFAULT '{}',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (contract_id) REFERENCES contracts(id) ON DELETE CASCADE
        )
    """)

    # 2. 供应商报价清单表
    c.execute("""
        CREATE TABLE IF NOT EXISTS supplier_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contract_id INTEGER NOT NULL,
            version_id INTEGER NOT NULL,
            device_name TEXT NOT NULL,
            device_model TEXT NOT NULL,
            specs_full TEXT DEFAULT '',
            specs_cpu TEXT DEFAULT '',
            specs_memory TEXT DEFAULT '',
            specs_disk TEXT DEFAULT '',
            specs_other TEXT DEFAULT '',
            quote_qty REAL DEFAULT 0,
            quote_unit TEXT DEFAULT '',
            quote_unit_price REAL DEFAULT 0,
            quote_amount REAL DEFAULT 0,
            remark TEXT DEFAULT '',
            raw_columns TEXT DEFAULT '{}',
            FOREIGN KEY (contract_id) REFERENCES contracts(id) ON DELETE CASCADE,
            FOREIGN KEY (version_id) REFERENCES versions(id)
        )
    """)

    # 3. 比对结果表
    c.execute("""
        CREATE TABLE IF NOT EXISTS comparison_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contract_id INTEGER NOT NULL,
            contract_item_id INTEGER,
            supplier_item_id INTEGER,
            match_status TEXT NOT NULL,
            anomaly_types TEXT DEFAULT '[]',
            anomaly_detail TEXT DEFAULT '',
            qty_diff TEXT DEFAULT '',
            param_diff TEXT DEFAULT '',
            version_id INTEGER NOT NULL,
            confirmed INTEGER DEFAULT 0,
            match_note TEXT DEFAULT '',
            compared_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (contract_id) REFERENCES contracts(id) ON DELETE CASCADE,
            FOREIGN KEY (contract_item_id) REFERENCES contract_items(id),
            FOREIGN KEY (supplier_item_id) REFERENCES supplier_items(id),
            FOREIGN KEY (version_id) REFERENCES versions(id)
        )
    """)

    # 兼容旧数据库：添加 match_note 字段
    try:
        c.execute("ALTER TABLE comparison_results ADD COLUMN match_note TEXT DEFAULT ''")
    except:
        pass

    # 4. 版本管理表（每个版本属于一个供应商）
    c.execute("""
        CREATE TABLE IF NOT EXISTS versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contract_id INTEGER NOT NULL,
            supplier_name TEXT DEFAULT '',
            upload_time TEXT DEFAULT (datetime('now','localtime')),
            uploader TEXT DEFAULT '管理员',
            total_items INTEGER DEFAULT 0,
            matched_count INTEGER DEFAULT 0,
            anomaly_count INTEGER DEFAULT 0,
            pending_count INTEGER DEFAULT 0,
            extra_count INTEGER DEFAULT 0,
            progress REAL DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            FOREIGN KEY (contract_id) REFERENCES contracts(id) ON DELETE CASCADE
        )
    """)

    # 兼容旧表：尝试添加 contract_id 列（如果表已存在但缺列）
    for table in ['contract_items', 'supplier_items', 'comparison_results', 'versions']:
        try:
            c.execute(f"ALTER TABLE {table} ADD COLUMN contract_id INTEGER DEFAULT 1")
        except:
            pass  # 列已存在

    # 兼容旧表：尝试添加 supplier_name 列
    try:
        c.execute("ALTER TABLE versions ADD COLUMN supplier_name TEXT DEFAULT ''")
    except:
        pass  # 列已存在

    # 兼容旧表：尝试添加 is_active 列
    try:
        c.execute("ALTER TABLE versions ADD COLUMN is_active INTEGER DEFAULT 1")
    except:
        pass  # 列已存在

    # 兼容旧表：添加 column_mapping 列（主合同列 ↔ 供应商列 对齐关系）
    try:
        c.execute("ALTER TABLE versions ADD COLUMN column_mapping TEXT DEFAULT '{}'")
    except:
        pass  # 列已存在

    # 5. 定时 ETL 任务表（轨道A：固定指标计算链路）
    c.execute("""
        CREATE TABLE IF NOT EXISTS etl_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_key TEXT UNIQUE NOT NULL,
            job_name TEXT NOT NULL,
            description TEXT DEFAULT '',
            calculation_logic TEXT DEFAULT '',
            schedule TEXT DEFAULT '',
            status TEXT DEFAULT 'stopped',
            last_run TEXT DEFAULT '',
            last_result TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    # 兼容旧表：添加 calculation_logic 列
    try:
        c.execute("ALTER TABLE etl_jobs ADD COLUMN calculation_logic TEXT DEFAULT ''")
    except:
        pass

    # 7. 指标汇总宽表（ETL 预计算结果）
    c.execute("""
        CREATE TABLE IF NOT EXISTS indicator_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_key TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            dim_type TEXT DEFAULT 'year',
            dim_value TEXT DEFAULT '',
            year TEXT DEFAULT '',
            contract_amt REAL DEFAULT 0,
            gross_profit REAL DEFAULT 0,
            gross_rate REAL DEFAULT 0,
            extra_json TEXT DEFAULT '{}',
            calc_time TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    # 8. ETL 执行记录表
    c.execute("""
        CREATE TABLE IF NOT EXISTS etl_executions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_key TEXT NOT NULL,
            run_time TEXT DEFAULT (datetime('now','localtime')),
            status TEXT DEFAULT 'success',
            detail TEXT DEFAULT '',
            rows_written INTEGER DEFAULT 0
        )
    """)

    # 9. 分析结果快照表（持久化分析结果，页面直接读，替代内存缓存）
    c.execute("""
        CREATE TABLE IF NOT EXISTS analysis_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_key TEXT UNIQUE NOT NULL,
            result_json TEXT NOT NULL,
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    # 10. 资金占用宽表（每合同一行，FIFO 冲抵结果）
    c.execute("""
        CREATE TABLE IF NOT EXISTS fund_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contract_no TEXT,
            customer_name TEXT DEFAULT '',
            project_name TEXT DEFAULT '',
            contract_amount REAL DEFAULT 0,
            total_pay REAL DEFAULT 0,
            total_recv REAL DEFAULT 0,
            current_occupy REAL DEFAULT 0,
            amount_day REAL DEFAULT 0,
            cycle_start TEXT DEFAULT '',
            cycle_days INTEGER DEFAULT 0,
            avg_occupy REAL DEFAULT 0,
            est_cost REAL DEFAULT 0,
            annual_rate TEXT DEFAULT '',
            segment_count INTEGER DEFAULT 0,
            settled_segments INTEGER DEFAULT 0,
            occupying_segments INTEGER DEFAULT 0,
            calc_time TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    # 11. 回款周期宽表（每合同一行）
    c.execute("""
        CREATE TABLE IF NOT EXISTS payment_cycle_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contract_no TEXT,
            contract_date TEXT DEFAULT '',
            last_payment_date TEXT DEFAULT '',
            cycle_days INTEGER DEFAULT 0,
            amount REAL DEFAULT 0,
            calc_time TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    # 12. 资金多维度分析：fund_metrics 增量加维度列+新指标列（兼容旧库）
    dim_cols = [
        "region TEXT DEFAULT ''",        # 区域
        "province TEXT DEFAULT ''",      # 省
        "dept TEXT DEFAULT ''",          # 部门
        "biz_line TEXT DEFAULT ''",      # 业务线
        "industry TEXT DEFAULT ''",      # 行业
        "customer_key TEXT DEFAULT ''",  # 脱敏客户键
        "project_status TEXT DEFAULT ''",# 项目状态
        "contract_status TEXT DEFAULT ''",# 合同状态
        "sign_year TEXT DEFAULT ''",     # 签约年度
        "recv_rate REAL DEFAULT 0",      # 回款率
        "occupy_intensity REAL DEFAULT 0",# 占用强度
        "risk_level TEXT DEFAULT 'healthy'", # 风险等级
        "prev_occupy REAL DEFAULT 0",    # 上年同期占用（CC-006 FR-13 表格同比）
    ]
    for col_def in dim_cols:
        try:
            c.execute(f"ALTER TABLE fund_metrics ADD COLUMN {col_def}")
        except Exception:
            pass  # 列已存在

    # 13. 风险预警配置表（阈值可配置，默认值由 main.py seed）
    c.execute("""
        CREATE TABLE IF NOT EXISTS risk_config (
            key TEXT PRIMARY KEY,
            value REAL NOT NULL,
            description TEXT DEFAULT '',
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    conn.commit()
    conn.close()


def clear_contract(contract_id: int):
    """清空某合同的基准清单"""
    conn = get_db()
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute("DELETE FROM contract_items WHERE contract_id = ?", (contract_id,))
    conn.execute("PRAGMA foreign_keys=ON")
    conn.commit()
    conn.close()


def create_contract(name: str, no: str = '', sign_date: str = '') -> int:
    """创建新合同，返回ID"""
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO contracts (contract_name, contract_no, sign_date) VALUES (?,?,?)",
              (name, no, sign_date))
    cid = c.lastrowid
    conn.commit()
    conn.close()
    return cid


def delete_contract(contract_id: int):
    """级联删除合同及所有关联数据"""
    conn = get_db()
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("DELETE FROM contracts WHERE id = ?", (contract_id,))
    conn.commit()
    conn.close()


def update_contract_status(contract_id: int):
    """根据比对结果更新合同状态"""
    conn = get_db()
    c = conn.cursor()
    v = c.execute(
        "SELECT progress, anomaly_count, pending_count, extra_count "
        "FROM versions WHERE contract_id = ? ORDER BY id DESC LIMIT 1",
        (contract_id,)
    ).fetchone()

    if not v:
        c.execute("UPDATE contracts SET status = '未上传基准', updated_at = datetime('now','localtime') WHERE id = ?", (contract_id,))
    elif v['progress'] >= 100:
        c.execute("UPDATE contracts SET status = '已闭环(100%)', updated_at = datetime('now','localtime') WHERE id = ?", (contract_id,))
    elif v['anomaly_count'] > 0 or v['pending_count'] > 0 or v['extra_count'] > 0:
        c.execute("UPDATE contracts SET status = '待供应商整改', updated_at = datetime('now','localtime') WHERE id = ?", (contract_id,))
    else:
        c.execute("UPDATE contracts SET status = '比对进行中', updated_at = datetime('now','localtime') WHERE id = ?", (contract_id,))

    conn.commit()
    conn.close()
