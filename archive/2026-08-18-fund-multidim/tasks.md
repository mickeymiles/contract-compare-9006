# 任务清单：资金占用多维度分析与预警体系

> 变更编号：`20260818-fund-multidim`
> 状态：已全部完成，待归档

## 前置

- [x] 更新 delta 规格 `specs/006-fund-analysis/spec.md`（ADDED/MODIFIED）
- [x] 人工评审 proposal 与 delta 规格（用户已确认方案）

## 实现

### 后端

- [x] [P0] `models.py`：`fund_metrics` 增量加维度列+新指标列；新建 `risk_config` 表并 seed 默认阈值（对应 `CC-006 FR-8/FR-9`）
- [x] [P0] `main.py`：`fund_analyze` 内新增 `_load_contract_dims()` join 总合同表+里程碑表，宽表写入维度列与新指标（对应 `CC-006 FR-8`）
- [x] [P0] `main.py`：`_encode_customer_key()` 客户键编码 + `sanitize_excel_file` 保留客户标识列（对应 `CC-006 FR-2 MODIFIED`）
- [x] [P0] `main.py`：风险分级 `_calc_risk_level()` 纯函数 + `_calc_trend_warning()`（对应 `CC-006 FR-9/FR-12`）
- [x] [P0] `main.py`：`GET /api/fund/dim/aggregate` 维度聚合查询（region/province/dept/biz_line/industry/customer_key/project_status/month）（对应 `CC-006 FR-8`）
- [x] [P0] `main.py`：`GET /api/fund/dim/drill` 下钻接口（维度→合同清单）+ `GET /api/fund/segments/{contract_id}` 复用（对应 `CC-006 FR-10`）
- [x] [P1] `main.py`：`GET/POST /api/fund/risk/config` 风险阈值配置（对应 `CC-006 FR-9`）
- [x] [P1] `main.py`：`GET /api/fund/risk/list` 预警清单 + `GET /api/fund/risk/trend` 趋势预警（对应 `CC-006 FR-9/FR-12`）
- [x] [P1] `main.py`：`GET /api/fund/dim/export` 导出 Excel + `GET /api/fund/risk/export`（对应 `CC-006 FR-11`）
- [x] [P1] `main.py`：ETL job「fund-multidim」注册，按 `(dim_type × month)` 聚合写入 `indicator_metrics`（对应 `CC-006 FR-8`）

### 前端

- [x] [P0] `index.html`：资金页重构为 5 Tab（总览/区域/客户集合/时间/风险预警）（对应 `CC-006 FR-8`）
- [x] [P0] `index.html`：区域 Tab（热力地图 + 双轴柱状）、客户集合 Tab（TOP10 条形 + 风险堆叠条形）（对应 `CC-006 FR-8/FR-11`）
- [x] [P1] `index.html`：时间 Tab（月度趋势折线 + 分段直方图）、风险 Tab（四象限散点 + 成本环形 + 预警清单）（对应 `CC-006 FR-9/FR-11`）
- [x] [P1] `index.html`：下钻联动（点击区域/客户 → 合同清单 → 片段明细）与导出按钮（PNG/Excel）（对应 `CC-006 FR-10/FR-11`）

## 测试

- [x] [P0] `tests/test_fund_multidim.py`：维度关联正确性（`# CC-006 FR-8`）
- [x] [P0] `tests/test_fund_multidim.py`：风险分级边界（`# CC-006 FR-9`）
- [x] [P1] `tests/test_fund_multidim.py`：趋势预警（`# CC-006 FR-12`）、聚合接口、导出接口
- [x] [P1] 更新敏感列清洗策略（`# CC-006 FR-2`）：`PRIVACY_HEADER_PATTERN` 保留客户标识列
- [x] 全量回归：`cd contract-compare && pytest -q`（47 passed, 10 skipped，无回归）

## 收尾

- [x] 更新 `specs/TRACEABILITY.md` 追踪矩阵（新增 FR-8~FR-12 映射）
- [ ] 归档：变更目录移入 `archive/2026-08-18-fund-multidim/`，delta 合并回 `specs/006-fund-analysis/spec.md`
