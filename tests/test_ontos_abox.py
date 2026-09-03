# -*- coding: utf-8 -*-
"""本体 ABox 适配层测试（9006）。

═══ 分层背景 ═══
- ``ontos/``       ：纯语义层。TBox 声明 + Function 实现，零 DB，已由 ontos 仓 37 例覆盖。
- ``ontos_abox.py``：ABox 适配层。**唯一**有 DB 依赖的本体层：读物理表 → 构造本体事实 → 调 ontos。
- ``routes_ontos`` ：API 层，只做参数校验与响应包装。

本文件验证 ABox 层两件事：
  1. ``_norm_date``       —— 日期归一化。★这是修复「Excel 序列值导致回款周期批量 NaN」
                             的关键函数（总合同表 sign_date 等列是序列值而非日期格式）。
  2. ``abox_payment_cycle``—— mock 掉三个 DB 读取函数，验证「ABox 事实 → 本体计算」链路：
                             口径是否与直接调本体函数一致、缺数据是否**不静默返回 0**。

★ 核心不变量：任何算不出的周期都必须返回 ``cycle_days=None`` + 明确 ``note``，
   绝不可用 0 冒充有效值——0 天会被当成「当天回款」进入平均值与分布统计，污染经营决策。
"""
from datetime import date, datetime

import pytest

import ontos_abox
from ontos_abox import _norm_date, abox_payment_cycle


# ═══════════════════════════════════════════════════════════════════
# 1. _norm_date —— 日期归一化
# ═══════════════════════════════════════════════════════════════════

# 说明：Excel 序列值基准 1899-12-30（避开 Excel 1900 闰年 bug），有效区间 20000–60000。
# 46234 取自现网真实数据（项目「麒麟操作系统采购」sign_date），期望 2026-07-31。
NORM_DATE_CASES = [
    # ── Excel 序列值（历史 NaN 问题的根因，重点防守）──
    (46234, "2026-07-31", "Excel序列值-现网真实案例"),
    ("46234", "2026-07-31", "Excel序列值-字符串形式"),
    # 已知对照：Excel 44927 = 2023-01-01（用于交叉验证基准 1899-12-30 正确）
    (44927, "2023-01-01", "Excel序列值-已知对照44927"),
    # 区间边界（由基准 1899-12-30 推算：1899-12-30 + N 天）
    (20000, "1954-10-03", "Excel序列值-区间下界"),
    (60000, "2064-04-08", "Excel序列值-区间上界"),
    (19999, None, "低于区间下界-不解析"),
    (60001, None, "高于区间上界-不解析"),
    # ── 日期对象 ──
    (date(2026, 7, 31), "2026-07-31", "date对象"),
    (datetime(2026, 7, 31, 15, 30), "2026-07-31", "datetime对象-丢弃时分秒"),
    # ── 字符串格式 ──
    ("2026-07-31", "2026-07-31", "ISO格式"),
    ("2026-07-31 15:30:00", "2026-07-31", "带时分秒"),
    ("2026/07/31", "2026-07-31", "斜杠格式"),
    ("2026.07.31", "2026-07-31", "点格式"),
    ("20260731", "2026-07-31", "紧凑格式"),
    # ── 无效输入（须返回 None，不得抛异常）──
    (None, None, "None"),
    ("", None, "空串"),
    ("-", None, "横线占位"),
    ("=TODAY()", None, "Excel公式"),
    ("abc", None, "非日期字符串"),
]


@pytest.mark.parametrize("value,expected,desc", NORM_DATE_CASES)
def test_norm_date(value, expected, desc):
    """日期归一化：三类输入（日期对象/字符串/Excel序列值）与无效输入容错"""
    assert _norm_date(value) == expected, f"[{desc}] 输入 {value!r}"


def test_norm_date_never_raises_on_weird_input():
    """任何异常输入都应返回 None，而不是抛异常打断批量计算"""
    for bad in [[], {}, object(), float("nan"), float("inf"), "0000-00-00", "2026-13-45"]:
        assert _norm_date(bad) is None, f"输入 {bad!r} 应返回 None"


