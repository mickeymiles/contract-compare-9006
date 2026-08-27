# 代码结构重构草案 & README 总纲

> 状态: **DRAFT（待评审）** | 版本: v0.1 | 日期: 2026-08-27
> 关联: 011 领域模型、CC-010 生命周期、采购/比对/运维（受备件询价迁移影响）
> 本文仅为结构草案，不落地代码、不动现行工程。

---

## 0. 背景与问题

项目起始只做「合同比对」，现演变为「经营业务多领域平台」（数据源 / 回款 / 毛利率 / 资金占用 / 采购 / 合同比对 / ETL / 本体 / 项目全生命周期）。但后端仍以
**单文件路由为主**：`backend/main.py`(4546 行) 承载几乎所有领域路由，仅有 `models.py / procurement_models.py / plm_models.py` 等数据文件，**未按领域/聚合分流**；前端平铺 `index/plm/procurement/gross/...`。

结论：**数据结构与代码结构一并重构**，代码包边界映射领域边界；落地可解耦，建议**代码先按结构拆分（不改变任何路由/数据语义）**，数据主数据随后迁移。

## 1. 决策记录（AD，含已确认项）

| # | 决策 | 结论 |
|---|------|------|
| AD-1 | 主数据域 | `core/`：项目(根/本体)+三号链路+子项目；合同 1:1；商机等。联系信息不属主数据，归运维 |
| AD-2 | 运维域 | **备件询价、备件主数据、供应商、联系人/收件/现场** 归 `ops/`（用户定：只有运维涉及）|
| AD-3 | 采购域 | **保留 `procurement/` 广概念**；目前仅 `contrast`(合同硬件采购对比)一个模块，预留其它采购类型 |
| AD-4 | 人力拆分 | `staffing` → `staff / assignment / timesheet` 三聚合；**人力成本归 `finance/cost`**（源数据来自 timesheet）|
| AD-5 | 基础支撑 | 预警+规则、字典、配置、操作日志归 `foundation/`（跨域横切）|
| AD-6 | 门户 | `portal/`（首页双分区/导航）**本轮暂不纳入**，想好再动 |
| AD-7 | 前端规范 | **主导航用左侧手风琴（样式统一美化）**，顶部配标准面包屑作位置指示；图标统一扁平线性（进 README 工程规范）|
| AD-8 | 前缀策略 | **沿用现有** `plm_*`/`procurement_*` 等作聚合标识，本轮不统一大改名（低成本）；新聚合按本表约定补前缀 |

## 2. 后端目标目录（领域 → 聚合，前缀为标识）

```
backend/app/
├─ main.py                # 仅 include_router（瘦身）
├─ core/                  # 主数据域
│   ├─ project/      prj_*    项目(唯一 project_no|三号链路|子项目|审计)
│   ├─ contract/     con_*    合同(Project 1:1)
│   └─ opportunity/  opp_*    商机/投标概算/售前资料
├─ domains/
│   ├─ lifecycle/
│   │   ├─ baseline/    bl_*     四算基线
│   │   ├─ pmo/milestone/ ms_*   里程碑(粗/细)
│   │   ├─ pmo/task/    tk_*     任务
│   │   └─ staffing/
│   │       ├─ staff/       hr_s_*  人员池(岗位/单价/可用工时/在职)
│   │       ├─ assignment/  hr_a_*  分配/绑定(项目/里程碑/任务三级)
│   │       └─ timesheet/   hr_t_*  工时填报
│   ├─ finance/
│   │   ├─ cost/      fin_c_*   成本归集（含人力成本自动折算+手工并存）
│   │   ├─ billing/   fin_b_*   收支台账/毛利(FR-7)
│   │   ├─ funding/   fin_f_*   资金占用
│   │   ├─ payment/   fin_p_*   回款周期
│   │   ├─ gross/     fin_g_*   毛利率
│   │   └─ report/    fin_r_*   报表导出(FR-10)
│   ├─ procurement/          # 采购域（广概念，保留）
│   │   ├─ contrast/   pu_c_*  合同硬件采购对比(基准/供应商版本/比对/报告)
│   │   └─ …(预留其它采购类型)
│   ├─ ops/                  # 运维域
│   │   ├─ sparepart/  ops_p_*   备件主数据
│   │   ├─ inquiry/    ops_q_*   备件询价/报价
│   │   ├─ supplier/   ops_s_*   供应商（仅运维侧使用）
│   │   └─ contact/    ops_c_*   项目联系人/收件人/现场地址
│   └─ foundation/            # 基础支撑域（跨域横切）
│       ├─ datasource/ fdn_d_*   数据源
│       ├─ etl/        fdn_e_*   ETL
│       ├─ ontology/   fdn_o_*   本体(已有 /api/mcp/ontology)
│       ├─ alert/      fdn_a_*   预警+规则(跨域)
│       ├─ dict/       fdn_dict_* 字典(FR-11)
│       ├─ config/     fdn_cfg_*  配置/基线开关(FR-11)
│       └─ log/        fdn_log_*  操作留痕(FR-11)
└─ shared/               # 共享基建（工程化）
    ├─ crud_engine/     元数据驱动 CRUD（PLM 已用，抽公共）
    ├─ ui/              面包屑组件、扁平 SVG 图标库、公共样式（议题2/3）
    └─ excel/           Excel 导出通用
```

