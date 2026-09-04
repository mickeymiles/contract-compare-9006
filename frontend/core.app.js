/* ================================================================
 * 主数据域 core 前端脚本（主数据重构：合同 / 项目 双面板）
 * 壳（手风琴/面包屑/图标）由 nav.config.js 提供，本页只接业务。
 *
 * - 合同主数据：合同表 / 收款表 / 付款表 三 Tab（全量导入 + 全量列表）
 * - 项目主数据：里程碑产值表（全量导入 + 全量列表）
 * - 本体可观测 6 面板由 ontology.app.js 的 loadOntPanel 渲染
 *
 * 数据接口：
 *   列表  GET /api/core/master?kind=contract|recv|pay|milestone&keyword=&page=
 *   导入  POST /api/core/master/import?kind=...  (multipart file)
 * kind 与库表：contract→md_contract / recv→md_receipt / pay→md_payment / milestone→md_milestone
 * ================================================================ */
'use strict';
var NC = window.NAV_CONFIG;

/* ---- 工具 ---- */
function withLoading(btnId, busyLabel, fn) {
  var btn = document.getElementById(btnId);
  var label = btn.textContent;
  btn.disabled = true; btn.textContent = busyLabel || label; btn.classList.add('off');
  return fn().finally(function () {
    btn.disabled = false; btn.textContent = label; btn.classList.remove('off');
  });
}
function toast(msg, ok) {
  var t = document.createElement('div');
  t.className = 'toast ' + (ok ? 'ok' : 'err'); t.textContent = msg;
  document.body.appendChild(t);
  requestAnimationFrame(function () { t.classList.add('show'); });
  setTimeout(function () { t.classList.remove('show'); setTimeout(function () { t.remove(); }, 400); }, 2400);
}
function api(url, opts) {
  opts = opts || {};
  return fetch(url, Object.assign({ headers: { 'Content-Type': 'application/json' } }, opts))
    .then(function (r) { return r.json().catch(function () { return { success: false, error: '响应解析失败' }; }); });
}
function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
  });
}
function emptyRow(msg, cols) {
  return '<tr><td colspan="' + (cols || 1) + '" style="text-align:center;color:var(--text2);padding:30px">'
    + NC.icon('empty', 'lg') + '<div style="margin-top:8px">' + msg + '</div></td></tr>';
}

/* ---- 主数据全量表渲染 ---- */
var MASTER_KIND = {
  contract:  { table: 'tblContract',  kw: 'kwContract',  sub: 'hdrSubContract',  label: '合同表' },
  recv:      { table: 'tblRecv',      kw: 'kwRecv',      sub: null,              label: '收款表' },
  pay:       { table: 'tblPay',       kw: 'kwPay',       sub: null,              label: '付款表' },
  milestone: { table: 'tblMilestone', kw: 'kwMilestone', sub: 'hdrSubProject',   label: '里程碑' }
};

