# AGENTS.md — contract-compare 工程规则

> 本文件为工程级规则，**根级 `../AGENTS.md` 的 SDD 铁律在本工程同样适用且优先**。进入本工程前必读。

## 1. 工程简介

合同比对系统（FastAPI + SQLite）。核心流程：导入合同 Excel → 双源数据比对 → 生成整改报告，并包含回款周期/资金占用分析、ETL 调度与聊天接口。

## 2. 代码结构速览

| 目录/文件 | 职责 |
|-----------|------|
| `backend/main.py` | FastAPI 入口，49 个路由（比对/回款/资金/聊天/ETL/MCP） |
| `backend/models.py` | 数据模型（合同主表、比对结果等） |
| `backend/excel_handler.py` | Excel 导入与列映射 |
| `backend/compare_engine.py` | 双向比对引擎 |
| `docs/` | 既有功能文档（`features.md`、`compare-rules.md`）——规格回填素材来源 |
| `tests/` | 测试（冒烟/引擎/Excel） |
| `frontend/`、`static/` | 前端页面与资源 |

## 3. 规格索引（详见 `specs/README.md`）

| 编号 | 模块 | 编号 | 模块 |
|------|------|------|------|
| CC-001 | 合同管理 | CC-005 | 回款周期分析 |
| CC-002 | 数据源导入 | CC-006 | 资金占用分析 |
| CC-003 | 比对引擎 | CC-007 | ETL 调度与聊天 |
| CC-004 | 报告导出 | | |

## 4. 本工程约定

- 规格编号前缀：`CC-`，如 `CC-003 FR-2.3`
- 变更目录：`changes/YYYYMMDD-<slug>/`，模板见 `changes/_template/`
- 归档目录：`archive/YYYY-MM-DD-<slug>/`
- 测试命令：`cd contract-compare && pytest -q`
- 比对规则细节以 `docs/compare-rules.md` 为准（规格 CC-003 与其保持一致）

## 5. 修改指引

1. 定位涉及模块 → 阅读对应 `specs/<编号>-<module>/spec.md`
2. 按根级 AGENTS.md 的 SDD 铁律建立变更提案
3. 实现时保持与既有规格一致；如需求变化，走 delta 流程
4. 运行 `pytest -q` 回归，更新 `specs/TRACEABILITY.md`