> 每域统一 `routes.py(APIRouter) + models.py + service.py`；`main.py` 仅 `include_router`。
> 现有 `main.py` 各区块按注释边界拆到对应域，`plm_models.py / procurement_models.py` 的表与函数按域归位。

## 3. 前端目标目录（与后端**同名一一对应**）

> 对齐原则：前端目录名 = 后端口径名，`frontend/ops` ↔ `backend/domains/ops`，便于按域找文件、跨端跳转不迷路。

```
frontend/
├─ common/                # 手风琴导航组件、面包屑指示、扁平SVG图标库、公共样式、excel前端工具（对应 shared/ui 规范）
├─ core/                  # 主数据：项目/合同/商机 管理页（对应 backend/core）
├─ lifecycle/             # 对应 backend/domains/lifecycle（接管原 plm.html）
├─ finance/               # 对应 backend/domains/finance（gross/fund/payment 等聚合页）
├─ procurement/           # 对应 backend/domains/procurement（现 contrast 硬件比对）
├─ ops/                   # 对应 backend/domains/ops（接管原 procurement.html 备件询价 + 联系人）
├─ foundation/            # 对应 backend/domains/foundation（数据源/ETL/本体/字典/配置/日志/预警）
└─ portal/                # 工作台/首页（AD-6：暂缓，待定后再动）
```
- 每个域目录放该域的 `html + app.js`（+ 需要的子目录），与后端 `domains/<域>` 目录层级一致。
- **对应关系集中登记**：在 `README` + 一份 `routes 映射表` 中列出「后端域 ↔ 前端目录 ↔ 入口 URL」，找对应关系直接查表，而非散落各文件。

### 3.1 工作台（portal/首页）变化的说明

前后端目录对齐后，**工作台需要改一次**——但做成"配置驱动"，而非逐页手改：
- 首页双分区（CC-009 经营管理/运维管理）与各入口卡片，改为**读取统一导航配置**（域名 → 目录 → 入口 URL → 面包屑路径 → 图标 → 手风琴菜单项），工作台遍历渲染。
- **左侧主导航用手风琴**（域→聚合→叶子层级，样式统一美化）；**顶部面包屑**从同一份配置生成位置路径（如 `经营业务 › 运维 › 备件询价`），保证导航与目录、域名三方一致。
- 新增/调整域时**只改配置**，不散改各页面；portal 一次性重构即完成，其后稳定。

> 结论：对齐后端做一次前端目录重排，工作台随之调整为"配置驱动的手风琴主导航 + 面包屑指示"的一次性改造（可归入 R4 前端统一 + portal 定稿后）。

### 3.2 首页卡片粒度：从「功能级」改为「领域级」

