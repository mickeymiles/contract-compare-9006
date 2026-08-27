# 任务清单：项目全生命周期管理（CC-010）

> 变更编号：`2026-08-27-project-lifecycle`
> 前置依赖：CC-009 门户双分区（`changes/2026-08-27-portal-zones/`）

## 前置

- [x] delta 规格 `specs/CC-010-project-lifecycle/spec.md`（FR-1 ~ FR-11）
- [x] 设计 `design.md`（16 张表 + 计算口径 + 分层）
- [x] 用户确认：核心链路全做 / 只做手工录入 / 分区标题「经营管理 · 运维管理」

## 后端 · 数据层

- [x] [P0] T1 `backend/plm_models.py` 建表 `init_plm_db()`：17 张 `plm_` 表 + 幂等列迁移
- [x] [P0] T2 `seed_plm_master()`：字典（项目状态 / 商机状态 / 里程碑类型 / 成本科目 / 岗位）、4 类预警规则默认阈值、`plm_config` 预置（`baseline_constraint=off`、`labor_day_hours=8`、`alert_staff_overload=1.2`） #CC-010 FR-9 FR-11
- [x] [P0] T3 商机 CRUD + 概算汇总重算（分项 → 总额 → 毛利 → 毛利率，income≤0 返回 None） #FR-1
- [x] [P0] T4 售前资料登记/删除 #FR-1
- [x] [P0] T5 合同 CRUD + 项目 CRUD + `convert_opportunity_to_project()` 联动立项（商机→合同→项目→锁定概算，写 `source_baseline_id`） #FR-2
- [x] [P0] T6 基线 CRUD + `lock_baseline()` + 管控开关校验（超概算按 `baseline_constraint` 决定提示或拒绝） #FR-2 FR-3
- [x] [P0] T7 核算/决算预留：字段与录入入口存在，计算返回 None #FR-3
- [x] [P0] T8 里程碑（父子两级）+ 任务 CRUD，子级 progress 向上汇总 #FR-4
- [x] [P0] T9 `project_progress()` 双维度：按期（完成率/延期清单/达成率口径标注）+ 按预算（消耗占比/剩余/剪刀差），未录预算兜底 #FR-5
- [x] [P0] T10 人员池 CRUD + 分配 CRUD + 工时 CRUD，工时保存触发 `sync_labor_cost()` 归集台账 #FR-6
- [x] [P0] T11 `staff_load()` 负荷三态（>1.2 过载 / >0 正常 / =0 闲置）+ 并行项目明细 #FR-6
- [x] [P0] T12 收支台账 CRUD + `project_finance()`（签单毛利/预估毛利/实际毛利/毛利率 + 概算-预算-实际三线差异） #FR-7
- [x] [P0] T13 `project_panorama()` 7 板块聚合，空数据返回空集合 #FR-8
- [x] [P0] T14 `scan_alerts()` 四类规则扫描 + 未闭环去重更新 + 风险消除自动闭环 #FR-9
- [x] [P0] T15 预警中心列表（按项目/类型/状态筛选）+ `handle_alert()` 状态流转与留痕 #FR-9
- [x] [P1] T16 `export_report()` 5 类 Excel（openpyxl 多 Sheet），空数据返回表头 #FR-10
- [x] [P0] T17 字典/参数 CRUD + 所有写操作 `log_op()` 留痕 #FR-11
- [x] [P0] T18 删除保护：实体删除前检查下游引用并返回引用计数 #FR-2 FR-4

## 后端 · 路由

- [x] [P0] T19 `main.py` 顶部 `import plm_models as plm`（命名空间引用，禁止符号导入污染全局）
- [x] [P0] T20 `startup()` 追加 `plm.init_plm_db()` + `plm.seed_plm_master()`
- [x] [P0] T21 `/plm` 页面路由 + `/plm.app.js` 静态路由
- [x] [P0] T22 `/api/plm/*` 约 60 个薄路由（Pydantic Body 模型统一置于 plm 段内，避免与既有模型同名）

## 前端

- [x] [P0] T23 `plm.html` 骨架：面包屑 + 左侧模块导航（10 项）+ 模块容器 + 专属样式
- [x] [P0] T24 `plm.app.js` 元数据驱动 CRUD 引擎（`PLM_MODULES` + 列表 + 表单弹窗 + 删除确认）
- [x] [P0] T25 经营驾驶舱：KPI 卡 + 项目健康列表 + 预警概览
- [x] [P0] T26 四算基线页：概算/预算/【预留】核算/决算对比表 + 锁定操作 + 管控开关提示
- [x] [P0] T27 PMO 进度页：双维度指标 + 里程碑树 + 任务表 + 延期标记
- [x] [P0] T28 人力与工时页：人员池 + 负荷条 + 分配 + 工时填报
- [x] [P0] T29 成本毛利页：收入/成本台账 + 毛利指标卡 + 三线差异图（ECharts）
- [x] [P0] T30 项目全景页：严格 7 板块布局 + 快捷跳转
- [x] [P0] T31 预警中心：筛选 + 处置弹窗 + 规则配置
- [x] [P0] T32 系统配置页：字典 + 阈值 + 基线管控开关 + 操作日志
- [x] [P0] T33 `index.html` 经营管理区新增「项目全生命周期管理」大卡 → `/plm`
- [x] [P1] T34 `common.css` 追加 PLM 通用样式

## 测试与收尾

- [x] [P0] T35 `tests/test_plm.py` 覆盖 FR-1 ~ FR-11，逐用例标注规格编号
- [x] [P0] T36 全量回归 `python -m pytest -q`（基线 57 passed 不回归）
- [x] [P1] T37 启动服务手工验证：空库引导、录入→全景→预警全链路、5 类报表可下载
- [x] [P0] T38 更新 `specs/README.md` 索引、`specs/TRACEABILITY.md`、`AGENTS.md` 规格索引、`index.html` 用户手册
- [x] [P0] T39 commit：`feat(CC-010): 项目全生命周期管理模块（四算基线/PMO双进度/人力工时/成本毛利/全景视图/风险预警）`
- [x] T40 归档：变更目录移入 `archive/`，delta 合并进 `specs/010-project-lifecycle/spec.md`
