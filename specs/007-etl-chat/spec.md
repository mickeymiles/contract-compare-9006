# ETL 调度与聊天 Specification

> 规格编号: CC-007 | 状态: 生效 | 最后更新: 2026-08-17
> 对应代码: `backend/main.py`（/api/etl/*、/api/chat/*、/api/mcp/ontology/*）

## Purpose

提供 ETL 任务调度管理（任务列表、运行、启停、指标）与基于合同数据的对话能力（消息发送、历史查询、SSE 流式响应），并开放 MCP 本体查询接口供 Agent 使用，形成"数据加工 + 自然语言交互"的一体化能力。

## Requirements

### Requirement: ETL 任务管理

系统 SHALL 提供 ETL 任务列表（`GET /api/etl/jobs`）、任务详情（`GET /api/etl/jobs/{job_key}`）、单次运行（`POST /api/etl/run/{job_key}`）、定时启动（`POST /api/etl/jobs/{job_key}/start`）与停止（`POST /api/etl/jobs/{job_key}/stop`）能力。

#### Scenario: 启停 ETL 任务

- GIVEN 存在 ETL 任务 `sync-contract`
- WHEN 调用 start 启动、随后调用 stop 停止
- THEN 任务状态在运行中与已停止之间切换，且状态可查询

### Requirement: ETL 指标查询

系统 SHALL 提供 ETL 指标查询（`GET /api/etl/metrics`），支持按 job_key、metric_name、dim_type 过滤，返回任务运行指标。

#### Scenario: 按任务查指标

- GIVEN 已运行 ETL 任务 `sync-contract`
- WHEN 以 job_key=sync-contract 查询指标
- THEN 返回该任务的处理量、耗时、成功率等指标

### Requirement: MCP 本体查询

系统 SHALL 提供数据表清单（`GET /api/mcp/ontology/tables`）与表结构查询（`GET /api/mcp/ontology/schema?table_name=xxx`），供外部 Agent 感知系统数据结构。

#### Scenario: 查询表结构

- GIVEN 系统存在 contracts 表
- WHEN 调用 `GET /api/mcp/ontology/schema?table_name=contracts`
- THEN 返回 contracts 表的字段名、类型与说明

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

## 非功能需求

- NFR-1：SSE 首包响应 SHALL 在 3 秒内到达
- NFR-2：聊天消息 SHALL 持久化，重启服务后历史不丢失

## 测试标准

- TC-1：ETL 任务启停用例（对应 FR-1），位置 `tests/test_etl.py`
- TC-2：聊天发送与历史查询用例（对应 FR-4~FR-5），位置 `tests/test_chat.py`
