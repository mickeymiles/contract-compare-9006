# 任务清单：CC-004 报告导出测试

> 变更编号：`20260817-cc004-export-tests`

## 前置

- [x] 评审 proposal（范围：纯测试补充，不改业务逻辑）
- [x] 核对 `excel_handler.export_report` 真实行为（双 Sheet，修正规格初稿的"五 Sheet"误写）

## 实现

- [x] [P0] 新增 `tests/test_export.py`：export_env fixture（临时 DB + 临时上传目录）
- [x] [P0] 用例一：双 Sheet 结构（对应 CC-004 FR-2）
- [x] [P0] 用例二：总览数据（版本号/条目数/各状态计数/进度，对应 CC-004 FR-3）
- [x] [P1] 用例三：异常明细着色与异常类型（对应 CC-004 FR-4/FR-5）

## 测试

- [x] 本地回归：`pytest tests/test_export.py -q` 通过
- [x] 全量回归：`pytest -q`（无既有用例被破坏）

## 收尾

- [x] 更新 `specs/TRACEABILITY.md`：CC-004 从 TODO 改为已覆盖
- [x] 归档：变更目录移入 `archive/2026-08-17-cc004-export-tests/`，delta 合并回主规格
