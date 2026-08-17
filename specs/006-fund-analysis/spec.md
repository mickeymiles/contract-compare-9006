# 资金占用分析 Specification

> 规格编号: CC-006 | 状态: 生效 | 最后更新: 2026-08-17
> 对应代码: `backend/main.py`（/api/fund/*）

## Purpose

基于付款、回款与规则数据，按 FIFO（先进先出）口径计算资金占用分布，输出资金占用状态、分合同分段占用明细与汇总指标，并支持快照持久化与结果导出，为资金周转决策提供依据。

## Requirements

### Requirement: 数据上传

系统 SHALL 支持上传三类数据：付款记录（type=payment）、回款记录（type=collection）、占用规则（type=rule），上传后 SHALL 持久化存储。

#### Scenario: 上传付款数据

- GIVEN 用户选择付款 Excel 文件并以 type=payment 上传
- WHEN 调用 `POST /api/fund/upload`
- THEN 系统解析并保存付款记录

### Requirement: 敏感列清洗

系统 SHALL 在上传时删除客户名称、客户简称、项目名称等敏感列，仅保留分析所需的金额、日期、合同标识等字段。

#### Scenario: 清洗敏感信息

- GIVEN 上传文件含 `客户名称`、`项目名称` 列
- WHEN 解析上传
- THEN 数据中不包含上述敏感列

### Requirement: FIFO 占用计算

系统 SHALL 按 FIFO（先进先出）原则计算资金占用：回款按时间顺序冲抵最早发生的付款占用，未被冲抵的付款金额计入占用余额，形成逐笔占用明细。

#### Scenario: FIFO 冲抵

- GIVEN 1 月付款 100 万、2 月付款 50 万，3 月回款 120 万
- WHEN 执行资金占用分析
- THEN 3 月回款先冲抵 1 月的 100 万，再冲抵 2 月的 20 万，剩余占用 30 万

### Requirement: 占用状态与分段

系统 SHALL 提供资金占用总览（`GET /api/fund/status`）、分合同分段占用明细（`GET /api/fund/segments/{contract_id}`）与汇总指标（`GET /api/fund/metrics`），输出占用金额、占用天数、占用区间分布等。

#### Scenario: 分段占用查询

- GIVEN 合同 C 存在多笔未冲抵付款
- WHEN 查询 `GET /api/fund/segments/C`
- THEN 返回该合同按时间分段（如 30 天/60 天/90 天以上）的占用明细

### Requirement: 快照持久化

系统 SHALL 在每次分析后保存快照（含分析时间、输入数据、计算结果），支持随时加载最近快照查看分析结果，避免重复上传数据。

#### Scenario: 快照复用

- GIVEN 已完成一次资金占用分析
- WHEN 再次打开资金分析页面
- THEN 页面直接展示最近一次快照结果，无需重新上传

### Requirement: 分析结果导出

系统 SHALL 支持导出资金占用分析结果（`GET /api/fund/analyze/export`）为 Excel。

#### Scenario: 导出占用结果

- GIVEN 资金占用分析已完成
- WHEN 调用导出接口
- THEN 返回包含占用明细与汇总的 Excel

## 非功能需求

- NFR-1：FIFO 分析 SHALL 在 10 秒内完成（十万行级数据）
- NFR-2：敏感数据清洗 SHALL 在任何持久化之前完成

## 测试标准

- TC-1：FIFO 冲抵计算用例（对应 FR-3），位置 `tests/test_fund.py`
- TC-2：敏感列清洗用例（对应 FR-2）
