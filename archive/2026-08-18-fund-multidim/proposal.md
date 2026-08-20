# 提案：资金占用多维度分析与预警体系

> 变更编号：`20260818-fund-multidim`
> 作者：AI 助手 | 日期：2026-08-18 | 状态：已批准

## 背景与问题

现有资金占用分析（CC-006）仅基于付款/收款明细表做 FIFO 冲抵，输出按合同粒度的指标（占用金额、元天合计、预估资金成本等）。存在以下不足：

1. **无维度切片**：未 join 总合同表/里程碑表，无法按区域、部门、业务线、客户集合等维度聚合，管理抓手缺失。
2. **无图表**：前端仅明细表 + 汇总卡片，无 ECharts 可视化，无法直观定位风险地域/条线/客户。
3. **无预警**：无风险分级、无趋势预警，资金占用风险暴露后被动应对，无法"提前预警、提前干预"。
4. **无穿透下钻**：无法从区域 → 客户集合 → 合同 → 占用片段逐级下钻定位问题。

## 目标

1. 为资金占用增加 **区域 / 项目集合（客户集合）/ 时间 / 风险** 四类分析维度，输出 10 张 ECharts 图表。
2. 建立**四级风险预警引擎**（健康/关注/预警/高危 + 趋势预警），阈值可配置。
3. 支持**穿透下钻**（区域→客户→合同→片段）与**图表/清单导出**。

## 变更范围

### In Scope

- 数据维度关联：`fund_analyze` 按合同编号 join 总合同表（区域/省/部门/业务线/行业/客户标识/合同状态/合同额/签约时间）与里程碑表（项目状态/账期/计划回款时间）。
- 敏感列策略调整：从"客户标识一律删除"改为"保留脱敏客户键 `customer_key`（确定性编码，不存真实名称）"。
- `fund_metrics` 宽表扩展：增加维度列（region/dept/biz_line/industry/customer_key/project_status/contract_status/sign_year）与新指标列（回款率、占用强度、风险等级）。
- 新增 ETL job：按 `(dim_type × 月份)` 聚合资金占用指标写入 `indicator_metrics`（复用 gross-margin 模式）。
- 新增 API：`/api/fund/dim/*`（维度聚合查询）、`/api/fund/risk/*`（预警清单/配置）、`/api/fund/export/*`（图表数据导出）。
- 前端资金占用页重构：多 Tab（总览/区域/客户集合/时间/风险预警）+ ECharts 图表 + 穿透下钻 + 导出按钮。
- 测试用例（标注 `# CC-006 FR-x`）。

### Out of Scope

- 客户名称/项目名称原文采集（维持脱敏策略，仅保留编码键）。
- 预警后的自动催收/对账动作（仅输出预警清单与干预建议）。
- 短信/邮件通知渠道。

## 接口与数据契约

### 维度聚合查询

```http
GET /api/fund/dim/aggregate?dim=region&month=2026-07&level=1
```

```json
{
  "success": true,
  "dim": "region",
  "rows": [
    {"name": "华东", "contract_count": 42, "total_pay": 120000000,
     "total_recv": 80000000, "current_occupy": 40000000,
     "recv_rate": 0.67, "occupy_intensity": 0.33, "risk_level": "warning"}
  ]
}
```

### 预警清单

```http
GET /api/fund/risk/list?level=high&dim=region&dim_value=华东
```

```json
{
  "success": true,
  "rows": [
    {"contract_no": "HT-001", "customer_key": "QDHEKJ", "region": "华东",
     "current_occupy": 5000000, "occupy_days": 210, "recv_rate": 0.2,
     "risk_level": "high", "suggestion": "立即催收并上报"}
  ]
}
```

### 风险配置

```http
GET /api/fund/risk/config        # 读取阈值
POST /api/fund/risk/config       # 更新阈值（30/90/180 天、回款率 50%、占用强度 50%、金额 100 万、环比连续 2 月）
```

## 涉及规格条目

- `CC-006`：
  - `MODIFIED` 需求「敏感列清洗」（FR-2）：保留脱敏客户键
  - `ADDED` 需求「维度关联与聚合」（FR-8）、「风险预警引擎」（FR-9）、「穿透下钻」（FR-10）、「图表与导出」（FR-11）、「趋势预警」（FR-12）
- `CC-005`（回款周期）：复用其 ETL 模式，不改其规格

## 验收标准

- [ ] `/api/fund/analyze` 执行后，`fund_metrics` 含维度列与新指标列，回款率/占用强度/风险等级计算正确
- [ ] `/api/fund/dim/aggregate` 对 region/dept/biz_line/customer_key/month 五类维度均返回正确聚合
- [ ] 风险分级：占用>180天且占用强度>50% → 高危；占用90–180天且回款率<50% → 预警；符合默认阈值
- [ ] 前端资金页含 5 个 Tab、10 张图表，可逐级下钻至合同片段明细
- [ ] 每张图表可导出 PNG，清单可导出 Excel
- [ ] `cd contract-compare && pytest -q` 全量通过

## 风险与兼容性

- **兼容性**：新增 API 均为新增路由，不破坏现有 `/api/fund/*`；`fund_metrics` 采用 ALTER TABLE 增量加列，兼容既有库。
- **敏感策略变化**：清洗规则从"删除客户标识"改为"编码化"，需同步 `sanitize_excel_file` 与测试用例 TC-2。
- **数据质量**：总合同表/里程碑表 join 不到的历史合同回退为"未归类"，维度聚合归入"未知"桶，不影响主分析。
