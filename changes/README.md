# 变更工作区（Changes）— contract-compare

> 本目录存放**进行中的变更**。每个变更一个独立目录：`changes/YYYYMMDD-<slug>/`。
> 参照 OpenSpec 变更模型：`proposal.md`（为什么）→ `specs/`（delta 增量规格）→ `design.md`（如何实现）→ `tasks.md`（具体步骤）。

## 目录结构

```
changes/
├── README.md
├── _template/                    # 新变更模板（复制此目录作为变更起点）
│   ├── proposal.md               # 提案：背景/目标/范围/接口契约/验收标准
│   ├── design.md                 # 设计（可选）：技术方案/架构决策/涉及文件
│   ├── tasks.md                  # 任务清单：可勾选实施步骤
│   └── specs/                    # delta 增量规格（ADDED/MODIFIED/REMOVED）
│       └── <domain>/spec.md
└── YYYYMMDD-<slug>/              # 实际变更（示例：20260817-fix-unit-normalize）
```

## 变更工作流

1. **提案**：新建 `changes/YYYYMMDD-<slug>/`，从 `_template/` 复制四工件，填写 `proposal.md`
2. **评审**：确认范围、验收标准与涉及规格条目（作者需对内容正确性负责）
3. **delta 规格**：在 `specs/<domain>/spec.md` 中按 ADDED / MODIFIED / REMOVED 三节描述需求变化
4. **设计**：如涉及架构决策，填写 `design.md`；简单变更可省略
5. **实现**：按 `tasks.md` 逐项实现，每项测试用例标注规格编号（如 `CC-003 FR-2.3`）
6. **验证**：对照规格校验实现（可用 `/opsx:verify` 思路人工核对）
7. **归档**：将变更目录移入 `../archive/YYYY-MM-DD-<slug>/`，并把 delta 合并回 `../specs/` 主规格，更新 `TRACEABILITY.md`

## 规则

- **改代码必须先建变更提案**，禁止绕过 `changes/` 直接修改主规格或代码
- 根本意图相同 → 更新现有变更；意图改变 / 范围扩大 → 新建变更
- commit message 携带规格编号，如 `feat(CC-003): 单位归一化支持组合表达式`
