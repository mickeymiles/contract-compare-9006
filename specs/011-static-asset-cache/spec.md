# 前端资源缓存策略 Specification

> 规格编号: CC-011 | 状态: 生效 | 最后更新: 2026-08-27
> 对应代码: `backend/main.py`（`no_cache_static_assets` 中间件、`NO_CACHE_PATHS`/`NO_CACHE_SUFFIXES`/`_etag_match`）
> 来源变更: `archive/2026-08-27-static-asset-cache/`

## Purpose

保证前端发版后用户首刷即见最新页面与样式，消除「新旧资源混搭」与「必须强制刷新」两类问题，
同时不因禁用缓存而造成全量重复传输。

## Requirements

### Requirement: 页面与静态资源必须再校验

系统 SHALL 对所有 HTML 页面与前端静态资源（CSS / JavaScript / 地图 JSON）的响应附带
`Cache-Control: no-cache`，使浏览器在每次使用前 SHALL 向服务端再校验一次新鲜度。

- 再校验 SHALL 复用文件指纹（`ETag` / `Last-Modified`），未变更时 SHALL 返回 `304 Not Modified` 且不传输响应体。
- 系统 SHALL NOT 对这些资源使用 `no-store`（避免每次全量重传）。
- 命中范围 SHALL 由「显式路径清单 + 资源后缀兜底」共同决定，使后续新增前端资源无需改动本策略。

#### Scenario: 首次请求带指令

- GIVEN 用户浏览器无任何缓存
- WHEN 请求 `/common.css`
- THEN 响应为 200，且响应头含 `Cache-Control: no-cache`
- AND 同时含 `ETag` 与 `Last-Modified`

#### Scenario: 资源变更后首刷即最新

- GIVEN 浏览器已缓存旧版 `common.css` 及其 ETag
- WHEN 服务端替换为新版 CSS 后用户普通刷新页面
- THEN 浏览器发起带 `If-None-Match` 的条件请求
- AND 因指纹变化返回 200 与新版内容，页面无需强制刷新即为最新样式

#### Scenario: 资源未变更走 304

- GIVEN 浏览器缓存的 `common.css` 指纹与服务端一致
- WHEN 用户再次刷新页面
- THEN 服务端返回 304 且无响应体
- AND 浏览器复用本地副本

#### Scenario: 后缀兜底覆盖新增资源

- GIVEN 后续新增了一个未被清单枚举的 `/foo.js`
- WHEN 请求该资源
- THEN 响应仍带 `Cache-Control: no-cache`

### Requirement: 动态接口不受影响

系统 SHALL NOT 对 `/api/*` 动态数据接口注入 `Cache-Control`，其响应头与行为 SHALL 与变更前一致。

#### Scenario: 接口保持原样

- GIVEN 客户端请求 `/api/plm/overview`
- WHEN 服务端返回
- THEN 响应不含由本策略注入的 `Cache-Control` 头
- AND 业务响应体结构与状态码不变
