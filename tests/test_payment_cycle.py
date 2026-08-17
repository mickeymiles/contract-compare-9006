# -*- coding: utf-8 -*-
"""回款周期分析单元测试（断言基于当前真实行为）
# 规格编号: CC-005 回款周期分析（双口径/按月累计/周期区间划分/年份过滤/数据源缺失降级）
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend'))

import openpyxl  # noqa: E402
import pytest  # noqa: E402

import main  # noqa: E402


# ==================== 测试数据构造 ====================

def _make_h_xlsx(path, extra_rows=None):
    """总合同表（H 表）：列名必须命中 find_col 匹配规则"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(['合同编号', '统计日期', '部门', '合同金额', '区域', '省'])
    rows = [
        ('C1', '2026-01-10', '系统集成业务', 1000000, '西部', '陕西'),
        ('C2', '2026-02-01', '软件研发', 2000000, '西部', '甘肃'),
        ('C3', '2026-03-01', '系统集成业务', 3000000, '东部', '江苏'),
        ('C4', '2025-05-01', '系统集成业务', 500000, '东部', '浙江'),
        ('C5', '2024-05-01', '系统集成业务', 800000, '东部', '浙江'),
    ]
    if extra_rows:
        rows.extend(extra_rows)
    for r in rows:
        ws.append(r)
    wb.save(path)
    wb.close()


