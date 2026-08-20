import json
import os
import sys
import sqlite3
import pytest
from datetime import datetime

# 把 backend 加入路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import main as app_main

TEST_DB = os.path.join(os.path.dirname(__file__), '..', 'contract_compare.db')


@pytest.fixture
def db_conn():
    """提供一个指向本地测试数据库的连接。"""
    app_main.DB_PATH = TEST_DB
    app_main.init_db()
    conn = sqlite3.connect(TEST_DB)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


def test_api_gross_metrics_includes_dept_region_rows(db_conn):
    """CC-008: /api/gross/metrics 应返回 dept_region_rows 字段。"""
    app_main.DB_PATH = TEST_DB
    app_main.init_db()

    # 直接插入测试数据，模拟 ETL 已写入 dept_region 记录
    c = db_conn.cursor()
    c.execute("DELETE FROM indicator_metrics WHERE job_key='gross-margin'")
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    records = [
        ('year', '2026', '2026', 1000000.0, 200000.0, 0.20),
        ('year', '2025', '2025', 800000.0, 160000.0, 0.20),
        ('dept_region', 'A部门|华北', '2026', 400000.0, 80000.0, 0.20),
        ('dept_region', 'A部门|华北', '2025', 300000.0, 51000.0, 0.17),
        ('dept_region', 'A部门|华东', '2026', 200000.0, 30000.0, 0.15),
        ('dept_region', 'B部门|华北', '2026', 150000.0, 18000.0, 0.12),
    ]
    for dim_type, dim_value, year, amt, gross, rate in records:
        extra = json.dumps({'dept': dim_value.split('|')[0], 'region': dim_value.split('|')[1]}) if dim_type == 'dept_region' else None
        c.execute(
            "INSERT INTO indicator_metrics (job_key, metric_name, dim_type, dim_value, year, contract_amt, gross_profit, gross_rate, extra_json, calc_time) VALUES (?,?,?,?,?,?,?,?,?,?)",
            ('gross-margin', '签单毛利率', dim_type, dim_value, year, amt, gross, rate, extra, now)
        )
    db_conn.commit()
    db_conn.close()

    from fastapi.testclient import TestClient
    client = TestClient(app_main.app)
    r = client.get('/api/gross/metrics')
    assert r.status_code == 200
    data = r.json()
    assert data['success'] is True
    assert 'dept_region_rows' in data
    dr = data['dept_region_rows']
    assert set(dr['depts']) == {'A部门', 'B部门'}
    assert set(dr['regions']) == {'华北', '华东'}

    a_huabei = dr['cells']['A部门']['华北']
    assert a_huabei['hasData'] is True
    # rate 保留多位小数
    assert round(a_huabei['rate'], 2) == 0.20
    # diff: 2026 20% - 2025 17% = 3.0 pct
    assert a_huabei['diff'] == 3.0

    a_huadong = dr['cells']['A部门']['华东']
    assert a_huadong['hasData'] is True
    # 缺少 2025 数据，diff 应为 None
    assert a_huadong['diff'] is None

    b_huabei = dr['cells']['B部门']['华北']
    assert b_huabei['hasData'] is True

    # B部门 × 华东 无数据 => 空白格
    assert dr['cells']['B部门']['华东']['hasData'] is False

    # 小计存在
    assert 'byDept' in dr['totals']
    assert 'byRegion' in dr['totals']


def test_gross_metrics_handles_empty_dept_region(db_conn):
    """CC-008: 当无 dept_region 数据时，API 仍返回正常结构。"""
    from fastapi.testclient import TestClient
    app_main.DB_PATH = TEST_DB
    app_main.init_db()

    c = db_conn.cursor()
    c.execute("DELETE FROM indicator_metrics WHERE job_key='gross-margin'")
    db_conn.commit()
    db_conn.close()

    # 仅写入非 dept_region 记录
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    c2 = sqlite3.connect(TEST_DB)
    c2.row_factory = sqlite3.Row
    cu = c2.cursor()
    cu.execute("INSERT INTO indicator_metrics (job_key, metric_name, dim_type, dim_value, year, contract_amt, gross_profit, gross_rate, calc_time) VALUES (?,?,?,?,?,?,?,?,?)",
               ('gross-margin', '签单毛利率', 'year', '2026', '2026', 1000000.0, 200000.0, 0.20, now))
    c2.commit()
    c2.close()

    client = TestClient(app_main.app)
    r = client.get('/api/gross/metrics')
    assert r.status_code == 200
    data = r.json()
    assert data['success'] is True
    assert 'dept_region_rows' in data
    assert data['dept_region_rows']['depts'] == []
    assert data['dept_region_rows']['regions'] == []
