# 提案：为 CC-004 报告导出补充测试覆盖

> 变更编号：`20260817-cc004-export-tests`
> 作者：SDD 体系搭建 | 日期：2026-08-17 | 状态：已批准

## 背景与问题

规格回填发现 `specs/TRACEABILITY.md` 中 CC-004（报告导出）无任何测试覆盖（TODO），违反"每个规格都有实现、每个实现都有测试"的追踪目标。同时规格初稿误写为"五 Sheet 结构"，经核对代码 `excel_handler.export_report` 实际为**双 Sheet 结构**（整改报告总览 + 异常明细），规格已同步修正。

## 目标

1. 新增 `tests/test_export.py`，覆盖 CC-004 的核心行为（双 Sheet 结构、总览数据、异常明细着色）
2. 消除 TRACEABILITY 矩阵中 CC-004 的测试缺口

## 变更范围

### In Scope

- 新增测试文件 `tests/test_export.py`
- 更新 `specs/TRACEABILITY.md`（CC-004 测试覆盖状态）
- 更新 `specs/004-report-export/spec.md`（修正 Sheet 数量描述、文件名规范，已并入本变更的 delta）

### Out of Scope

- 不修改 `excel_handler.py` 的导出逻辑（纯测试补充）
- 不改动其他规格

## 接口与数据契约

无接口变更。测试通过临时数据库（monkeypatch `models.DB_PATH`）与临时上传目录（monkeypatch `excel_handler.UPLOAD_DIR`）隔离运行。

## 涉及规格条目

- CC-004：MODIFIED（测试标准 TC-1/TC-2 指向新测试文件；行为描述修正为双 Sheet）

## 验收标准

- [x] `pytest tests/test_export.py` 全部通过
- [x] TRACEABILITY.md 中 CC-004 行不再为 TODO
- [x] 不修改任何既有测试与业务代码

## 风险与兼容性

- 低风险：测试使用临时 DB，不影响开发库数据
- 依赖：需环境已安装 `openpyxl`（excel_handler 本身依赖）
