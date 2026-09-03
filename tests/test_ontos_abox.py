# -*- coding: utf-8 -*-
"""本体 ABox 适配层测试（9006）。

═══ 分层背景 ═══
- ``ontos/``       ：纯语义层。TBox 声明 + Function 实现，零 DB，已由 ontos 仓覆盖。
- ``ontos_abox.py``：ABox 适配层。**唯一**有 DB 依赖的本体层：读物理表 → 构造本体事实 → 调 ontos。
- ``routes_ontos`` ：API 层，只做参数校验与响应包装。

═══ 回款周期口径（2026-09-03 用户拍板）═══
**默认 prefer='milestone_plan'**：只按里程碑【计划回款时间】(plm_milestone.plan_payback_date)
计算，**不使用财务明细、也无任何回退**——无里程碑计划回款日即算不出。
注意计划回款日常指向未来（"维护期"/"验收后1年"），故该口径是【计划回款周期】。
另有 'finance_detail'（实际已发生回款）与 'milestone'（里程碑优先+回退明细）供对照。

★ 核心不变量（显式断言）：任何算不出的周期必须返回 ``cycle_days=None`` + 明确 ``note``，
   绝不可用 0 冒充——0 天会被当成「当天回款」进入平均值与分布统计，污染经营决策。
"""
from datetime import date, datetime

import pytest

import ontos_abox
from ontos_abox import _norm_date, abox_payment_cycle


# ═══════════════════════════════════════════════════════════════════
# 0. 公共 fixture
# ═══════════════════════════════════════════════════════════════════

def _ms(plans=None, actuals=None, name="", amount=None):
    """构造 milestone_payback 的返回结构（按新契约含 plans/actuals 列表）"""
    plans = plans or []
    actuals = actuals or []
    return {'has_milestone': bool(plans or actuals),
            'plans': sorted(plans), 'actuals': sorted(actuals),
            'plan': plans[-1] if plans else None,
            'actual': actuals[-1] if actuals else None,
            'payback_amount': amount, 'name': name}


@pytest.fixture
def stub_db(monkeypatch):
    """打桩 ABox 的 DB 读取函数，使测试不依赖真实数据库。

    返回可变 state，用例按需设置：
      state['row']   主数据行（None 表示查无此合同）
      state['recvs'] 财经回款明细 [{'received_date','amount'}]
      state['ms']    里程碑（用 _ms() 构造）
    """
    state = {
        "row": {"project_no": "P001", "contract_no": "C001", "name": "测试项目",
                "sign_date": "2026-01-01", "sign_amount": 100000.0,
                "accum_received": 0.0, "last_received_date": None},
        "recvs": [],
        "ms": _ms(),
    }
    monkeypatch.setattr(ontos_abox, "main_row", lambda no: state["row"])
    monkeypatch.setattr(ontos_abox, "receipt_facts",
                        lambda no, alt_no=None: state["recvs"])
    monkeypatch.setattr(ontos_abox, "milestone_payback",
                        lambda no, alt_no=None: state["ms"])
    return state


# ═══════════════════════════════════════════════════════════════════
# 1. _norm_date —— 日期归一化
# ═══════════════════════════════════════════════════════════════════