# ═══════════════════════════════════════════════════════════════════
# 2. abox_payment_cycle —— ABox 事实 → 本体计算
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def stub_db(monkeypatch):
    """打桩 ABox 的三个 DB 读取函数，使测试不依赖真实数据库。

    返回可变 state，用例按需设置：
      state['row']   主数据行（None 表示查无此合同）
      state['recvs'] 财经回款明细 [{'received_date','amount'}]
      state['ms']    里程碑 {'has_milestone','actual','plan','name'}
    """
    state = {
        "row": {"project_no": "P001", "contract_no": "C001", "name": "测试项目",
                "sign_date": "2026-01-01", "sign_amount": 100000.0,
                "accum_received": 0.0, "last_received_date": None},
        "recvs": [],
        "ms": {"has_milestone": False, "actual": None, "plan": None, "name": ""},
    }
    monkeypatch.setattr(ontos_abox, "main_row", lambda no: state["row"])
    monkeypatch.setattr(ontos_abox, "receipt_facts",
                        lambda no, alt_no=None: state["recvs"])
    monkeypatch.setattr(ontos_abox, "milestone_payback", lambda no: state["ms"])
    return state


def test_cycle_single_receipt(stub_db):
    """单笔回款：签约 2026-01-01、回款 2026-02-01 → 31 天"""
    stub_db["recvs"] = [{"received_date": "2026-02-01", "amount": 100000.0}]
    r = abox_payment_cycle("C001")
    assert r["success"] is True
    assert r["cycle_days"] == 31
    assert r["recv_count"] == 1
    assert r["recv_source"] == "finance_detail"


def test_cycle_basis_last_vs_first(stub_db):
    """basis 口径：last 取最后一笔(61天)，first 取首笔(31天)"""
    stub_db["recvs"] = [
        {"received_date": "2026-02-01", "amount": 60000.0},
        {"received_date": "2026-03-03", "amount": 40000.0},
    ]
    assert abox_payment_cycle("C001", basis="last")["cycle_days"] == 61
    assert abox_payment_cycle("C001", basis="first")["cycle_days"] == 31


def test_cycle_no_receipt_returns_none_not_zero(stub_db):
    """★核心不变量：无回款记录 → cycle_days=None + NaN 说明，绝不可返回 0

    0 天会被下游当成「当天回款」计入平均值与分布桶，静默污染经营决策。
    """
    stub_db["recvs"] = []
    r = abox_payment_cycle("C001")
    assert r["cycle_days"] is None, "无回款时不得返回 0（会被误判为当天回款）"
    assert r["cycle_days"] != 0
    assert "NaN" in (r.get("note") or "")
    assert r["sources"]["finance_detail"]["count"] == 0


def test_cycle_missing_sign_date_returns_none(stub_db):
    """缺 sign_date → None + 明确说明，不静默返回 0"""
    stub_db["row"]["sign_date"] = None
    stub_db["recvs"] = [{"received_date": "2026-02-01", "amount": 100000.0}]
    r = abox_payment_cycle("C001")
    assert r["cycle_days"] is None
    assert "sign_date" in (r.get("note") or "")


def test_cycle_excel_serial_sign_date_is_normalized(stub_db):
    """★Excel 序列值 sign_date 必须被正确解析（46234 → 2026-07-31）

    这是历史事故的回归防线：总合同表 sign_date 存的是序列值，
    若不做归一化，回款周期会批量算成 NaN。
    """
    stub_db["row"]["sign_date"] = 46234
    stub_db["recvs"] = [{"received_date": "2026-08-30", "amount": 17420.0}]
    r = abox_payment_cycle("C001")
    assert r["sign_date"] == "2026-07-31", "Excel 序列值未归一化"
    assert r["cycle_days"] == 30, "基于归一化后的签约日应算出 30 天"
    assert r["sign_date_raw"] == 46234, "应保留原始值便于核对"


def test_cycle_receipt_before_sign_flagged(stub_db):
    """回款早于签约 → 负数天数 + 异常标记（数据有问题要暴露，不能静默取绝对值）"""
    stub_db["row"]["sign_date"] = "2026-03-01"
    stub_db["recvs"] = [{"received_date": "2026-01-01", "amount": 100000.0}]
    r = abox_payment_cycle("C001")
    assert r["cycle_days"] == -59
    assert "异常" in (r.get("note") or "")


