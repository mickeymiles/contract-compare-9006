# 报告导出 Specification

> 规格编号: CC-004 | 状态: 生效 | 最后更新: 2026-08-17
> 对应代码: `backend/excel_handler.py`（export_report）、`backend/main.py`（/api/contract/*/export/report）

## Purpose

将指定版本的比对结果导出为 Excel 整改报告，供采购与供应商核对整改。报告以多 Sheet 结构组织，覆盖整改总览、异常明细、待采购漏报、供应商增项与完整明细，并按状态着色便于快速识别问题。

## Requirements

### Requirement: 报告导出入口

系统 SHALL 提供 `GET /api/contract/{contract_id}/export/report?version_id={version_id}` 导出指定版本的整改报告，返回 xlsx 文件，文件名 SHALL 为 `整改报告_v{version_id}.xlsx`。

#### Scenario: 导出报告

- GIVEN 合同 A 存在已完成比对的版本 v2
- WHEN 调用导出接口并指定 version_id=v2
- THEN 返回文件名为 `整改报告_v2.xlsx` 的 Excel 文件

### Requirement: 双 Sheet 结构

系统 SHALL 将报告组织为两个 Sheet：整改报告总览、异常明细，顺序固定。

#### Scenario: Sheet 齐全

- GIVEN 导出报告成功
- THEN 文件内包含上述两个 Sheet，且顺序为总览在前、异常明细在后

### Requirement: 总览页内容

系统 SHALL 在"整改报告总览"Sheet 中呈现：版本号、上传时间、总条目数、成功匹配数、匹配异常数、待采购漏报数、供应商增项数、整体采购进度，以及基于异常分布生成的整改提示文本。

#### Scenario: 总览数据

- GIVEN 版本含 10 条条目，其中成功 8、异常 1、待采购 1
- WHEN 查看总览 Sheet
- THEN 显示总条目 10、成功 8、异常 1、待采购 1、增项 0、进度与整改提示

### Requirement: 异常明细页

系统 SHALL 在"异常明细"Sheet 中按状态列出全部比对条目：设备名称、型号规格、合同数量、报价数量、合同参数、报价参数、异常类型与异常详情，并按状态着色（匹配异常橙色、待采购红色、供应商增项紫色）；待采购与供应商增项条目以同一 Sheet 承载，通过字体颜色区分。

#### Scenario: 异常着色

- GIVEN 某条结果状态为【匹配异常】、异常类型为【数量少报异常】
- WHEN 查看异常明细 Sheet
- THEN 该行以橙色字体呈现，且异常类型列显示"数量少报异常"

#### Scenario: 待采购着色

- GIVEN 某条结果状态为【待采购】
- WHEN 查看异常明细 Sheet
- THEN 该行以红色字体呈现，与匹配异常行可区分

### Requirement: 报表格式规范

系统 SHALL 统一报表样式：微软雅黑字体、深色表头底纹、自动列宽、金额列千分位格式、单元格对齐统一。

#### Scenario: 样式统一

- GIVEN 任意导出报告
- THEN 所有 Sheet 表头样式、字体、列宽策略一致

## 非功能需求

- NFR-1：报告导出 SHALL 在 10 秒内完成（单版本 1 万条目以内）
- NFR-2：导出的 xlsx SHALL 可被 Excel/WPS 正常打开，无损坏

## 测试标准

- TC-1：双 Sheet 结构与总览数据用例（对应 FR-1~FR-3），位置 `tests/test_export.py`
- TC-2：异常明细着色用例（对应 FR-4~FR-5）
