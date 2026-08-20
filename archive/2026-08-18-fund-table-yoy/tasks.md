# 任务清单：资金占用表格增加同比分析与变化率

> 变更编号：`20260818-fund-table-yoy`

## 后端

- [x] T1: `fund_analyze` 主循环内计算每合同 `prev_occupy`（上年同日 FIFO），写入明细行 `'上年同期占用'`，并累加 `_grand_occupy_prev`
- [x] T2: `fund_metrics` 宽表 INSERT 增加 `prev_occupy` 字段
- [x] T3: `models.py` dim_cols 追加 `prev_occupy REAL DEFAULT 0`（幂等 ALTER TABLE）
- [x] T4: `/api/fund/metrics` `detail_rows` 透出 `'上年同期占用'`
- [x] T5: `_fund_dim_aggregate_inner` 聚合 `prev_occupy`（sum）并输出
- [x] T6: `fund_dim_drill` 清单行透出 `'上年同期占用'`

## 前端

- [x] T7: 明细表 `renderFundResult` 追加"上年同期占用""同比变化率"两列，变化率按占用语义着色
- [x] T8: 客户集合表格 `loadFundCustomer` 追加两列与着色

## 规格与测试

- [x] T9: `specs/006-fund-analysis/spec.md` FR-13 追加表格同比场景（delta MODIFIED）
- [x] T10: `tests/test_fund_yoy.py` 新增用例：明细行含"上年同期占用"、维度聚合含 `prev_occupy`、`fund_metrics` 透出
- [x] T11: 全量测试通过（pytest -q）
- [x] T12: 更新 `specs/TRACEABILITY.md`，变更目录归档至 `archive/2026-08-18-fund-table-yoy/`

## 验证清单

- [x] `POST /api/fund/analyze` 明细行含"上年同期占用"，且按合同加总 == `data.yoy.occupy_prev`
- [x] 前端明细表/客户集合表格渲染两列，升红降绿
- [x] 全量 pytest 通过
