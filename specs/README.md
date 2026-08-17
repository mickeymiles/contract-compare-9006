# 规格库（Specs）— contract-compare

> 本目录是 contract-compare 系统行为规范的**单一事实源**（Single Source of Truth）。
> 遵循 OpenSpec（Fission-AI 开源 SDD 框架）规范模型：
> `## Purpose`（能力解决什么问题）+ `### Requirement: xxx`（SHALL/MUST/SHOULD，RFC 2119）+ `#### Scenario: xxx`（GIVEN/WHEN/THEN 可验证场景）。

## 规格索引

| 编号 | 模块 | 状态 | 最后更新 | 对应代码/文档 |
|------|------|------|----------|----------------|
| CC-001 | 合同管理 | 生效 | 2026-08-17 | `backend/models.py`、`/api/contracts`、`/api/contract/*` |
| CC-002 | 数据源导入 | 生效 | 2026-08-17 | `backend/excel_handler.py`、`/api/datasource/*` |
| CC-003 | 比对引擎 | 生效 | 2026-08-17 | `backend/compare_engine.py`、`docs/compare-rules.md` |
| CC-004 | 报告导出 | 生效 | 2026-08-17 | `backend/excel_handler.py`(export_report)、`/api/contract/*/export/report` |
| CC-005 | 回款周期分析 | 生效 | 2026-08-17 | `/api/analysis/payment-cycle*`、`/api/payment-cycle/metrics` |
| CC-006 | 资金占用分析 | 生效 | 2026-08-17 | `/api/fund/*` |
| CC-007 | ETL 调度 | 生效 | 2026-08-17 | `/api/etl/*`、`/api/mcp/ontology/*` |

## 状态定义

- **规划中**：模块已列入规格计划，尚未回填
- **回填中**：正在依据存量代码提炼行为规格
- **生效**：规格已与代码行为对齐，作为开发契约
- **已废弃**：该功能已被移除或合并，规格仅作历史参考

## 规范约定

- 规格是**行为合同**，不是实现说明书：类名、框架选型、具体文件路径不写入 spec.md
- 需求语气词遵循 RFC 2119：`SHALL`（必须）/ `MUST`（绝对要求）/ `SHOULD`（建议）
- 每个 Requirement 至少配一个 GIVEN/WHEN/THEN Scenario
- 需求编号：`FR-x`（功能需求）、`NFR-x`（非功能需求）、`TC-x`（测试标准）
- 规格变更必须走 `changes/` 提案流程，delta 合并回本目录，禁止直接改主规格

## 追踪

规格 ↔ 代码 ↔ 测试的映射见 [TRACEABILITY.md](./TRACEABILITY.md)（规格回填完成后维护）。
