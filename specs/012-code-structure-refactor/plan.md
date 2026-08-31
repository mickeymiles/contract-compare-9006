# 落地实施计划（领域模型 011 + 代码结构 012 逐步落地）

> 状态：PLAN | 目标：把经营业务按「项目为主数据」的领域模型与「按域分包」的结构逐步落地
> 原则：**小步、逐个验证、不影响现网**；每步独立 commit 可回滚；现网 main 在显式合入前不受影响。

---

## 0. 基线（先立基础，避免影响）

1. **分支策略**：在本地 `feature/refactor-*` 分支推进，现网 `main` 不动，直到块级确认再考虑合入。
2. **测试基线**：先跑 `python -m pytest tests/ -v`，确认为绿（当前 contract CI 已补 httpx 修复），作为回归基准。
3. **文档基线**：011/012/README 已产 DRAFT（本地、未 commit）——作为计划输入。
4. **回退手段**：每改动一域即为一次独立 commit；出错 `git revert`/切回旧 commit，不影响其它域。

---

## R1 结构定稿（文档）
- [ ] 定稿 011（领域模型：项目为主数据/三号链路/运维域收敛）、012（代码结构/前后端对齐/UI 规范/路由清单）、README。
- [ ] 完成「路由搬迁清单」核对（附录 A，162 条已映射）。
- 验证：文档评审通过。产出：可执行目录蓝图。

## R2 后端按域拆分 `main.py`（行为不变，风险最低，优先）
把 `main.py` 按域抽成 router，**不改任何 Path/数据，前端零影响**。逐块：
- [ ] R2.1 搭基架：`app/main.py` 仅 `include_router` + 各 `domains/<域>/routes.py` 空壳。
- [ ] R2.2 搬 `foundation`：datasource / etl / ontology / dict / config / log / alert
- [ ] R2.3 搬 `finance`：payment / gross / funding / billing / report
- [ ] R2.4 搬 `procurement`：contrast（合同硬件对比）+ 预留
- [ ] R2.5 搬 `ops`：备件询价全套（tasks/ledger/suppliers/contracts/mail-cc/spare-parts）
- [ ] R2.6 搬 `core`：商机/合同/项目（plm 三号）
- [ ] R2.7 搬 `lifecycle`：baseline / pmo / staffing（原 plm_models 分散归位）
- **每块验证**：`pytest tests/` + 该域 API 手工/HTTP 冒烟（路由、字段、返回一致）→ 绿才搬下一块。
- **每块独立 commit**，可单独回退。
- 里程碑：`main.py` 瘦身完成，行为零回归 → 可灰度合入并部署验证一次。

## R3 数据主数据（项目为根 + 运维域）
- [ ] R3.1 建 `Project` 主数据（`project_no` 唯一、三号链路 `contract_no/opportunity_no`、子项目余量、审计留痕）。
- [ ] R3.2 迁移工具：`plm_project` 升级为主数据；`procurement_contract / contracts` 做映射层（先视图后物理，现网不动）。
- [ ] R3.3 Ops 联系域：`contact`（收件人/电话/地址）迁入运维；采购确认邮件取数路径改 `project→ops`。
- [ ] R3.4 各业务表 `project_id` 挂接（baseline/milestone/task/ledger/timesheet…）。
- **每步验证**：建新表/视图后业务仍读旧，`count/总量对账` 一致 → 切读主数据 → 冒烟；迁移脚本幂等可重跑。
- **风险**：工程量最大，严格小步；先 master-data 只读映射，后物理迁移。

## R4 前端统一（目录对齐 + common 组件）
- [ ] R4.1 建 `frontend/common`：扁平 SVG 图标库 + 手风琴组件 + 面包屑 + 统一导航配置(domains[]).
- [ ] R4.2 前端目录同名后端重排（core/lifecycle/finance/procurement/ops/foundation）+ 统一导航引用。
- [ ] R4.3 现有页面逐页接入手风琴/面包屑/图标；首页改**领域卡片**（3.2/3.3）。
- [ ] R4.4 全局替换 emoji 写实图标为图标库（议题3 宪章）。
- **每页验证**：页面可用、导航/面包屑/图标一致性；无回归。
- **顺序**：先建库/组件 → 接一个样板域 → 再扩散。

## R5 收尾
- [ ] 废弃旧合同表/旧入口；统一前后缀评估（AD-8）；README 终版。
- [ ] 全量回归（pytest + 端到端冒烟）+ 最终部署。
- [ ] 清理草案中间产物，沉淀为正式规范。

---

## 验证手段（贯穿全程）
- **单元/接口**：`pytest tests/`
- **冒烟**：直连 HTTP 验证该域核心 API（路径/字段/返回与迁移前一致）
- **对账**：主数据迁移前后 `count/统计` 比对
- **回归**：每完成一阶段跑全量；未部署或显式合入 main 前，现网不受影响

## 风险与规避
- **R2 行为回归**：只搬不改 Path/字段；每块 pytest+冒烟，独立 commit。
- **R3 迁移大**：先映射层只读、后物理；幂等脚本 + 对账；可停在任意小步。
- **前端影响**：全部本地改造，示范页先做样板域；common 未就位前现网页面不改。
- **并发依赖**：R2 依赖新文件结构；R3 依赖 master-data；R4 依赖 common；按序推进，但各阶段产物相互独立可暂停。

## 当前进度

> 更新 2026-08-30。此前本节写着「R2~R5：未启动」，与实际提交严重脱节。
> **判断进度请以 `git log` 为准**，本节可能再次滞后。

### 重构线（feature/refactor-r2，同事在推进）

已推进到 R4。按 git log 的实际提交：

- R2.6　ETL 计算服务（`run_etl_*`）→ `services/etl.py`
- R2.7　合同硬件比对 contrast（`/api/contract*`、`/api/compare`）→ `procurement/`
- R2.8　neuops 智能体网关（`trigger_neuops`）→ `common/neuops.py`
- R2.9　备件询价 ops（`/api/procurement/tasks|suppliers|contracts|mail-cc|spare-parts|ledger`）→ `ops/`
- R2.10 ETL 调度（`/api/etl*`）→ `foundation/routes_etl.py`
- R2.11 PLM 路由（`/api/plm*` 74 条）→ `lifecycle/routes_plm.py`
- R2.11b `routes_plm` 补 urllib 导入（fr10 导出文件名引号）
- R4　　前端统一壳 + 主数据 + 财经指标迁移

剩余：`backend/core/` 仍平铺（`project.py` / `routes.py` / `migrate.py` 等），
`backend/main.py` 未完成瘦身。

**分叉状态**：r2 领先 main 13 个提交，main 领先 r2 5 个（采购 / 运维域业务改动）。
合入前需解决 `routes_plm.py` 与采购 / 运维改动的冲突。

### 主线（main，2026-08-30）

本轮未做结构重构，只做「保证能用」的止血与跨工程契约固化，
清单见 `neuops-agent-demo/docs/cross-project-contract.md` 第四、五节。

**重构前必须先固化契约**：两个工程之间的隐式约定（trigger payload、共享 DB 字段所有权、
状态机两份推导、邮件关键词）目前分散在代码里，见该文档第四节 10 项待办。