# 提案：新增「项目全生命周期管理」大模块（CC-010）

> 变更编号：`2026-08-27-project-lifecycle`
> 作者：AI 编程助手 | 日期：2026-08-27 | 状态：已实现并归档（delta 已合并至 `specs/010-project-lifecycle/spec.md`）
> 需求来源：《项目全生命周期全景管控系统-产品架构规格文档（V1.0 可迭代版）》

## 背景与问题

现系统（CC-001 ~ CC-008）覆盖的是**合同视角的存量经营分析**：合同比对、回款周期、资金占用、签单毛利率。它们回答的是「钱回没回来、赚了多少」，但回答不了「**某个项目现在健康吗**」——因为缺少把售前概算、立项预算、PMO 进度、人员工时、实际成本串成一条链的项目维度管控载体。

用户已提供顶层骨架规格文档，要求以「四算为纲、财经为尺、PMO 为缰、人力为本」为纲领，在项目维度上建立售前 → 立项 → 执行 → 成本 → 预警的完整闭环，并提供单项目全景视图。

## 目标

1. 建立项目维度的**四算基线体系**（概算 / 预算落地，核算 / 决算预留字段与入口），实现「预算对标概算」的前置展示与可选强约束。
2. 实现 **PMO 双维度进度管控**：按期进度（里程碑/任务完成率、延期节点）+ 按预算进度（消耗占比、剩余预算、超支风险节点）。
3. 打通**人力 → 成本 → 毛利**归集链路：工时填报自动折算实际人力成本，实时算出预估毛利与实际毛利差异。
4. 交付**单项目全景视图**，严格按文档模块六的 7 个固定板块布局。
5. 建立**多维预警**（成本超耗 / 毛利偏低 / 进度延期 / 人员过载）+ 预警中心 + 待处理→处理中→已闭环的处置留痕。

## 变更范围

### In Scope

- **模块一 商机与售前投标管理**：商机档案 CRUD、投标概算（含分项明细）、售前资料归档（元数据 + 附件上传）、中标一键联动立项、商机状态流转与跟进记录。
- **模块二 合同与项目立项管理**：合同主数据 CRUD、概算基线自动带入 + 人工确认锁定、项目立项（编号 / 负责人 / 部门 / 状态）、立项级粗里程碑、商机-合同-项目三级溯源。
- **模块三 PMO 项目执行管控**：执行预算（总额 + 分项人力/其他）、粗里程碑拆解为细里程碑、任务拆解（负责人 / 计划工时 / 交付物）、双维度进度监控、进度变更与预算调整日志。
- **模块四 人力资源池管理**：人员池档案（岗位 / 成本单价 / 可用工时）、人员→项目/里程碑/任务三级绑定、负荷看板（过载 / 正常 / 闲置）、工时填报与自动归集、人效元效字段预留。
- **模块五 成本与财务管控**：收入归集（签单 / 变更）、全维度成本（预估 / 实际 / 累计）、毛利四指标（签单毛利、预估毛利、实际毛利、毛利率）、概算-预算-实际三线差异对比、核算/决算预留入口。
- **模块六 项目全景视图**：7 个固定板块聚合 + 快捷跳转。
- **模块七 风险预警管控**：阈值规则可配置、四类自动预警、预警中心筛选、闭环处置留痕。
- **模块八 报表与导出（最小可用）**：5 类标准化 Excel 报表（单项目全景 / 多项目概算-预算对比 / PMO 进度 / 人力工时负荷 / 成本毛利经营）。
- **模块九 系统配置（最小可用）**：状态与分类字典维护、预警阈值配置、四算逐级约束开关（默认关闭）、操作日志留存。**不做登录与角色鉴权**。
- 门户经营管理区新增该模块入口（依赖 CC-009）。
- 模块内导航采用**左侧菜单树**（10 个一级节点 + 14 个二级叶子），不使用页面内 Tab 条（见 FR-12）。

### Out of Scope

- 核算、决算的计算与校验逻辑（仅占位字段与录入入口，文档 1.3 明确本期预留）。
- 四算基线逐级强制拦截（默认关闭，仅通过配置开关可选开启概览级校验）。
- 人效 / 元效精准算法（仅沉淀原始数据源字段）。
- 预警自动处置、风险复盘机制、趋势预测与智能分析。
- 登录鉴权、角色数据隔离（系统当前无鉴权体系，本期不引入）。
- 与 `datasource` 上传表（总合同表 / 项目里程碑表）的 ETL 打通 —— 本期全部**手工录入**，数据源接入留待下一变更。
- 跨模块改造：不改动 CC-001 ~ CC-008 的任何接口、表结构与页面逻辑。

