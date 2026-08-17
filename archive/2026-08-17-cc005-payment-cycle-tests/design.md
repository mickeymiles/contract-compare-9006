# 设计：CC-005 回款周期分析测试

## 被测对象

`backend/main.py` 中的回款周期分析函数（`GET /api/analysis/payment-cycle`）：

- `_load_ds_meta()`：读取 `datasource/versions.json`，`_get_versions` 取 `versions[0]`（最新版）
- `ds_latest_file(table_name)`：按 meta 中 `versions[0]['file']` 定位 Excel
- H 表（总合同表）列识别：`h_col_no`（合同编号）、`h_col_date`（统计日期/签约日期）、
  `h_col_dept`（部门）、`h_col_amount`（合同金额）、`h_col_zone`（区域）、`h_col_province`（省）
- R 表（项目里程碑表）：`r_col_no`（合同编号）、`r_col_time`（计划回款时间）、`r_col_amount`（计划产值）
- 年份过滤：仅统计 `sd.year in (2026, 2025)` 的合同（写死当年/上年）
- `cycle_days = (最晚计划回款时间 - 签约日期).days`；`years = cycle_days / 365`
- zone 五档：`<0.5 → '0.5以内'`，`<1 → '0.5-1年'`，`<2 → '1年以上'`，`<3 → '2年以上'`，`else '3年以上'`
- 按月累计：months 桶 `2026-06 / 2026-07 / 2026-08`，条件 `sd.year < Y or (sd.year == Y and sd.month <= M)`，
  计数 `project_count`（H 表合同数）与 `plan_amount`（R 表计划产值累计）
- 聚合：`regions`（按区域计数+金额）、`province_stats`（按省计数）、`department`（按部门计数+金额）
- 返回：`{success, source_version, months, regions, province_stats, department, enriched_rows, enriched_2025, enriched_total, ...}`

## 测试策略

- 在临时目录构造 `datasource/`：`versions.json` + H.xlsx + R.xlsx（openpyxl 生成），
  `monkeypatch.setattr(main, 'DATASOURCE_DIR', str(ds_dir))` 隔离真实数据
- 直接调用被测函数（`main.analysis_payment_cycle()`），不经过 HTTP，避免服务依赖
- 行数据用确定性的 `datetime` 构造，断言精确的 `cycle_days` / `zone` / 月份计数

## 关键测试数据

| 合同 | 签约日期 | 金额 | 区域/省 | R 表最晚回款 | cycle_days | years | zone |
|------|----------|------|---------|--------------|-----------|-------|------|
| C1 | 2026-01-10 | 100万 | 西部/陕西 | 2026-07-01 | 172 | 0.471 | 0.5以内 |
| C2 | 2026-02-01 | 200万 | 西部/甘肃 | 2027-02-01 | 365 | 1.0 | 1年以上 |
| C3 | 2026-03-01 | 300万 | 东部/江苏 | 2026-12-01 | 275 | 0.753 | 0.5-1年 |
| C4 | 2025-05-01 | 50万 | 东部/浙江 | 2026-05-01 | 365 | 1.0 | 1年以上 |
| C5 | 2024-05-01 | 80万 | 东部/浙江 | 2025-05-01 | 365 | 1.0 | （2024 排除） |

- 2026-06 桶：C1（1 个） ；2026-07 桶：C1+C2+C3（3 个）
- enriched_rows（2026）：3 条；enriched_2025：1 条（C4）；C5 不进任何 enriched
