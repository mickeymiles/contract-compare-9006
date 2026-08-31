"""
备件采购域 schema 守卫测试。

背景：备件采购流程强依赖 `procurement_task` 的双流列（internal_status / external_status）
与三入口列（source），以及 `mail_inquiry_task` 表。这些由 `init_procurement_db()` 幂等补建，
而 `models.init_db()` **不负责**采购域，bootstrap.sh 也曾长期漏调该函数。

曾出现过的故障形态：148 个测试全绿，但主流程因 procurement_task 缺列而不可用
——测试覆盖的恰好不是会出问题的那部分。本文件把「结构性缺列」变成一次红灯，
避免同类问题再次静默发生。

用例使用独立临时库，不触碰开发库。
"""

import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import procurement_models as pm  # noqa: E402


REQUIRED_TABLES = (
    'procurement_task',
    'mail_inquiry_task',
    'procurement_supplier',
    'procurement_spare_part',
    'procurement_ledger',
)

# 双流 / 三入口 / 审批字段：
#   - 前端 9 节点统一流程按 internal_status + external_status 推导节点状态
#   - 9007 侧 _derive_task_status 同样依赖双流列回写 task_status
#   - source 区分「页面 / Agent对话 / 邮件」三个入口
REQUIRED_TASK_COLUMNS = (
    'source',
    'internal_status',
    'external_status',
    'approval_state',
    'target_supplier',
)


@pytest.fixture()
def proc_db(tmp_path, monkeypatch):
    """把采购域指向独立临时库并初始化，用完即弃。"""
    db_file = tmp_path / 'proc_schema.db'
    monkeypatch.setattr(pm, 'DB_PATH', str(db_file))
    pm.init_procurement_db()
    conn = sqlite3.connect(str(db_file))
    try:
        yield conn
    finally:
        conn.close()


def _tables(conn):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _columns(conn, table):
    return [r[1] for r in conn.execute(f'PRAGMA table_info({table})')]


def test_required_tables_created(proc_db):
    """采购域核心表必须存在，缺一张主流程就跑不起来"""
    missing = [t for t in REQUIRED_TABLES if t not in _tables(proc_db)]
    assert not missing, f'采购域缺少表: {missing}'


def test_task_dual_flow_columns_exist(proc_db):
    """双流与三入口列必须存在，缺列会导致 9 节点流程渲染异常"""
    cols = _columns(proc_db, 'procurement_task')
    missing = [c for c in REQUIRED_TASK_COLUMNS if c not in cols]
    assert not missing, f'procurement_task 缺少关键列: {missing}'


def test_init_is_idempotent(proc_db):
    """重复初始化不得报错，也不得丢列（换机器重装时会被多次调用）"""
    pm.init_procurement_db()
    pm.init_procurement_db()
    cols = _columns(proc_db, 'procurement_task')
    for c in REQUIRED_TASK_COLUMNS:
        assert c in cols, f'重复初始化后丢失列: {c}'
