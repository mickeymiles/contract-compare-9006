# 资金占用分析 Specification（delta 增量）

> 变更编号：`20260818-fund-multidim` | 类型：delta | 目标主规格：`specs/006-fund-analysis/spec.md`

> 本文件描述**相对主规格的差异**，归档时按三节合并进主规格：
> - `## ADDED Requirements` → 追加
> - `## MODIFIED Requirements` → 替换同名 Requirement
> - `## REMOVED Requirements` → 删除

## ADDED Requirements

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

#### Scenario: 导出维度聚合数据

- GIVEN 区域维度聚合已完成
- WHEN 调用 `GET /api/fund/dim/export?dim=region`
- THEN 返回含区域聚合行的 Excel 文件

## MODIFIED Requirements

### Requirement: 敏感列清洗

系统 SHALL 在上传时删除客户名称、客户简称、项目名称等敏感列，仅保留分析所需的金额、日期、合同标识与脱敏客户键字段。

#### Scenario: 清洗敏感信息

- GIVEN 上传文件含 `客户名称`、`项目名称` 列
- WHEN 解析上传
- THEN 数据中不包含客户名称/项目名称原文，但保留脱敏客户键编码

## 非功能需求（delta）

- NFR-3：维度聚合查询 SHALL 在 3 秒内完成（基于宽表/指标宽表预计算，前端只读）
- NFR-4：风险分级 SHALL 随分析完成即时计算并持久化，不阻塞主分析

## 测试标准（delta）

- TC-3：维度关联正确性用例（对应 FR-8），位置 `tests/test_fund_multidim.py`
- TC-4：风险分级与趋势预警用例（对应 FR-9/FR-12）
- TC-5：穿透下钻与导出用例（对应 FR-10/FR-11）
