# Delta Spec：CC-007 移除 AI 对话（聊天）功能

> 变更编号: 20260817-remove-ai-chat

## ADDED Requirements

无。

## MODIFIED Requirements

无新增修改（CC-007 主规格中仅移除聊天相关 Requirement，见 REMOVED）。

## REMOVED Requirements

### Requirement: 消息发送

系统 SHALL 支持发送对话消息（`POST /api/chat/send`，字段 message、contract_id），将消息关联到指定合同上下文并持久化。

#### Scenario: 发送消息

- GIVEN 用户输入"帮我比对雷神项目"并指定 contract_id=1
- WHEN 调用发送接口
- THEN 消息被持久化并关联到合同 1

### Requirement: 历史消息查询

系统 SHALL 支持按合同查询历史消息（`GET /api/chat/messages?contract_id=&since_id=`），支持增量拉取（since_id 之后的新消息）。

#### Scenario: 增量拉取

- GIVEN 合同 1 已有 5 条消息
- WHEN 以 since_id=3 查询
- THEN 返回第 4、5 条消息

### Requirement: SSE 流式响应

系统 SHALL 提供 SSE 流式对话（`GET /api/chat/stream`），在消息发送后通过 SSE 事件流推送"思考过程 → 工具调用 → 最终回答"的渐进式响应。

#### Scenario: 流式输出

- GIVEN 用户发送一条查询消息
- WHEN 客户端订阅 SSE 流
- THEN 客户端按序收到 agent_thought、tool_call（如适用）、agent_message、message_end 事件

## REMOVED 非功能需求

- NFR-1：SSE 首包响应 SHALL 在 3 秒内到达
- NFR-2：聊天消息 SHALL 持久化，重启服务后历史不丢失

## REMOVED 测试标准

- TC-2：聊天发送与历史查询用例（对应 FR-4~FR-5），位置 `tests/test_chat.py`
