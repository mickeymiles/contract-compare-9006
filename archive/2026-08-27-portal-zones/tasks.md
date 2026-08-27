# 任务清单：工作台首页双分区

> 变更编号：`2026-08-27-portal-zones`

## 前置

- [x] 更新 delta 规格 `specs/CC-009-portal-zones/spec.md`
- [x] 人工评审 proposal 与 delta 规格（用户确认：分区标题用「经营管理 / 运维管理」）

## 实现

- [x] [P0] `common.css` 新增分区容器与标题栏样式（`#CC-009 FR-1`）
  - `.zone` / `.zone-head` / `.zh-bar` / `.zh-title` / `.zh-sub` / `.zh-count`
  - `.zone-biz`（主蓝）与 `.zone-ops`（青）两套强调色
  - `.portal-grid` 最大宽度 `1100px → 1240px`，`margin-bottom` 分区留白
- [x] [P0] `index.html` 重组 `#page-portal`（`#CC-009 FR-1`）
  - 数据源横条改为撑满分区宽度
  - 经营管理分区：01 回款周期 / 02 资金占用 / 03 签单毛利率 / 04 项目决算报告(即将上线) / 05 采购合同比对 / 06 项目全生命周期管理(feature)
  - 运维管理分区：01 备品备件采购询比价 + `add` 占位卡
- [x] [P0] `index.html` 新增 feature 大卡（`#CC-009 FR-2`）
  - `portal-card feature` + 子模块 chip 列表 + `location.href='/plm'`
- [x] [P0] `index.html` 收敛页切换（`#CC-009 FR-3/FR-4`）
  - 新增 `ALL_PAGES` 常量与 `showPage(id)`
  - 替换 `goPortal` / `enterFromPortal` / `enterContract` / `openDatasourcePage` / `openPaymentCycle` / `openFundOccupancy` / 手册页 内 6+ 处字面量数组
- [x] [P1] 更新 `index.html` 用户手册：系统概述补双分区说明、模块清单新增「项目全生命周期管理」章节

## 测试

- [x] `tests/test_portal_layout.py`：门户 HTML 结构断言（两分区存在、卡片归属唯一、无重复页 ID 字面量数组）
- [x] `tests/test_plm.py` 内断言 `/plm` 路由 200（与 CC-010 联合覆盖）
- [x] 全量回归：`python -m pytest -q`（基线 57 passed 不回归）

## 收尾

- [x] 更新 `specs/TRACEABILITY.md` 追加 CC-009 行
- [x] 归档：`changes/2026-08-27-portal-zones/` → `archive/2026-08-27-portal-zones/`，delta 合并进 `specs/009-portal-zones/spec.md`
- [x] commit message：`feat(CC-009): 工作台首页拆分经营管理/运维管理双分区`
