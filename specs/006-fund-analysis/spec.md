# 资金占用分析 Specification

> 规格编号: CC-006 | 状态: 生效 | 最后更新: 2026-08-18
> 对应代码: `backend/main.py`（/api/fund/*、/api/fund/dim/*、/api/fund/risk/*）

## Purpose

基于付款、回款与规则数据，按 FIFO（先进先出）口径计算资金占用分布，输出资金占用状态、分合同分段占用明细与汇总指标，并支持多维度聚合分析（区域/客户集合/部门/业务线/时间）、四级风险预警、趋势预警、穿透下钻与结果导出，为资金周转决策提供依据。

## Requirements

### Requirement: 数据上传

系统 SHALL 支持上传三类数据：付款记录（type=payment）、回款记录（type=collection）、占用规则（type=rule），上传后 SHALL 持久化存储。

#### Scenario: 上传付款数据

- GIVEN 用户选择付款 Excel 文件并以 type=payment 上传
- WHEN 调用 `POST /api/fund/upload`
- THEN 系统解析并保存付款记录

### Requirement: 敏感列清洗

系统 SHALL 在上传时删除客户名称、客户简称、项目名称等敏感列，仅保留分析所需的金额、日期、合同标识与脱敏客户键字段。

#### Scenario: 清洗敏感信息

- GIVEN 上传文件含 `客户名称`、`项目名称` 列
- WHEN 解析上传
- THEN 数据中不包含客户名称/项目名称原文，但保留脱敏客户键编码

### Requirement: 维度关联

系统 SHALL 在资金占用分析时按合同编号 join 总合同表（区域、省、分区、部门、签定部门、业务线、业务类型、客户分类、签订行业、行业、合同状态、是否小额/认证合同、合同总金额、合同签定时间、客户标识）与项目里程碑表（项目状态、项目合同状态、业务线名称、执行部门、项目区域、账期、计划回款时间），为每个合同附加维度标签；join 不到的合同归入"未知"桶，不得影响主 FIFO 计算结果。

#### Scenario: 维度标签附加

- GIVEN 付款明细中存在合同 `HT-001`，总合同表存在 `HT-001` 记录（区域=华东，部门=政企一部）
- WHEN 执行 `POST /api/fund/analyze`
- THEN `fund_metrics` 中 `HT-001` 行的 `region='华东'`、`dept='政企一部'`

### Requirement: 敏感列清洗（客户键保留）

系统 SHALL 在上传时删除客户名称、客户简称、项目名称等敏感列，但 SHALL 保留脱敏客户键：优先取总合同表「客户标识」列原文；总合同表缺省时对客户名称做确定性编码（拼音缩写+哈希尾缀），仅持久化编码，不持久化真实名称。

#### Scenario: 保留脱敏客户键

- GIVEN 总合同表存在客户标识列（如 `QDHEKJ`）
- WHEN 执行资金占用分析并写入宽表
- THEN `fund_metrics.customer_key='QDHEKJ'`，且表中不存在客户名称原文

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

### Requirement: 多维度聚合指标

系统 SHALL 提供维度聚合查询 `GET /api/fund/dim/aggregate`，支持维度 `region`（区域）、`province`（省）、`dept`（部门）、`biz_line`（业务线）、`industry`（行业）、`customer_key`（客户集合）、`project_status`（项目状态）、`month`（月份），返回各维度下的合同数、累计付款、累计收款、净现金流、当前资金占用、平均资金占用、回款率、占用强度、预估资金成本、风险等级分布。

#### Scenario: 区域维度聚合

- GIVEN 完成资金占用分析且宽表含维度列
- WHEN 调用 `GET /api/fund/dim/aggregate?dim=region`
- THEN 返回按区域聚合的指标行，含回款率与占用强度

### Requirement: 风险预警引擎

系统 SHALL 依据占用天数、回款率、占用强度组合对每个合同与每个维度分组进行风险分级（健康/关注/预警/高危），默认阈值：占用 ≤30 天健康；30–90 天关注；90–180 天且回款率 ≥50% 关注、<50% 预警；>180 天且占用强度 ≤50% 预警、>50% 高危；回款率为 0 且占用金额 ≥100 万为高危。阈值 SHALL 可通过 `GET/POST /api/fund/risk/config` 查询与更新，更新后重算风险等级。

#### Scenario: 高危判定

- GIVEN 合同占用 210 天、占用强度 60%、回款率 20%
- WHEN 调用 `GET /api/fund/risk/list`
- THEN 该合同风险等级为 `high`，且预警清单包含该合同与干预建议

### Requirement: 趋势预警

系统 SHALL 提供 `GET /api/fund/risk/trend`，对区域与客户集合维度的占用金额按月聚合，当某维度占用金额环比连续上升 2 个月（默认配置，可调整）时，标记为趋势预警。

#### Scenario: 连续两月上升预警

- GIVEN 华东区域 5 月占用 1000 万、6 月 1200 万、7 月 1400 万
- WHEN 调用 `GET /api/fund/risk/trend`
- THEN 华东区域被标记为趋势预警

### Requirement: 穿透下钻

系统 SHALL 支持维度逐级下钻：区域/客户集合 → 该维度下合同清单 → 合同占用片段明细（复用 `GET /api/fund/segments/{contract_id}`）。

#### Scenario: 区域下钻到合同

- GIVEN 区域聚合页展示华东区域
- WHEN 用户点击华东区域
- THEN 返回该区域下合同清单（含每合同占用与风险等级），点击合同可查看片段明细

### Requirement: 图表与导出

系统 SHALL 提供资金占用多维度图表（区域热力地图、区域占用×回款率双轴柱状、客户集合占用 TOP10、风险等级分布堆叠条形、项目状态环形、月度趋势折线、占用时长分段直方图、风险四象限散点、资金成本构成环形），每张图表可导出 PNG；维度聚合数据与预警清单可导出 Excel。

### Requirement: 同比对比分析（FR-13）

系统 MUST 在资金占用总览中提供与去年同期（YoY）对比的同比数据，涵盖累计付款、累计回款、净现金流与当前资金占用四项指标，呈现本期值与同比变化（数值与百分比）。同比窗口 MUST 以报表截止日对齐上年同期：本期为当年 1 月 1 日至报表截止日，上期为上年 1 月 1 日至上年同期日。

#### Scenario: 返回同比所需现金流序列

- GIVEN 用户调用 `POST /api/fund/analyze` 完成资金占用分析
- WHEN 接口返回结果
- THEN `data.flows` 返回全量逐笔现金流序列，元素含 `date`（YYYY-MM-DD）、`type`（PAY/RECEIVE）、`amount`（付款为负、回款为正）
- AND `data.yoy.occupy_prev` 返回截至上年同期日的 FIFO 资金占用合计（口径与当前占用一致）

#### Scenario: 累计付款/回款同比

- GIVEN 报表截止日为 2026-08-12，2026 年前 8 个月累计付款 9000 万、2025 年同期累计付款 7500 万
- WHEN 前端加载资金占用总览
- THEN 累计付款 KPI 展示本期 9000 万、同比 +20.0%，方向为上升

#### Scenario: 当前资金占用同比

- GIVEN 当前资金占用总额 1.2 亿，上年同期日（2025-08-12）FIFO 占用 1.5 亿
- WHEN 前端加载资金占用总览
- THEN 当前资金占用 KPI 展示本期 1.2 亿、同比 -20.0%（占用下降，以绿色语义色渲染）

#### Scenario: 上期无数据

- GIVEN 上期（上年同期窗口）付款或回款合计为 0
- WHEN 前端计算同比变化率
- THEN 该指标同比变化率显示为无数据（`—`），不得报除零错误

#### Scenario: 月度同比对比图

- GIVEN 前端已获得 `data.flows`
- WHEN 用户查看资金占用总览
- THEN 展示月度同比对比图：X 轴为当年 1 月至截止月，逐月对比上年同月与当月的付款、回款，提示框包含同比变化

#### Scenario: 表格同比（明细表与客户集合表格）

- GIVEN 系统完成资金占用分析，每合同已计算截至上年同期日的 FIFO 占用
- WHEN 前端渲染资金占用明细表或客户集合表格
- THEN 明细表每行展示"上年同期占用"与"同比变化率"两列，客户集合表格同样展示该两列
- AND 同比变化率按升降着色：占用上升（或上年为 0 且本期新增占用）以红色渲染，占用下降以绿色渲染，持平或双零以中性色渲染
- AND `GET /api/fund/metrics` 明细行含 `上年同期占用`；`GET /api/fund/dim/aggregate` 每行含 `prev_occupy`（该维度下各合同上年占用之和）；`GET /api/fund/dim/drill` 清单行含 `上年同期占用`

#### Scenario: 导出维度聚合数据

- GIVEN 区域维度聚合已完成
- WHEN 调用 `GET /api/fund/dim/export?dim=region`
- THEN 返回含区域聚合行的 Excel 文件

## 非功能需求

- NFR-1：FIFO 分析 SHALL 在 10 秒内完成（十万行级数据）
- NFR-2：敏感数据清洗 SHALL 在任何持久化之前完成
- NFR-3：维度聚合查询 SHALL 在 3 秒内完成（基于宽表/指标宽表预计算，前端只读）
- NFR-4：风险分级 SHALL 随分析完成即时计算并持久化，不阻塞主分析

## 测试标准

- TC-1：FIFO 冲抵计算用例（对应 FR-3），位置 `tests/test_fund.py`
- TC-2：敏感列清洗用例（对应 FR-2）
- TC-3：维度关联正确性用例（对应 FR-8），位置 `tests/test_fund_multidim.py`
- TC-4：风险分级与趋势预警用例（对应 FR-9/FR-12）
- TC-5：穿透下钻与导出用例（对应 FR-10/FR-11）
