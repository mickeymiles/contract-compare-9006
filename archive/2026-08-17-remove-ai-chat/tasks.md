# Tasks: 移除 AI 对话窗口（聊天）功能

> 变更编号: 20260817-remove-ai-chat | 规格: CC-007

## 任务清单

- [x] T1 删除 `backend/chat_handler.py`
- [x] T2 移除 `backend/main.py`：第 18 行 `from chat_handler import ...`、第 1320-1370 行聊天 API 区块（含局部 import）
- [x] T3 移除 `backend/models.py` 第 160-170 行 `chat_messages` 建表语句
- [x] T4 移除 `frontend/index.html`：第 50-71 行聊天 CSS、第 680-697 行聊天浮窗 HTML、第 1081-1131 行聊天 JS
- [x] T5 移除 `frontend/common.css` 第 105-130 行聊天浮窗样式块
- [x] T6 更新 `specs/007-etl-chat/spec.md`（移除聊天 Requirement/NFR/TC）
- [x] T7 更新 `specs/README.md`、`specs/TRACEABILITY.md`、工程 AGENTS.md、测试注释
- [x] T8 全量测试 `python3 -m pytest -q` 通过（49 passed）
- [ ] T9 归档变更到 `archive/2026-08-17-remove-ai-chat/` 并合并 delta
