# Proposal: 移除 AI 对话窗口（聊天）功能

> 变更编号: 20260817-remove-ai-chat | 日期: 2026-08-17 | 规格: CC-007

## 背景与动机

contract-compare 系统前端右下角提供「AI 对话窗口」（小欢欢），通过 `/api/chat/send`、`/api/chat/messages`、`/api/chat/stream` 三个接口实现网页消息存储与 SSE 流式推送。该功能依赖飞书桥接（`chat_handler.py` 调用 `hermes -z`）且与核心合同比对业务无关，用户决定移除对话窗口相关功能。

## 变更范围

### REMOVED（功能移除）

1. **后端聊天 API**：`backend/main.py` 中 `/api/chat/send`、`/api/chat/messages`、`/api/chat/stream` 三个路由及其局部 import（`StreamingResponse`、`Form`、`asyncio`、`json` 的局部重复 import）。
2. **后端聊天处理器**：删除 `backend/chat_handler.py`（消息持久化、飞书转发、SSE 监听器注册/注销）。
3. **数据库表**：`backend/models.py` 中 `chat_messages` 建表语句（表结构定义移除；存量数据库文件不动）。
4. **前端对话窗口**：
   - `frontend/index.html`：聊天浮窗 CSS（`.chat-btn`、`.chat-panel` 及 `.cp-*` 系列）、HTML 浮窗结构（`#chatBtn`、`#chatPanel`）、JS 聊天功能（`toggleChat`、`loadChatHistory`、`addChatMsg`、`connectSSE`、`sendChat`）。
   - `frontend/common.css`：聊天浮窗样式块（`.chat-btn`、`.chat-panel`、`.cp-*`、`@keyframes pulse/breathe/drawerIn`）。

### MODIFIED（规格同步）

- `specs/007-etl-chat/spec.md`：移除「消息发送」「历史消息查询」「SSE 流式响应」三个 Requirement、NFR-1/NFR-2、TC-2；模块名与对应代码描述同步去掉 `/api/chat/*`。
- `specs/README.md`、`specs/TRACEABILITY.md`：CC-007 描述去掉 `/api/chat/*`。

## 明确不移除

- MCP 本体查询接口（`/api/mcp/ontology/*`）保留，属于 ETL 能力。
- ETL 任务管理、指标查询全部保留。
- 顶部已存在的公共 import（`Form`、`StreamingResponse`）保留，因其被 ETL/导出等其他路由使用（第 6-7 行与第 843 行）。

## 影响评估

- `chat_handler.py` 仅被 `main.py` 第 18 行引用，无其他调用方。
- 聊天功能为独立浮窗，与合同管理、比对、导出、ETL 页面无耦合。
- 无 `tests/test_chat.py`（TC-2 仅为占位），移除不破坏既有测试。

## 验收标准

1. `backend/main.py` 无 `chat` 相关路由与 import，服务可正常启动。
2. 前端无聊天浮窗入口与相关 JS/CSS。
3. `python3 -m pytest -q` 全量通过（基线 49 通过）。
4. specs/README.md、TRACEABILITY.md 同步更新。
