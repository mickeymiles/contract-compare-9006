# 任务清单：补齐 httpx 依赖

- [x] 用 Actions API 定位失败步骤（Run tests，deploy skipped）
- [x] 用 CI 等价 venv（3.11 + requirements + pytest + ruff）本地复现 ModuleNotFoundError: httpx
- [x] `backend/requirements.txt` 增加 `httpx>=0.27`
- [x] CI 等价环境复跑：ruff 0 错误、pytest 126 passed / 10 skipped
- [x] 归档：`archive/2026-08-27-ci-httpx-dep/`，同步 `archive/README.md` 与 `specs/TRACEABILITY.md`
- [ ] 推送后确认 Actions run 转绿且生产 9006 出现 `/plm`