现状首页是**功能级卡片**（回款周期、毛利率、资金占用、合同比对、备件询价、生命周期…各自一张）。按领域模型这套**不再合适**，首页应改为**领域级入口**：

- 每张卡片/区块 = 一个**领域**（core/lifecycle/finance/procurement/ops/foundation），卡片上是该域的名称、描述、入口 URL、快捷指标。
- **同域功能收进该域页**，靠域内导航进入，首页不再为每个功能单列卡片。
  - 例：回款周期、毛利率、资金占用等一律归入「财经」一张卡，域内再进 payment/gross/funding。
  - 例：备件询价、备件、联系人等归入「运维」一张卡。
- **域内导航形态**：**左侧主导航用手风琴**（域→聚合→叶子，折叠/展开、扁平样式、active 高亮、折叠记忆）；**顶部面包屑作位置指示**。聚合内部更深的层级（如里程碑→任务）用手风琴子级展开或页内 Tab 承载。
- 卡片与**统一导航配置**同源——首页卡片列表、左侧手风琴、顶部面包屑都用同一份 `领域导航配置` 渲染，保证首页/目录/入口三方一致。

> 由此 portal 需要按「领域粒度」重做一次首页（含双分区 CC-009、美化后的手风琴主导航 + 面包屑）；此即 AD-6 待定后纳入 R4 的一次性改造。

### 3.3 统一导航配置：域 → 聚合（两层），手风琴/卡片/面包屑同源

手风琴顶层 = **域**，展开 = **聚合**，与首页领域卡片**同一套层级**。导航由一份配置驱动，三处同源渲染：

```json
{
  "domains": [
    { "key": "lifecycle", "label": "生命周期", "icon": "ico-lifecycle",
      "route": "/lifecycle", "order": 1,
      "items": [
        { "key": "baseline",  "label": "四算基线",  "route": "/lifecycle/baseline" },
        { "key": "pmo",       "label": "PMO 进度",  "route": "/lifecycle/pmo", "children": [
            { "key": "milestone", "label": "里程碑", "route": "/lifecycle/pmo/milestone" },
            { "key": "task",      "label": "任务",   "route": "/lifecycle/pmo/task" } ] },
        { "key": "staffing",  "label": "人力与工时","route": "/lifecycle/staffing",
          "children": [
            { "key": "staff", "label": "人员池",  "route": "/lifecycle/staffing/staff" },
            { "key": "assign","label": "分配",    "route": "/lifecycle/staffing/assign" },
            { "key": "timesheet","label":"工时","route":"/lifecycle/staffing/timesheet" } ] }
      ] },
    { "key": "finance", "label": "财经", "icon": "ico-finance", "route": "/finance", "order": 2,
      "items": [
        { "key": "payment", "label": "回款周期", "route": "/finance/payment" },
        { "key": "gross",   "label": "毛利率",   "route": "/finance/gross" },
        { "key": "funding", "label": "资金占用", "route": "/finance/funding" },
        { "key": "billing", "label": "收支台账", "route": "/finance/billing" },
        { "key": "cost",    "label": "成本归集", "route": "/finance/cost" } ] },
    { "key": "ops", "label": "运维", "icon": "ico-ops", "route": "/ops", "order": 3,
      "items": [
        { "key": "inquiry",   "label": "备件询价", "route": "/ops/inquiry" },
        { "key": "sparepart", "label": "备件",     "route": "/ops/sparepart" },
        { "key": "supplier",  "label": "供应商",   "route": "/ops/supplier" },
        { "key": "contact",   "label": "联系人",   "route": "/ops/contact" } ] }
    // procurement / core / foundation 同理
  ]
}
```

消费方式：
- **首页领域卡片**：`domains[]`（一级域）直接渲染为卡片。
- **左侧手风琴**：同一份 `domains[]` 递归渲染域→聚合→(children)。
- **顶部面包屑**：由当前 `route` 反查配置得到路径序列（如 `/ops/inquiry` → `经营业务 › 运维 › 备件询价`）。
- 层级规范：**顶层=域、二层=聚合**；聚合内如需再分用 `children`（仅两到三级），更深一律进页内 Tab。