## 接口与数据契约

新增页面：`/plm`（左侧菜单树导航 + 右侧内容区，独立整页，与 `/gross`、`/procurement` 同构）。

新增接口族 `/api/plm/*`（统一响应 `{"success": true, "data": ...}` / `{"success": false, "error": "..."}`）：

| 分组 | 接口 |
|------|------|
| 商机 | `GET/POST /api/plm/opportunities`、`GET/PUT/DELETE /api/plm/opportunities/{id}`、`POST .../follow`、`GET/POST .../estimate`、`POST .../docs`、`GET/DELETE .../docs/{doc_id}` |
| 联动立项 | `POST /api/plm/opportunities/{id}/convert` |
| 合同 | `GET/POST /api/plm/contracts`、`GET/PUT/DELETE /api/plm/contracts/{id}` |
| 项目 | `GET/POST /api/plm/projects`、`GET/PUT/DELETE /api/plm/projects/{id}` |
| 四算基线 | `GET/POST /api/plm/projects/{id}/baselines`、`GET/PUT/DELETE /api/plm/baselines/{id}`、`POST /api/plm/baselines/{id}/lock` |
| 里程碑/任务 | `GET/POST /api/plm/projects/{id}/milestones`、`GET/PUT/DELETE /api/plm/milestones/{id}`、`GET/POST /api/plm/milestones/{id}/tasks`、`GET/PUT/DELETE /api/plm/tasks/{id}` |
| 进度 | `GET /api/plm/projects/{id}/progress` |
| 人力 | `GET/POST /api/plm/staff`、`GET/PUT/DELETE /api/plm/staff/{id}`、`GET /api/plm/staff/load`、`GET/POST /api/plm/assignments`、`PUT/DELETE /api/plm/assignments/{id}`、`GET/POST /api/plm/timesheets`、`PUT/DELETE /api/plm/timesheets/{id}` |
| 成本毛利 | `GET/POST /api/plm/ledger`、`PUT/DELETE /api/plm/ledger/{id}`、`GET /api/plm/projects/{id}/finance` |
| 全景/总览 | `GET /api/plm/projects/{id}/panorama`、`GET /api/plm/overview` |
| 预警 | `GET/PUT /api/plm/alert-rules`、`POST /api/plm/alerts/scan`、`GET /api/plm/alerts`、`PUT /api/plm/alerts/{id}/handle` |
| 配置/日志 | `GET/POST/DELETE /api/plm/dict`、`GET/PUT /api/plm/config`、`GET /api/plm/logs` |
| 报表 | `GET /api/plm/export/{report}`（`panorama`/`project_compare`/`schedule`/`labor`/`cost`） |

核心响应示例 —— `GET /api/plm/projects/{id}/progress`：

```json
{
  "success": true,
  "data": {
    "schedule": {
      "milestone_total": 8, "milestone_done": 5, "milestone_overdue": 1,
      "on_time_rate": 0.8, "progress_rate": 0.625,
      "task_total": 24, "task_done": 14, "task_overdue": 3,
      "overdue_nodes": [{"type": "milestone", "name": "初验", "plan_end": "2026-08-10", "overdue_days": 17}]
    },
    "budget": {
      "estimate_total": 1200000.0, "budget_total": 1150000.0,
      "actual_cum": 610000.0, "budget_usage_rate": 0.53,
      "remaining": 540000.0, "over_budget_nodes": [],
      "estimate_vs_budget_diff": -50000.0, "time_vs_cost_gap": -0.095
    }
  }
}
```

`GET /api/plm/projects/{id}/panorama` 固定返回 7 个板块键：`base_info`、`baseline_area`、`pmo_area`、`hr_area`、`finance_area`、`alert_area`、`quick_links`（板块内字段缺失时返回空集合而非报错）。

关键业务规则：