var Master = {
  page: { contract: 1, recv: 1, pay: 1, milestone: 1 },
  loaded: {},
  pageSize: 200,

  reload: function (kind) {
    var cfg = MASTER_KIND[kind];
    if (!cfg) return Promise.resolve();
    var kw = (document.getElementById(cfg.kw).value || '').trim();
    var url = '/api/core/master?kind=' + kind + '&page=' + (this.page[kind] || 1) + '&pageSize=' + this.pageSize;
    if (kw) url += '&keyword=' + encodeURIComponent(kw);
    var self = this;
    return api(url).then(function (j) {
      if (!j.success) { self._renderEmpty(cfg.table, '加载失败：' + (j.error || '')); return; }
      self._render(kind, cfg, j);
    }).catch(function (e) { self._renderEmpty(cfg.table, '加载失败：' + e.message); });
  },

  _render: function (kind, cfg, j) {
    var cols = j.columns || [];
    var rows = j.rows || [];
    var tbl = document.getElementById(cfg.table);
    if (cfg.sub) {
      var subEl = document.getElementById(cfg.sub);
      if (subEl) subEl.textContent = '共 ' + (j.total || 0) + ' 行 · ' + cols.length + ' 列（全量导入）';
    }
    if (!cols.length) { this._renderEmpty(cfg.table, '表未导入，请先点击「导入 Excel」'); return; }
    if (!rows.length) { this._renderEmpty(cfg.table, '无匹配数据'); return; }
    var thead = '<thead><tr><th style="width:54px">#</th>'
      + cols.map(function (c) { return '<th>' + esc(c) + '</th>'; }).join('') + '</tr></thead>';
    var tbody = '<tbody>' + rows.map(function (r) {
      return '<tr><td class="muted">' + esc(r.row_id) + '</td>'
        + cols.map(function (c) {
            var v = r[c];
            return '<td>' + (v === null || v === undefined || v === '' ? '—' : esc(v)) + '</td>';
          }).join('') + '</tr>';
    }).join('') + '</tbody>';
    tbl.innerHTML = thead + tbody;
    this._renderPager(kind, cfg, j);
  },

  _renderEmpty: function (tblId, msg) {
    var tbl = document.getElementById(tblId);
    if (tbl) tbl.innerHTML = emptyRow(msg, 6);
  },

  _renderPager: function (kind, cfg, j) {
    var host = document.getElementById(cfg.table);
    if (!host) return;
    var twrap = host.closest('.twrap');
    if (!twrap) return;
    var total = j.total || 0;
    var pages = Math.ceil(total / this.pageSize) || 1;
    var cur = this.page[kind] || 1;
    var bar = document.getElementById(cfg.table + 'Pager');
    if (!bar) {
      bar = document.createElement('div');
      bar.id = cfg.table + 'Pager';
      bar.className = 'pager';
      twrap.parentNode.insertBefore(bar, twrap.nextSibling);
    }
    var prev = cur > 1 ? '<button class="btn btn-o btn-sm" onclick="Master.goPage(\'' + kind + '\',-1)">‹ 上一页</button>' : '';
    var next = cur < pages ? '<button class="btn btn-o btn-sm" onclick="Master.goPage(\'' + kind + '\',1)">下一页 ›</button>' : '';
    bar.innerHTML = '共 ' + total + ' 行 · 第 ' + cur + '/' + pages + ' 页 ' + prev + next;
  },

  goPage: function (kind, d) {
    this.page[kind] = Math.max(1, (this.page[kind] || 1) + d);
    this.reload(kind);
  },

  ensureLoaded: function (kind) {
    if (this.loaded[kind]) return;
    this.loaded[kind] = true;
    this.reload(kind);
  },

  onContractTab: function (key) {
    if (key === 'contract' || key === 'recv' || key === 'pay') this.ensureLoaded(key);
  },

  importMaster: function (kind, inp) {
    var f = inp.files && inp.files[0];
    if (!f) return;
    var fd = new FormData();
    fd.append('file', f);
    var kindLabel = { contract: '合同', recv: '收款', pay: '付款', milestone: '里程碑' }[kind] || kind;
    toast('导入中：' + kindLabel + '…', true);
    var self = this;
    fetch('/api/core/master/import?kind=' + kind, { method: 'POST', body: fd })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (j.success) {
          var extra = j.warn_curated ? '（裁剪表回写提示：' + j.warn_curated + '）' : '';
          toast('导入成功：' + j.rows + ' 行 / ' + j.columns + ' 列' + extra, true);
          self.page[kind] = 1;
          self.loaded[kind] = true;
          self.reload(kind);
        } else {
          toast('导入失败：' + (j.error || '未知错误'), false);
        }
      })
      .catch(function (e) { toast('导入失败：' + e.message, false); })
      .finally(function () { inp.value = ''; });
  }
};
window.Master = Master;

/* ================================================================
 * 面板路由（系统域单页多面板）
 * 合同 / 项目 为主数据面板；本体可观测 6 面板由 ontology.app.js 渲染。
 * 入口来自 nav.config.js 的 /core?panel=xxx；同页内点击拦截为无刷新切换。
 * ================================================================ */
