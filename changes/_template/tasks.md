# 任务清单：<变更标题>

> 变更编号：`YYYYMMDD-<slug>`
> 任务粒度建议：每项 1-2 小时完成；标注优先级 [P0]/[P1]/[P2]

## 前置

- [ ] 更新 delta 规格 `specs/<domain>/spec.md`（ADDED/MODIFIED/REMOVED）
- [ ] 人工评审 proposal 与 delta 规格

## 实现

- [ ] [P0] <任务描述>（对应 `CC-00X FR-x`）
- [ ] [P1] <任务描述>（对应 `CC-00X FR-x`）

## 测试

- [ ] 补充/更新测试用例，标注规格编号（如 `tests/test_xxx.py::test_yyy # CC-003 FR-2.3`）
- [ ] 全量回归：`cd contract-compare && pytest -q`

## 收尾

- [ ] 更新 `specs/TRACEABILITY.md` 追踪矩阵
- [ ] 归档：变更目录移入 `archive/YYYY-MM-DD-<slug>/`，delta 合并回 `specs/` 主规格
