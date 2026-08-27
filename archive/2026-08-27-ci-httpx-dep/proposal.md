# 提案：补齐 httpx 依赖，恢复 CI 测试与自动部署

> 变更编号：`2026-08-27-ci-httpx-dep`
> 作者：AI 编程助手 | 日期：2026-08-27 | 状态：已实现并归档（工程维护，无规格 delta）

## 背景与问题

GitHub Actions 连续三次红（run #14 `1fdff05`、#15 `a371135`、#16 `a1e3529`），失败步骤均为
`Lint & Unit Tests` 的 **Run tests**，`deploy` 因 `needs: lint` 被跳过 —— 即 push 到 main 实际
从未自动部署过，生产 9006 是靠手工 `scripts/remote_deploy.sh` 更新的。

根因：`fastapi.testclient.TestClient` 依赖 `httpx`，而 `backend/requirements.txt` 只列了
`requests`。CI 的依赖安装步骤是 `pip install ruff pytest` + `pip install -r backend/requirements.txt`，
因此 runner 上没有 httpx，凡是 import TestClient 的测试模块（test_gross / test_fund_multidim /
test_fund_yoy / test_payment_cycle）在收集阶段即 `ModuleNotFoundError: No module named 'httpx'`。

本地之所以一直没暴露：开发者全局 site-packages 里恰好装了 httpx。

## 目标

1. CI 的 lint + test 转绿，恢复 push → 自动部署闭环。
2. 让本地与 CI 的依赖集一致，杜绝「本地能跑、CI 不能跑」。

## 变更范围

- `backend/requirements.txt`：新增 `httpx>=0.27`（TestClient 的硬依赖）。

## Out of Scope

- 不改测试代码、不改业务代码、不放宽 CI 参数。
- 不引入 fastapi[all] 这类大而全的 extra。

## 验收标准

- [x] 以 CI 等价环境复现：`uv venv --python 3.11` + `pip install pytest ruff -r backend/requirements.txt`
      → 修改前 4 个模块收集失败，修改后 `126 passed, 10 skipped`。
- [x] `ruff check backend/ --select E,F --ignore ...` All checks passed。
- [x] push 后 Actions run 结论为 success，deploy job 实际执行。

## 风险与兼容性

零风险：仅新增一个测试期依赖，不改变任何运行时行为（httpx 不被 backend/main.py 引用）。
