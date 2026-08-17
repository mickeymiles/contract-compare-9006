# 报告导出 Specification（delta 增量）

> 变更编号：`20260817-cc004-export-tests` | 类型：delta | 目标主规格：`specs/004-report-export/spec.md`

## MODIFIED Requirements

### Requirement: 报告导出入口

原描述补正导出文件名：系统 SHALL 提供 `GET /api/contract/{contract_id}/export/report?version_id={version_id}` 导出指定版本的整改报告，返回 xlsx 文件，文件名 SHALL 为 `整改报告_v{version_id}.xlsx`。

### Requirement: 双 Sheet 结构

原"五 Sheet 结构"为规格初稿误写，更正为：系统 SHALL 将报告组织为两个 Sheet：整改报告总览、异常明细，顺序固定。

### Requirement: 异常明细页

更正为：系统 SHALL 在"异常明细"Sheet 中按状态列出全部比对条目，按状态着色（匹配异常橙色、待采购红色、供应商增项紫色）；待采购与供应商增项条目以同一 Sheet 承载，通过字体颜色区分。

## ADDED Requirements

（无新增行为需求；测试标准 TC-1/TC-2 已指向新增测试文件 `tests/test_export.py`）

## REMOVED Requirements

（无删除）
