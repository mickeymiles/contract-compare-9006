# 提案：页面与静态资源改为「每次再校验」，消除发版后需强制刷新

> 变更编号：`2026-08-27-static-asset-cache`
> 作者：AI 编程助手 | 日期：2026-08-27 | 状态：已实现并归档（delta 已合并至 `specs/011-static-asset-cache/spec.md`）

## 背景与问题

CC-009 门户双分区部署到生产后，用户打开首页看到的是「结构对、样式没套上」的半新状态：
分区标题没有左侧色条、卡片计数挤成一行、feature 大卡没跨列、子模块 chip 变成行内文字流。
排查确认服务端 `common.css` 已是新版（29573 字节，`.zone-head` / `.portal-card.feature` /
`.pcf-chips` / `grid-column:span 2` 全部存在），是浏览器复用了旧的 CSS 副本，需 Ctrl+Shift+R 才正常。

根因：所有页面都是裸引用静态资源（`<link rel="stylesheet" href="/common.css">`、
`<script src="/plm.app.js">`），既没有版本位，也没有任何 `Cache-Control` 指令。
`FileResponse` 虽然会发 `ETag` / `Last-Modified`，但在缺少 `Cache-Control` 的情况下，
浏览器可以按启发式新鲜度直接复用缓存副本、根本不发起再校验——于是每次前端发版都要用户手动强刷，
而且 HTML 本身被缓存时还会出现「新旧混搭」的更糟观感。

## 目标

1. 页面与 CSS/JS 资源在**每次使用时都向服务端再校验一次**：未变更走 304（几百字节开销），
   变更后首刷即生效，不再需要强制刷新。
2. 一处生效、无需人工维护版本号，也不改动任何页面引用写法。

## 变更范围

### In Scope

- `backend/main.py`：新增 HTTP 中间件，对页面路由与静态资源响应注入
  `Cache-Control: no-cache`。
  - 显式清单：`/`、`/gross`、`/plm`、`/procurement`、`/common.css`、`/plm.app.js`、
    `/procurement.app.js`、`/china.json`
  - 后缀兜底：任何 `.css` / `.js` 路径，覆盖后续新增的前端资源
- 同一中间件内补**条件请求短路**：Starlette 的 `FileResponse` 只 `setdefault("etag")`、
  并不处理 `If-None-Match`（只有 `StaticFiles` 会返回 304）。若只加 `no-cache` 而不做 304，
  浏览器每次导航都会全量重下约 170KB 的 `index.html` + 30KB 的 `common.css`，反而比改前更费带宽。
  因此命中资源时，若 `If-None-Match` 与响应 ETag 相符（按 RFC 7232 支持 `*`、逗号列表、`W/` 弱标记），
  直接返回 304 空响应体并保留 `ETag` / `Last-Modified` / `Cache-Control`。
- 回归测试：断言上述响应带 `no-cache`、指纹相符回 304、指纹过期回 200 全量、
  且 `/api/*` 动态接口不被注入。

### Out of Scope

- 不引入 `?v=<hash>` 版本号 URL 方案（需要把 4 个页面的 `FileResponse` 改成带替换的
  `HTMLResponse`，改动面更大；`no-cache` 已能满足「首刷即最新」）。
- 不给 `/api/*` 加缓存指令（动态数据接口，浏览器默认不缓存 XHR）。
- 不做 `no-store`（那会让 304 失效、每次都全量重传 170KB 的 index.html 与 30KB 的 CSS）。
- 不改前端任何文件。

## 接口与数据契约

响应头新增（仅命中清单/后缀时）：

```
Cache-Control: no-cache
ETag: "351c07327e451538b32d5ec2619ff9af"      # FileResponse 原有，保持不变
Last-Modified: Thu, 27 Aug 2026 03:37:39 GMT   # FileResponse 原有，保持不变
```

配合浏览器带 `If-None-Match` 回访时，未变更返回 `304 Not Modified`（无响应体）。

## 涉及规格条目

- `ADDED` `CC-011` 前端资源缓存策略

## 验收标准

- [x] `GET /`、`/gross`、`/plm`、`/procurement`、`/common.css`、`/plm.app.js`、
      `/procurement.app.js`、`/china.json` 响应头含 `Cache-Control: no-cache`。
- [x] 任一 `.css` / `.js` 路径同样带 `no-cache`。
- [x] `GET /api/plm/overview` 等动态接口**不**被注入 `Cache-Control`。
- [x] 带 `If-None-Match`（匹配当前 ETag）请求 `/common.css` 返回 304。
- [x] 指纹过期（发版后）请求返回 200 全量内容，不被误判为 304。
- [x] `If-None-Match` 的逗号列表与 `W/` 弱标记形式均能命中 304。
- [x] `pytest -q` 全绿、ruff（CI 同参数）零错误。
- [x] 部署后在生产上复验：首刷即拿到最新样式，无需强制刷新。

## 风险与兼容性

- 风险：再校验会增加少量 304 往返。缓解：304 不传响应体；页面与 CSS 总量约 200KB，
  命中 304 时实际传输仅数百字节，远小于一次强刷的全量重传。
- 兼容性：纯响应头新增，不改 URL、不改文件、不改前端；对既有接口行为零影响。
- 已知局限：个别不遵守 `no-cache` 的代理/企业浏览器仍可能滞留旧副本。若日后遇到，
  再单独开变更叠加 `?v=<hash>` 版本号方案（本变更 Out of Scope 已说明）。
- 回滚：删除该中间件即可，无数据与文件影响。
