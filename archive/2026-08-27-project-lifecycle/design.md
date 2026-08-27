# 设计：项目全生命周期管理（CC-010）

> 变更编号：`2026-08-27-project-lifecycle` | 日期：2026-08-27 | 状态：已评审

## 架构决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 承载形态 | 独立整页 `/plm` + 左侧模块导航，不塞进 `index.html` | `index.html` 已 2705 行；9 个子模块继续内嵌会失控。`/gross`、`/procurement` 已是同构先例 |
| 数据落库 | 复用同一 SQLite 文件 `contract_compare.db`，全部表以 `plm_` 前缀 | 与 `procurement_models.py` 一致，避免多库与跨库 join |
| 符号引用 | `import plm_models as plm`，命名空间引用 | `main.py` 曾因 `from procurement_models import create_contract` 覆盖 `models.py` 同名函数，留下 `import contract_models` 兜底补丁。新模块必须避免污染全局 |
| 前端 CRUD | 元数据驱动引擎（模块配置 → 列表 + 表单 + 删除） | 商机/合同/项目/人员/分配/工时/台账/规则/字典 9 个模块结构相似，专属代码只写全景视图、双进度、预警中心 |
| 四算建模 | 单表 `plm_baseline` 以 `stage` 区分概算/预算/核算/决算 | 避免 4 张近似表；核算/决算是天然预留（插行即可，无需改结构） |
| 工时折算 | 人天单价 ÷ 8 × 小时，口径固化在字典与表单标注 | 与人员池「元/人天」单价保持一致 |
| 权限 | 本期不做鉴权，仅 `operator` / `role` 字段留痕 | 系统当前无登录体系，强行引入会牵连全局 |

## 数据模型（16 张表）

所有表含 `created_at TEXT DEFAULT (datetime('now','localtime'))`；可变表含 `updated_at`。金额统一 `REAL`（元），工时统一 `REAL`（小时）。

```sql
-- 1 商机档案
plm_opportunity(id, opp_no UNIQUE, opp_name, customer, industry, region, dept,
                owner, status, bid_date, expect_income, est_cost, est_gross,
                est_gross_rate, follow_log, won_at, remark)

-- 2 售前资料归档（附件落 uploads/presale/）
plm_presale_doc(id, opportunity_id, doc_name, doc_type, file_name, file_path,
                remark, uploader)

-- 3 合同主数据
plm_contract(id, contract_no UNIQUE, contract_name, customer, industry, region,
             dept, sign_amount, sign_date, project_cycle, owner,
             opportunity_id, remark)

-- 4 项目
plm_project(id, project_no UNIQUE, project_name, customer, contract_id,
            opportunity_id, manager, dept, status, start_date, end_date,
            kickoff_date, remark)

-- 5 四算基线（概算-投标 / 概算-锁定 / 预算 / 核算[预留] / 决算[预留]）
plm_baseline(id, scope_type, scope_id, stage, total_income, total_cost,
             gross, gross_rate, status, source_baseline_id, version,
             locked_at, locked_by, created_by, remark)
--   scope_type: 'opportunity' | 'project'
--   stage: 'estimate_bid' | 'estimate_locked' | 'budget' | 'accounting' | 'final'
--   status: '草稿' | '已确认' | '已锁定'

-- 6 基线分项
plm_baseline_item(id, baseline_id, category, item_name, plan_amount,
                  actual_amount, remark)
--   category: 人力成本 | 分包成本 | 硬件成本 | 软件成本 | 服务成本 | 其他费用

-- 7 里程碑（两级：粗/细，parent_id 自关联）
plm_milestone(id, project_id, parent_id, level, name, owner, plan_start,
              plan_end, actual_start, actual_end, progress, status, is_key,
              plan_output, deliverable, remark)
--   level: '粗' | '细' ; status: 未开始|进行中|已完成|延期

-- 8 任务
plm_task(id, project_id, milestone_id, name, owner, plan_hours, actual_hours,
         progress, status, plan_start, plan_end, actual_end, deliverable, remark)

-- 9 人员池
plm_staff(id, name UNIQUE, role, dept, cost_rate, available_hours, status,
          skills, remark)
--   cost_rate 单位：元/人天 ; available_hours 单位：小时/月

-- 10 人员分配（绑定到项目/里程碑/任务任一层）
plm_assignment(id, staff_id, project_id, milestone_id, task_id, role_in_proj,
               planned_hours, start_date, end_date, status)

-- 11 工时填报
plm_timesheet(id, staff_id, project_id, task_id, work_date, hours, remark)

-- 12 收支台账（收入 + 成本统一，含工时自动归集）
plm_ledger(id, project_id, contract_id, kind, category, plan_or_actual,
           amount, occur_date, source, milestone_id, ref_type, ref_id, remark)
--   kind: 'income' | 'cost' ; plan_or_actual: '预估' | '实际'
--   source: '手工录入' | '工时归集' ; ref_type/ref_id 指向 timesheet 等来源

-- 13 预警规则
plm_alert_rule(rule_key PRIMARY KEY, rule_name, dim, metric, op, threshold,
               level, enabled, description, updated_at)
--   dim: 'cost'|'gross'|'schedule'|'staff' ; level: 提醒|警告|严重

-- 14 预警实例
plm_alert(id, project_id, rule_key, dim, level, title, detail, metric_value,
          threshold, status, handler, handle_note, handle_time, last_scan_at)
--   status: 待处理|处理中|已闭环

-- 15 操作日志
plm_op_log(id, target_type, target_id, target_name, action, change_json,
           operator, role, remark)

-- 16 字典 + 17 全局参数
plm_dict(id, category, key, label, sort, enabled, remark)
plm_config(key PRIMARY KEY, value, description, updated_at)
--   plm_config 预置：baseline_constraint='off'、labor_day_hours='8'、
--                    alert_staff_overload='1.2'
```