var PANELS = {
  contract:     { link: 'sys-contract',     crumb: ['系统', '主数据', '合同'],           title: '合同主数据' },
  project:      { link: 'sys-project',      crumb: ['系统', '主数据', '项目'],           title: '项目主数据' },
  ontEntities:  { link: 'sys-ont-entities',  crumb: ['系统', '本体可观测', '实体与关系'],   title: '本体 · 实体与关系' },
  ontKnowledge: { link: 'sys-ont-knowledge', crumb: ['系统', '本体可观测', '知识'],         title: '本体 · 知识' },
  ontActions:   { link: 'sys-ont-actions',   crumb: ['系统', '本体可观测', '动作'],         title: '本体 · 动作' },
  ontTasks:     { link: 'sys-ont-tasks',     crumb: ['系统', '本体可观测', '任务列表'],     title: '本体 · 任务列表' },
  ontLedger:    { link: 'sys-ont-ledger',    crumb: ['系统', '本体可观测', '台账'],         title: '本体 · 台账' },
  ontTopology:  { link: 'sys-ont-topology',  crumb: ['系统', '本体可观测', '拓扑与一致性'], title: '本体 · 拓扑与一致性' }
};

function switchPanel(name, opts) {
  opts = opts || {};
  var meta = PANELS[name];
  if (!meta) { console.warn('[core] 未知面板：' + name); return; }
  var el = document.getElementById('panel-' + name);
  if (!el) { console.warn('[core] 面板容器 #panel-' + name + ' 不存在'); return; }
  document.querySelectorAll('.core-panel').forEach(function (p) { p.classList.remove('active'); });
  el.classList.add('active');
  NC.renderBreadcrumb(document.getElementById('breadcrumb'), meta.crumb);
  NC.renderAccordion(document.getElementById('navRail'), {
    rootTitle: '经营业务工作台', domainLabel: '系统', activeKey: 'sys', activeLink: meta.link
  });
  document.title = meta.title;
  if (!opts.keepUrl) {
    try { history.replaceState(null, '', '/core?panel=' + name); } catch (e) {}
  }
  if (name === 'contract') {
    if (!window._contractLoaded) { window._contractLoaded = true; Master.reload('contract'); }
  } else if (name === 'project') {
    if (!window._projectLoaded) { window._projectLoaded = true; Master.reload('milestone'); }
  } else if (typeof window.loadOntPanel === 'function') {
    window.loadOntPanel(name);
  } else {
    console.error('[core] ontology.app.js 未加载，本体面板无法渲染');
  }
}

/* 侧栏 /core?panel=xxx 链接拦截：同页切换，免整页刷新。 */
function bindPanelLinks() {
  var rail = document.getElementById('navRail');
  if (!rail) return;
  rail.addEventListener('click', function (ev) {
    var a = ev.target.closest && ev.target.closest('a.acc-link');
    if (!a) return;
    var href = a.getAttribute('href') || '';
    var m = href.match(/^\/core\?panel=([A-Za-z]+)$/);
    if (!m || !PANELS[m[1]]) return;
    ev.preventDefault();
    switchPanel(m[1]);
  });
}

function currentPanelFromUrl() {
  var p = new URLSearchParams(location.search).get('panel') || 'contract';
  return PANELS[p] ? p : 'contract';
}

function init() {
  document.getElementById('contractTitleIcon').innerHTML = NC.ICONS.contract;
  document.getElementById('projTitleIcon').innerHTML = NC.ICONS.project;
  NC.renderTopMenu(document.getElementById('topMenu'), { activeKey: 'sys' });
  bindPanelLinks();
  var panel = currentPanelFromUrl();
  switchPanel(panel, { keepUrl: true });
}

window.Core = { switchPanel: switchPanel };
document.addEventListener('DOMContentLoaded', init);
