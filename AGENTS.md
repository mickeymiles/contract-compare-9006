# AGENTS.md — contract-compare 工程规则

> 本文件为工程级规则，**根级 `../AGENTS.md` 的 SDD 铁律在本工程同样适用且优先**。进入本工程前必读。

## 1. 工程简介

合同比对系统（FastAPI + SQLite）。核心流程：导入合同 Excel → 双源数据比对 → 生成整改报告，并包含回款周期/资金占用分析、ETL 调度与 MCP 本体查询接口。

## 2. 代码结构速览

| 目录/文件 | 职责 |
|-----------|------|
| `backend/main.py` | FastAPI 入口，100+ 路由（比对/回款/资金/ETL/MCP/备件采购/项目全生命周期） |
| `backend/models.py` | 数据模型（合同主表、比对结果等） |
| `backend/excel_handler.py` | Excel 导入与列映射 |
| `backend/compare_engine.py` | 双向比对引擎 |
| `backend/procurement_models.py` | 备品备件采购询比价数据层（运维管理分区） |
| `backend/plm_models.py` | 项目全生命周期数据层与业务计算（CC-010：四算基线/PMO 双进度/人力工时/预警/报表） |
| `docs/` | 既有功能文档（`features.md`、`compare-rules.md`）——规格回填素材来源 |
| `tests/` | 测试（冒烟/引擎/Excel） |
| `frontend/index.html` | 工作台门户（经营管理 / 运维管理 双分区）+ 合同比对工作区 |
| `frontend/plm.html` / `plm.app.js` | 项目全生命周期管理（左侧菜单树 + 元数据驱动 CRUD） |
| `frontend/procurement.html` / `procurement.app.js` | 备品备件采购询比价 |
| `frontend/common.css` | 全站统一主题（9007 monitor 风格），含门户分区样式 |

## 3. 规格索引（详见 `specs/README.md`）

| 编号 | 模块 | 编号 | 模块 |
|------|------|------|------|
| CC-001 | 合同管理 | CC-005 | 回款周期分析 |
| CC-002 | 数据源导入 | CC-006 | 资金占用分析 |
| CC-003 | 比对引擎 | CC-007 | ETL 调度 |
| CC-004 | 报告导出 | CC-008 | 签单毛利率热力图 |
| CC-009 | 门户双分区导航 | CC-010 | 项目全生命周期管理 |

## 4. 本工程约定

- 规格编号前缀：`CC-`，如 `CC-003 FR-2.3`
- 变更目录：`changes/YYYYMMDD-<slug>/`，模板见 `changes/_template/`
- 归档目录：`archive/YYYY-MM-DD-<slug>/`
- 测试命令：`cd contract-compare && pytest -q`
- 比对规则细节以 `docs/compare-rules.md` 为准（规格 CC-003 与其保持一致）
- **新增业务域必须命名空间导入**（`import xxx_models as xxx`）：历史上 `from procurement_models import create_contract` 覆盖了 `models.py` 同名函数，迫使 `/api/contracts` 走 `import contract_models` 兜底
- 若既有代码无法整体命名空间化（如 `procurement_models` 的 40+ 符号导入），**至少对跨域同名函数做前缀别名**（`create_contract as proc_create_contract`），并在导入处写明原因；`/api/contracts` 曾因遮蔽引用不存在的 `contract_models` 而长期 500
- 门户新增卡片按职责归入「经营管理」或「运维管理」分区；分区卡片数由 `initZoneCounts()` 自动统计，勿写死
- 页面内子功能导航统一使用**左侧菜单树**（一级模块 + 二级叶子，手风琴展开），不使用横向 Tab 页
- 新增前端页面或静态资源时，把路径加进 `main.py` 的 `NO_CACHE_PATHS`（`.css`/`.js` 已被后缀兜底）；否则发版后用户需强制刷新才能看到新样式（CC-011）

## 5. 修改指引

1. 定位涉及模块 → 阅读对应 `specs/<编号>-<module>/spec.md`
2. 按根级 AGENTS.md 的 SDD 铁律建立变更提案
3. 实现时保持与既有规格一致；如需求变化，走 delta 流程
4. 运行 `pytest -q` 回归，更新 `specs/TRACEABILITY.md`
