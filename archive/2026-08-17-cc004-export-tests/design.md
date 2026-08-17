# 设计：CC-004 报告导出测试

> 变更编号：`20260817-cc004-export-tests`
> 日期：2026-08-17 | 状态：已评审

## 技术方案

测试直接调用 `excel_handler.export_report(version_id)`，通过 fixture 隔离运行环境：

1. `monkeypatch.setattr(models, 'DB_PATH', 临时文件)` 与 `monkeypatch.setattr(models, 'DB_DIR', 临时目录)` → `models.init_db()` 建临时库
2. `monkeypatch.setattr(excel_handler, 'UPLOAD_DIR', 临时目录)` → 导出文件落临时目录
3. 用 SQL 直插最小数据集（versions + comparison_results），调用 `export_report`
4. 用 `openpyxl.load_workbook` 回读断言：sheet 名顺序、总览单元格、异常明细着色行内容

## 涉及文件

| 文件 | 改动说明 |
|------|----------|
| `tests/test_export.py` | 新增：3 个用例（双 Sheet 结构 / 总览数据 / 异常明细） |
| `specs/004-report-export/spec.md` | 修正：双 Sheet 结构、文件名规范（delta 合并） |
| `specs/TRACEABILITY.md` | 更新：CC-004 覆盖状态 |

## 备选方案

- 通过 HTTP 接口导出：依赖 9006 服务与完整业务数据，脆弱且慢，未采用
- 直接断言导出文件字节：无法验证语义内容，未采用

## 兼容性说明

测试不触碰业务逻辑；临时 DB 与上传目录随 pytest tmp_path 自动清理。