### 3.4 前端 UI 规范（手风琴 / 面包屑 / 扁平图标 —— 工程宪章）

> 本节即议题2/3固化成果，进入 README「工程规范」作为**全局强制遵守**；现存页面统一按此改造，新增功能一律遵守。

#### 3.4.1 页面布局骨架
```
┌─页头区──────────────────────────────┐
│ [面包屑 经营业务 › 运维 › 备件询价]     │
├─┬─────────────────────────────────┤
│手│                                 │
│风│           内容区                 │
│琴│                                 │
│ │  （按聚合做页内 Tab/分区）          │
├─┴─────────────────────────────────┤
```
左列=主导航(手风琴，固定/可折叠)，顶部=面包屑(位置指示)，右侧=内容区。

#### 3.4.2 手风琴样式规范（主导航）
- **扁平化**：无重阴影，用 1px 弱色分隔线（`rgba(…,.06)`）；背景纯色分层（域级底色 < 聚合级）。
- **层级**：一级=域（分组标题，小字/大写标题），二级=聚合（可点击叶子或可再展开），`children` 再缩进一级。
- **间距/尺寸**：域分组 padding 16/8；子项行高 ≤38、缩进 18/层级；字号 13/12。
- **态**：
  - `hover`：淡背景 + 主色字
  - `active`（当前项）：左竖条 3px 主色 + 淡主色背景 + 主色字 + 加粗
  - **折叠记忆**：展开态存 localStorage（键=`nav.expanded`），或 URL 携带路由反解，刷新不丢。
  - 折叠箭头只用线性图标（`chevron-down/right`），旋转过渡。
- **图标**：全部用扁平线性 icon，域级可带 icon，聚合叶子可不带或带语义小图标；**禁止彩色 emoji**。
- 长文本省略 `text-overflow:ellipsis` + `title`。

#### 3.4.3 面包屑（位置指示）
- 层级用 `›` 分隔；首级=`经营业务`；当前级加粗主色。
- 最多展示 2~3 级，过长中间省略（`/…/`），末级可 `title` 完整。
- 由统一导航配置 `route` 反查生成（见 3.3），不硬编码。

#### 3.4.4 扁平线性图标库（议题3 宪章）
- **风格**：线性 `stroke`，线宽 1.5px（小尺寸 1.25px），端点圆角；统一 `viewBox="0 0 24 24"`、≥16/20/24 三档 `width/height`。
- **语义色淡 icon**：成功/警告/危险用**线性图标 + 语义色**（如 `circle-check`+绿、`triangle-warning`+黄、`circle-x`+红），**不靠彩色 emoji** 表达状态。
- **封装**：`frontend/common` 提供 `Icon` 组件/`icon` CSS class + 名表（`ico-{name}`）；导航配置的 `icon` 字段引用名表。
- **约束（强制）**：新增/改造功能一律引用图标库；禁止新增 emoji/写实/贴图图标。
- **落地任务**：建图标库 → 全局替换现存 emoji（面包屑、手风琴、表格操作按钮、门户卡片、状态徽标）→ 纳入 R4。

## 4. README 总纲建议

README 从「合同比对」改写为「**经营业务多领域平台**」总纲，建议章节：
1. **定位**：以项目为主数据的经营业务平台（商机→合同→项目 + 各业务域 + 运维域）
2. **领域导航**：主数据 / 生命周期 / 财经 / 采购 / 运维 / 基础支撑，各域入口与职责
3. **目录结构**：`backend/app/{core,domains/{…},shared}` + `frontend/{common,…}`
4. **工程规范**：标准面包屑导航；扁平线性图标库；统一字典/数据契约；升级/新增必须遵守
5. **部署**：CI（lint→test→SSH 自动部署 9006/9007）+ `scripts/remote_deploy.sh`
6. **规格索引**：`specs/*` 目录导航（011 领域模型、012 结构、010 生命周期…）

## 5. 迁移路线（大工程，谨慎）

