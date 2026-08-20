# Delta Spec：资金占用分析（CC-006）

> 变更编号：20260818-fund-yoy | delta 三节：ADDED / MODIFIED / REMOVED

## ADDED

### Requirement: 同比对比分析

系统 SHALL 在资金占用总览中提供与去年同期（YoY）对比的同比数据，涵盖累计付款、累计回款、净现金流与当前资金占用四项指标，并 SHALL 展示本期值与同比变化（数值与百分比）。同比窗口 SHALL 以报表截止日对齐上年同期（本期为当年 1 月 1 日至报表截止日，上期为上年 1 月 1 日至上年同期日）。

#### Scenario: 返回同比所需现金流序列

- GIVEN 用户调用 `POST /api/fund/analyze` 完成资金占用分析
- WHEN 接口返回结果
- THEN `data.flows` 返回全量逐笔现金流序列，元素含 `date`（YYYY-MM-DD）、`type`（PAY/RECEIVE）、`amount`（付款为负、回款为正）

#### Scenario: 累计付款/回款同比

- GIVEN 报表截止日为 2026-08-12，2026 年前 8 个月累计付款 9000 万、2025 年同期累计付款 7500 万
- WHEN 前端加载资金占用总览
- THEN 累计付款 KPI 展示本期 9000 万、同比 +20.0%，方向为上升

#### Scenario: 当前资金占用同比

- GIVEN 当前资金占用总额 1.2 亿，截至 2025-08-12 的同口径存量占用 1.5 亿
- WHEN 前端加载资金占用总览
- THEN 当前资金占用 KPI 展示本期 1.2 亿、同比 -20.0%（占用下降）

#### Scenario: 上期无数据

- GIVEN 上期（上年同期窗口）付款或回款合计为 0
- WHEN 前端计算同比变化率
- THEN 该指标同比变化率显示为无数据（`—`），不得报除零错误

#### Scenario: 月度同比对比图

- GIVEN 前端已获得 `data.flows`
- WHEN 用户查看资金占用总览
- THEN 展示月度同比对比图：X 轴为当年 1 月至截止月，逐月对比上年同月与当月的付款、回款，提示框包含同比变化

## MODIFIED

（无）

## REMOVED

（无）
