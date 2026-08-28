# 经营业务多领域平台（contract-compare）

以**项目为主数据**的经营管理与运维一体平台。覆盖「商机 → 合同 → 项目」业务主链路，以及围绕项目的生命周期（四算基线 / PMO / 人力）、财经（回款 / 毛利 / 资金占用）、采购（合同硬件对比）、运维（备件询价 / 联系人）等业务域，支持智能体通过统一数据契约接入。

- 后端：FastAPI + SQLite
- 前端：原生 HTML/JS/CSS（手风琴主导航 + 面包屑 + 扁平图标）
- 部署：CI（lint→test→SSH 自动部署）→ `:9006`

---

## 领域导航（功能地图）

| 域 | 入口 | 聚合/功能 |
|----|------|-----------|
| **主数据** `core/` | `/core` | 项目(根/三号链路)、合同、商机/投标概算/售前资料 |
| **生命周期** `lifecycle/` | `/lifecycle` | 四算基线；PMO(里程碑/任务)；人力(人员池/分配/工时) |
| **财经** `finance/` | `/finance` | 回款周期、毛利率、资金占用、收支台账、成本归集、报表 |
| **采购** `procurement/` | `/procurement` | 合同硬件采购对比（基准/供应商版本/比对/报告）|
| **运维** `ops/` | `/ops` | 备件询价、备件、供应商、联系人/收件/现场 |
| **基础支撑** `foundation/` | `/foundation` | 数据源、ETL、本体、字典、配置、日志、预警 |

> 导航由统一导航配置驱动：首页=领域卡片、左=手风琴、顶=面包屑，三方同源（见 `specs/012`）。

---

## 快速开始

```bash
# 新环境一键初始化（建库 + 导入脱敏种子数据）
./bootstrap.sh

# 启动服务（默认端口 9006，可用环境变量 CC_PORT 覆盖）
python backend/main.py
# 或
CC_PORT=9007 python backend/main.py
```

启动后访问：`http://localhost:9006`

## 目录结构（改造目标）

```
contract-compare/
├── backend/app/
│   ├── main.py            # 仅 include_router（瘦身）
│   ├── core/              # 主数据域：project / contract / opportunity
│   ├── domains/           # 业务域
│   │   ├── lifecycle/     #   baseline / pmo(milestone,task) / staffing(staff,assignment,timesheet)
│   │   ├── finance/       #   cost / billing / funding / payment / gross / report
│   │   ├── procurement/   #   contrast（合同硬件对比；预留其它采购类型）
│   │   ├── ops/           #   sparepart / inquiry / supplier / contact
│   │   └── foundation/    #   datasource / etl / ontology / alert / dict / config / log
│   └── shared/            # crud_engine / ui / excel
├── frontend/
│   ├── common/            # 手风琴导航组件、面包屑、扁平图标库、公共样式
│   ├── core/ lifecycle/ finance/ procurement/ ops/ foundation/ portal/
├── specs/                 # 领域/结构规格（011 领域模型、012 代码结构…）
├── scripts/               # export_seed / import_seed / remote_deploy.sh
├── seeds/ datasource/ name_abbr_mapping.json
└── bootstrap.sh
```

> 迁移尚在进行（对应 `specs/012` R1~R5）。当前 `backend/main.py` 仍集中大量路由，将按域拆分。

---

## 工程规范（宪章 — 全局强制遵守）

见 `specs/012 §3.4`：
- **导航**：左侧**手风琴主导航**（域→聚合→叶子，扁平化/active 高亮/折叠记忆）；顶部**面包屑**作位置指示（`经营业务 › 运维 › 备件询价`）。
- **图标**：统一**扁平线性 SVG 图标库**（stroke 1.5px / viewBox 24 / 语义色表达状态）；**禁止新增 emoji/写实图标**。
- **数据契约**：各业务域间仅通过 `project_id` 传递，不再散传 `contract_no` 字符串；枚举走统一字典。
- **主数据**：以项目为主数据；**收件人/联系方式/地址等联系信息归运维域**，不属主数据字段。
- **成本/预算口径**：主数据中「预估成本即预算」（硬件预估成本 `hardware_est`、服务预估成本 `service_est`；**软件预估实施费字段不使用**）。
  - **概算** = 项目整体概算，含软硬件（`hardware_est + service_est`），`plm_baseline` 概算作回退。
  - **预算** = **服务预估成本 `service_est`**（即软件/服务预估成本=软件自主预估成本）。`plm_baseline` 预算作后续细化来源。

新增功能必须遵守以上规范；现存页面按此统一改造。

---

## 数据链路与脱敏

```
原始 xlsx（服务器） → datasource → ETL → SQLite 宽表 → 分析页面
                    ↓ 脱敏
           seeds/seed_data.sql（git 发布）
                    ↓ import_seed.py（幂等）
           新环境 SQLite 宽表
```

脱敏策略（**名称替换 + 数值保留**）：

| 字段 | 处理方式 |
|---|---|
| 客户名称 / 甲方 | 拼音缩写（如 `东软集团` → `DRJT`），映射见 `name_abbr_mapping.json` |
| 人员名称 | 姓 + 叉叉（如 `袁善鹏` → `袁叉叉`） |
| 项目名称 | 映射表子串替换 + 补充词典 |
| 金额 / 日期 / 周期 | **数值原样保留**，分析结果与现网一致 |

```bash
python3 scripts/export_seed.py   # 生成 seeds/seed_data.sql + seed_meta.json
python3 scripts/import_seed.py   # 导入到数据库（幂等）
```

---

## 测试

```bash
python -m pytest tests/ -v
```

## CI / 部署（9006）

- `.github/workflows/ci.yml`：push main → `lint`（ruff+pytest）通过 → `deploy`（SSH rsync + `scripts/remote_deploy.sh` 重启）
- 依赖：Actions Secrets `DEPLOY_SSH_KEY / DEPLOY_HOST / DEPLOY_USER / DEPLOY_PATH`
- 生产地址：`http://122.51.98.98:9006`

## 规格索引（specs/）

- `011-operations-domain-model`：经营业务领域模型（项目为主数据、三号链路、运维域）
- `012-code-structure-refactor`：代码结构重构、前后端目录对齐、UI/图标规范、路由搬迁清单
- `010-project-lifecycle`：项目全生命周期（四算/PMO/人力/财经/预警/报表）
- `008-gross-heatmap` / `009-portal-zones` / … 各功能规格

## git 发布注意事项

- `*.xlsx`、`*.db`、`uploads/`、`*.bak_*` 已加入 `.gitignore`，不会误提交
- git 只发布：代码 + `seeds/seed_data.sql`（脱敏种子）+ `name_abbr_mapping.json`（脱敏映射）
- 新环境执行 `./bootstrap.sh` 即可从零到页面可用