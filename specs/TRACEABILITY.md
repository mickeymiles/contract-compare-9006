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
| CC-009 | 门户双分区导航 | `frontend/index.html`（`#page-portal` 双分区、`ALL_PAGES`/`showPage`/`initZoneCounts`）、`frontend/common.css`（`.zone`/`.portal-card.feature`） | `tests/test_portal_layout.py`（test_portal_has_two_zones / test_zone_order_and_datasource_above / test_ops_zone_only_contains_procurement / test_biz_zone_card_count / test_feature_card_links_plm_with_children / test_page_ids_defined_once / test_all_page_switch_paths_use_showpage / test_zone_counts_computed_not_hardcoded） |
| CC-010 | 项目全生命周期管理 | `backend/plm_models.py`（17 张 `plm_` 表 + CRUD + 四算基线/双维度进度/工时归集/预警扫描/报表导出）、`backend/main.py`（`/plm`、`/api/plm/*`）、`frontend/plm.html`、`frontend/plm.app.js` | `tests/test_plm.py`（FR-1~FR-11 逐条：test_fr1_estimate_rollup_from_items … test_fr11_operation_logs_traceable；路由冒烟 test_routes_crud_flow_via_http / test_route_staff_load_not_swallowed_by_id / test_route_404_for_missing_entities / test_no_legacy_route_regression）+ `tests/test_portal_layout.py`（test_plm_*） |

## 覆盖情况统计

- 已回填规格：10 个（CC-001 ~ CC-010）
- 有测试覆盖：10 个（CC-001 ~ CC-010），全部模块均已覆盖
- 待补测试：无（CC-009 / CC-010 的视觉与交互另由 Playwright 截图人工验收）

## 变更登记

| 日期 | 变更编号 | 说明 |
|------|----------|------|
| 2026-08-17 | （规格回填） | 依据存量代码回填 7 个规格并建立本矩阵 |
| 2026-08-17 | 20260817-cc004-export-tests | 新增 CC-004 报告导出测试（双 Sheet 结构/总览/着色），归档于 archive/2026-08-17-cc004-export-tests/ |
| 2026-08-17 | 20260817-cc005-payment-cycle-tests | 新增 CC-005 回款周期测试（双口径/按月累计/zone 分档/年份过滤/降级），归档于 archive/2026-08-17-cc005-payment-cycle-tests/ |
| 2026-08-17 | 20260817-remove-ai-chat | 移除 AI 对话窗口（聊天）功能：删除 /api/chat/* 路由、chat_handler、chat_messages 表定义与前端聊天浮窗，CC-007 改名"ETL 调度" |
| 2026-08-18 | 20260818-fund-multidim | 资金占用多维度分析与预警：维度关联（区域/客户集合/部门/业务线等）、四级风险预警（阈值可配置）、趋势预警、穿透下钻、10 张 ECharts 图表与 Excel/PNG 导出，CC-006 新增 FR-8~FR-12 |
| 2026-08-18 | 20260818-fund-yoy | 资金占用同比（YoY）分析：后端 `_fifo_occupy_upto` 精确计算上年同期日 FIFO 占用，`fund_analyze` 返回 `data.flows`（逐笔现金流）与 `data.yoy.occupy_prev`；前端总览页新增 4 张同比 KPI 卡（付款/回款/净现金流/当前占用，YTD 2026 vs 上年同期 2025-01-01~2025-08-12）与月度同比对比图，CC-006 新增 FR-13；顺带修复趋势图付款/回款曲线缺失 |
| 2026-08-20 | 2026-08-20-gross-heatmap | 签单毛利率部门 × 区域二维热力图：ETL 新增 `dim_type='dept_region'` 聚合、`/api/gross/metrics` 新增 `dept_region_rows`、`gross.html` 热力图与 8 档配色；CC-008 新增 |
| 2026-08-27 | 2026-08-27-portal-zones | 工作台首页拆分「经营管理 / 运维管理」双分区（备件采购归运维，其余归经营）；新增 `ALL_PAGES` 注册表与 `showPage()` 收敛 6 处重复页 ID 字面量；分区卡片数改为 DOM 自动统计；CC-009 新增 |
| 2026-08-27 | 2026-08-27-project-lifecycle | 新增「项目全生命周期管理」大模块（CC-010）：17 张 `plm_` 表、`/api/plm/*` 60+ 接口、概算+预算双基线与基线管控开关、中标商机联动立项三级溯源、PMO 双维度进度、工时折算人力成本归集与人员负荷三态、四类预警扫描与闭环、5 类 Excel 报表、字典/参数/操作日志；前端 `/plm` 采用左侧菜单树（10 一级 + 14 二级）与元数据驱动 CRUD；本期全部手工录入，核算/决算预留 |
| 2026-08-27 | 2026-08-27-ci-httpx-dep | 工程维护（无规格变更）：`backend/requirements.txt` 补 `httpx>=0.27`。TestClient 依赖它，CI 只装 requirements 导致 Run tests 连续失败、deploy 被 `needs: lint` 跳过，push 到 main 从未真正自动部署 |
| 2026-08-18 | 20260818-fund-table-yoy | 资金占用表格同比：明细表与客户集合表格新增"上年同期占用"与"同比变化率"两列，变化率按升降着色（占用升红/降绿）；宽表 `fund_metrics` 新增 `prev_occupy` 列（幂等迁移），`/api/fund/metrics`、`/api/fund/dim/aggregate`、`/api/fund/dim/drill` 透出上年占用；CC-006 FR-13 追加表格同比场景 |
