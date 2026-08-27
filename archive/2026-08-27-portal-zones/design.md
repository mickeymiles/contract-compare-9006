# 设计：工作台首页双分区

> 变更编号：`2026-08-27-portal-zones` | 日期：2026-08-27 | 状态：已评审

## 技术方案

### 1. 分区结构

`#page-portal` 由「单栅格」改为「纵向 stacked 双分区」：

```html
<div id="page-portal" class="portal active">
  <div class="subtitle">经营管理 · 运维管理 · 一站式工作台</div>
  <div class="ds-panel">…数据源横条（保持原样，宽度撑满分区容器）…</div>

  <section class="zone zone-biz">
    <header class="zone-head">
      <span class="zh-bar"></span>
      <span class="zh-title">经营管理</span>
      <span class="zh-sub">财经视角 · 四算基线与经营质量量化</span>
      <span class="zh-count">6</span>
    </header>
    <div class="portal-grid">…6 张卡 + add 占位卡…</div>
  </section>

  <section class="zone zone-ops">
    <header class="zone-head">…运维管理…</header>
    <div class="portal-grid">…1 张卡 + add 占位卡…</div>
  </section>
</div>
```

分区容器最大宽度从原 `1100px` 提升到 `1240px`，以容纳跨列大卡。

### 2. 大模块卡（feature card）

「项目全生命周期管理」卡使用 `portal-card feature` 类，`grid-column: span 2`，内部左侧标题+描述、右侧 4×2 子模块 chip 网格，突出「下辖多子模块」的信息量。既有 `.portal-card` 的 hover 与顶部渐变条样式全部复用，只覆盖跨列与内部布局。

### 3. 页面注册表与 `showPage`

```js
const ALL_PAGES = ['page-portal','page-home','page-workspace','page-datasource',
                   'page-payment-cycle','page-fund-occupancy'];
function showPage(id){
  ALL_PAGES.forEach(x=>{const el=document.getElementById(x);if(el)el.classList.toggle('active',x===id);});
}
```

`goPortal` / `enterFromPortal` / `enterContract` / `openDatasourcePage` / `openPaymentCycle` / `openFundOccupancy` / 手册返回等 6+ 处调用点改为 `showPage('page-xxx')`。原实现使用 `remove('active')` 再 `add('active')` 两步，新实现用 `toggle(x, cond)` 一步完成，行为等价但少一次 DOM 往返。

`showPage` 对不存在的容器做空值保护，避免 `gross`/`plm` 这类独立页面（走 `location.href` 整页跳转）被误注册进来时报错。

### 4. 配色语义

两个分区用现有主题变量做区分，不新增颜色定义：经营管理用主蓝 `--cyan`（`#4f8cff`）延续既有卡片观感；运维管理用 `--orange`/`--green` 系的青色变体区分（实际取 `--cyan2` → `#22d3ee` 与备件卡现有 `badge` 观感对齐）。分区标题栏左侧色条 + 标题文字同色，卡片本身颜色不变，避免破坏既有的「已上线 / 即将上线 / 智能体」标签识别度。

## 涉及文件

| 文件 | 改动说明 |
|------|----------|
| `frontend/index.html` | `#page-portal` 结构重组；新增 `ALL_PAGES`/`showPage`；替换 6 处页 ID 字面量；手册概述与模块清单更新 |
| `frontend/common.css` | 新增 `.zone` / `.zone-head` / `.zone-biz` / `.zone-ops` / `.portal-card.feature` / `.pc-chips`；`.portal-grid` 宽度提升 |

## 数据模型变更

无。

## 备选方案

- **方案 B：顶部 Tab 切换「经营 / 运维」两个视图**。被否：用户需要一眼看到全貌，Tab 会隐藏另一侧入口，且引入额外状态。
- **方案 C：把备件采购卡也放进同一栅格并用颜色区分**。被否：不满足「分成 2 个区域」的显式诉求，纵向归属不清晰。

## 兼容性说明

- 卡片点击行为、目标 URL、`location.href` 整页跳转方式全部保持。
- `.portal-grid` 类名保留并被两个分区复用，既有针对 `.portal-card` 的样式与后续潜在外部引用不受影响。
- 独立页面（`/gross`、`/plm`、`/procurement`）的面包屑「运营管理」仍指回 `/`，不受影响。
