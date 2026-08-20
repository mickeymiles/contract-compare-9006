# 设计：资金占用表格增加同比分析与变化率

> 变更编号：`20260818-fund-table-yoy`
> 日期：2026-08-18 | 状态：已评审

## 技术方案

复用 FR-13 已有的 `_fifo_occupy_upto(payments, collections, cutoff)` 精确重放函数：

1. **后端口径统一**：`fund_analyze` 主循环内把上年同日 cutoff 的 FIFO 占用先算到局部变量 `prev_occupy`，既累加进 `_grand_occupy_prev`（总览 KPI），也写入明细行 `'上年同期占用'`，保证两者口径完全一致。
2. **宽表落库**：`fund_metrics` 增加 `prev_occupy REAL DEFAULT 0` 列（models.py dim_cols 追加，`ALTER TABLE` 幂等兼容旧库）；INSERT 语句同步加字段。
3. **读路径透出**：`/api/fund/metrics` 的 `detail_rows`、`_fund_dim_aggregate_inner` 聚合行的 `prev_occupy`（sum）、`fund_dim_drill` 清单行透出该字段。
4. **前端**：
   - 明细表（`renderFundResult`）：`data.columns` 遍历后追加"上年同期占用""同比变化率"两个表头；每行按 `row['上年同期占用']` 计算 `pct` 渲染变化率单元格。
   - 客户集合表格（`loadFundCustomer`）：表头追加两列，`x.prev_occupy` 参与计算。
   - 着色规则（占用语义色，与 `yoyCard` kind='semantic' 一致）：`pct>0` 红 `#ff4d4f`（↥）、`pct<0` 绿 `#52c41a`（↧）、`pct==0` 中性灰（—）；`prev==0&&cur>0` 显示"新增占用"红色；双零显示 `—`。
5. **导出兜底**：旧快照/旧宽表缺 `prev_occupy` 时读路径 `or 0` 兜底，前端 `prev=0` 分支安全。

## 涉及文件

| 文件 | 改动说明 |
|------|----------|
| `backend/main.py` | `fund_analyze` 计算并写入 `上年同期占用`；INSERT 宽表加 `prev_occupy`；`fund_metrics`/`_fund_dim_aggregate_inner`/`fund_dim_drill` 透出 |
| `backend/models.py` | `dim_cols` 追加 `prev_occupy REAL DEFAULT 0`（幂等迁移） |
| `frontend/index.html` | 明细表与客户集合表格新增两列与着色逻辑 |
| `specs/006-fund-analysis/spec.md` | FR-13 追加表格同比场景 |
| `tests/test_fund_yoy.py` | 新增明细行/维度聚合/宽表字段用例 |

## 数据模型变更

```sql
-- 幂等迁移（models.py dim_cols 循环 ALTER TABLE ADD COLUMN）
ALTER TABLE fund_metrics ADD COLUMN prev_occupy REAL DEFAULT 0;
```

## 兼容性说明

- 旧库自动补列，新库建表即含列。
- `/api/fund/analyze/export` 导出列不变（不导出同比列）。
- 前端对缺失字段有 `or 0`/`prev=0` 分支，旧快照不报错。
