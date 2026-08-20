# 追踪矩阵（TRACEABILITY）— contract-compare

> 规格编号 → 代码文件 → 测试用例 的三向映射，验证"每个规格都有实现、每个实现都有测试"。
> 维护规则：新增/修改规格或测试后必须同步更新本表；后续新增测试用例请在用例处标注规格编号（如 `# CC-003 FR-7`）。

## 映射矩阵

| 规格编号 | 模块 | 代码文件 | 测试用例 |
|----------|------|----------|----------|
| CC-001 | 合同管理 | `backend/models.py`、`backend/main.py`（`/api/contracts`、`/api/contract/*`） | `tests/test_api_smoke.py::TestApiSmoke::test_contracts`、`test_stats` |
| CC-002 | 数据源导入 | `backend/excel_handler.py`、`backend/main.py`（`/api/datasource/*`） | `tests/test_excel_handler.py`（TestCleanHeader::test_remove_newline / test_remove_long_bracket / test_keep_short_bracket / test_lower、TestFindColumn::test_find_by_alias / test_not_found） |
| CC-003 | 比对引擎 | `backend/compare_engine.py`、`docs/compare-rules.md` | `tests/test_compare_engine.py`（TestNormalizeUnit::test_g_to_gb / test_t_to_tb / test_core / test_standard_unchanged / test_empty / test_unit / test_strip_space / test_upper、TestExtractStructuredParams::test_full_extract / test_no_structured_param、TestRangeMatch::test_fullwidth_to_halfwidth / test_parse_range / test_range_match_unit_convert / test_range_match_satisfy、TestNameSimilarity::test_levenshtein / test_find_group / test_name_similarity_identical / test_name_similarity_synonym） |
| CC-004 | 报告导出 | `backend/excel_handler.py`（export_report）、`backend/main.py`（`/api/contract/*/export/report`） | `tests/test_export.py`（test_export_two_sheets / test_export_overview_data / test_export_anomaly_detail） |
| CC-005 | 回款周期分析 | `backend/main.py`（`/api/analysis/payment-cycle*`、`/api/payment-cycle/metrics`） | `tests/test_payment_cycle.py`（test_payment_cycle_basic_structure / test_payment_cycle_enriched_rows / test_payment_cycle_zone_edges / test_payment_cycle_missing_h_table / test_payment_cycle_missing_r_table） |
| CC-006 | 资金占用分析 | `backend/main.py`（`/api/fund/*`，含 `/api/fund/dim/*`、`/api/fund/risk/*`、`/api/fund/dim/export`、`/api/fund/risk/export`）、`frontend/index.html`（资金页 5 Tab 图表） | `tests/test_api_smoke.py::TestApiSmoke::test_fund_status`、`test_fund_metrics`；`tests/test_fund_multidim.py`（test_fund_analyze_has_dims / test_fund_analyze_risk_level / test_calc_risk_level_edges / test_trend_warning / test_customer_key_encode / test_fund_dim_aggregate / test_fund_risk_list / test_fund_metrics_columns）；`tests/test_fund_yoy.py`（test_fund_analyze_has_flows / test_fifo_occupy_upto / test_yoy_window_pay_recv / test_yoy_prev_zero / test_yoy_occupy_prev / test_analyze_rows_have_prev_occupy / test_fund_metrics_prev_occupy / test_dim_aggregate_prev_occupy） |
| CC-007 | ETL 调度 | `backend/main.py`（`/api/etl/*`、`/api/mcp/ontology/*`） | `tests/test_api_smoke.py::TestApiSmoke::test_etl_jobs`、`test_etl_metrics`、`test_tables`、`test_schema`、`test_query` |
| CC-008 | 签单毛利率二维热力图 | `backend/main.py`（`run_etl_gross_margin`、`/api/gross/metrics`）、`frontend/gross.html`、`frontend/common.css` | `tests/test_gross.py`（test_api_gross_metrics_includes_dept_region_rows、test_gross_metrics_handles_empty_dept_region） |

## 覆盖情况统计

- 已回填规格：8 个（CC-001 ~ CC-008）
- 有测试覆盖：8 个（CC-001 ~ CC-008），全部模块均已覆盖
- 待补测试：无

## 变更登记

| 日期 | 变更编号 | 说明 |
|------|----------|------|
| 2026-08-17 | （规格回填） | 依据存量代码回填 7 个规格并建立本矩阵 |
| 2026-08-17 | 20260817-cc004-export-tests | 新增 CC-004 报告导出测试（双 Sheet 结构/总览/着色），归档于 archive/2026-08-17-cc004-export-tests/ |
| 2026-08-17 | 20260817-cc005-payment-cycle-tests | 新增 CC-005 回款周期测试（双口径/按月累计/zone 分档/年份过滤/降级），归档于 archive/2026-08-17-cc005-payment-cycle-tests/ |
| 2026-08-17 | 20260817-remove-ai-chat | 移除 AI 对话窗口（聊天）功能：删除 /api/chat/* 路由、chat_handler、chat_messages 表定义与前端聊天浮窗，CC-007 改名"ETL 调度" |
| 2026-08-18 | 20260818-fund-multidim | 资金占用多维度分析与预警：维度关联（区域/客户集合/部门/业务线等）、四级风险预警（阈值可配置）、趋势预警、穿透下钻、10 张 ECharts 图表与 Excel/PNG 导出，CC-006 新增 FR-8~FR-12 |
| 2026-08-18 | 20260818-fund-yoy | 资金占用同比（YoY）分析：后端 `_fifo_occupy_upto` 精确计算上年同期日 FIFO 占用，`fund_analyze` 返回 `data.flows`（逐笔现金流）与 `data.yoy.occupy_prev`；前端总览页新增 4 张同比 KPI 卡（付款/回款/净现金流/当前占用，YTD 2026 vs 上年同期 2025-01-01~2025-08-12）与月度同比对比图，CC-006 新增 FR-13；顺带修复趋势图付款/回款曲线缺失 |
| 2026-08-18 | 20260818-fund-table-yoy | 资金占用表格同比：明细表与客户集合表格新增"上年同期占用"与"同比变化率"两列，变化率按升降着色（占用升红/降绿）；宽表 `fund_metrics` 新增 `prev_occupy` 列（幂等迁移），`/api/fund/metrics`、`/api/fund/dim/aggregate`、`/api/fund/dim/drill` 透出上年占用；CC-006 FR-13 追加表格同比场景 |
