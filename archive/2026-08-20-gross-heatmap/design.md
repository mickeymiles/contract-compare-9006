# 设计文档：签单毛利率部门 × 区域二维热力图

## 设计目标

在现有签单毛利率统计页面上，新增一个与参考图片风格一致的二维热力图。行维度为部门，列维度为区域，单元格展示 2026 年毛利率与同比变化百分点，并用颜色直观反映同比变化幅度。

## 变更方案

1. **ETL 层**：在 `run_etl_gross_margin()` 中新增二维聚合 `dept_region`。对原始合同数据按 `(部门, 区域, 年份)` 聚合签单金额与毛利额，计算毛利率，写入 `indicator_metrics` 表 `dim_type='dept_region'`，`dim_value` 格式为 `部门|区域`，并通过 `extra_json` 分别记录 `dept` 与 `region`。
2. **API 层**：在 `gross_metrics()` 中读取 `dim_type='dept_region'` 记录，构造 `dept_region_rows`。计算每个 (dept, region) 的 2026 毛利率与较 2025 的变化百分点，同时计算部门小计、区域小计。
3. **前端层**：在 `gross.html` 中新增 `<section id="heatmapPanel">`，使用 `renderHeatmap(dept_region_rows)` 动态生成表格。单元格采用双层结构：上层显示 2026 毛利率百分比，下层显示同比变化百分点。颜色按 `diffPct` 分档。
4. **样式层**：在 `common.css` 追加热力图单元格、表头、小计、空白格样式，保持现有深色主题。

## Delta 规格

- `ADDED` `CC-008` 签单毛利率二维热力图分析（见 `specs/CC-008-gross-heatmap/spec.md`）

## 接口设计

`/api/gross/metrics` 现有响应结构不变，新增顶层字段 `dept_region_rows`：

```json
{
  "dept_region_rows": {
    "regions": ["华北", "华东", ...],
    "depts": ["部门A", "部门B", ...],
    "cells": {
      "部门A": {
        "华北": { "rate": 0.184, "diff": 2.9, "hasData": true }
      }
    },
    "totals": {
      "byDept": { "部门A": { "rate": 0.21, "diff": 1.5 } },
      "byRegion": { "华北": { "rate": 0.22, "diff": 3.1 } }
    }
  }
}
```

### 字段说明

- `regions`：列维度列表。
- `depts`：行维度列表。
- `cells[dept][region]`：单元格数据；`hasData=false` 表示无数据，前端显示空白灰格。
- `totals.byDept`：按部门聚合的小计行。
- `totals.byRegion`：按区域聚合的小计列。

## UI 设计

### 页面布局

在「部门维度签单毛利率（2026 vs 2025）」表格之后新增一个 panel：

```html
<section class="card" id="heatmapPanel">
  <h2>部门 × 区域 签单毛利率同比变化热力图</h2>
  <div class="table-responsive">
    <table id="heatmapTable" class="heatmap-table"></table>
  </div>
</section>
```

### 单元格设计

每个单元格渲染为双层：

```html
<td class="heat-cell heat-down-5">
  <div class="heat-rate">18.4%</div>
  <div class="heat-diff">+2.9pct</div>
</td>
```

### 颜色分档

按 `diff`（同比变化百分点）分档：

| diff 范围 | CSS 类 | 颜色 |
|-----------|--------|------|
| >= +20    | heat-up-20  | 深红 `#c92a2a` |
| +5 ~ +20  | heat-up-5   | 红 `#fa5252` |
| +2 ~ +5   | heat-up-2   | 浅红 `#ff8787` |
| -2 ~ +2   | heat-flat   | 黄 `#ffd43b` |
| -5 ~ -2   | heat-down-2 | 浅绿 `#69db7c` |
| -20 ~ -5  | heat-down-5 | 绿 `#40c057` |
| <= -20    | heat-down-20| 深绿 `#2b8a3e` |
| 无数据    | heat-empty  | 灰 `#343a40` |

### 表头与表尾

- 第一列固定为「部门」。
- 首行表头为区域名称；最后一列为「小计」。
- 首行行为「小计」行。

## 数据库改动

`indicator_metrics` 表结构不变。`run_etl_gross_margin()` 写入时新增 `dim_type='dept_region'` 的行。删除旧 ETL 记录逻辑保持原样（先按 `job_key='gross-margin'` 删除本 job 的记录，再重新写入）。

## 测试策略

- 在 `tests/test_gross.py` 中新增测试：
  - `test_etl_dept_region_rows`：验证 ETL 后 `dim_type='dept_region'` 记录存在。
  - `test_gross_metrics_dept_region`：验证 API 返回的 `dept_region_rows` 结构及数值计算正确。
- 前端不做自动化 UI 测试，通过手工截图验收。

## 回滚方案

- 回滚前端：删除 `gross.html` 中 `heatmapPanel` 及 `renderHeatmap` 相关代码；删除 `common.css` 中热力图样式。
- 回滚后端：删除 `run_etl_gross_margin` 中 `dept_region` 聚合逻辑与写入；删除 `gross_metrics` 中 `dept_region_rows` 构造逻辑。
- 数据库回滚：重新执行 ETL（此时不再生成 `dept_region` 记录）。
