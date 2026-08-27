# 归档区（Archive）— contract-compare

> 已完成的变更按 `archive/YYYY-MM-DD-<slug>/` 归档留档。
> 归档时 delta 增量已合并回 `../specs/` 主规格，本目录仅保存变更历史（proposal/design/tasks/delta）。

## 归档记录

| 归档日期 | 变更编号 | 标题 | 涉及规格 |
|----------|----------|------|----------|
| 2026-08-17 | 20260817-cc004-export-tests | CC-004 报告导出补充测试覆盖（修正规格为双 Sheet） | CC-004 |
| 2026-08-17 | 20260817-cc005-payment-cycle-tests | CC-005 回款周期分析补充测试覆盖 | CC-005 |
| 2026-08-18 | 20260818-fund-multidim | 资金占用多维度分析与预警：维度关联、四级风险预警（阈值可配置）、趋势预警、穿透下钻、10 张 ECharts 图表与导出 | CC-006 |
| 2026-08-17 | 20260817-remove-ai-chat | 移除 AI 对话窗口（删 /api/chat/*、chat_handler、chat_messages 表与前端浮窗） | CC-007（改名） |
| 2026-08-18 | 20260818-fund-yoy | 资金占用同比（YoY）：FIFO 精确计算上年同期占用、4 张同比 KPI 卡与月度同比图 | CC-006 FR-13 |
| 2026-08-18 | 20260818-fund-table-yoy | 资金占用表格同比：新增上年占用与变化率两列 | CC-006 FR-13 |
| 2026-08-20 | 2026-08-20-gross-heatmap | 签单毛利率部门 × 区域二维热力图（ETL `dept_region` 聚合 + 8 档配色 + 小计行列） | CC-008 |
| 2026-08-27 | 2026-08-27-portal-zones | 工作台首页拆分「经营管理 / 运维管理」双分区；`ALL_PAGES` + `showPage()` 收敛页切换 | CC-009 |
| 2026-08-27 | 2026-08-27-static-asset-cache | 页面与静态资源改为每次再校验（no-cache + 304 短路），消除发版后需强制刷新与新旧资源混搭 | CC-011 |
| 2026-08-27 | 2026-08-27-fix-contract-symbol-shadowing | 修复采购域同名导入遮蔽 `models.create_contract/delete_contract`，导致前端「新建合同」`POST /api/contracts` 稳定 500（兜底引用的 `contract_models` 模块并不存在）；改为 `proc_` 别名并补 7 条回归 | CC-001 FR-1/FR-2/FR-3 |
| 2026-08-27 | 2026-08-27-ci-httpx-dep | 补齐 `httpx` 测试依赖：CI 的 Run tests 因 TestClient 缺依赖连续 3 次红、deploy 从未执行；修复后恢复 push→自动部署 | —（工程维护） |
| 2026-08-27 | 2026-08-27-project-lifecycle | 新增项目全生命周期管理大模块（四算基线 / 联动立项 / PMO 双进度 / 人力工时 / 成本毛利 / 7 板块全景 / 多维预警 / 5 类报表 / 左侧菜单树） | CC-010 |

## 规则

- 归档目录只读，不再修改
- 归档内容与 `specs/` 主规格、`TRACEABILITY.md` 保持同步
- 如需追溯历史决策，查阅对应归档目录
