# 变更提案：CC-005 回款周期分析补充测试覆盖

- 编号：`20260817-cc005-payment-cycle-tests`
- 日期：2026-08-17
- 类型：测试补齐（规格回填闭环）
- 涉及规格：CC-005 回款周期分析

## 为什么（Why）

CC-005 回款周期分析为存量核心功能（双口径分析、按月累计、周期区间划分），
但 `specs/TRACEABILITY.md` 标注其**无测试覆盖**。为满足 SDD 铁律
"测试绑定规格（# CC-005 FR-x）"，需补齐单元测试。

## 范围（In / Out of Scope）

- In scope：新增 `tests/test_payment_cycle.py`，覆盖 CC-005 的：
  - 双数据源加载（总合同表 H / 项目里程碑表 R，versions.json 解析）
  - 按月累计（2026-06/07/08 三个月桶，current/previous 双口径）
  - 周期区间划分（zone 五档边界）
  - 年份过滤（仅 2026/2025 参与，2024 排除）
  - 数据源缺失降级（无总合同表 / 无里程碑表）
- Out of scope：不改动 `backend/main.py` 回款逻辑；不涉及前端与数据库结构变更

## 验收标准（Acceptance）

- `python3 -m pytest tests/test_payment_cycle.py -q` 全部通过
- 既有回归 `tests/test_compare_engine.py tests/test_excel_handler.py tests/test_export.py` 不受影响