1. **概算来源优先级**：项目概算基线 = 中标商机投标概算自动带入（`source_baseline_id` 溯源）→ 人工确认调整 → `status='已锁定'` 后作为顶层基线，锁定后金额变更须写操作日志。
2. **预算 vs 概算**：`budget_total > estimate_total` 时，默认仅在响应与页面标注「超出概算」；当 `plm_config.baseline_constraint='on'` 时返回 `success:false` 拒绝保存（文档 3.2 预留能力，本期实现开关）。
3. **实际人力成本折算**：`actual_amount = Σ(timesheet.hours) / 8 × staff.cost_rate`（人天单价口径），随工时填报自动重算，与手工台账中 `kind='cost' AND category='人力成本' AND source='手工录入'` 的记录并存不覆盖。
4. **预警去重与闭环**：同项目同规则在未闭环状态下只保留一条；再次扫描只更新数值与等级，不回退已人工置为「处理中 / 已闭环」的状态。
5. **删除保护**：删除商机/合同/项目前若存在下游引用（合同→项目、项目→里程碑/台账/预警），返回引用计数并拒绝级联删除。
6. **名称字段口径**：项目 / 客户名称来自手工录入，允许真实名称；本期不接入数据源 ETL，故不触发既有脱敏管道。若后续接入，ETL 带入的名称字段必须走 `name_abbr_mapping.json` 脱敏。

## 涉及规格条目

- `ADDED` `CC-010` 项目全生命周期管理（FR-1 ~ FR-9，覆盖文档模块一 ~ 模块九）
- 不影响 CC-001 ~ CC-009 既有需求

## 验收标准

- [ ] `/plm` 可访问，左侧菜单树 10 个一级节点 + 14 个二级叶子均可切换且同时只有一个分区可见；空库状态下每个模块显示引导占位而非报错。
- [ ] 新建商机并录入投标概算（含 ≥1 条分项）→ 概算总额、预估毛利、毛利率自动计算正确。
- [ ] 商机关联新建合同 → 项目立项 → 锁定概算基线，三级数据可互相溯源，全景视图基础信息区正确显示。
- [ ] 录入执行预算（人力 / 其他分项）→ 四算基线区展示概算 / 预算 / 【预留：核算 / 决算】三列对比与差异。
- [ ] 预算总额大于概算时：默认提示不拦截；配置开关置 `on` 后保存被拒绝（`success:false`）。
- [ ] 拆解细里程碑与任务，计划/实际日期与完成百分比重算后按期进度、按预算进度指标与手工算例一致。
- [ ] 人员池录入 → 绑定到任务 → 填报工时 → 项目实际人力成本自动归集，人员负荷状态（过载 / 正常 / 闲置）计算正确。
- [ ] 触发四类预警中至少三类，预警中心可按项目 / 类型 / 状态筛选，处置后状态流转到「已闭环」并留存处置记录。
- [ ] 全景视图 7 板块全部有内容，快捷操作区可跳转到商机 / 合同 / 任务 / 工时 / 报表。
- [ ] 5 类报表导出均返回可打开的 `.xlsx`，且导出内容与页面展示数值一致。
- [ ] 所有新增 / 修改 / 锁定 / 处置操作在操作日志中可查（含操作对象、动作、变更前后值）。
- [ ] 核算、决算字段与录入入口存在但计算逻辑不启用（返回 `null` / 空值 + 「预留」标注）。
- [ ] `python -m pytest -q` 通过，且既有 57 passed 不回归。

## 风险与兼容性

- **风险 1 · 规模**：16 张表 + 60+ 接口 + 9 子模块前端，单次交付体量大。缓解：前端采用**元数据驱动 CRUD 引擎**（列表 / 表单 / 删除由模块配置声明生成），仅全景视图、双进度、预警中心写专属逻辑；后端按「表 → CRUD → 聚合 → 路由」四层顺序推进，每层跑一次回归。
- **风险 2 · 符号污染**：`main.py` 已存在 `from procurement_models import create_contract, delete_contract` **覆盖**了 `models.py` 的同名函数（并因此出现 `import contract_models` 兜底的临时补丁）。缓解：CC-010 一律用 `import plm_models as plm` 命名空间方式引用，函数全部以业务实体命名（`plm.create_project` 等），绝不进入 `main.py` 全局命名空间。
- **风险 3 · 空库验证**：`*.db` 与 `*.xlsx` 均在 `.gitignore` 内，本地无现网数据。缓解：测试用自建夹具数据断言计算逻辑；页面空态必须通过验收。
- **风险 4 · 工时口径**：人天单价 × 小时折算依赖 `cost_rate` 与 `available_hours` 的单位口径一致。缓解：字典中固化单位为「元/人天」「小时/月」，录入表单标注单位并在保存时做数值合法性校验。
- **兼容性**：全部新表以 `plm_` 前缀落在同一个 `contract_compare.db`，不改动既有表；`startup()` 追加 `plm.init_plm_db()` 幂等建表；`/api/plm/*` 与既有路由无路径重叠。
- **回滚**：删除 `/api/plm/*` 路由块与 `plm_models.py`、`frontend/plm*`，`DROP TABLE plm_*` 即可完全撤除，对既有模块零影响。