def test_cycle_no_main_data(stub_db):
    """主数据查无此合同 → success=False + no_main_data，不伪装成计算成功"""
    stub_db["row"] = None
    r = abox_payment_cycle("NOT_EXIST")
    assert r["success"] is False
    assert r["error"] == "no_main_data"


def test_prefer_milestone_falls_back_to_detail(stub_db):
    """prefer=milestone 但无里程碑时，应回落到财经明细口径"""
    stub_db["recvs"] = [{"received_date": "2026-02-01", "amount": 100000.0}]
    stub_db["ms"] = {"has_milestone": False, "actual": None, "plan": None, "name": ""}
    r = abox_payment_cycle("C001", prefer="milestone")
    assert r["cycle_days"] == 31
    assert r["recv_source"] == "finance_detail"


def test_prefer_milestone_uses_milestone_when_present(stub_db):
    """有里程碑时 prefer=milestone 应改用里程碑回款日（口径差异可对照）"""
    stub_db["recvs"] = [{"received_date": "2026-02-01", "amount": 100000.0}]
    stub_db["ms"] = {"has_milestone": True, "actual": "2026-04-01",
                     "plan": "2026-03-15", "name": "终验"}
    r_ms = abox_payment_cycle("C001", prefer="milestone")
    r_fd = abox_payment_cycle("C001", prefer="finance_detail")
    assert r_ms["recv_source"] == "plm_milestone"
    assert r_ms["cycle_days"] == 90, "里程碑口径：签约→2026-04-01 = 90 天"
    assert r_fd["recv_source"] == "finance_detail"
    assert r_fd["cycle_days"] == 31, "财经口径：签约→2026-02-01 = 31 天"
    # 两个口径都应保留在 sources 里，便于业务核对差异
    assert r_fd["sources"]["plm_milestone"]["actual"] == "2026-04-01"


def test_abox_matches_direct_ontology_call(stub_db):
    """★口径一致性：ABox 链路的结果，必须与直接调本体纯函数完全相同

    这是「固化(9006) 与 探索(demo) 调同一批 ontos 纯函数」的落地验证——
    ABox 层只负责构造事实，不得夹带任何自己的算法（否则就是口径漂移）。
    """
    stub_db["recvs"] = [
        {"received_date": "2026-02-01", "amount": 60000.0},
        {"received_date": "2026-03-03", "amount": 40000.0},
    ]
    via_abox = abox_payment_cycle("C001", basis="last")

    biz = ontos_abox.load_ontos()
    direct = biz.functions.call(
        "F-payment-cycle",
        sign_date="2026-01-01",
        receipts=stub_db["recvs"],
        basis="last",
        recv_source="finance_detail",
    )
    for key in ("cycle_days", "recv_date", "first_recv_date",
                "last_recv_date", "recv_count", "note"):
        assert via_abox[key] == direct[key], f"{key} 出现口径漂移"


def test_abox_enriches_business_fields(stub_db):
    """ABox 除本体结果外，应补上业务字段（合同/项目/金额/来源），供页面直接渲染"""
    stub_db["recvs"] = [{"received_date": "2026-02-01", "amount": 100000.0}]
    r = abox_payment_cycle("C001")
    assert r["project_no"] == "P001"
    assert r["contract_no"] == "C001"
    assert r["name"] == "测试项目"
    assert r["sign_amount"] == 100000.0
    assert set(r["sources"]) == {"finance_detail", "plm_milestone",
                                 "maindata_last_received_date"}


# ═══════════════════════════════════════════════════════════════════
# 3. receipt_facts / payment_facts —— 双键并集（现网缺陷修复的防线）
# ═══════════════════════════════════════════════════════════════════
#
# 现网缺陷：get_finance_detail 的 SQL 是
#   WHERE project_no=? OR (COALESCE(project_no,'')='' AND contract_no=?)
# 即 project_no 一旦回填非空，就**不再回落** contract_no。
# 于是用合同号查询时，若明细行的 project_no 已回填成真实项目号，会整条落空，
# 回款周期被算成 NaN。ABox 层用「查询键 + 备选键各查一次取并集」修复。

