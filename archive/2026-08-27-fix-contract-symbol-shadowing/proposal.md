# 提案：修复合同域符号遮蔽导致「新建合同」500

> 变更编号：`2026-08-27-fix-contract-symbol-shadowing`
> 作者：AI 编程助手 | 日期：2026-08-27 | 状态：已实现并归档
> 涉及规格：CC-001 FR-1（合同创建）、FR-2（查询）、FR-3（删除与级联）——**恢复既有行为，无规格 delta**

## 背景与问题

`backend/main.py` 的采购模块导入块写了 `from procurement_models import (..., create_contract, delete_contract, ...)`，
把 `models.py` 的同名函数**遮蔽**掉。为绕过遮蔽，遗留合同路由改成了：

```python
import contract_models as _cm          # ← 仓库里根本没有 contract_models.py
cid = _cm.create_contract(name, no, sign_date)
```

结果是 `POST /api/contracts` 稳定抛 `ModuleNotFoundError: No module named 'contract_models'` → HTTP 500。
前端 `index.html` 的「＋ 新建合同」按钮（`showCreateContract()` → `POST /api/contracts`）点下去就是报错，
`DELETE /api/contracts/{id}` 同样不可用。该缺陷自备件采购重构起存在，生产环境同样中招。

## 目标

1. 恢复 CC-001 已承诺的合同创建 / 删除行为（规格未变，是实现偏离规格）。
2. 从根因消除遮蔽，而不是继续加兜底补丁。
3. 加回归测试锁死，防止未来再次被同名导入破坏。

## 变更范围

- `backend/main.py` 采购导入块：`create_contract as proc_create_contract`、`delete_contract as proc_delete_contract`。
- 采购侧 2 处调用点改用别名（`POST /api/procurement/contracts`、`DELETE /api/procurement/contracts/{id}`）。
- 遗留合同路由：删除 `import contract_models as _cm` 兜底，直接调用 `models.create_contract` / `models.delete_contract`；
  补空名称 400 校验（此前空名会落库）。
- `tests/test_contract_domain.py`：7 条回归（遮蔽守卫 + 创建/查询/删除级联 + 三域互不串写 + 采购侧不回退）。

### Out of Scope

- 不改 `PUT /api/contracts/{id}`（`update_contract_legacy` 是历史空实现，一直直接返回 success，
  属另一处待清理项，本次不动行为，仅在此登记）。
- 不重构采购域其余 40+ 个符号导入（仅碰撞的 2 个必须别名，全量命名空间化留待独立变更）。

## 接口与数据契约

`POST /api/contracts?name=&no=&sign_date=` → `{"success": true, "contract_id": <int>}`；空 `name` → 400。
`DELETE /api/contracts/{id}` → `{"success": true}`，级联清理 `contract_items` / `supplier_items` /
`comparison_results` / `versions`。采购与 PLM 两个合同接口契约不变。

## 验收标准

- [x] `POST /api/contracts` 返回 200 且 `contracts` 表出现对应行（含名称/编号/签约日期）。
- [x] 空名称返回 400。
- [x] `DELETE /api/contracts/{id}` 后主表与明细表均无残留。
- [x] `main.create_contract is models.create_contract`，`main.proc_create_contract is procurement_models.create_contract`。
- [x] 合同比对 / 备件采购 / 项目全生命周期三个合同域各写各表，互不串写。
- [x] `pytest -q` 133 passed / 10 skipped；ruff（CI 同参数）All checks passed。

## 风险与兼容性

行为变更仅限「原本必然 500 的两个接口恢复可用」，无接口签名变化、无数据迁移。
采购侧改的是别名，函数实现与参数完全不变。