> 表数标 16，实际建 17（字典与参数分表）。迁移全部用 `CREATE TABLE IF NOT EXISTS` + `try: ALTER TABLE ADD COLUMN except: pass`，与 `models.py`/`procurement_models.py` 的既有幂等风格保持一致。

## 计算逻辑

```
概算/预算毛利率      = (total_income - total_cost) / total_income        # income<=0 → None
预估毛利            = expect_income - est_cost
签单毛利            = 合同签单收入 - 预估成本(概算总成本)
实际毛利            = Σincome - Σcost(kind='cost', plan_or_actual='实际')
预算消耗占比        = Σ实际成本 / budget_total                            # budget_total<=0 → None
按时完成率          = 按期完成节点数 / 已完成节点数
整体进度达成率      = avg(细里程碑 progress)，若 plan_output 全有值则按计划产值加权
剪刀差              = 预算消耗占比 - 整体进度达成率
工时归集人力成本     = Σhours/8 × staff.cost_rate   → 覆写 plm_ledger(source='工时归集')
人员负荷率          = 当期(已分配∪已填报)小时 max / available_hours
                      >1.2 → 过载 ; >0 → 正常 ; =0 → 闲置
```

自动重算点：保存概算/预算分项时重算基线汇总；保存工时或人员分配时重算该项目 `source='工时归集'` 的人力成本台账；保存里程碑/任务时向上汇总父里程碑 progress。

## 预警扫描 `plm.scan_alerts()`

对每个未结项项目按启用规则判定：

| dim | metric | 默认规则 | 默认阈值 |
|-----|--------|----------|----------|
| cost | `budget_usage_rate` | 预算超耗预警 | 0.80 提醒 / 1.00 严重 |
| gross | `actual_gross_rate` | 毛利偏低预警 | 0.15 提醒 / 0.00 严重 |
| schedule | `max_overdue_days` | 进度延期预警 | 7 天提醒 / 30 天或关键节点 警告 |
| staff | `max_load_rate` | 人员工时过载预警 | 1.2 提醒 |

未命中规则的项目若存在未闭环旧预警，SHALL 置为「已闭环」并标注「风险已消除（自动）」。

## 接口分层

