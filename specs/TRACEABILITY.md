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
| CC-006 | 资金占用分析 | `backend/main.py`（`/api/fund/*`） | `tests/test_api_smoke.py::TestApiSmoke::test_fund_status`、`test_fund_metrics` |
| CC-007 | ETL 调度与聊天 | `backend/main.py`（`/api/etl/*`、`/api/chat/*`、`/api/mcp/ontology/*`） | `tests/test_api_smoke.py::TestApiSmoke::test_etl_jobs`、`test_etl_metrics`、`test_tables`、`test_schema`、`test_query` |

## 覆盖情况统计

- 已回填规格：7 个（CC-001 ~ CC-007）
- 有测试覆盖：7 个（CC-001 ~ CC-007），全部模块均已覆盖
- 待补测试：无

## 变更登记

| 日期 | 变更编号 | 说明 |
|------|----------|------|
| 2026-08-17 | （规格回填） | 依据存量代码回填 7 个规格并建立本矩阵 |
| 2026-08-17 | 20260817-cc004-export-tests | 新增 CC-004 报告导出测试（双 Sheet 结构/总览/着色），归档于 archive/2026-08-17-cc004-export-tests/ |
| 2026-08-17 | 20260817-cc005-payment-cycle-tests | 新增 CC-005 回款周期测试（双口径/按月累计/zone 分档/年份过滤/降级），归档于 archive/2026-08-17-cc005-payment-cycle-tests/ |