def _make_r_xlsx(path, extra_rows=None):
    """项目里程碑表（R 表）：计划回款时间 / 计划产值(元) 为代码硬编码列名"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(['合同编号', '计划回款时间', '计划产值(元)'])
    rows = [
        ('C1', '2026-03-01', 200000),   # 较早一笔：验证取最晚回款
        ('C1', '2026-07-01', 500000),
        ('C2', '2027-02-01', 1000000),
        ('C3', '2026-12-01', 1500000),
        ('C4', '2026-05-01', 300000),
        ('C5', '2025-05-01', 400000),
    ]
    if extra_rows:
        rows.extend(extra_rows)
    for r in rows:
        ws.append(r)
    wb.save(path)
    wb.close()


def _write_datasource(tmp_path, with_h=True, with_r=True, extra_h=None, extra_r=None):
    """构造临时 datasource 目录并返回其路径（versions.json + H/R 表）"""
    ds = tmp_path / 'datasource'
    ds.mkdir(exist_ok=True)
    meta = {}
    if with_h:
        _make_h_xlsx(str(ds / 'H_v2.xlsx'), extra_h)
        meta['总合同表'] = {'versions': [{'id': 2, 'file': 'H_v2.xlsx'}], 'next_id': 3}
    if with_r:
        _make_r_xlsx(str(ds / 'R_v2.xlsx'), extra_r)
        meta['项目里程碑表'] = {'versions': [{'id': 2, 'file': 'R_v2.xlsx'}], 'next_id': 3}
    (ds / 'versions.json').write_text(json.dumps(meta, ensure_ascii=False), encoding='utf-8')
    return str(ds)


def _patch_ds(monkeypatch, d):
    """DATASOURCE_DIR 与 DS_META_FILE（导入期固化）需同时替换"""
    monkeypatch.setattr(main, 'DATASOURCE_DIR', d)
    monkeypatch.setattr(main, 'DS_META_FILE', os.path.join(d, 'versions.json'))


@pytest.fixture
def ds_dir(tmp_path, monkeypatch):
    d = _write_datasource(tmp_path)
    _patch_ds(monkeypatch, d)
    return d


# ==================== 用例 ====================

def test_payment_cycle_basic_structure(ds_dir):
    """基础结构：source_version / 三个月份桶 / 区域与省份聚合"""
    res = main.analysis_payment_cycle()
    assert res['success'] is True
    data = res['data']

    assert data['source_version'] == 2
    # 月份桶固定 2026-06/07/08
    assert [m['key'] for m in data['months']] == ['2026-06', '2026-07', '2026-08']

    # 累计口径：2026-06 桶含全部 3 个 2026 年合同（签约月份 ≤ 6），previous 为 2025 年 1 个
    assert data['icid']['project_count']['2026-06']['current'] == 3
    assert data['icid']['project_count']['2026-06']['previous'] == 1
    assert data['icid']['project_count']['2026-07']['current'] == 3
    assert data['icid']['project_count']['2026-08']['current'] == 3

    # 区域聚合（按 count 降序）
    regions = {r['region']: r for r in data['regions']}
    assert set(regions) == {'西部', '东部'}
    assert regions['西部']['count'] == 2
    assert regions['西部']['with_payment'] == 2
    assert regions['东部']['count'] == 1

    # 省份聚合
    prov = {p['province']: p for p in data['province_stats']}
    assert prov['陕西']['count'] == 1
    assert prov['甘肃']['count'] == 1
    assert prov['江苏']['count'] == 1

    # 2026 年合同全部进入 enriched_rows
    assert data['enriched_total'] == 3


def test_payment_cycle_enriched_rows(ds_dir):
    """enriched_rows 字段计算：cycle_days（取最晚里程碑）、zone、年份过滤"""
    data = main.analysis_payment_cycle()['data']
    by_no = {r['contract_no']: r for r in data['enriched_rows']}

    # C1 两条里程碑，取最晚 2026-07-01 → 172 天
    c1 = by_no['C1']
    assert c1['last_payback_date'] == '2026-07-01'
    assert c1['cycle_days'] == 172
    assert c1['zone'] == '0.5以内'
    assert c1['dept'] == '系统集成业务'
    assert c1['region'] == '西部'
    assert c1['province'] == '陕西'

    # C2：365 天 → 1年以上；C3：275 天 → 0.5-1年
    assert by_no['C2']['cycle_days'] == 365
    assert by_no['C2']['zone'] == '1年以上'
    assert by_no['C3']['cycle_days'] == 275
    assert by_no['C3']['zone'] == '0.5-1年'

    # 年份过滤：2024（C5）完全排除，2025（C4）不进入 2026 enriched
    assert 'C5' not in by_no
    assert 'C4' not in by_no


def test_payment_cycle_zone_edges(tmp_path, monkeypatch):
    """zone 五档边界：182/183/365/730/1095 天对应 0.5以内/0.5-1年/1年以上/2年以上/3年以上"""
    d = _write_datasource(
        tmp_path,
        extra_h=[
            ('D1', '2026-01-01', '系统集成业务', 100000, '中部', '河南'),
            ('D2', '2026-01-01', '系统集成业务', 100000, '中部', '河南'),
            ('D3', '2026-01-01', '系统集成业务', 100000, '中部', '河南'),
            ('D4', '2026-01-01', '系统集成业务', 100000, '中部', '河南'),
            ('D5', '2026-01-01', '系统集成业务', 100000, '中部', '河南'),
        ],
        extra_r=[
            ('D1', '2026-07-02', 100000),   # 182 天 → 0.5以内
            ('D2', '2026-07-03', 100000),   # 183 天 → 0.5-1年
            ('D3', '2027-01-01', 100000),   # 365 天 → 1年以上
            ('D4', '2028-01-01', 100000),   # 730 天 → 2年以上
            ('D5', '2028-12-31', 100000),   # 1095 天 → 3年以上
        ],
    )
    _patch_ds(monkeypatch, d)

    data = main.analysis_payment_cycle()['data']
    by_no = {r['contract_no']: r for r in data['enriched_rows']}
    assert by_no['D1']['zone'] == '0.5以内'
    assert by_no['D2']['zone'] == '0.5-1年'
    assert by_no['D3']['zone'] == '1年以上'
    assert by_no['D4']['zone'] == '2年以上'
    assert by_no['D5']['zone'] == '3年以上'
    # 182 天 < 365/2，183 天 > 182.5
    assert by_no['D1']['cycle_days'] == 182
    assert by_no['D2']['cycle_days'] == 183
    assert by_no['D3']['cycle_days'] == 365
    assert by_no['D4']['cycle_days'] == 730
    assert by_no['D5']['cycle_days'] == 1095


def test_payment_cycle_missing_h_table(tmp_path, monkeypatch):
    """无总合同表：降级返回空结构"""
    d = _write_datasource(tmp_path, with_h=False)
    _patch_ds(monkeypatch, d)
    res = main.analysis_payment_cycle()
    assert res['success'] is True
    assert res['data']['source_version'] == 0
    assert res['data']['months'] == []
    assert res['data']['enriched_rows'] == []


def test_payment_cycle_missing_r_table(tmp_path, monkeypatch):
    """无里程碑表：cycle_days=0、zone='0.5以内'、无回款标记"""
    d = _write_datasource(tmp_path, with_r=False)
    _patch_ds(monkeypatch, d)
    res = main.analysis_payment_cycle()
    assert res['success'] is True
    data = res['data']
    assert data['enriched_total'] == 3
    for r in data['enriched_rows']:
        assert r['cycle_days'] == 0
        assert r['zone'] == '0.5以内'
        assert r['last_payback_date'] == ''
    for reg in data['regions']:
        assert reg['with_payment'] == 0
        assert reg['no_payment'] == reg['count']
