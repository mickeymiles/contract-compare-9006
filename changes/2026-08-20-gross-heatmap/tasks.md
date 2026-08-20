# 任务清单：签单毛利率部门 × 区域二维热力图

## 后端

- [ ] T1 ETL 二维聚合 #CC-008
  - 在 `backend/main.py` 的 `run_etl_gross_margin` 中新增 `dept_region` 聚合。
  - 按 `(部门, 区域, 年份)` 分组汇总 `sign_amount`、`gross_profit`。
  - 写入 `indicator_metrics`，`dim_type='dept_region'`，`dim_value='部门|区域'`，`extra_json` 记录 `dept`、`region`。
  - 在 `extra_json` 中附带 2025/2026 原始金额（与现有维度一致）。

- [ ] T2 API 返回热力图数据 #CC-008
  - 在 `gross_metrics` 中查询 `dim_type='dept_region'` 记录。
  - 构造 `dept_region_rows`（regions / depts / cells / totals）。
  - 单元格计算 `rate`（2026 毛利率）与 `diff`（2026 vs 2025 百分点）。
  - 小计按部门和区域分别汇总 2025/2026 金额后计算毛利率与 diff。

- [ ] T3 后端测试 #CC-008
  - 在 `tests/test_gross.py` 新增 ETL 与 API 测试，验证二维聚合结构正确。
  - 运行 `cd contract-compare && pytest -q`，确保无新增失败。

## 前端

- [ ] T4 热力图 HTML 结构 #CC-008
  - 在 `frontend/gross.html` 增加 `heatmapPanel` section。
  - 调用 `renderHeatmap(data)` 生成 `<table id="heatmapTable">`。

- [ ] T5 热力图渲染脚本 #CC-008
  - 实现 `renderHeatmap()`：
    - 表头：首列为空，中间为区域名，最后为「小计」。
    - 表体：首列为部门名，中间为单元格数据，最后一列为部门小计。
    - 最后一行为区域小计。
    - 单元格按 `diff` 分档设置 CSS 类。
    - 无数据单元格显示为空白灰格并标注 Tooltip（可选）。
  - 在 `loadPage()` 的 `gross_metrics` 回调中调用 `renderHeatmap(data.dept_region_rows)`。

- [ ] T6 热力图样式 #CC-008
  - 在 `frontend/common.css` 新增热力图表格与单元格样式。
  - 颜色分档覆盖：深红、红、浅红、黄、浅绿、绿、深绿、灰。
  - 单元格内文字居中，行高紧凑，数字与 diff 字号区分。

## 文档与验收

- [ ] T7 更新 TRACEABILITY.md #CC-008
  - 在 `contract-compare/specs/TRACEABILITY.md` 追加 `CC-008` 条目，映射代码文件、测试。

- [ ] T8 手工验证 #CC-008
  - 运行 ETL 后访问 `/gross`。
  - 截图确认热力图行列、颜色、空白格、小计均正确。
