/* ================================================================
 * 统一导航配置（R4） —— 所有页面的壳共享唯一菜单来源
 * 领域顺序：可视化 → 采购 → PMO → 财经 → 运维 → 系统（PMO 域保留；仅「里程碑」功能迁至系统›主数据›项目）
 * 约定：对外暴露 window.NAV_CONFIG = { ICONS, icon(), NAV, renderAccordion(), renderBreadcrumb() }
 * 迁移动态：带 ⏳ 的条目为待建页面，链接暂指向现有可用页或占位 '#'。
 * ================================================================ */
'use strict';
(function (root) {
  var ICONS = {
    home:     '<svg viewBox="0 0 24 24"><path d="M12 3 2 12h3v8h6v-6h2v6h6v-8h3L12 3z"/></svg>',
    dashboard:'<svg viewBox="0 0 24 24"><path d="M3 3h8v8H3V3zm10 0h8v8h-8V3zM3 13h8v8H3v-8zm10 0h8v8h-8v-8z"/></svg>',
    refresh:  '<svg viewBox="0 0 24 24"><path d="M17.65 6.35A8 8 0 1 0 20 12h-2a6 6 0 1 1-1.76-4.24L13 11h7V4l-2.35 2.35z"/></svg>',
    project:  '<svg viewBox="0 0 24 24"><path d="M3 5c0-1.1.9-2 2-2h5l2 2h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5z"/></svg>',
    opp:      '<svg viewBox="0 0 24 24"><path d="M12 5a7 7 0 1 1-7 7 2 2 0 0 1-4 0 11 11 0 1 1 4.34 8.8A2 2 0 0 1 7.7 17.3 7 7 0 0 0 12 5z"/><circle cx="12" cy="12" r="3"/></svg>',
    contract: '<svg viewBox="0 0 24 24"><path d="M6 2h9l4 4v16H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2zm8 2v4h4l-4-4zm-7 8h6v2H7v-2zm0 4h6v2H7v-2zM7 8h3v2H7V8z"/></svg>',
    contact:  '<svg viewBox="0 0 24 24"><path d="M12 12a4 4 0 1 0-4-4 4 4 0 0 0 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/></svg>',
    chart:    '<svg viewBox="0 0 24 24"><path d="M4 20h16v2H4v-2zM6 16h3v4H6v-4zm5-6h3v10h-3V10zm5-4h3v14h-3V6z"/></svg>',
    fund:     '<svg viewBox="0 0 24 24"><path d="M4 20h16v2H4v-2zM6 16h3v4H6v-4zm5-6h3v10h-3V10zm5-4h3v14h-3V6z"/></svg>',
    cycle:    '<svg viewBox="0 0 24 24"><path d="M13 3a9 9 0 1 0 8.7 6.5l-2.2.8A7 7 0 1 1 13 5a6.9 6.9 0 0 1 5.04 2.2L16 9h6V3l-2.35 2.35A8.8 8.8 0 0 0 13 3z"/></svg>',
    gross:    '<svg viewBox="0 0 24 24"><path d="M3 3h18v2H3V3zm2 4h3v11H5V7zm5 0h3v8h-3V7zm5 0h3v13h-3V7zM3 20h18v2H3v-2z"/></svg>',
    compare:  '<svg viewBox="0 0 24 24"><path d="M9 3v4h2V3h3v5c0 1-1 2-2 2v11h-2v-9a2 2 0 0 1-2-2V3h1zm6 2h6v2h-3v6a2 2 0 0 1-2 2h-1v-2h1v-4h-1V5zm1 9v5a2 2 0 0 1-2 2h-1v-2h1v-5h2z"/></svg>',
    lifecycle:'<svg viewBox="0 0 24 24"><path d="M12 12m-9 0a9 9 0 1 0 18 0 9 9 0 1 0-18 0"/><path d="M12 12l4-3"/></svg>',
    pmo:      '<svg viewBox="0 0 24 24"><path d="M12 2 4 5v6c0 5 3.4 9.7 8 11 4.6-1.3 8-6 8-11V5L12 2zm-1 14H9v-2h2v2zm0-4H9V7h2v5zm4 0h-2V7h2v5z"/></svg>',
    ops:      '<svg viewBox="0 0 24 24"><path d="M12 3a4 4 0 1 1-4 4 4 4 0 0 1 4-4zm0 9c-3.33 0-7 1.5-7 4v3h14v-3c0-2.5-3.67-4-7-4zM4 3h2v4H4V3zm0-2h6v2H4V1z"/></svg>',
    receipt:  '<svg viewBox="0 0 24 24"><path d="M5 2h14a1 1 0 0 1 1 1v18l-2-1-2 1-2-1-2 1-2-1-2 1-2-1V3a1 1 0 0 1 1-1zm3 4v2h8V6H8zm0 4v2h8v-2H8zm0 4v2h5v-2H8z"/></svg>',
    pay:      '<svg viewBox="0 0 24 24"><path d="M4 4h16a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1zm6 12h6v2h-6v-2zm-2 0v-3H5v3h3zm0-7H5v3h3V9zm2 5h6v-2h-6v2zm0-7h6V5h-6v2zm7-1h-2v2h2V6zm0 4h-2v2h2v-2z"/></svg>',
    setting:  '<svg viewBox="0 0 24 24"><path d="M12 8a4 4 0 1 0 4 4 4 4 0 0 0-4-4zm9 4c0 .34-.03.67-.08 1l2.02 1.58-1.9 3.29-2.38-.96a7.96 7.96 0 0 1-1.73 1L16.7 20.6h-3.8l-.4-2.48a7.94 7.94 0 0 1-2 0l-.4 2.48H6.5L5.9 18a7.96 7.96 0 0 1-1.73-1l-2.38.96-1.9-3.29 2.02-1.58A8 8 0 0 1 3 12c0-.34.03-.67.08-1L1.06 9.42l1.9-3.29 2.38.96a7.96 7.96 0 0 1 1.73-1l.6-2.48h3.8l.4 2.48a7.94 7.94 0 0 1 2 0l.4-2.48h3.8l.6 2.48a7.96 7.96 0 0 1 1.73 1l2.38-.96 1.9 3.29L20.92 11a8 8 0 0 1 .08 1z"/></svg>',
    datasource:'<svg viewBox="0 0 24 24"><path d="M12 3C7.03 3 3 4.34 3 6v2c0 1.66 4.03 3 9 3s9-1.34 9-3V6c0-1.66-4.03-3-9-3zM3 10.24V12c0 1.66 4.03 3 9 3s9-1.34 9-3v-1.76C19.23 11.9 15.77 13 12 13s-7.23-1.1-9-2.76zM3 15.24V17c0 1.66 4.03 3 9 3s9-1.34 9-3v-1.76c-1.77 1.66-5.23 2.76-9 2.76s-7.23-1.1-9-2.76z"/></svg>',
    chev:     '<svg viewBox="0 0 24 24"><path d="M8.6 4 7 5.6 13.4 12 7 18.4 8.6 20l6.6-8-6.6-8z"/></svg>',
    edit:     '<svg viewBox="0 0 24 24"><path d="M3 17.25V21h3.75L17.8 9.94l-3.75-3.75L3 17.25zM20.7 7.04a1 1 0 0 0 0-1.41l-2.34-2.34a1 1 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/></svg>',
    del:      '<svg viewBox="0 0 24 24"><path d="M6 7h12l-1 13H7L6 7zm3-3h6l1 1H8l1-1zM4 5h16v2H4V5z"/></svg>',
    empty:    '<svg viewBox="0 0 24 24"><path d="M20 4H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2zm0 14H4V6h16zM7 8h3v3H7V8zm0 5h3v2H7v-2zm9-5h-5v2h5V8z"/></svg>'
  };

  function icon(name, cls) {
    return '<span class="icon ' + (cls || 'md') + '">' + (ICONS[name] || ICONS.empty) + '</span>';
  }

  /* ---- 领域树：可视化 → 采购 → PMO → 财经 → 运维 → 系统 ----
   * href 约定：
   *   有独立页面的功能 → 挂真实页面（/gross /plm /procurement /core）
   *   依赖门户且暂无独立页的功能 → 统一指向 /dev?feature=xx 开发中占位（不直接跳原工作台）
   * 可视化仅作总览（门户本身），不再重复财经/采购细项。 */
  var NAV = [
    { key: 'vis',  label: '可视化', icon: 'dashboard', href: '/dev?feature=经营工作台总览', children: [
      { sub: '经营视图', links: [
        { id: 'vis-home', label: '经营工作台总览', href: '/dev?feature=经营工作台总览', icon: 'dashboard' }
      ] }
    ]},
    { key: 'proc', label: '采购', icon: 'compare', href: '/contrast', children: [
      { sub: '合同硬件采购比对', links: [
        { id: 'proc-contrast', label: '对比分析', href: '/contrast', icon: 'compare' }
      ] }
    ]},
    { key: 'pmo',  label: 'PMO', icon: 'pmo', href: '/plm', children: [
      { sub: '计划执行', links: [
        { id: 'pmo-plm', label: '计划 / 任务 / 台账 / 预警', href: '/plm', icon: 'lifecycle' }
      ] }
    ]},
    { key: 'fin',  label: '财经', icon: 'fund', href: '/gross', children: [
      { sub: '资金运作', links: [
        { id: 'fin-cycle', label: '回款周期', href: '/finance-cycle', icon: 'cycle' },
        { id: 'fin-gross', label: '毛利率', href: '/gross', icon: 'gross' },
        { id: 'fin-fund',  label: '资金占用 · 周转率', href: '/finance-fund', icon: 'fund' },
        { id: 'fin-cost',  label: '成本预警', href: '/finance-cost', icon: 'chart' }
      ] }
    ]},
    { key: 'ops',  label: '运维', icon: 'ops', href: '/procurement', children: [
      { sub: '备件采购', links: [
        { id: 'ops-quote', label: '询比价智能体', href: '/procurement', icon: 'compare' }
      ] }
    ]},
    { key: 'sys',  label: '系统', icon: 'setting', href: '/core', children: [
      { sub: '主数据', links: [
        { id: 'sys-opp', label: '商机', href: '/dev?feature=商机', icon: 'opp' },
        { id: 'sys-presale', label: '售前', href: '/dev?feature=售前', icon: 'cycle' },
        { id: 'sys-contract', label: '合同', href: '/core?panel=contract', icon: 'contract' },
        { id: 'sys-project', label: '项目', href: '/core?panel=project', icon: 'project' }
      ] },
      // 本体可观测（Ontology）：引擎 + ABox 库已迁入本工程（backend/ontology_engine），
      // 原挂在「运维 › 备件采购」下、读 neuops 9007，现整体迁到系统域、主数据之下。
      { sub: '本体可观测', links: [
        { id: 'sys-ont-entities',  label: '实体与关系',   href: '/core?panel=ontEntities',  icon: 'ops' },
        { id: 'sys-ont-knowledge', label: '知识',         href: '/core?panel=ontKnowledge', icon: 'datasource' },
        { id: 'sys-ont-actions',   label: '动作',         href: '/core?panel=ontActions',   icon: 'refresh' },
        { id: 'sys-ont-tasks',     label: '任务列表',     href: '/core?panel=ontTasks',     icon: 'project' },
        { id: 'sys-ont-ledger',    label: '台账',         href: '/core?panel=ontLedger',    icon: 'receipt' },
        { id: 'sys-ont-topology',  label: '拓扑与一致性', href: '/core?panel=ontTopology',  icon: 'chart' }
      ] }
    ]}
  ];

  /* 顶部主菜单（域级）。opts: { activeKey } */
  function renderTopMenu(el, opts) {
    opts = opts || {};
    var html = '';
    NAV.forEach(function (sec) {
      var a = opts.activeKey === sec.key;
      html += '<a class="tm-btn' + (a ? ' active' : '') + '" href="' + sec.href + '" title="' + sec.label + '">'
        + icon(sec.icon, 'sm') + '<span>' + sec.label + '</span></a>';
    });
    el.innerHTML = html;
  }

  /* 渲染左侧手风琴（统一组件，全站一致）：
   * 数据源 = opts.sections（页面自定义 聚合→条目）或 NAV[activeKey]
   * 条目 = { key, label, icon, href? | action? }
   * opts: { rootTitle, domainLabel, activeKey, activeLink, sections } */
  function renderAccordion(el, opts) {
    opts = opts || {};
    var secs = [];
    if (opts.sections) {
      secs = opts.sections;
    } else {
      (opts.activeKey ? NAV.filter(function (s) { return s.key === opts.activeKey; }) : NAV)
        .forEach(function (sec) {
          (sec.children || []).forEach(function (g) { secs.push(g); });
        });
    }
    var html = '';
    secs.forEach(function (sec) {
      var links = (sec.links || []);
      var hasActive = links.some(function (l) { return (l.key || l.id) === opts.activeLink; });
      var open = !opts.collapseAll && (hasActive || opts.openAll !== false);
      html += '<section class="acc-sec' + (open ? ' open' : '') + '">'
        + '<div class="acc-group" onclick="this.parentElement.classList.toggle(\'open\')" title="点击展开/收起">'
        + '<span class="acc-label">' + sec.sub + '</span>'
        + '<span class="icon xs acc-chev">' + ICONS.chev + '</span>'
        + '</div><div class="acc-content">';
      links.forEach(function (l) {
        var active = ((l.key || l.id) === opts.activeLink) ? ' active' : '';
        if (l.action) {
          html += '<a class="acc-link' + active + '" href="javascript:void(0)" onclick="AccordNav(this);' + l.action + '">'
            + icon(l.icon || 'empty', 'sm') + '<span>' + l.label + '</span></a>';
        } else {
          html += '<a class="acc-link' + active + '" href="' + l.href + '">'
            + icon(l.icon || 'empty', 'sm') + '<span>' + l.label + '</span></a>';
        }
      });
      html += '</div></section>';
    });
    if (!html) html = '<div class="acc-sub">暂无子菜单</div>';
    el.innerHTML = '<nav class="accordion">' + html + '</nav>';
  }

  /* 统一手风琴条目点击：先清除组内 active，再给当前项 active */
  function accordNav(el) {
    var r = el.closest('.accordion');
    if (r) r.querySelectorAll('.acc-link').forEach(function (x) { x.classList.remove('active'); });
    el.classList.add('active');
  }

  /* 渲染面包屑。items 第一层为一级菜单（域），末位为当前。不含"首页"。 */
  function renderBreadcrumb(el, items) {
    var nodes = [];
    (items || []).forEach(function (it, i) {
      if (i > 0) nodes.push('<span class="bc-sep">/</span>');
      nodes.push(i === items.length - 1
        ? '<span class="bc-cur">' + it + '</span>'
        : '<span class="bc-root">' + it + '</span>');
    });
    el.innerHTML = nodes.join('') || '';
  }

  /* ================================================================
   * 通用分析页 顶部 Tab 组件（财经三页共用）
   * 复用 common.css 的 .tabbar / .tab-btn / .ana-pane 样式：
   *   .tab-btn.active 高亮当前 tab；.ana-pane 默认隐藏，.ana-pane.on 显示。
   * 约定：所有 tab-btn 与 ana-pane 挂在同一个宿主容器下，且宿主带 data-host。
   * - anaTabs(tabs, active, hostId)  生成 .tabbar HTML（onclick 调 anaSwitch）
   * - anaPane(key, content, active)  生成一个 .ana-pane（on 表示默认显示）
   * - anaSwitch(btn)                 切换 active 高亮 + 显示对应 pane + echarts resize
   * - anaPager(page, total, pageSize, hostId, refreshFn) 生成分页条 HTML
   * - anaPagerGo(newPage, hostId, refreshFn) 触发某全局刷新函数重渲染当前页
   * ================================================================ */
  /* 解析全局函数：支持 'Foo.bar.baz' 点号路径 或 直接函数。 */
  function ncResolveFn(name) {
    if (typeof name === 'function') return name;
    if (typeof name !== 'string' || !name) return null;
    var o = window; var parts = name.split('.'); var i;
    for (i = 0; i < parts.length && o != null; i++) o = o[parts[i]];
    return typeof o === 'function' ? o : null;
  }
  function anaTabs(tabs, active, hostId) {
    var h = '<div class="tabbar">';
    (tabs || []).forEach(function (t, i) {
      var a = (active || (tabs[0] && tabs[0].key)) === t.key;
      h += '<button type="button" class="tab-btn' + (a ? ' active' : '') + '"'
        + ' data-tab="' + t.key + '" data-host="' + hostId + '"'
        + ' onclick="NAV_CONFIG.anaSwitch(this)">' + t.label + '</button>';
    });
    return h + '</div>';
  }
  function anaPane(key, content, active) {
    return '<div class="ana-pane' + (active ? ' on' : '') + '" data-pane="' + key + '">' + content + '</div>';
  }
  function anaSwitch(btn) {
    if (!btn) return;
    var host = document.getElementById(btn.getAttribute('data-host'));
    var key = btn.getAttribute('data-tab');
    if (!host || !key) return;
    host.querySelectorAll('.tab-btn').forEach(function (b) {
      b.classList.toggle('active', b.getAttribute('data-tab') === key);
    });
    host.querySelectorAll('.ana-pane').forEach(function (p) {
      p.classList.toggle('on', p.getAttribute('data-pane') === key);
    });
    setTimeout(function () {
      if (window.echarts) {
        (host.querySelector('.ana-pane.on') || host).querySelectorAll('[id]').forEach(function (el) {
          var c = echarts.getInstanceByDom(el); if (c) { try { c.resize(); } catch (e) {} }
        });
      }
      var custom = host.getAttribute('data-on-switch');
      if (custom) { var f = ncResolveFn(custom); if (f) { try { f(key); } catch (e) {} } }
    }, 120);
  }
  function anaPager(page, total, pageSize, hostId, refreshFn) {
    var pages = Math.max(1, Math.ceil((total || 0) / (pageSize || 10)));
    page = Math.min(Math.max(1, page || 1), pages);
    var j = function (c) { return (c === null || c === undefined) ? '' : String(c); };
    var h = '<div class="pager" style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-top:12px">'
      + '<span style="font-size:12px;color:var(--text2)">共 ' + total + ' 条 · 第 ' + page + '/' + pages + ' 页</span>';
    var prevDisabled = page <= 1;
    h += '<button type="button" class="btn btn-o btn-sm"' + (prevDisabled ? ' disabled' : '')
      + ' onclick="' + (prevDisabled ? '' : 'NAV_CONFIG.anaPagerGo(' + (page - 1) + ',\'' + hostId + '\',\'' + j(refreshFn) + '\')') + '">‹ 上一页</button>';
    var start = Math.max(1, page - 2);
    var end = Math.min(pages, start + 4);
    start = Math.max(1, end - 4);
    for (var i = start; i <= end; i++) {
      h += '<button type="button" class="btn btn-sm ' + (i === page ? 'btn-c' : 'btn-o') + '"'
        + ' onclick="NAV_CONFIG.anaPagerGo(' + i + ',\'' + hostId + '\',\'' + j(refreshFn) + '\')">' + i + '</button>';
    }
    var nextDisabled = page >= pages;
    h += '<button type="button" class="btn btn-o btn-sm"' + (nextDisabled ? ' disabled' : '')
      + ' onclick="' + (nextDisabled ? '' : 'NAV_CONFIG.anaPagerGo(' + (page + 1) + ',\'' + hostId + '\',\'' + j(refreshFn) + '\')') + '">下一页 ›</button>';
    return h + '</div>';
  }
  function anaPagerGo(newPage, hostId, refreshFn) {
    var el = document.getElementById(hostId);
    if (!el) return;
    var fn = ncResolveFn(refreshFn);
    if (fn) { try { fn(newPage); } catch (e) {} }
  }

  root.NAV_CONFIG = {
    ICONS: ICONS, icon: icon, NAV: NAV,
    renderTopMenu: renderTopMenu,
    renderAccordion: renderAccordion, renderBreadcrumb: renderBreadcrumb,
    anaTabs: anaTabs, anaPane: anaPane, anaSwitch: anaSwitch,
    anaPager: anaPager, anaPagerGo: anaPagerGo
  };
  root.AccordNav = accordNav;
})(window);