| 期 | 内容 | 交付 |
|----|------|------|
| R1 | 结构文档定稿（本文档评审）| 目录 + README 总纲 + 路由搬迁清单 |
| R2 | **代码按域拆分** main.py（不改行为）| 各域 routes/models/service；主数据日后落 core |
| R3 | 数据主数据落地 | 项目为根 + Ops 关联 + 各表 project_id 挂接（联动 011）|
| R4 | 前端统一 | 面包屑 + 扁平图标 + common 收敛 |
| R5 | 收尾 | 废弃旧表/旧入口，前缀统一评估（见 AD-8）|

> 每一步保持现有功能可用、可灰度；portal 按 AD-6 待议后纳入。

## 6. 风险与开放问题

- **底层契约冻结**：R2 只搬不改路由/字段，需保证 API 路径不变，避免前端/智能体破坏。
- **备件询价迁移影响**：`procurement_*` 中备件询价迁至 `ops/inquiry`，涉及前端 procurement 页与邮件链路，需单独评估。
- **供应商归属**：归 `ops/supplier` 仅为当前"备件询价"使用；若未来采购域也需供应商，需调整为共享。
- **本体与智能体**：`foundation/ontology`(既有) 作为领域模型/契约的承载，与 011 课题衔接。

## 下一步
1. 评审本目录结构（尤其 procurement 广概念、ops 收备件+供应商、人力三拆、人力成本入 finance）。
2. 通过后进入 R1：产出 README 总纲正文 + 路由搬迁清单（现 main.py 各区块 → 目标域）。
3. 议题2/3（面包屑、扁平图标）随前端 common/ 一并纳入 R4。

---

## 附录 A：路由搬迁清单（`main.py` → 目标域）

> 依据 `backend/main.py` 实际 `@app.*` 路由（162 条，行号供定位）。仅映射、不变更 Path。
> 缩略：`{id}`=/{id}，`c`=对比/`pu`=采购；"→"后为目标域模块。

### A.0 主数据域 `core/`

| 现状路由 | 目标模块 | 说明 |
|----------|----------|------|
| `/api/plm/opportunities`(+`/{opp_id}`|`/follow`|`/estimate`|`/docs`) 4153-4209、`/presale-docs/{doc_id}` 4209、`/opportunities/convert` 4215 | `core/opportunity` | 商机/投标概算/售前资料 |
| `/api/plm/contracts`(+`/{contract_id}`) 4221-4244 | `core/contract` | 合同（项目 1:1） |
| `/api/plm/projects`(+`/{project_id}`) 4250-4276、`/projects/{id}/panorama` 4278、`/progress` 4286 | `core/project` | 项目主数据/三号链路 |

### A.1 生命周期域 `lifecycle/`

| 现状路由 | 目标模块 | 说明 |
|----------|----------|------|
| `/api/plm/projects/{id}/baselines` 4297/4302/4307、`/baselines/{bid}`(+confirm/lock/`/delete`) 4316-4341 | `lifecycle/baseline` | 四算基线 |
| `/api/plm/projects/{id}/milestones` 4347/4352、`/milestones/{mid}` 4359/4364 | `lifecycle/pmo/milestone` | 里程碑 |
| `/api/plm/projects/{id}/tasks` 4369/4374、`/tasks/{tid}` 4379-4392 | `lifecycle/pmo/task` | 任务 |
| `/api/plm/staff`(+`/load`|`/{sid}`) 4398-4427 | `lifecycle/staffing/staff` | 人员池 |
| `/api/plm/assignments`(+`/{aid}`) 4432-4448 | `lifecycle/staffing/assignment` | 三级分配 |
| `/api/plm/timesheets`(+`/{tid}`|`/sync`) 4453-4473 | `lifecycle/staffing/timesheet` | 工时填报 |
| `/api/plm/overview` 4109 | `lifecycle`(或 `portal`,待议) | 项目全景/驾驶舱 |

### A.2 财经域 `finance/`

