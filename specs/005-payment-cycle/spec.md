# 回款周期分析 Specification

> 规格编号: CC-005 | 状态: 生效 | 最后更新: 2026-08-17
> 对应代码: `backend/main.py`（/api/analysis/payment-cycle、/api/analysis/payment-cycle/export、/api/payment-cycle/metrics）

## Purpose

基于"总合同表（H 表）∪ 项目里程碑表（R 表）"双数据源合并计算各客户/项目的回款周期与按月份累计回款情况，输出合同金额、回款金额、回款周期天数等指标，并兼容 9006 系统的字段口径。

## Requirements

### Requirement: 双源数据合并

系统 SHALL 以总合同表（H 表）为主表，用项目里程碑表（R 表）补充回款记录，按客户/项目维度合并计算，形成"合同 → 里程碑回款"的完整视图。

#### Scenario: 合并计算

- GIVEN H 表含合同金额 100 万，R 表含 3 条回款记录（合计 60 万）
- WHEN 执行回款周期分析
- THEN 该合同回款合计为 60 万，回款率为 60%

### Requirement: 按月累计统计

系统 SHALL 按月份对回款金额做累计统计，输出各月回款额与累计回款额，用于呈现回款节奏。

#### Scenario: 按月累计

- GIVEN 3 月回款 10 万、4 月回款 20 万
- WHEN 查看按月统计
- THEN 3 月累计 10 万，4 月累计 30 万

### Requirement: 回款周期天数

系统 SHALL 计算回款周期天数 =（最后回款时间 − 签约日期）的天数差，并换算为年限（days/365），支持按周期年限分档统计（如 0.5 年内、0.5~1 年、1 年以上）。

#### Scenario: 周期分档

- GIVEN 合同签约于 2024-01-01，最后回款于 2024-06-30
- WHEN 计算回款周期
- THEN 周期约 181 天（0.5 年内档位）

### Requirement: 9006 字段兼容

系统 SHALL 兼容 9006 系统的字段命名与口径（客户名称、合同编号、签约日期、回款日期等），解析日期时 SHALL 支持多种日期格式，列名匹配 SHALL 采用模糊匹配。

#### Scenario: 9006 兼容解析

- GIVEN 数据源列名为 9006 风格（如 `签约日期`、`回款日期`）
- WHEN 执行分析
- THEN 字段被正确识别与解析，不产生列缺失

### Requirement: 数据过滤

系统 SHALL 支持按年份过滤分析范围，仅统计指定年份的数据。

#### Scenario: 年份过滤

- GIVEN 数据含 2023 与 2024 年回款记录
- WHEN 以年份=2024 过滤
- THEN 分析结果仅含 2024 年数据

### Requirement: 指标查询与导出

系统 SHALL 提供回款周期指标接口（`GET /api/payment-cycle/metrics`）与统计视图（`GET /api/analysis/payment-cycle`），并支持导出（`GET /api/analysis/payment-cycle/export`）为 Excel。

#### Scenario: 导出分析结果

- GIVEN 回款周期分析已完成
- WHEN 调用导出接口
- THEN 返回包含合同金额、回款金额、回款率、周期天数的 Excel

## 非功能需求

- NFR-1：分析接口 SHALL 在 5 秒内返回（万行级数据）
- NFR-2：字段缺失时 SHALL 给出缺失提示而非静默出错

## 测试标准

- TC-1：双源合并与按月累计用例（对应 FR-1~FR-2），位置 `tests/test_payment_cycle.py`
- TC-2：周期天数与分档用例（对应 FR-3）