```
main.py  (路由层，~60 个薄路由，只做参数校验/错误包装)
   └─ plm_models.py
        ├─ init_plm_db() / seed_plm_master()      建表 + 字典/规则/参数预置
        ├─ CRUD 层： create_/update_/delete_/get_/list_  每实体一组
        │            （删除前引用检查 → 返回 {"success":False,"error":..., "refs":{...}}）
        └─ 聚合层： baseline_summary / milestone_progress / project_progress /
                    project_finance / staff_load / project_panorama / overview /
                    scan_alerts / export_report
```

统一响应约定：`{"success": true, "data": ...}`；业务失败 `{"success": false, "error": "..."}`（HTTP 200，与既有 `/api/procurement/*` 风格一致）；仅资源不存在用 404。

## 前端结构

```
frontend/plm.html          骨架 + 左侧菜单树容器 #plmNav + 10 个模块容器 + 专属样式
frontend/plm.app.js        逻辑
  ├─ NAV 菜单树配置（一级模块 + 二级叶子 + 角标）与 renderNav/go/navClick/showSub 路由
  ├─ MODULES 元数据配置（字段/类型/枚举/列顺序/接口路径）
  ├─ renderModuleGrid(cfg) 通用列表 + 分页/筛选
  ├─ openForm(cfg, row)     通用新建/编辑弹窗（含数值与必填校验）
  ├─ 专属：renderOverview / renderProgress(双维度) / renderPanorama(7 板块)
  │        /renderStaffLoad(负荷条) /renderAlerts(预警中心) /renderBaseline(四算对比)
  └─ exportReport(name, params) → location.href 下载
```

模块导航（**左侧菜单树，非页面内 Tab**，用户明确要求）：

```
📡 经营驾驶舱
🎯 售前商机
📑 合同与立项        ▸ 项目立项 / 合同主数据
🧱 四算基线
🚩 PMO 进度          ▸ 双维度进度 / 里程碑与任务
👥 人力与工时        ▸ 人员池与负荷 / 人员分配 / 工时填报
💹 成本与毛利        ▸ 毛利与差异 / 收支台账
🔭 项目全景
⚠️ 风险预警 (角标)   ▸ 预警中心 / 规则配置
⚙️ 系统配置          ▸ 全局参数 / 字典维护 / 操作日志
```

10 个一级节点 + 14 个二级叶子，手风琴式展开（进入某模块时收起其它模块），模块记忆上次停留叶子。

「四算基线 / PMO 进度 / 成本毛利 / 项目全景」四页以**项目选择器**为上下文入口，其余为全量列表页。

## 涉及文件

| 文件 | 改动 |
|------|------|
| `backend/plm_models.py` | 新增，约 1100 行（建表 + CRUD + 聚合 + 扫描 + 导出） |
| `backend/main.py` | 新增 `/plm` 页面路由 + `/api/plm/*` 路由块；`startup()` 追加 `plm.init_plm_db()`、`plm.seed_plm_master()` |
| `frontend/plm.html` | 新增 |
| `frontend/plm.app.js` | 新增 |
| `frontend/common.css` | 追加 PLM 通用样式（板块、进度条、负荷条、预警徽章） |
| `frontend/index.html` | 经营管理区新增大卡（依赖 CC-009） |
| `tests/test_plm.py` | 新增 |
| `specs/TRACEABILITY.md`、`specs/README.md`、`AGENTS.md` | 追加 CC-010 |

## 测试策略

`tests/test_plm.py` 按规格编号标注，覆盖：概算汇总与零收入兜底（FR-1）、联动立项与三级溯源与锁定留痕（FR-2）、预算四场景含管控开关与核算决算预留（FR-3）、父子里程碑与任务归属（FR-4）、双进度算例与未录预算兜底（FR-5）、工时归集与过载识别（FR-6）、实际毛利与三线差异（FR-7）、全景 7 板块完整性与空项目（FR-8）、四类预警触发/去重/闭环/阈值生效（FR-9）、5 类报表导出（FR-10）、字典维护与操作留痕（FR-11）。

## 回滚方案

删 `plm_models.py` / `plm.html` / `plm.app.js` / `main.py` 内 `# ===== 项目全生命周期管理 =====` 整段 + `startup()` 两行 + `index.html` 大卡 + `common.css` PLM 段；`DROP TABLE plm_*`。既有 8 个模块零影响。
