# 合同管理 Specification

> 规格编号: CC-001 | 状态: 生效 | 最后更新: 2026-08-17
> 对应代码: `backend/models.py`、`backend/main.py`（/api/contracts、/api/contract/*）

## Purpose

管理合同主数据，提供多合同创建、查询、更新、删除与数据隔离能力，作为比对系统的**唯一权威基准**来源。同一系统可同时管理多个独立合同，各合同数据互不干扰。

## Requirements

### Requirement: 合同创建与基础校验

系统 SHALL 支持创建合同，其中合同名称（contract_name）为必填项，合同编号、签约日期、合同总金额为可选项，创建时合同状态默认为 `未上传基准`。

#### Scenario: 创建合同

- GIVEN 用户提供合同名称"XX 项目采购合同"
- WHEN 调用 `POST /api/contracts`
- THEN 系统创建合同并返回合同对象，状态为 `未上传基准`

### Requirement: 合同查询与过滤

系统 SHALL 支持按关键字（keyword）与状态（status）过滤查询合同列表，返回每个合同的名称、编号、状态与最新比对进度。

#### Scenario: 按状态查询合同

- GIVEN 系统中存在状态为 `比对中` 和 `已完成` 的多个合同
- WHEN 以 `status=比对中` 查询 `GET /api/contracts`
- THEN 仅返回状态为 `比对中` 的合同列表

### Requirement: 合同更新与删除

系统 SHALL 支持更新合同基本信息，且 SHALL 支持删除合同；删除合同 SHALL 级联清理该合同下全部关联数据（合同条目、供应商条目、比对结果、版本记录），避免残留脏数据。

#### Scenario: 删除合同级联清理

- GIVEN 合同 A 已上传合同条目、供应商报价并执行过比对
- WHEN 调用 `DELETE /api/contracts/A`
- THEN 合同 A 及其全部条目、比对结果、版本记录均被删除，其他合同数据不受影响

### Requirement: 合同状态机

系统 SHALL 依据合同数据就绪程度维护状态流转：`未上传基准`（创建后默认）→ 上传合同条目后进入 `已上传基准` → 上传供应商报价并比对后进入 `比对中` → 全部条目确认且无未处理异常时进入 `已完成`。

#### Scenario: 状态流转

- GIVEN 新合同处于 `未上传基准`
- WHEN 用户上传合同清单 Excel 并完成解析
- THEN 合同状态更新为 `已上传基准`

### Requirement: 多合同数据隔离

系统 SHALL 通过 contract_id 对合同条目、供应商条目、比对结果、版本进行隔离，任何查询与操作 SHALL 限定在指定合同范围内，不允许跨合同读取或修改数据。

#### Scenario: 跨合同隔离

- GIVEN 合同 A 与合同 B 均存在合同条目
- WHEN 查询合同 A 的条目（`GET /api/contract/A/items`）
- THEN 结果仅包含合同 A 的条目，不包含合同 B 的任何数据

### Requirement: 合同统计

系统 SHALL 提供单合同统计（`GET /api/contract/{contract_id}/stats`）与全局统计（`GET /api/stats`），返回合同条目数、比对进度、各状态分布等汇总指标。

#### Scenario: 查看合同统计

- GIVEN 合同 A 已完成比对
- WHEN 调用 `GET /api/contract/A/stats`
- THEN 返回合同 A 的条目总数、匹配成功数、异常数、待采购数、增项数与整体进度

## 非功能需求

- NFR-1：合同相关接口响应时间 SHALL 小于 2 秒
- NFR-2：删除操作 SHALL 具备事务性，级联清理失败时不得留下半删除状态

## 测试标准

- TC-1：合同创建/查询/更新/删除用例（对应 FR-1~FR-3），位置 `tests/test_smoke.py`、`tests/test_app.py`
- TC-2：状态机流转用例（对应 FR-4）
