# Design: 移除 AI 对话窗口（聊天）功能

> 变更编号: 20260817-remove-ai-chat | 规格: CC-007

## 设计决策

1. **纯删除、零重构**：聊天功能是独立功能块，直接删除代码，不引入替代实现，不影响 ETL/MCP 本体查询等保留能力。
2. **数据库保守处理**：`models.py` 中删除 `chat_messages` 建表语句；存量 SQLite 数据文件中已存在的 `chat_messages` 表不执行 DROP（避免影响已有数据与迁移复杂度），仅新库不再创建。
3. **import 处置**：
   - `main.py` 第 1322-1325 行是聊天区块的**局部重复 import**（`StreamingResponse`、`Form`、`asyncio`、`json`），随区块整体删除。
   - 顶部第 6-7 行公共 import（`Form`、`StreamingResponse`）保留，仍被 ETL/资金占用等路由使用；`asyncio` 经核实仅聊天区块使用，一并删除。
4. **前端联动**：`index.html` 内联 CSS 与 `common.css` 中的聊天样式、HTML 浮窗、JS 函数三处同步删除，避免残留死代码与无效引用。

## 文件改动清单

| 文件 | 改动 |
|------|------|
| `backend/chat_handler.py` | 删除整个文件 |
| `backend/main.py` | 删除 import 行与聊天 API 区块 |
| `backend/models.py` | 删除 chat_messages 建表 |
| `frontend/index.html` | 删除聊天 CSS/HTML/JS |
| `frontend/common.css` | 删除聊天样式块 |
| `specs/007-etl-chat/spec.md` | delta 移除聊天需求 |
| `specs/README.md` / `TRACEABILITY.md` | 同步 CC-007 描述 |
