# ETL 调度 Specification

> 规格编号: CC-007 | 状态: 生效 | 最后更新: 2026-08-17
> 对应代码: `backend/main.py`（/api/etl/*、/api/mcp/ontology/*）

## Purpose

提供 ETL 任务调度管理（任务列表、运行、启停、指标）并开放 MCP 本体查询接口供 Agent 使用，形成"数据加工 + Agent 数据感知"的一体化能力。

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

## 测试标准

- TC-1：ETL 任务启停用例（对应 FR-1），位置 `tests/test_etl.py`