# Excel 序列值基准 1899-12-30（避开 Excel 1900 闰年 bug），有效区间 20000–60000。
# 46234 取自现网真实数据（项目「麒麟操作系统采购」sign_date），期望 2026-07-31。
NORM_DATE_CASES = [
    (46234, "2026-07-31", "Excel序列值-现网真实案例"),
    ("46234", "2026-07-31", "Excel序列值-字符串形式"),
    # 已知对照：Excel 44927 = 2023-01-01（用于交叉验证基准 1899-12-30 正确）
    (44927, "2023-01-01", "Excel序列值-已知对照44927"),
    (20000, "1954-10-03", "Excel序列值-区间下界"),
    (60000, "2064-04-08", "Excel序列值-区间上界"),
    (19999, None, "低于区间下界-不解析"),
    (60001, None, "高于区间上界-不解析"),
    (date(2026, 7, 31), "2026-07-31", "date对象"),
    (datetime(2026, 7, 31, 15, 30), "2026-07-31", "datetime对象-丢弃时分秒"),
    ("2026-07-31", "2026-07-31", "ISO格式"),
    ("2026-07-31 15:30:00", "2026-07-31", "带时分秒"),
    ("2026/07/31", "2026-07-31", "斜杠格式"),
    ("2026.07.31", "2026-07-31", "点格式"),
    ("20260731", "2026-07-31", "紧凑格式"),
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
# 2. 默认口径：里程碑计划回款（milestone_plan，无回退）
# ═══════════════════════════════════════════════════════════════════

def test_default_prefer_is_milestone_plan():
    """默认口径必须是里程碑计划回款（用户拍板）"""
    import inspect
    sig = inspect.signature(abox_payment_cycle)
    assert sig.parameters["prefer"].default == "milestone_plan"


def test_milestone_plan_single(stub_db):
    """单个里程碑：签约 2026-01-01、计划回款 2026-02-01 → 31 天"""
    stub_db["ms"] = _ms(plans=["2026-02-01"], name="验收")
    r = abox_payment_cycle("C001")
    assert r["success"] is True
    assert r["cycle_days"] == 31
    assert r["recv_source"] == "plm_milestone.plan"


def test_milestone_plan_basis_last_vs_first(stub_db):
    """多里程碑：basis=last 取最晚，basis=first 取最早"""
    stub_db["ms"] = _ms(plans=["2026-02-01", "2026-03-03"])
    assert abox_payment_cycle("C001", basis="last")["cycle_days"] == 61
    assert abox_payment_cycle("C001", basis="first")["cycle_days"] == 31


def test_milestone_plan_no_fallback_to_finance(stub_db):
    """★无回退：没有里程碑计划回款日时，即使有财务明细也**不算**（返回 None）

    这是用户 2026-09-03 明确拍板的口径：就是里程碑数据，不用财务、不回退。
    """
    stub_db["recvs"] = [{"received_date": "2026-05-01", "amount": 50000.0}]
    stub_db["ms"] = _ms()          # 无任何里程碑
    r = abox_payment_cycle("C001")
    assert r["cycle_days"] is None, "无回退口径下，不得用财务明细兜底"
    assert r["recv_source"] is None
    # 财务明细仍应在 sources 里保留，供业务核对
    assert r["sources"]["finance_detail"]["count"] == 1


def test_milestone_plan_may_point_to_future(stub_db):
    """计划回款日可以指向未来（如"维护期"）——该口径是计划周期，非已发生回款"""
    stub_db["ms"] = _ms(plans=["2029-12-30"], name="维护期")
    r = abox_payment_cycle("C001")
    assert r["cycle_days"] == (1459), "2026-01-01 → 2029-12-30"
    assert r["recv_date"] == "2029-12-30"


def test_milestone_plan_missing_sign_date(stub_db):
    """缺 sign_date → None + 明确说明（不返回 0）"""
    stub_db["row"]["sign_date"] = None
    stub_db["ms"] = _ms(plans=["2026-02-01"])
    r = abox_payment_cycle("C001")
    assert r["cycle_days"] is None
    assert "sign_date" in (r.get("note") or "")


def test_milestone_plan_excel_serial_sign_date(stub_db):
    """Excel 序列值 sign_date 必须被归一化（46234 → 2026-07-31）"""
    stub_db["row"]["sign_date"] = 46234
    stub_db["ms"] = _ms(plans=["2026-08-30"])
    r = abox_payment_cycle("C001")
    assert r["sign_date"] == "2026-07-31"
    assert r["cycle_days"] == 30
    assert r["sign_date_raw"] == 46234


# ═══════════════════════════════════════════════════════════════════
# 3. 对照口径：finance_detail / milestone（带回退）
# ═══════════════════════════════════════════════════════════════════

def test_finance_detail_caliber(stub_db):
    """显式 prefer='finance_detail'：按财经明细实际回款计算"""
    stub_db["recvs"] = [{"received_date": "2026-02-01", "amount": 100000.0}]
    stub_db["ms"] = _ms(plans=["2026-09-09"])   # 里程碑计划另有值
    r = abox_payment_cycle("C001", prefer="finance_detail")
    assert r["cycle_days"] == 31, "应取财务明细口径，而非里程碑计划"
    assert r["recv_source"] == "finance_detail"


def test_milestone_caliber_with_fallback(stub_db):
    """prefer='milestone'（带回退，非默认）：无里程碑时回落财务明细"""
    stub_db["recvs"] = [{"received_date": "2026-02-01", "amount": 100000.0}]
    stub_db["ms"] = _ms()
    r = abox_payment_cycle("C001", prefer="milestone")
    assert r["cycle_days"] == 31
    assert r["recv_source"] == "finance_detail"


def test_milestone_caliber_prefers_milestone_when_present(stub_db):
    """prefer='milestone' 且里程碑存在时，用里程碑（实际优先于计划）"""
    stub_db["recvs"] = [{"received_date": "2026-02-01", "amount": 100000.0}]
    stub_db["ms"] = _ms(plans=["2026-03-15"], actuals=["2026-04-01"], name="终验")
    r = abox_payment_cycle("C001", prefer="milestone")
    assert r["recv_source"] == "plm_milestone"
    assert r["cycle_days"] == 90, "里程碑实际回款 2026-04-01 → 90 天"


# ═══════════════════════════════════════════════════════════════════
# 4. 不变量与通用行为
# ═══════════════════════════════════════════════════════════════════

def test_never_returns_zero_as_fake_value(stub_db):
    """★核心不变量：算不出必须是 None，绝不可返回 0

    0 天会被下游当成「当天回款」计入平均值与分布桶，静默污染经营决策。
    """
    stub_db["recvs"] = []
    stub_db["ms"] = _ms()
    r = abox_payment_cycle("C001")
    assert r["cycle_days"] is None
    assert r["cycle_days"] != 0
    assert "NaN" in (r.get("note") or "")


def test_receipt_before_sign_flagged(stub_db):
    """回款早于签约 → 负数天数 + 异常标记（暴露数据问题，不静默归零）"""
    stub_db["row"]["sign_date"] = "2026-03-01"
    stub_db["ms"] = _ms(plans=["2026-01-01"])
    r = abox_payment_cycle("C001")
    assert r["cycle_days"] == -59
    assert "异常" in (r.get("note") or "")
    # ★端到端异常标志：负周期必须显式标为 anomaly，避免下游误桶为"0.5年以内"
    assert r.get("anomaly") is True


def test_no_main_data(stub_db):
    """主数据查无此合同 → success=False + no_main_data"""
    stub_db["row"] = None
    r = abox_payment_cycle("NOT_EXIST")
    assert r["success"] is False
    assert r["error"] == "no_main_data"


def test_abox_matches_direct_ontology_call(stub_db):
    """★口径一致性：ABox 结果必须与直接调本体纯函数完全相同

    ABox 只负责构造事实，不得夹带自己的算法（否则就是口径漂移）。
    """
    stub_db["ms"] = _ms(plans=["2026-02-01"])
    via_abox = abox_payment_cycle("C001", basis="last")

    biz = ontos_abox.load_ontos()
    direct = biz.functions.call(
        "F-payment-cycle",
        sign_date="2026-01-01",
        receipts=[{"received_date": "2026-02-01"}],
        basis="last",
        recv_source="plm_milestone.plan",
    )
    for key in ("cycle_days", "recv_date", "first_recv_date",
                "last_recv_date", "note"):
        assert via_abox[key] == direct[key], f"{key} 出现口径漂移"


def test_abox_enriches_business_fields(stub_db):
    """ABox 除本体结果外，应补上业务字段，供页面直接渲染"""
    stub_db["ms"] = _ms(plans=["2026-02-01"])
    r = abox_payment_cycle("C001")
    assert r["project_no"] == "P001"
    assert r["contract_no"] == "C001"
    assert r["name"] == "测试项目"
    assert r["sign_amount"] == 100000.0
    assert set(r["sources"]) == {"finance_detail", "plm_milestone",
                                 "maindata_last_received_date"}
    assert r["prefer"] == "milestone_plan"
    assert r["basis"] == "last"


# ═══════════════════════════════════════════════════════════════════
# 5. receipt_facts / payment_facts —— 双键并集（现网缺陷修复的防线）
# ═══════════════════════════════════════════════════════════════════
#
# 现网缺陷：get_finance_detail 的 SQL 是
#   WHERE project_no=? OR (COALESCE(project_no,'')='' AND contract_no=?)
# 即 project_no 一旦回填非空，就**不再回落** contract_no。
# 于是用合同号查询时，若明细行的 project_no 已回填成真实项目号，会整条落空。
# ABox 层用「查询键 + 备选键各查一次取并集」修复。

@pytest.fixture
def stub_finance(monkeypatch):
    """打桩财经明细读取：按查询键返回不同结果，用于验证双键并集与去重。"""
    data = {}

    def _fake(no):
        return data.get(no, {"recv": [], "pay": []})

    monkeypatch.setattr(ontos_abox.pm, "get_finance_detail", _fake)
    return data


def _recv(d, amount=1000.0):
    from datetime import date as _d
    y, m, day = (int(x) for x in d.split("-"))
    return {"occur_date": _d(y, m, day), "amount": amount}


def test_receipt_facts_dual_key_union(stub_finance):
    """★合同号查不到（project_no 已回填）时，备选项目号必须能补上"""
    stub_finance["C001"] = {"recv": []}
    stub_finance["P001"] = {"recv": [_recv("2026-02-01")]}
    rows = ontos_abox.receipt_facts("C001", alt_no="P001")
    assert len(rows) == 1, "备选键未生效，回款事实丢失"
    assert rows[0]["received_date"] == "2026-02-01"


def test_receipt_facts_dedupes_overlap(stub_finance):
    """两个键命中同一条记录时，按 (日期, 金额) 去重"""
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
    """occur_date 为空的脏数据应跳过，不能让 None 参与排序而崩溃"""
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
