# 任务清单：前端资源缓存策略

> 变更编号：`2026-08-27-static-asset-cache`

## 前置

- [x] delta 规格 `specs/CC-010` → 本变更 `specs/CC-011-static-asset-cache/spec.md`
- [x] 人工确认方案：只做 `no-cache`，不做 `?v=<hash>` 版本号（用户指定）

## 实现

- [ ] [P0] T1 `backend/main.py` 新增 `no_cache_static_assets` HTTP 中间件 #CC-011
  - `NO_CACHE_PATHS`：`/`、`/gross`、`/plm`、`/procurement`、`/common.css`、
    `/plm.app.js`、`/procurement.app.js`、`/china.json`
  - `NO_CACHE_SUFFIXES`：`.css`、`.js`
  - 命中则注入 `Cache-Control: no-cache`，其余响应原样透传
  - 注册位置紧随 CORS 中间件之后，附注说明「为何是 no-cache 而非 no-store」
- [ ] [P0] T1b 条件请求短路 `_etag_match()` + 304 返回 #CC-011
  - `FileResponse` 不处理 `If-None-Match`，必须在中间件内自行比对并回 304 空体
  - 按 RFC 7232 支持 `*` / 逗号列表 / `W/` 弱标记

## 测试

- [ ] [P0] T2 `tests/test_static_cache.py` #CC-011
  - 清单内 8 个路径均带 `no-cache`
  - 后缀兜底：任意 `.css` / `.js` 带 `no-cache`
  - `/api/plm/overview` 不被注入
  - 条件请求 `If-None-Match` 命中返回 304
  - 断言未使用 `no-store`
  - 指纹过期回 200 全量；`W/` 与逗号列表命中 304
- [ ] [P0] T3 全量回归 `pytest -q` + CI 同参数 ruff

## 收尾

- [ ] [P0] T4 推送并确认 Actions run 绿、deploy 执行
- [ ] [P1] T5 生产复验：`curl -D-` 看响应头；带 `If-None-Match` 复验 304
- [ ] [P1] T6 归档：`archive/2026-08-27-static-asset-cache/`，delta 合并进
      `specs/011-static-asset-cache/spec.md`，同步 `specs/README.md`、
      `specs/TRACEABILITY.md`、`AGENTS.md`