| 现状路由 | 目标模块 | 说明 |
|----------|----------|------|
| `/api/analysis/payment-cycle`(+`/export`) 246/525、`/api/payment-cycle/metrics` 3755 | `finance/payment` | 回款周期 |
| `/api/fund/*`（status/upload/analyze/metrics/segments/dim/risk/export 等）1839-3183 | `finance/funding` | 资金占用/风险 |
| `/api/gross/metrics` 3448 | `finance/gross` | 毛利率 |
| `/api/plm/ledger`(+`/{lid}`) 4480-4496 | `finance/billing` | 收支台账（含人力成本归集消费） |
| `/api/plm/export/{report}` 4529 | `finance/report` | 报表导出 |

### A.3 采购域 `procurement/`（广概念，现仅 `contrast`）

| 现状路由 | 目标模块 | 说明 |
|----------|----------|------|
| `/api/contracts`(+`/{id}`) 1389-1442 | `procurement/contrast` | 合同基础（硬件比对） |
| `/api/contract/{id}/upload|items` 1452/1473 | `procurement/contrast` | 合同基准/明细 |
| `/api/contract/{id}/supplier/*` 1492-1551 | `procurement/contrast` | 供应商版本 |
| `/api/contract/{id}/compare/run|results` 1592/1602、`/api/compare/{result_id}/confirm` 1721 | `procurement/contrast` | 比对引擎 |
| `/api/contract/{id}/column-mapping` 1665/1684 | `procurement/contrast` | 列映射 |
| `/api/contract/{id}/stats|export/report` 1775/1822 | `procurement/contrast` | 统计/报告 |

### A.4 运维域 `ops/`（备件询价链路迁移，AD-2）

| 现状路由 | 目标模块 | 说明 |
|----------|----------|------|
| `/api/procurement/tasks`(+`/{task_id}`|`/select`|`/test`|`/cancel`|`/logs`|`/quote/manual`|`/agent`) 989-1109 | `ops/inquiry` | 备件询价任务/报价 |
| `/api/procurement/ledger` 1128 | `ops/inquiry` | 询价台账 |
| `/api/procurement/suppliers`(+`/{id}`) 1157-1193 | `ops/supplier` | 供应商（仅运维侧） |
| `/api/procurement/contracts`(+`/{id}`) 1226-1272 | `ops`(询价关联合同/收件) | 备件询价用合同（收件/地址亦归 ops/contact）|
| `/api/procurement/mail-cc`(+`/{id}`|`/emails`) 1290-1310 | `ops/inquiry` | 邮件抄送 |
| `/api/procurement/spare-parts`(+`/{id}`|`/categories`) 1321-1378 | `ops/sparepart` | 备件主数据 |
| `/procurement` 978、`/procurement.app.js` 983 | `ops` 前端入口 | 备件询价页 |

### A.5 基础支撑域 `foundation/`

| 现状路由 | 目标模块 | 说明 |
|----------|----------|------|
| `/api/datasource/*` 127-220 | `foundation/datasource` | 数据源 |
| `/api/etl/*` 3797-3879 | `foundation/etl` | ETL |
| `/api/mcp/ontology/*` 3906-3940 | `foundation/ontology` | 本体 |
| `/api/plm/dict`(+`/{dict_id}`) 4114-4126 | `foundation/dict` | 字典 |
| `/api/plm/config` 4131/4136 | `foundation/config` | 配置/基线开关 |
| `/api/plm/logs` 4146 | `foundation/log` | 操作留痕 |
| `/api/plm/alert-rules`(+`/{rule_key}`) 4502/4507、`/alerts`(+`/scan`|`/{id}/handle`) 4512-4523 | `foundation/alert` | 预警+规则（跨域）|

### A.6 门户/静态入口（AD-6：暂缓）

| 现状路由 | 目标模块 | 说明 |
|----------|----------|------|
| `/` 889、`/common.css` 894、`/china.json` 903、`/gross` 899、`/plm` 4098、`/plm.app.js` 4103、`/api/stats` 1808 | `portal`（暂缓） | 门户/首页/双分区/静态 |