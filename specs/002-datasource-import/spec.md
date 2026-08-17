# 数据源导入 Specification

> 规格编号: CC-002 | 状态: 生效 | 最后更新: 2026-08-17
> 对应代码: `backend/excel_handler.py`、`backend/main.py`（/api/datasource/*）

## Purpose

支持用户上传 Excel 格式的合同清单与供应商报价清单，通过列名模糊映射与智能列检测将异构表头规范化，并以"版本"机制保留导入历史，支撑"合同基准不可篡改、供应商可迭代"的比对原则。

## Requirements

### Requirement: 表头模糊映射

系统 SHALL 依据内置列名别名表（COLUMN_ALIASES）将异构表头映射到标准字段（device_name / device_model / specs_full / qty / unit / unit_price / amount / remark）。映射 SHALL 先清洗表头（去换行、去 4 字以上括号注释、转小写），再按"别名包含表头或表头包含别名"的双向包含规则匹配。

#### Scenario: 常见表头映射

- GIVEN 表头为 `设备名称`、`型号规格`、`数量`、`单价（元）`
- WHEN 执行列匹配（find_column）
- THEN `设备名称`→device_name、`型号规格`→device_model、`数量`→qty、`单价（元）`→unit_price，均匹配成功

#### Scenario: 表头清洗

- GIVEN 表头为 `品牌（如指定请填写）`
- WHEN 执行表头清洗（_clean_header）
- THEN 长括号注释被去除，清洗为 `品牌`

### Requirement: 智能列检测兜底

系统 SHALL 在标准匹配失败时启用四层兜底策略：device_name 取第一个非数字/非金额列、specs_full 取包含"参数/配置/描述/要求/技术/功能"的列、device_model 取包含"型号/规格/model"的列、qty 取第一个全数字列。兜底命中后 SHALL 生成列映射供用户核对。

#### Scenario: 兜底检测

- GIVEN 表头为 `品名|规格|采购量|报价`
- WHEN 标准映射无法识别 `品名` 与 `采购量`
- THEN 系统将 `品名` 兜底为 device_name、`采购量` 兜底为 qty

### Requirement: 导入版本留痕

系统 SHALL 为每次成功导入生成版本记录，保存供应商名称、导入时间、条目总数与各状态计数；新版本导入后系统 SHALL 支持版本查询（`GET /api/datasource/versions`）、最新版本获取（`GET /api/datasource/latest`）与指定版本删除（`DELETE /api/datasource/version/{table}/{version_id}`）。

#### Scenario: 版本历史

- GIVEN 供应商 B 先后上传两个版本的报价清单
- WHEN 查询该供应商的版本列表
- THEN 返回两个版本记录，且各自条目数与导入时间可区分

### Requirement: Excel 清洗与安全

系统 SHALL 在解析上传文件时删除敏感列（客户名称、客户简称、项目名称等），统一金额/数量单元格格式，并拒绝解析失败或格式非法的文件，返回明确错误信息。

#### Scenario: 敏感列清理

- GIVEN 上传的 Excel 包含 `客户名称`、`项目名称` 列
- WHEN 执行 sanitize 清洗
- THEN 解析后的数据不包含上述敏感列

### Requirement: 数据源表管理

系统 SHALL 支持列出可导入的数据源表（`GET /api/datasource/tables`），区分合同表与供应商表，供前端导入流程选择。

#### Scenario: 查询数据源表

- GIVEN 系统初始化了合同与供应商两类数据表
- WHEN 调用 `GET /api/datasource/tables`
- THEN 返回全部可用数据表及类型说明

## 非功能需求

- NFR-1：单次导入支持的最大行数 SHALL 不低于 1 万行
- NFR-2：导入解析失败 SHALL 返回可读错误，不写入任何部分数据

## 测试标准

- TC-1：列映射与兜底检测用例（对应 FR-1~FR-2），位置 `tests/test_excel.py`
- TC-2：版本留痕用例（对应 FR-3）
