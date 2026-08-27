# 任务清单：修复合同域符号遮蔽

- [x] 审计三个数据域的导出碰撞（models ∩ procurement = create_contract / delete_contract / get_db）
- [x] 确认 `get_db` 未被采购导入块引入，无需处理
- [x] 采购导入块对 2 个碰撞名做 `proc_` 别名
- [x] 采购侧 2 处调用点改别名
- [x] 遗留路由去掉 `import contract_models` 兜底，补空名 400 校验
- [x] 新增 `tests/test_contract_domain.py`（7 条，含遮蔽守卫与三域隔离）
- [x] 全量回归 133 passed / 10 skipped，ruff 0 错误
- [x] 归档：`archive/2026-08-27-fix-contract-symbol-shadowing/`，同步 TRACEABILITY 与 AGENTS.md
