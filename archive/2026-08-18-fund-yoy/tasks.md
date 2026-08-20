# 任务清单：资金占用同比分析（YoY）

- 变更编号：`20260818-fund-yoy` | 关联规格：CC-006 FR-13

## 后端

- [ ] T1.1 `backend/main.py` `fund_analyze`：主循环外初始化 `_global_cashflow = []`，每合同 `_cashflow` 构造后 `_global_cashflow.extend(_cashflow)`
- [ ] T1.2 `result['data']` 增加 `'flows': _global_cashflow`
- [ ] T1.3 快速回归：`POST /api/fund/analyze` 返回 `data.flows`，`len>0`，首元素结构正确

## 前端

- [ ] T2.1 `fundYoY(flows)` 同比口径计算函数（本期/上期/变化率/去年同期占用）
- [ ] T2.2 总览页 4 张同比 KPI 卡（替换原 3 张静态卡），含 `.yoy-up/.yoy-down/.yoy-flat` 样式与语义色
- [ ] T2.3 `fundChartMonthCompare(flows)` 月度同比对比图（2025 vs 2026 付款/回款 4 系列柱状图）
- [ ] T2.4 图表实例注册 `fundDimCharts['chartMonthCompare']`，加入 resize 集
- [ ] T2.5 验证趋势图付款/回款曲线恢复（依赖 flows 下发）

## 测试

- [ ] T3.1 `tests/test_fund_yoy.py`：`test_fund_analyze_has_flows`（# CC-006 FR-13）
- [ ] T3.2 `test_yoy_window_pay_recv`（构造 flows 验证窗口求和与变化率）
- [ ] T3.3 `test_yoy_prev_zero`（上期为 0 → 变化率 null）
- [ ] T3.4 `pytest -q` 全量通过

## 验收与归档

- [ ] T4.1 浏览器截图验证：总览页 KPI 卡与月度同比图渲染、趋势图付款/回款曲线
- [ ] T4.2 更新 `specs/TRACEABILITY.md`（登记变更 + 映射行）
- [ ] T4.3 delta 合并回 `specs/006-fund-analysis/spec.md`，变更目录移入 `archive/`