@pytest.fixture
def stub_finance(monkeypatch):
    """打桩财经明细读取：按查询键返回不同结果，用于验证双键并集与去重。

    用法：stub_finance['C001'] = {'recv': [...], 'pay': [...]}
    未设置的键返回空。
    """
    data = {}

    def _fake(no):
        return data.get(no, {"recv": [], "pay": []})

    monkeypatch.setattr(ontos_abox.pm, "get_finance_detail", _fake)
    return data


def _recv(d, amount=1000.0):
    """构造一条财经回款明细（occur_date 用 date 对象，贴近真实返回）"""
    from datetime import date as _d
    y, m, day = (int(x) for x in d.split("-"))
    return {"occur_date": _d(y, m, day), "amount": amount}


def test_receipt_facts_dual_key_union(stub_finance):
    """★核心：合同号查不到（project_no 已回填）时，备选项目号必须能补上

    这正是现网缺陷的场景——若只查合同号，结果为空，回款周期被误算成 NaN。
    """
    stub_finance["C001"] = {"recv": []}                      # 合同号查不到
    stub_finance["P001"] = {"recv": [_recv("2026-02-01")]}   # 项目号能查到
    rows = ontos_abox.receipt_facts("C001", alt_no="P001")
    assert len(rows) == 1, "备选键未生效，回款事实丢失"
    assert rows[0]["received_date"] == "2026-02-01"


def test_receipt_facts_dedupes_overlap(stub_finance):
    """两个键命中同一条记录时，按 (日期, 金额) 去重，不得重复计入"""
    same = _recv("2026-02-01", amount=1000.0)
    stub_finance["C001"] = {"recv": [same]}
    stub_finance["P001"] = {"recv": [dict(same)]}
    rows = ontos_abox.receipt_facts("C001", alt_no="P001")
    assert len(rows) == 1, "同一笔回款被重复计入，会虚增 recv_count"


def test_receipt_facts_distinct_rows_are_all_kept(stub_finance):
    """不同日期/金额的记录都要保留，且按日期升序"""
    stub_finance["C001"] = {"recv": [_recv("2026-03-03", 400.0),
                                     _recv("2026-02-01", 600.0)]}
    stub_finance["P001"] = {"recv": [_recv("2026-01-15", 100.0)]}
    rows = ontos_abox.receipt_facts("C001", alt_no="P001")
    assert [r["received_date"] for r in rows] == [
        "2026-01-15", "2026-02-01", "2026-03-03"], "未按日期升序或记录丢失"
    assert [r["amount"] for r in rows] == [100.0, 600.0, 400.0]


def test_receipt_facts_skips_rows_without_date(stub_finance):
    """occur_date 为空的脏数据应跳过，不能让 is None 参与排序/比较而崩溃"""
    stub_finance["C001"] = {"recv": [{"occur_date": None, "amount": 999.0},
                                     _recv("2026-02-01")]}
    rows = ontos_abox.receipt_facts("C001", alt_no=None)
    assert len(rows) == 1
    assert rows[0]["received_date"] == "2026-02-01"


def test_receipt_facts_alt_no_optional(stub_finance):
    """不传备选键时只查主键，且不应报错"""
    stub_finance["C001"] = {"recv": [_recv("2026-02-01")]}
    assert len(ontos_abox.receipt_facts("C001")) == 1


def test_payment_facts_dual_key_and_dedup(stub_finance):
    """付款事实与回款同理：双键并集 + 去重 + 按 paid_date 升序"""
    from datetime import date as _d
    stub_finance["C001"] = {"pay": [{"occur_date": _d(2026, 3, 1), "amount": 500.0},
                                    {"occur_date": _d(2026, 1, 20), "amount": 300.0}]}
    stub_finance["P001"] = {"pay": [{"occur_date": _d(2026, 3, 1), "amount": 500.0}]}
    rows = ontos_abox.payment_facts("C001", alt_no="P001")
    assert len(rows) == 2, "去重未生效"
    assert [r["paid_date"] for r in rows] == ["2026-01-20", "2026-03-01"]
    assert all("paid_date" in r and "amount" in r for r in rows)
