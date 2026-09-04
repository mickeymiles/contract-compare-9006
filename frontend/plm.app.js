/* ================================================================
 * CC-010 项目全生命周期管理 — 前端逻辑
 *   · 元数据驱动 CRUD 引擎（列表 / 表单 / 删除 / 明细行编辑）
 *   · 专属视图：经营驾驶舱、四算基线、PMO 双进度、人力负荷、
 *              成本毛利、项目全景 7 板块、预警中心、系统配置
 * 规格：changes/2026-08-27-project-lifecycle/specs/CC-010-project-lifecycle/spec.md
 * ================================================================ */
(function (global) {
  'use strict';

  var API = '';
  var OPERATOR = 'admin';

  // ---------------- 基础工具 ----------------
  function h(s) {
    if (s === null || s === undefined) return '';
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function money(v) {
    if (v === null || v === undefined || v === '') return '-';
    var n = Number(v);
    if (isNaN(n)) return h(v);
    if (Math.abs(n) >= 100000000) return (n / 100000000).toFixed(2) + ' 亿';
    if (Math.abs(n) >= 10000) return (n / 10000).toFixed(1) + ' 万';
    return n.toLocaleString('zh-CN', { maximumFractionDigits: 2 });
  }
  function pct(v, digits) {
    if (v === null || v === undefined || v === '') return '-';
    var n = Number(v);
    if (isNaN(n)) return '-';
    return (n * 100).toFixed(digits === undefined ? 1 : digits) + '%';
  }
  function num(v) {
    if (v === null || v === undefined || v === '') return '-';
    var n = Number(v);
    return isNaN(n) ? h(v) : n.toLocaleString('zh-CN', { maximumFractionDigits: 2 });
  }
  function barHtml(v, danger) {
    var p = Math.max(0, Math.min(100, Number(v) || 0));
    return '<div class="plm-prog-cell"><div class="plm-prog"><i class="' +
      (danger || p >= 100 ? (p >= 100 ? 'ok' : 'warn') : '') + '" style="width:' + p +
      '%"></i></div><span>' + p.toFixed(0) + '%</span></div>';
  }
  function diffCell(v) {
    if (v === null || v === undefined) return '<span class="plm-chip gray">-</span>';
    var n = Number(v);
    var cls = n > 0 ? 'pos' : (n < 0 ? 'neg' : '');
    return '<span class="plm-diff ' + cls + '">' + (n > 0 ? '+' : '') + money(n) + '</span>';
  }
  function toast(msg, ok) {
    var t = document.getElementById('plmToast');
    t.textContent = msg;
    t.className = 'toast ' + (ok === false ? 'err' : 'ok') + ' show';
    clearTimeout(t._t);
    t._t = setTimeout(function () { t.classList.remove('show'); }, 2600);
  }
  function qs(sel, root) { return (root || document).querySelector(sel); }
  function qsa(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function escAttr(s) { return h(s); }

  // ---------------- API 封装 ----------------
  function req(method, url, body) {
    var opt = { method: method, headers: { 'Content-Type': 'application/json' } };
    if (body !== undefined && body !== null) opt.body = JSON.stringify(body);
    return fetch(API + url, opt).then(function (r) {
      if (r.status === 204) return { success: true };
      return r.json().catch(function () { return { success: false, error: 'HTTP ' + r.status }; });
    }).catch(function (e) {
      return { success: false, error: '网络异常：' + e.message };
    });
  }
  function GET(url) { return req('GET', url); }
  function POST(url, b) { return req('POST', url, b || {}); }
  function PUT(url, b) { return req('PUT', url, b || {}); }
  function DEL(url) { return req('DELETE', url); }
  function unwrap(res) {
    if (res && res.success === false) { toast(res.error || '操作失败', false); return null; }
    return res && (res.data !== undefined) ? res.data : res;
  }

  // ---------------- 全局状态 ----------------
  var S = {
    active: { view: 'overview', sub: '' },
    lastSub: {},
    pendingAlerts: 0,
    dicts: {},          // category → [label]
    projects: [],       // 项目列表缓存
    contracts: [],
    staff: [],
    milestones: {},     // projectId → [里程碑]
    tasks: {},          // projectId → [任务]
    opportunities: [],
    ctx: {},            // 各视图当前项目 {baseline:3, pmo:3, ...}
    loaded: {}          // 视图是否已初始化
  };

  function loadDicts() {
    return GET('/api/plm/dict').then(function (res) {
      var rows = unwrap(res) || [];
      S.dicts = {};
      rows.forEach(function (d) {
        (S.dicts[d.category] = S.dicts[d.category] || []).push(d.label);
      });
      return S.dicts;
    });
  }
  function dictOf(cat) { return S.dicts[cat] || []; }
  function loadProjects(force) {
    if (S.projects.length && !force) return Promise.resolve(S.projects);
    return GET('/api/plm/projects').then(function (res) {
      S.projects = unwrap(res) || [];
      return S.projects;
    });
  }
  function projectName(pid) {
    var p = S.projects.filter(function (x) { return x.id === Number(pid); })[0];
    return p ? (p.project_no + ' ' + p.project_name) : ('#' + pid);
  }

  // ---------------- 弹窗引擎 ----------------
  function closeModal() {
    document.getElementById('plmModalHost').innerHTML = '';
    document.body.style.overflow = '';
  }
  function showModal(opt) {
    var host = document.getElementById('plmModalHost');
    var fields = opt.fields || [];
    var vals = opt.values || {};
    var html = '<div class="plm-overlay" onclick="if(event.target===this)PLM.closeModal()">' +
      '<div class="plm-dialog" style="max-width:' + (opt.width || 720) + 'px">' +
      '<h3>' + h(opt.title) + '</h3>' +
      (opt.sub ? '<div class="pd-sub">' + h(opt.sub) + '</div>' : '') +
      (opt.bodyHtml || '') +
      (fields.length ? '<div class="plm-form">' + fields.map(function (f) {
        return fieldHtml(f, vals[f.k]);
      }).join('') + '</div>' : '');
    if (opt.itemsCfg) html += itemsEditorHtml(opt.itemsCfg, vals[opt.itemsCfg.key] || []);
    html += (opt.footerHtml || '') +
      '<div class="pd-foot">' +
      '<button class="btn btn-o" onclick="PLM.closeModal()">取消</button>' +
      '<button class="btn btn-c" id="plmModalOk">' + h(opt.okText || '保存') + '</button>' +
      '</div></div></div>';
    host.innerHTML = html;
    document.body.style.overflow = 'hidden';
    var ok = qs('#plmModalOk');
    ok.onclick = function () {
      var payload = collectFields(fields, host);
      if (payload === null) return;
      if (opt.itemsCfg) payload[opt.itemsCfg.key] = collectItems(opt.itemsCfg, host);
      if (opt.transform) payload = opt.transform(payload);
      if (payload === null) return;
      ok.disabled = true;
      ok.textContent = '提交中…';
      Promise.resolve(opt.onSubmit(payload)).then(function (res) {
        if (res === false) { ok.disabled = false; ok.textContent = opt.okText || '保存'; return; }
        closeModal();
        if (res && res.warning) toast(res.warning, true);
        else toast((opt.doneText || '已保存'));
        if (opt.onDone) opt.onDone(res);
      });
    };
    if (opt.afterOpen) opt.afterOpen(host);
    return host;
  }
  function fieldHtml(f, v) {
    var id = 'fld_' + f.k;
    var val = (v === undefined || v === null) ? (f.def !== undefined ? f.def : '') : v;
    var inner;
    if (f.t === 'select') {
      var opts = (f.opts || []).map(function (o) {
        var ov = (typeof o === 'object') ? o.v : o, ol = (typeof o === 'object') ? o.l : o;
        return '<option value="' + escAttr(ov) + '"' + (String(ov) === String(val) ? ' selected' : '') +
          '>' + h(ol) + '</option>';
      }).join('');
      inner = '<select id="' + id + '" data-k="' + f.k + '" data-t="select">' + opts + '</select>';
    } else if (f.t === 'textarea') {
      inner = '<textarea id="' + id + '" data-k="' + f.k + '" data-t="text" placeholder="' +
        escAttr(f.ph || '') + '">' + h(val) + '</textarea>';
    } else if (f.t === 'checkbox') {
      inner = '<label style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--text)">' +
        '<input type="checkbox" id="' + id + '" data-k="' + f.k + '" data-t="bool"' +
        (val ? ' checked' : '') + '> ' + h(f.cbText || '是') + '</label>';
    } else {
      inner = '<input id="' + id + '" data-k="' + f.k + '" data-t="' + (f.t || 'text') +
        '" type="' + (f.t === 'num' ? 'number' : (f.t === 'date' ? 'date' : 'text')) +
        '" step="any" value="' + escAttr(val) + '" placeholder="' + escAttr(f.ph || '') + '"' +
        (f.readonly ? ' readonly' : '') + '>';
    }
    return '<div class="fi' + (f.wide ? ' wide' : '') + '">' +
      '<label for="' + id + '">' + h(f.l) + (f.req ? '<em>*</em>' : '') +
      (f.unit ? ' <span style="color:var(--text2);font-weight:normal">(' + h(f.unit) + ')</span>' : '') +
      '</label>' + inner + (f.hint ? '<div class="hint">' + h(f.hint) + '</div>' : '') + '</div>';
  }
  function collectFields(fields, root) {
    var out = {};
    for (var i = 0; i < fields.length; i++) {
      var f = fields[i];
      var el = document.getElementById('fld_' + f.k);
      if (!el) continue;
      var v;
      if (f.t === 'bool') v = el.checked;
      else if (f.t === 'num') v = el.value === '' ? null : Number(el.value);
      else v = el.value;
      if (f.req && (v === '' || v === null || (f.t === 'num' && isNaN(v)))) {
        toast('「' + f.l + '」为必填项', false);
        el.focus();
        return null;
      }
      if (f.t === 'num' && v !== null && f.min !== undefined && v < f.min) {
        toast('「' + f.l + '」不能小于 ' + f.min, false);
        return null;
      }
      out[f.k] = v;
    }
    return out;
  }
  // 明细行编辑器（概算/预算分项、粗里程碑）
  function itemsEditorHtml(cfg, rows) {
    var catOpts = cfg.cats.map(function (c) { return '<option value="' + escAttr(c) + '">' + h(c) + '</option>'; }).join('');
    var body = (rows || []).map(function (r) { return itemRowHtml(cfg, r, catOpts); }).join('');
    return '<div class="plm-items-edit" id="' + cfg.dom + '">' +
      '<div class="ie-hd"><span>' + h(cfg.title) + '</span>' +
      '<button class="btn btn-o btn-s" type="button" onclick="PLM.addItemRow(\'' + cfg.key + '\')">＋ 添加分项</button>' +
      '<span class="ie-sum">合计 <b id="' + cfg.dom + '_sum">0</b> 元</span></div>' +
      '<table><thead><tr>' + cfg.cols.map(function (c) { return '<th>' + h(c.l) + '</th>'; }).join('') +
      '<th style="width:44px"></th></tr></thead><tbody id="' + cfg.dom + '_body">' + body + '</tbody></table>' +
      (cfg.note ? '<div class="plm-note" style="margin-top:8px">' + h(cfg.note) + '</div>' : '') + '</div>';
  }
  function itemRowHtml(cfg, r, catOpts) {
    r = r || {};
    return '<tr>' + cfg.cols.map(function (c) {
      var v = r[c.k] === undefined || r[c.k] === null ? '' : r[c.k];
      if (c.t === 'select') {
        var opts = (catOpts || cfg.cats.map(function (x) {
          return '<option value="' + escAttr(x) + '">' + h(x) + '</option>';
        }));
        return '<td><select data-ik="' + c.k + '">' + opts.replace('value="' + escAttr(v) + '"',
          'value="' + escAttr(v) + '" selected') + '</select></td>';
      }
      if (c.t === 'num') {
        return '<td><input type="number" step="any" data-ik="' + c.k + '" data-inum="1" value="' +
          escAttr(v) + '" placeholder="' + escAttr(c.ph || '0') + '"></td>';
      }
      return '<td><input data-ik="' + c.k + '" value="' + escAttr(v) + '" placeholder="' +
        escAttr(c.ph || '') + '"></td>';
    }).join('') + '<td style="text-align:right"><button class="row-act del" type="button" ' +
      'onclick="this.closest(\'tr\').remove();PLM.recalcItems(\'' + cfg.key + '\')">✕</button></td></tr>';
  }
  var ITEM_CFGS = {};
  function addItemRow(key) {
    var cfg = ITEM_CFGS[key];
    var tb = qs('#' + cfg.dom + '_body');
    if (!tb) return;
    tb.insertAdjacentHTML('beforeend', itemRowHtml(cfg, {}));
    recalcItems(key);
  }
  function collectItems(cfg, root) {
    return qsa('#' + cfg.dom + '_body tr', root).map(function (tr) {
      var o = {};
      qsa('[data-ik]', tr).forEach(function (el) {
        var k = el.getAttribute('data-ik');
        o[k] = el.getAttribute('data-inum') ? (el.value === '' ? 0 : Number(el.value)) : el.value;
      });
      return o;
    }).filter(function (x) {
      return (x[cfg.sumKey] || 0) || x[cfg.nameKey];
    });
  }
  function recalcItems(key) {
    var cfg = ITEM_CFGS[key];
    var sum = collectItems(cfg).reduce(function (a, r) { return a + (Number(r[cfg.sumKey]) || 0); }, 0);
    var el = document.getElementById(cfg.dom + '_sum');
    if (el) el.textContent = sum.toLocaleString('zh-CN', { maximumFractionDigits: 2 });
    if (cfg.onRecalc) cfg.onRecalc(sum);
  }

  // ---------------- 通用表格渲染 ----------------
  function renderTable(cols, rows, opt) {
    opt = opt || {};
    if (!rows || !rows.length) {
      return '<div class="plm-empty"><span class="e-ico">' + (opt.icon || '📭') + '</span>' +
        h(opt.empty || '暂无数据') + (opt.emptyHint ?
          '<br><span style="font-size:11px">' + h(opt.emptyHint) + '</span>' : '') + '</div>';
    }
    var thead = '<thead><tr>' + cols.map(function (c) {
      return '<th' + (c.n ? ' class="num"' : '') + '>' + h(c.l) + '</th>';
    }).join('') + (opt.acts ? '<th class="act" style="text-align:right">操作</th>' : '') + '</tr></thead>';
    var tbody = '<tbody>' + rows.map(function (r, i) {
      return '<tr>' + cols.map(function (c) {
        var v = cellVal(c, r, i);
        return '<td' + (c.n ? ' class="num"' : '') + '>' + v + '</td>';
      }).join('') + (opt.acts ? '<td class="act">' + opt.acts(r, i) + '</td>' : '') + '</tr>';
    }).join('') + '</tbody>';
    return '<div class="plm-wrap"><table>' + thead + tbody + '</table></div>';
  }
  function cellVal(c, r, i) {
    if (c.render) return c.render(r[c.k], r, i);
    var v = r[c.k];
    if (c.t === 'money') return money(v);
    if (c.t === 'num') return num(v);
    if (c.t === 'pct') {
      if (v === null || v === undefined) return '-';
      var n = Number(v);
      var cls = c.danger !== false && n >= 1 ? ' color:var(--red)' : '';
      return '<span style="font-family:var(--mono)' + cls + '">' + pct(v) + '</span>';
    }
    if (c.t === 'diff') return diffCell(v);
    if (c.t === 'badge') {
      var map = c.map || {};
      return '<span class="plm-chip ' + (map[v] || 'gray') + '">' + h(v || '-') + '</span>';
    }
    if (c.t === 'bar') {
      var p = Math.max(0, Math.min(100, Number(v) || 0));
      var kc = p >= 100 ? 'ok' : (p <= 0 ? '' : '');
      return '<div class="plm-prog-cell"><div class="plm-prog"><i class="' + kc +
        '" style="width:' + p + '%"></i></div><span>' + p.toFixed(0) + '%</span></div>';
    }
    if (c.t === 'date') return v ? h(String(v).slice(0, 10)) : '-';
    return v === null || v === undefined || v === '' ? '<span style="color:var(--text2)">-</span>' : h(v);
  }
  function actBtn(label, fn, arg, cls) {
    return '<button class="row-act ' + (cls || '') + '" onclick="' + fn + '(' + JSON.stringify(arg) +
      ')">' + h(label) + '</button>';
  }

  // ---------------- 元数据驱动的 CRUD 模块 ----------------
  var MODULES = {
    staff: {
      title: '人员池', api: '/api/plm/staff', icon: '👤',
      emptyHint: '录入姓名、岗位、人力成本单价（元/人天）与月可用工时',
      cols: [
        { k: 'name', l: '姓名' }, { k: 'role', l: '岗位' }, { k: 'dept', l: '部门' },
        { k: 'cost_rate', l: '单价(元/人天)', n: 1, t: 'num' },
        { k: 'available_hours', l: '可用工时', n: 1, t: 'num' },
        { k: 'planned_hours', l: '已分配', n: 1, t: 'num' },
        { k: 'actual_hours', l: '实际工时', n: 1, t: 'num' },
        { k: 'load_rate', l: '负荷率', n: 1, t: 'pct' },
        { k: 'load_state', l: '负荷', t: 'badge', map: { 过载: 'red', 正常: 'green', 闲置: 'gray' } },
        { k: 'parallel_projects', l: '并行项目', n: 1, t: 'num' },
        { k: 'status', l: '状态', t: 'badge', map: { 可用: 'green', 占用: 'orange', 休假: 'gray', 离职: 'red' } }
      ],
      fields: function () {
        return [
          { k: 'name', l: '姓名', req: 1 },
          { k: 'role', l: '岗位', t: 'select', opts: dictOf('role') },
          { k: 'dept', l: '归属部门' },
          { k: 'cost_rate', l: '人力成本单价', t: 'num', unit: '元/人天', req: 1, min: 0 },
          { k: 'available_hours', l: '月可用工时', t: 'num', unit: '小时/月', def: 160, min: 1 },
          { k: 'status', l: '在职状态', t: 'select', opts: dictOf('staff_status') },
          { k: 'skills', l: '技能标签' },
          { k: 'remark', l: '备注', t: 'textarea', wide: 1 }
        ];
      }
    },
    assignment: {
      title: '人员分配', api: '/api/plm/assignments', icon: '🔗',
      emptyHint: '把人员绑定到项目 / 里程碑 / 任务，并填写计划工时',
      cols: [
        { k: 'staff_name', l: '人员' }, { k: 'role_in_proj', l: '项目角色' },
        { k: 'project_no', l: '项目' },
        { k: 'milestone_name', l: '里程碑' }, { k: 'task_name', l: '任务' },
        { k: 'planned_hours', l: '计划工时', n: 1, t: 'num' },
        { k: 'start_date', l: '开始', t: 'date' }, { k: 'end_date', l: '结束', t: 'date' },
        { k: 'status', l: '状态', t: 'badge', map: { 生效中: 'green', 已解除: 'gray' } }
      ],
      fields: function () {
        return [
          { k: 'staff_id', l: '人员', t: 'select', opts: opts(S.staff, 'id', 'name'), req: 1 },
          { k: 'project_id', l: '项目', t: 'select', opts: opts(S.projects, 'id', 'project_no', 'project_name'), req: 1 },
          { k: 'milestone_id', l: '里程碑', t: 'select', opts: [{ v: '', l: '（不绑定）' }] },
          { k: 'task_id', l: '任务', t: 'select', opts: [{ v: '', l: '（不绑定）' }] },
          { k: 'planned_hours', l: '计划工时', t: 'num', unit: '小时', req: 1, min: 0 },
          { k: 'role_in_proj', l: '项目角色', t: 'select', opts: dictOf('role') },
          { k: 'start_date', l: '开始日期', t: 'date' }, { k: 'end_date', l: '结束日期', t: 'date' },
          { k: 'status', l: '状态', t: 'select', opts: ['生效中', '已解除'] },
          { k: 'remark', l: '备注', t: 'textarea', wide: 1 }
        ];
      }
    },
    timesheet: {
      title: '工时填报', api: '/api/plm/timesheets', icon: '⏱',
      emptyHint: '填报后系统按「工时 ÷ 8 × 人天单价」自动归集实际人力成本',
      cols: [
        { k: 'work_date', l: '日期', t: 'date' }, { k: 'staff_name', l: '人员' },
        { k: 'project_no', l: '项目' }, { k: 'task_name', l: '任务' },
        { k: 'hours', l: '工时', n: 1, t: 'num' }, { k: 'remark', l: '备注' }
      ],
      fields: function () {
        return [
          { k: 'staff_id', l: '人员', t: 'select', opts: opts(S.staff, 'id', 'name'), req: 1 },
          { k: 'project_id', l: '项目', t: 'select', opts: opts(S.projects, 'id', 'project_no', 'project_name'), req: 1 },
          { k: 'task_id', l: '关联任务', t: 'select', opts: [{ v: '', l: '（不关联）' }] },
          { k: 'work_date', l: '工作日期', t: 'date', req: 1, def: today() },
          { k: 'hours', l: '工时', t: 'num', unit: '小时', req: 1, min: 0.5 },
          { k: 'remark', l: '备注', t: 'textarea', wide: 1 }
        ];
      }
    },
    contract: {
      title: '合同主数据', api: '/api/plm/contracts', icon: '📄',
      emptyHint: '合同编号留空时自动生成 HT-年份-序号',
      cols: [
        { k: 'contract_no', l: '合同编号' }, { k: 'contract_name', l: '合同名称' },
        { k: 'customer', l: '客户' }, { k: 'sign_amount', l: '签约金额', n: 1, t: 'money' },
        { k: 'sign_date', l: '签约日期', t: 'date' }, { k: 'project_cycle', l: '项目周期' },
        { k: 'owner', l: '负责人' },
        { k: 'status', l: '状态', t: 'badge', map: { 已签署: 'green', 草签: 'orange', 执行中: 'purple', 已结项: 'gray', 已终止: 'red' } },
        { k: 'opp_no', l: '来源商机' }, { k: 'project_count', l: '项目数', n: 1, t: 'num' }
      ],
      fields: function () {
        return [
          { k: 'contract_no', l: '合同编号', hint: '留空自动生成' },
          { k: 'contract_name', l: '合同名称', req: 1 },
          { k: 'customer', l: '客户名称', req: 1 },
          { k: 'sign_amount', l: '签约金额', t: 'num', unit: '元', req: 1, min: 0 },
          { k: 'sign_date', l: '签约日期', t: 'date' },
          { k: 'project_cycle', l: '项目周期', ph: '如 2026-01 ~ 2026-12' },
          { k: 'industry', l: '行业', t: 'select', opts: dictOf('industry') },
          { k: 'region', l: '区域' }, { k: 'dept', l: '归属部门' },
          { k: 'owner', l: '合同负责人' },
          { k: 'status', l: '合同状态', t: 'select', opts: dictOf('contract_status') },
          { k: 'opportunity_id', l: '来源商机', t: 'select', opts: [{ v: '', l: '（无，直接建合同）' }].concat(opts(S.opportunities, 'id', 'opp_no', 'opp_name')) },
          { k: 'remark', l: '备注', t: 'textarea', wide: 1 }
        ];
      }
    },
    project: {
      title: '项目', api: '/api/plm/projects', icon: '🗂',
      emptyHint: '项目编号留空自动生成 XM-年份-序号',
      cols: [
        { k: 'project_no', l: '项目编号' }, { k: 'project_name', l: '项目名称' },
        { k: 'customer', l: '客户' }, { k: 'manager', l: '项目经理' },
        { k: 'status', l: '状态', t: 'badge', map: { 待启动: 'gray', 执行中: 'green', 暂停: 'orange', 结项: 'purple' } },
        { k: 'estimate_cost', l: '概算', n: 1, t: 'money' },
        { k: 'budget_cost', l: '预算', n: 1, t: 'money' },
        { k: 'actual_cost', l: '实际成本', n: 1, t: 'money' },
        { k: 'actual_gross_rate', l: '毛利率', n: 1, t: 'pct' },
        { k: 'milestone_done', l: '里程碑', n: 1, render: function (v, r) {
          return '<span style="font-family:var(--mono)">' + (v || 0) + '/' + (r.milestone_total || 0) + '</span>' +
            (r.milestone_overdue ? ' <span class="plm-chip red">延期' + r.milestone_overdue + '</span>' : '');
        } },
        { k: 'open_alerts', l: '预警', n: 1, render: function (v) {
          return v ? '<span class="plm-chip red">' + v + '</span>' : '<span class="plm-chip green">0</span>';
        } }
      ],
      fields: function () {
        return [
          { k: 'project_no', l: '项目编号', hint: '留空自动生成' },
          { k: 'project_name', l: '项目名称', req: 1 },
          { k: 'customer', l: '客户' }, { k: 'manager', l: '项目经理', req: 1 },
          { k: 'dept', l: '归属部门' }, { k: 'region', l: '区域' },
          { k: 'status', l: '项目状态', t: 'select', opts: dictOf('project_status') },
          { k: 'contract_id', l: '所属合同', t: 'select', opts: [{ v: '', l: '（未关联）' }].concat(opts(S.contracts, 'id', 'contract_no', 'contract_name')) },
          { k: 'opportunity_id', l: '来源商机', t: 'select', opts: [{ v: '', l: '（未关联）' }].concat(opts(S.opportunities, 'id', 'opp_no', 'opp_name')) },
          { k: 'kickoff_date', l: '立项日期', t: 'date' },
          { k: 'start_date', l: '执行开始', t: 'date' }, { k: 'end_date', l: '执行结束', t: 'date' },
          { k: 'remark', l: '项目说明', t: 'textarea', wide: 1 }
        ];
      }
    },
    ledger: {
      title: '收支台账', api: '/api/plm/ledger', icon: '💰',
      emptyHint: '收入录「签单收入 / 变更收入」，成本录「预估」与「实际」两档',
      cols: [
        { k: 'occur_date', l: '发生日期', t: 'date' },
        { k: 'project_no', l: '项目', render: function (v, r) { return h(v || projectName(r.project_id)); } },
        { k: 'kind', l: '方向', t: 'badge', map: { income: 'green', cost: 'orange' }, render: function (v) {
          return '<span class="plm-chip ' + (v === 'income' ? 'green' : 'orange') + '">' + (v === 'income' ? '收入' : '成本') + '</span>';
        } },
        { k: 'category', l: '科目' }, { k: 'plan_or_actual', l: '口径' },
        { k: 'amount', l: '金额', n: 1, t: 'money' },
        { k: 'source', l: '来源', t: 'badge', map: { 工时归集: 'purple', 手工录入: 'gray' } },
        { k: 'remark', l: '备注' }
      ],
      fields: function () {
        return [
          { k: 'project_id', l: '项目', t: 'select', opts: opts(S.projects, 'id', 'project_no', 'project_name'), req: 1 },
          { k: 'kind', l: '方向', t: 'select', opts: [{ v: 'income', l: '收入' }, { v: 'cost', l: '成本' }], req: 1 },
          { k: 'category', l: '科目', t: 'select', opts: dictOf('income_category').concat(dictOf('cost_category')), req: 1 },
          { k: 'plan_or_actual', l: '口径', t: 'select', opts: ['实际', '预估'] },
          { k: 'amount', l: '金额', t: 'num', unit: '元', req: 1 },
          { k: 'occur_date', l: '发生日期', t: 'date', def: today() },
          { k: 'remark', l: '备注', t: 'textarea', wide: 1 }
        ];
      },
      lockedField: function (r) { return r.source === '工时归集'; }
    }
  };
  function opts(list, vKey, lKey, lKey2) {
    return (list || []).map(function (x) {
      return { v: x[vKey], l: lKey2 ? (x[lKey] + ' ' + x[lKey2]) : x[lKey] };
    });
  }
  function today() { return new Date().toISOString().slice(0, 10); }

  // 通用 CRUD 表格容器
  function crudHost(key, cfg, extraActs) {
    return '<div class="plm-card"><h3>' + cfg.icon + ' ' + h(cfg.title) +
      '<span class="hc-sub" id="' + key + '_count"></span>' +
      '<span class="hc-act">' +
      '<input id="' + key + '_kw" placeholder="搜索…" style="background:var(--bg3);border:1px solid var(--border);color:var(--text);padding:5px 9px;border-radius:7px;font-size:11px" onkeydown="if(event.key===\'Enter\')PLM.crud(\'' + key + '\')">' +
      '<button class="btn btn-o btn-s" onclick="PLM.crud(\'' + key + '\')">🔍 查询</button>' +
      '<button class="btn btn-c btn-s" onclick="PLM.crudNew(\'' + key + '\')">＋ 新建</button>' +
      '</span></h3><div id="' + key + '_table"><div class="plm-loading">加载中…</div></div></div>';
  }
  function crud(key, keepFilters) {
    var cfg = MODULES[key];
    var table = qs('#' + key + '_table');
    if (!table) return Promise.resolve();
    table.innerHTML = '<div class="plm-loading">加载中…</div>';
    var kwEl = qs('#' + key + '_kw');
    var url = cfg.api + '?operator=' + encodeURIComponent(OPERATOR);
    if (kwEl && kwEl.value.trim()) url += '&keyword=' + encodeURIComponent(kwEl.value.trim());
    if (cfg.projectScoped && S.ctx[key] !== undefined && S.ctx[key] !== '') {
      url += (url.indexOf('?') >= 0 ? '&' : '?') + 'project_id=' + S.ctx[key];
    }
    return GET(url).then(function (res) {
      var rows = unwrap(res) || [];
      if (key === 'staff') S.staff = rows;
      if (key === 'contract') S.contracts = rows;
      if (key === 'project') S.projects = rows;
      if (key === 'opportunity') S.opportunities = rows;
      var cnt = qs('#' + key + '_count');
      if (cnt) cnt.textContent = rows.length + ' 条';
      table.innerHTML = renderTable(cfg.cols, rows, {
        icon: cfg.icon, empty: '还没有' + cfg.title + '数据', emptyHint: cfg.emptyHint,
        acts: function (r) {
          var locked = cfg.lockedField && cfg.lockedField(r);
          var html = (cfg.rowActs || []).map(function (a) {
            return '<button class="row-act" onclick="PLM.' + a.fn + '(' + r.id + ')">' + h(a.l) + '</button>';
          }).join('');
          if (locked) {
            html += '<span class="plm-chip purple" title="由系统自动维护">系统维护</span>';
          } else {
            if (!cfg.noEdit) {
              html += '<button class="row-act" onclick="PLM.crudEdit(\'' + key + '\',' + r.id + ')">编辑</button>';
            }
            html += '<button class="row-act del" onclick="PLM.crudDel(\'' + key + '\',' + r.id + ')">删除</button>';
          }
          return html;
        }
      });
      return rows;
    });
  }
  function crudForm(key, row) {
    var cfg = MODULES[key];
    return {
      title: (row ? '编辑' : '新增') + cfg.title,
      sub: cfg.sub || '',
      fields: cfg.fields(),
      values: row || {},
      itemsCfg: cfg.itemsCfg || null,
      okText: row ? '保存修改' : '创建',
      onSubmit: function (payload) {
        payload.operator = OPERATOR;
        var p = row ? PUT(cfg.api + '/' + row.id, payload) : POST(cfg.api, payload);
        return p.then(function (res) {
          var d = unwrap(res);
          if (d === null) return false;
          return d;
        });
      },
      onDone: function () {
        if (cfg.afterSave) cfg.afterSave();
        refreshCaches().then(function () { crud(key); });
        afterMutate(key);
      }
    };
  }
  function crudNew(key) {
    var cfg = MODULES[key];
    var pre = {};
    if (cfg.projectScoped && S.ctx[key]) pre.project_id = Number(S.ctx[key]);
    if (cfg.preset) cfg.preset(pre);
    var opt = crudForm(key, null);
    opt.values = pre;
    opt.afterOpen = function (host) { bindDynamicOptions(key, host, pre); if (cfg.itemsCfg) recalcItems(cfg.itemsCfg.key); };
    showModal(opt);
  }
  function crudEdit(key, id) {
    var cfg = MODULES[key];
    var list = { staff: S.staff, contract: S.contracts, project: S.projects, opportunities: S.opportunities }[key];
    var row = (cfg.sourceRows ? cfg.sourceRows() : []).filter(function (x) { return x.id === id; })[0];
    var open = function (r) {
      var opt = crudForm(key, r);
      opt.afterOpen = function (host) { bindDynamicOptions(key, host, r); if (cfg.itemsCfg) recalcItems(cfg.itemsCfg.key); };
      showModal(opt);
    };
    if (row) return open(row);
    GET(cfg.api).then(function (res) {
      var rows = unwrap(res) || [];
      if (key === 'staff') S.staff = rows;
      if (key === 'timesheet') { /* 明细含 join 字段 */ }
      var hit = rows.filter(function (x) { return x.id === id; })[0] || { id: id };
      open(hit);
    });
  }
  function crudDel(key, id) {
    var cfg = MODULES[key];
    if (!global.confirm('确认删除该' + cfg.title + '记录？删除后不可恢复。')) return;
    DEL(cfg.api + '/' + id).then(function (res) {
      var r = res;
      if (r.success === false) { toast(r.error + (r.refs ? '（' + JSON.stringify(r.refs) + '）' : ''), false); return; }
      toast('已删除');
      refreshCaches().then(function () { crud(key); });
      afterMutate(key);
    });
  }
  // 表单里依赖项目的动态下拉（里程碑 / 任务）
  function bindDynamicOptions(key, host, row) {
    var projSel = qs('#fld_project_id', host);
    if (!projSel) return;
    var fill = function () {
      var pid = projSel.value;
      if (!pid) return;
      Promise.all([
        GET('/api/plm/projects/' + pid + '/milestones'),
        GET('/api/plm/projects/' + pid + '/tasks')
      ]).then(function (rs) {
        var ms = unwrap(rs[0]) || [], tk = unwrap(rs[1]) || [];
        var mSel = qs('#fld_milestone_id', host), tSel = qs('#fld_task_id', host);
        if (mSel) fillSelect(mSel, ms.map(function (m) {
          return { v: m.id, l: (m.level === '粗' ? '【粗】' : '【细】') + m.name };
        }), row && row.milestone_id);
        if (tSel) fillSelect(tSel, tk.map(function (t) { return { v: t.id, l: t.name }; }), row && row.task_id);
      });
    };
    projSel.onchange = fill;
    fill();
  }
  function fillSelect(sel, list, keep) {
    var head = '<option value="">（不绑定）</option>';
    sel.innerHTML = head + list.map(function (o) {
      return '<option value="' + o.v + '"' + (String(o.v) === String(keep || '') ? ' selected' : '') + '>' + h(o.l) + '</option>';
    }).join('');
  }
  function afterMutate(key) {
    // 数据变更后刷新受影响的视图
    if (['timesheet', 'assignment', 'staff', 'ledger'].indexOf(key) >= 0) {
      ['finance', 'pmo', 'panorama', 'overview'].forEach(function (v) { S.loaded[v] = false; });
    }
    if (['contract', 'project', 'opportunity'].indexOf(key) >= 0) {
      ['baseline', 'pmo', 'finance', 'panorama', 'labor', 'overview'].forEach(function (v) { S.loaded[v] = false; });
    }
    if (key === 'opportunity') ['opportunity'].forEach(function (v) { S.loaded[v] = false; });
  }
  function refreshCaches() {
    return Promise.all([
      loadProjects(true),
      GET('/api/plm/contracts').then(function (r) { S.contracts = unwrap(r) || []; }),
      GET('/api/plm/staff').then(function (r) { S.staff = unwrap(r) || []; }),
      GET('/api/plm/opportunities').then(function (r) { S.opportunities = unwrap(r) || []; })
    ]);
  }

  // ==== VIEWS ====

  // ---------- 通用：项目上下文选择器 ----------
  function projSelector(viewKey, extra) {
    var cur = S.ctx[viewKey] === undefined ? '' : String(S.ctx[viewKey]);
    var list = S.projects;
    if (!list.length) {
      return '<div class="plm-card"><div class="plm-empty"><span class="e-ico">🗂</span>' +
        '尚无任何项目<br><span style="font-size:11px">请先在「售前商机」中标联动立项，或在「合同与立项」新建项目</span></div></div>';
    }
    return '<div class="plm-bar"><label>当前项目</label>' +
      '<select onchange="PLM.ctxChange(\'' + viewKey + '\',this.value)">' +
      '<option value="">请选择项目…</option>' +
      list.map(function (p) {
        return '<option value="' + p.id + '"' + (String(p.id) === cur ? ' selected' : '') + '>' +
          h(p.project_no + ' · ' + p.project_name) + (p.status ? '（' + h(p.status) + '）' : '') + '</option>';
      }).join('') + '</select>' + (extra || '') + '</div>';
  }
  function ensureCtx(viewKey) {
    if (S.ctx[viewKey] === undefined || S.ctx[viewKey] === '') {
      var first = S.projects.filter(function (p) { return p.status !== '结项'; })[0] || S.projects[0];
      S.ctx[viewKey] = first ? first.id : '';
    }
    return S.ctx[viewKey];
  }
  function ctxChange(viewKey, val) {
    S.ctx[viewKey] = val;
    renderView(viewKey, true);
  }
  function pageHead(title, sub, extra) {
    return '<div class="plm-page-hd"><h2>' + title + '</h2>' +
      (sub ? '<span class="pp-sub">' + h(sub) + '</span>' : '') +
      '<span class="pp-sp"></span>' + (extra || '') + '</div>';
  }
  function noCtx(viewKey) {
    return '<div class="plm-card"><div class="plm-empty"><span class="e-ico">👆</span>' +
      '请先在上方选择一个项目</div></div>';
  }
  // ---------- 1 经营驾驶舱 ----------
  function viewOverview() {
    var el = qs('#v-overview');
    el.innerHTML = '<div class="plm-page-hd"><h2>📡 经营驾驶舱</h2>' +
      '<span class="pp-sub">四算为纲 · 财经为尺 · PMO为缰 · 人力为本</span><span class="pp-sp"></span>' +
      '<button class="btn btn-o btn-s" onclick="PLM.exportReport(\'project_compare\')">📥 概算预算对比表</button>' +
      '<button class="btn btn-o btn-s" onclick="PLM.exportReport(\'cost\')">📥 成本毛利表</button>' +
      '<button class="btn btn-c btn-s" onclick="PLM.scanAlerts()">⚠️ 重算预警</button></div>' +
      '<div class="plm-loading">加载中…</div>';
    return GET('/api/plm/overview').then(function (res) {
      var d = unwrap(res);
      if (!d) { el.innerHTML = '<div class="plm-empty">加载失败</div>'; return; }
      var k = d.kpi;
      var cards = [
        ['在管项目', k.projects, 'c', '执行中 ' + (d.project_by_status['执行中'] || 0) + ' 个'],
        ['售前商机', k.opportunities, 'c', '中标 ' + k.won_opportunities + ' 个'],
        ['合同签约额', money(k.sign_amount), 'c', k.contracts + ' 份合同'],
        ['概算总成本', money(k.estimate_total), 'p', '顶层管控基线'],
        ['执行预算', money(k.budget_total), 'p', '预算消耗 ' + pct(k.budget_usage_rate)],
        ['累计实际成本', money(k.actual_cost), 'o', ''],
        ['实际毛利', money(k.actual_gross), (k.actual_gross >= 0 ? 'g' : 'r'), '毛利率 ' + pct(k.actual_gross_rate)],
        ['未闭环预警', k.open_alerts, k.open_alerts > 0 ? 'r' : 'g', '待处理优先']
      ].map(function (c) {
        return '<div class="k"><div class="kl">' + h(c[0]) + '</div><div class="kv ' + c[2] + '">' +
          h(c[1]) + '</div>' + (c[3] ? '<div class="kn">' + h(c[3]) + '</div>' : '') + '</div>';
      }).join('');
      var dimChips = ['cost', 'gross', 'schedule', 'staff'].map(function (dm) {
        var cn = { cost: '成本超耗', gross: '毛利偏低', schedule: '进度延期', staff: '人员过载' }[dm];
        return '<span class="plm-chip ' + (d.alert_by_dim[dm] ? 'red' : 'green') + '">' + cn + ' ' +
          (d.alert_by_dim[dm] || 0) + '</span>';
      }).join('');
      el.innerHTML = '<div class="plm-page-hd"><h2>📡 经营驾驶舱</h2>' +
        '<span class="pp-sub">项目维度经营总览</span><span class="pp-sp"></span>' +
        '<button class="btn btn-o btn-s" onclick="PLM.exportReport(\'project_compare\')">📥 概算预算对比表</button>' +
        '<button class="btn btn-o btn-s" onclick="PLM.exportReport(\'cost\')">📥 成本毛利表</button>' +
        '<button class="btn btn-o btn-s" onclick="PLM.exportReport(\'schedule\')">📥 PMO进度表</button>' +
        '<button class="btn btn-c btn-s" onclick="PLM.scanAlerts()">⚠️ 重算预警</button></div>' +
        '<div class="plm-kpi">' + cards + '</div>' +
        '<div class="plm-2col">' +
        '<div class="plm-card"><h3>🚩 项目健康度<span class="hc-sub">进度 / 成本 / 预警</span></h3>' +
        renderTable([
          { k: 'project_no', l: '项目编号' }, { k: 'project_name', l: '项目名称' },
          { k: 'status', l: '状态', t: 'badge', map: { 待启动: 'gray', 执行中: 'green', 暂停: 'orange', 结项: 'purple' } },
          { k: 'budget_cost', l: '预算', n: 1, t: 'money' },
          { k: 'actual_cost', l: '实际', n: 1, t: 'money' },
          { k: 'consume', l: '消耗率', n: 1, render: function (v, r) {
            var rate = (r.budget_cost && r.actual_cost !== null) ? r.actual_cost / r.budget_cost : null;
            if (rate === null) return '<span style="color:var(--text2)">-</span>';
            var w = Math.min(100, rate * 100);
            return '<div class="plm-prog-cell"><div class="plm-prog"><i class="' + (rate > 1 ? 'warn' : '') +
              '" style="width:' + w + '%"></i></div><span>' + pct(rate, 0) + '</span></div>';
          } },
          { k: 'milestone_done', l: '里程碑', n: 1, render: function (v, r) {
            return '<span style="font-family:var(--mono)">' + (v || 0) + '/' + (r.milestone_total || 0) + '</span>' +
              (r.milestone_overdue ? ' <span class="plm-chip red">延' + r.milestone_overdue + '</span>' : '');
          } },
          { k: 'actual_gross_rate', l: '毛利率', n: 1, t: 'pct' },
          { k: 'open_alerts', l: '预警', n: 1, render: function (v) {
            return v ? '<span class="plm-chip red">' + v + '</span>' : '<span class="plm-chip green">0</span>';
          } }
        ], d.projects, { icon: '🗂', empty: '暂无项目', emptyHint: '先在「售前商机」录入商机并联动立项',
          acts: function (r) {
            return '<button class="row-act" onclick="PLM.openProjPanorama(' + r.id + ')">全景</button>' +
              '<button class="row-act" onclick="PLM.go(\'pmo\');PLM.ctxChange(\'pmo\',' + r.id + ')">进度</button>';
          } }) + '</div>' +
        '<div class="plm-card"><h3>⚠️ 待处理风险<span class="hc-sub">' + dimChips + '</span></h3>' +
        renderTable([
          { k: 'project_no', l: '项目', render: function (v, r) { return h(v || r.project_name || '-'); } },
          { k: 'dim', l: '维度', render: function (v) {
            var cn = { cost: '成本', gross: '毛利', schedule: '进度', staff: '人员' }[v] || v;
            return '<span class="plm-chip gray">' + h(cn) + '</span>';
          } },
          { k: 'level', l: '等级', t: 'badge', map: { 严重: 'red', 警告: 'orange', 提醒: 'gray' } },
          { k: 'title', l: '预警内容' },
          { k: 'status', l: '状态', t: 'badge', map: { 待处理: 'red', 处理中: 'orange', 已闭环: 'green' } }
        ], d.alerts, { icon: '✅', empty: '当前无未闭环预警', emptyHint: '点击「重算预警」按启用规则扫描全部项目',
          acts: function (r) {
            return '<button class="row-act" onclick="PLM.handleAlert(' + r.id + ')">处置</button>';
          } }) + '</div></div>';
      S.loaded.overview = true;
    });
  }

  // ---------- 2 售前商机 ----------
  MODULES.opportunity = {
    title: '商机', api: '/api/plm/opportunities', icon: '🎯',
    sourceRows: function () { return S.opportunities; },
    emptyHint: '录入客户、跟进人与预估收入后，再录入投标概算分项',
    cols: [
      { k: 'opp_no', l: '商机编号' }, { k: 'opp_name', l: '商机名称' },
      { k: 'customer', l: '客户' }, { k: 'owner', l: '跟进人' },
      { k: 'status', l: '状态', t: 'badge', map: { 跟进中: 'gray', 投标中: 'orange', 中标: 'green', 流标: 'red' } },
      { k: 'bid_date', l: '投标日期', t: 'date' },
      { k: 'expect_income', l: '预估收入', n: 1, t: 'money' },
      { k: 'est_cost', l: '概算成本', n: 1, t: 'money' },
      { k: 'est_gross_rate', l: '预估毛利率', n: 1, t: 'pct' },
      { k: 'item_count', l: '概算分项', n: 1, render: function (v, r) {
        return r.has_estimate ? '<span class="plm-chip green">' + (v || 0) + ' 项</span>'
          : '<span class="plm-chip orange">未录概算</span>';
      } }
    ],
    rowActs: [{ l: '概算', fn: 'estOpp' }, { l: '跟进', fn: 'followOpp' },
              { l: '资料', fn: 'docOpp' }, { l: '立项', fn: 'convertOpp' }],
    fields: function () {
      return [
        { k: 'opp_no', l: '商机编号', hint: '留空自动生成 SJ-年份-序号' },
        { k: 'opp_name', l: '商机名称', req: 1 },
        { k: 'customer', l: '客户名称', req: 1 },
        { k: 'owner', l: '跟进人', req: 1 },
        { k: 'dept', l: '归属部门' }, { k: 'region', l: '区域' },
        { k: 'industry', l: '行业', t: 'select', opts: dictOf('industry') },
        { k: 'status', l: '商机状态', t: 'select', opts: dictOf('opp_status'), req: 1 },
        { k: 'bid_date', l: '计划投标日期', t: 'date' },
        { k: 'expect_income', l: '预估收入', t: 'num', unit: '元', min: 0 },
        { k: 'won_at', l: '中标日期', t: 'date' },
        { k: 'remark', l: '商机说明', t: 'textarea', wide: 1 }
      ];
    }
  };
  function viewOpportunity() {
    var el = qs('#v-opportunity');
    el.innerHTML = '<div class="plm-page-hd"><h2>🎯 售前商机与投标概算</h2>' +
      '<span class="pp-sub">模块一 · 沉淀售前基线，中标后可一键联动立项</span></div>' +
      '<div class="plm-bar"><label>状态筛选</label>' +
      '<select onchange="PLM.oppFilter(this.value)"><option value="全部">全部</option>' +
      dictOf('opp_status').map(function (s) { return '<option>' + h(s) + '</option>'; }).join('') + '</select>' +
      '<span class="plm-note" style="margin-left:auto">概算总成本由分项明细自动汇总；毛利率 = （预估收入 − 概算成本）÷ 预估收入</span></div>' +
      '<div id="oppHost">' + crudHost('opportunity', MODULES.opportunity) + '</div>';
    S.loaded.opportunity = true;
    return crud('opportunity');
  }
  function oppFilter(status) {
    var url = '/api/plm/opportunities' + (status && status !== '全部' ? '?status=' + encodeURIComponent(status) : '');
    return GET(url).then(function (res) {
      var rows = unwrap(res) || [];
      S.opportunities = rows;
      qs('#opportunity_table').innerHTML = renderTable(MODULES.opportunity.cols, rows, {
        icon: '🎯', empty: '无匹配商机',
        acts: function (r) {
          return MODULES.opportunity.rowActs.map(function (a) {
            return '<button class="row-act" onclick="PLM.' + a.fn + '(' + r.id + ')">' + h(a.l) + '</button>';
          }).join('') +
            '<button class="row-act" onclick="PLM.crudEdit(\'opportunity\',' + r.id + ')">编辑</button>' +
            '<button class="row-act del" onclick="PLM.crudDel(\'opportunity\',' + r.id + ')">删除</button>';
        }
      });
    });
  }
  function estOpp(id) {
    GET('/api/plm/opportunities/' + id).then(function (res) {
      var o = unwrap(res);
      if (!o) return;
      var est = o.estimate || {};
      ITEM_CFGS.estimate_items.cats = dictOf('cost_category');
      showModal({
        title: '投标概算 · ' + o.opp_name,
        sub: '录入预估收入与分项概算明细，系统自动汇总概算总成本、预估毛利与毛利率（FR-1）',
        width: 780,
        fields: [{ k: 'total_income', l: '预估收入', t: 'num', unit: '元', req: 1, min: 0 }],
        values: { total_income: est.total_income || o.expect_income || 0 },
        itemsCfg: ITEM_CFGS.estimate_items,
        okText: '保存概算',
        footerHtml: '<div class="plm-note" id="estPreview" style="margin-top:12px"></div>',
        doneText: '投标概算已保存'
      });
      ITEM_CFGS.estimate_items.onRecalc = function (sum) {
        var inc = Number(qs('#fld_total_income').value || 0);
        qs('#estPreview').innerHTML = '概算总成本 <b style="font-family:var(--mono);color:var(--cyan2)">' +
          sum.toLocaleString() + '</b> 元 ｜ 预估毛利 <b style="font-family:var(--mono);color:' +
          ((inc - sum) >= 0 ? 'var(--green)' : 'var(--red)') + '">' + (inc - sum).toLocaleString() +
          '</b> 元 ｜ 毛利率 <b style="font-family:var(--mono)">' +
          (inc > 0 ? pct((inc - sum) / inc) : '-') + '</b>';
      };
      if (est.items) {
        setTimeout(function () {
          var tb = qs('#ie_est_body');
          if (tb) tb.innerHTML = est.items.map(function (it) {
            return itemRowHtml(ITEM_CFGS.estimate_items, it);
          }).join('');
          recalcItems('estimate_items');
        }, 0);
      }
      var body = qs('#plmModalHost');
      qs('#plmModalOk').onclick = function () {
        var inc = Number(qs('#fld_total_income').value || 0);
        if (!qs('#fld_total_income').value) { toast('请填写预估收入', false); return; }
        var items = collectItems(ITEM_CFGS.estimate_items);
        if (!items.length) { toast('至少录入一条概算分项', false); return; }
        POST('/api/plm/opportunities/' + id + '/estimate',
          { total_income: inc, items: items, operator: OPERATOR }).then(function (r) {
            var d = unwrap(r);
            if (d === null) return;
            closeModal();
            toast('概算已保存：成本 ' + money(d.total_cost) + '，毛利率 ' + pct(d.gross_rate));
            refreshCaches().then(function () { crud('opportunity'); });
          });
      };
    });
  }
  function followOpp(id) {
    GET('/api/plm/opportunities/' + id).then(function (res) {
      var o = unwrap(res);
      if (!o) return;
      var list = (o.follow_records || []).slice().reverse().map(function (r) {
        return '<div style="border-bottom:1px dashed var(--border2);padding:8px 0">' +
          '<div style="font-size:11px;color:var(--text2)">' + h(r.time) + ' · ' + h(r.owner) + '</div>' +
          '<div style="font-size:12px">' + h(r.content) + '</div></div>';
      }).join('') || '<div class="plm-note">暂无跟进记录</div>';
      showModal({
        title: '跟进记录 · ' + o.opp_name,
        sub: '记录客户沟通、投标进展，形成售前过程资产',
        bodyHtml: '<div style="max-height:240px;overflow-y:auto;margin-bottom:14px">' + list + '</div>',
        fields: [{ k: 'content', l: '新增跟进内容', t: 'textarea', req: 1, wide: 1 }],
        okText: '追加记录',
        onSubmit: function (p) {
          return POST('/api/plm/opportunities/' + id + '/follow',
            { content: p.content, operator: OPERATOR }).then(function (r) { return unwrap(r) === null ? false : r; });
        },
        onDone: function () { viewOpportunity(); }
      });
    });
  }
  function docOpp(id) {
    GET('/api/plm/opportunities/' + id).then(function (res) {
      var o = unwrap(res);
      if (!o) return;
      var rows = (o.docs || []).map(function (d) {
        return '<tr><td>' + h(d.doc_name) + '</td><td>' + h(d.doc_type) + '</td>' +
          '<td>' + h(d.file_name || '-') + '</td><td>' + h(d.uploader || '-') + '</td>' +
          '<td>' + h(d.created_at) + '</td><td class="act"><button class="row-act del" onclick="PLM.delDoc(' +
          d.id + ',' + id + ')">删除</button></td></tr>';
      }).join('');
      showModal({
        title: '售前资料归档 · ' + o.opp_name,
        sub: '投标方案、报价单、售前沟通等资料的归档索引',
        bodyHtml: '<div class="plm-wrap" style="margin-bottom:14px"><table><thead><tr><th>资料名称</th>' +
          '<th>类型</th><th>附件</th><th>归档人</th><th>时间</th></tr></thead><tbody>' +
          (rows || '<tr><td colspan="5" style="color:var(--text2);text-align:center;padding:18px">暂无归档资料</td></tr>') +
          '</tbody></table></div>',
        fields: [
          { k: 'doc_name', l: '资料名称', req: 1 },
          { k: 'doc_type', l: '资料类型', t: 'select', opts: dictOf('presale_doc_type') },
          { k: 'file_name', l: '附件名/链接', hint: '可填写网盘链接或文件名' },
          { k: 'remark', l: '说明' }
        ],
        okText: '归档',
        onSubmit: function (p) {
          return POST('/api/plm/opportunities/' + id + '/docs', p).then(function (r) {
            return unwrap(r) === null ? false : r;
          });
        },
        onDone: function () { docOpp(id); }
      });
    });
  }
  function delDoc(docId, oppId) {
    DEL('/api/plm/presale-docs/' + docId).then(function (r) {
      if (r.success === false) return toast(r.error, false);
      toast('已删除'); docOpp(oppId);
    });
  }
  function convertOpp(id) {
    GET('/api/plm/opportunities/' + id).then(function (res) {
      var o = unwrap(res);
      if (!o) return;
      if (o.status !== '中标') {
        toast('仅「中标」商机可联动立项，请先在编辑里把状态改为中标', false);
        return;
      }
      if (!o.estimate) { toast('该商机尚未录入投标概算，无法形成顶层基线', false); return; }
      ITEM_CFGS.rough_milestones = roughMsCfg();
      showModal({
        title: '联动立项 · ' + o.opp_no,
        sub: '一次生成合同与项目，并把投标概算（成本 ' + money(o.estimate.total_cost) +
          '）带入为项目概算基线，形成商机—合同—项目三级溯源（FR-2）',
        width: 820,
        fields: [
          { k: 'contract_no', l: '合同编号', hint: '留空自动生成' },
          { k: 'contract_name', l: '合同名称', def: o.opp_name },
          { k: 'customer', l: '客户', def: o.customer },
          { k: 'sign_amount', l: '签约金额', t: 'num', unit: '元', def: o.expect_income },
          { k: 'sign_date', l: '签约日期', t: 'date' },
          { k: 'project_cycle', l: '项目周期' },
          { k: 'project_name', l: '项目名称', req: 1, def: o.opp_name + ' 交付项目' },
          { k: 'manager', l: '项目经理', req: 1, def: o.owner },
          { k: 'dept', l: '归属部门', def: o.dept },
          { k: 'start_date', l: '执行开始', t: 'date' }, { k: 'end_date', l: '执行结束', t: 'date' }
        ],
        itemsCfg: ITEM_CFGS.rough_milestones,
        okText: '生成合同与项目',
        onSubmit: function (p) {
          return POST('/api/plm/opportunities/convert', {
            opportunity_id: id, operator: OPERATOR,
            contract: {
              contract_no: p.contract_no, contract_name: p.contract_name, customer: p.customer,
              sign_amount: p.sign_amount, sign_date: p.sign_date, project_cycle: p.project_cycle,
              industry: o.industry, region: o.region, dept: o.dept, owner: p.manager
            },
            project: {
              project_name: p.project_name, customer: p.customer, manager: p.manager,
              dept: p.dept, region: o.region, start_date: p.start_date, end_date: p.end_date,
              milestones: p.rough_milestones
            }
          }).then(function (r) {
            if (r.success === false) { toast(r.error, false); return false; }
            return r;
          });
        },
        doneText: '联动立项完成',
        onDone: function (r) {
          toast('项目 ' + r.project_no + ' 已生成，请到「四算基线」确认并锁定概算');
          refreshCaches().then(function () { crud('opportunity'); });
          ['baseline', 'pmo', 'finance', 'panorama', 'overview'].forEach(function (v) { S.loaded[v] = false; });
        }
      });
    });
  }
  function roughMsCfg() {
    return {
      key: 'rough_milestones', dom: 'ie_ms', title: '顶层粗里程碑（可留空后补）',
      sumKey: '', nameKey: 'name', cats: [],
      cols: [{ k: 'name', l: '里程碑名称' }, { k: 'owner', l: '负责人' },
             { k: 'plan_start', l: '计划开始' }, { k: 'plan_end', l: '计划结束' },
             { k: 'deliverable', l: '交付物' }]
    };
  }

  // ---------- 3 合同与立项 ----------
  MODULES.project.rowActs = [{ l: '全景', fn: 'openProjPanorama' }, { l: '基线', fn: 'gotoBaseline' }];
  function viewProject() {
    var el = qs('#v-project');
    el.innerHTML = pageHead('📑 合同与项目立项',
      '模块二 · 锁定概算顶层基线，建立商机—合同—项目溯源') +
      '<div class="plm-sub" id="sub-project-projects">' + crudHost('project', MODULES.project) + '</div>' +
      '<div class="plm-sub" id="sub-project-contracts">' + crudHost('contract', MODULES.contract) + '</div>';
    S.loaded.project = true;
    return Promise.all([crud('project'), crud('contract')]);
  }
  function gotoBaseline(pid) { S.ctx.baseline = pid; go('baseline'); }
  function openProjPanorama(pid) { S.ctx.panorama = pid; go('panorama'); }

  // ---------- 4 四算基线 ----------
  function baselineItemsCfg(key, dom, title, cats) {
    return { key: key, dom: dom, title: title, sumKey: 'plan_amount', nameKey: 'item_name',
      cats: cats, cols: [{ k: 'category', l: '成本科目', t: 'select' }, { k: 'item_name', l: '分项名称' },
        { k: 'plan_amount', l: '金额(元)', t: 'num' }, { k: 'actual_amount', l: '实际(元)', t: 'num' },
        { k: 'remark', l: '说明' }] };
  }
  function viewBaseline() {
    var el = qs('#v-baseline');
    ensureCtx('baseline');
    el.innerHTML = '<div class="plm-page-hd"><h2>🧱 四算基线管控</h2>' +
      '<span class="pp-sub">四算为纲 · 概算/预算本期落地，核算/决算预留</span></div>' +
      projSelector('baseline') + '<div id="baselineBody"><div class="plm-loading">加载中…</div></div>';
    S.loaded.baseline = true;
    return renderBaseline();
  }
  function renderBaseline() {
    var pid = S.ctx.baseline;
    var body = qs('#baselineBody');
    if (!body) return Promise.resolve();
    if (!pid) { body.innerHTML = noCtx('baseline'); return Promise.resolve(); }
    return Promise.all([
      GET('/api/plm/projects/' + pid + '/baseline-compare'),
      GET('/api/plm/config')
    ]).then(function (rs) {
      var d = unwrap(rs[0]);
      var cfgs = unwrap(rs[1]) || [];
      var sw = cfgs.filter(function (c) { return c.key === 'baseline_constraint'; })[0];
      var on = sw && String(sw.value).toLowerCase() === 'on';
      if (!d) { body.innerHTML = '<div class="plm-empty">加载失败</div>'; return; }
      function row(label, b, reserved) {
        if (!b) return '<tr><td>' + label + '</td><td class="num">-</td><td class="num">-</td>' +
          '<td class="num">-</td><td class="num">-</td><td><span class="plm-chip gray">未录入</span></td></tr>';
        return '<tr><td>' + h(label) + (reserved ? ' <span class="plm-chip purple">预留</span>' : '') + '</td>' +
          '<td class="num">' + money(b.total_income) + '</td><td class="num">' + money(b.total_cost) + '</td>' +
          '<td class="num">' + money(b.gross) + '</td><td class="num">' +
          (reserved ? '-' : pct(b.gross_rate)) + '</td>' +
          '<td><span class="plm-chip ' + (b.status === '已锁定' ? 'green' : 'orange') + '">' +
          h(b.status || '-') + '</span></td></tr>';
      }
      var itemsTable = function (title, items, note) {
        if (!items || !items.length) return '';
        var sum = items.reduce(function (a, r) { return a + Number(r.plan_amount || 0); }, 0);
        return '<div class="plm-card"><h3>' + h(title) + '<span class="hc-sub">合计 ' + money(sum) +
          ' 元' + (note ? ' · ' + h(note) : '') + '</span></h3>' +
          renderTable([{ k: 'category', l: '成本科目' }, { k: 'item_name', l: '分项名称' },
            { k: 'plan_amount', l: '计划金额', n: 1, t: 'money' },
            { k: 'actual_amount', l: '实际金额', n: 1, render: function (v) {
              return v === null || v === undefined ? '<span style="color:var(--text2)">预留</span>' : money(v);
            } }, { k: 'remark', l: '说明' }], items) + '</div>';
      };
      body.innerHTML =
        '<div class="plm-card"><h3>📐 概算 / 预算 /【预留】核算 /【预留】决算' +
        '<span class="hc-act">' +
        '<button class="btn btn-o btn-s" onclick="PLM.editBaseline(' + pid + ',\'estimate_locked\')">🧱 录入概算</button>' +
        '<button class="btn btn-o btn-s" onclick="PLM.editBaseline(' + pid + ',\'budget\')">📝 录入预算</button>' +
        '<button class="btn btn-o btn-s" onclick="PLM.editBaseline(' + pid + ',\'accounting\')">🈳 核算（预留）</button>' +
        '<button class="btn btn-o btn-s" onclick="PLM.editBaseline(' + pid + ',\'final\')">🈳 决算（预留）</button>' +
        '</span></h3>' +
        '<div class="plm-wrap"><table><thead><tr><th>基线</th><th class="num">收入(元)</th>' +
        '<th class="num">成本(元)</th><th class="num">毛利(元)</th><th class="num">毛利率</th>' +
        '<th>状态</th></tr></thead><tbody>' +
        row('概算（顶层基线）', d.estimate) + row('预算（执行）', d.budget) +
        row('核算', d.accounting, true) + row('决算', d.final, true) + '</tbody></table></div>' +
        '<div style="display:flex;gap:14px;align-items:center;flex-wrap:wrap;margin-top:12px">' +
        '<span class="plm-note">概算 vs 预算差异：</span>' + diffCell(d.estimate_vs_budget) +
        (d.budget_usage_note ? '<span class="plm-chip orange">' + h(d.budget_usage_note) + '</span>' : '') +
        '<span class="plm-note">基线管控开关：<span class="plm-chip ' + (on ? 'red' : 'gray') + '">' +
        (on ? '已开启 · 预算超概算禁止保存' : '关闭 · 仅提示不拦截') + '</span>' +
        '<button class="row-act" onclick="PLM.go(\'config\')">去配置</button></span>' +
        (d.estimate && d.estimate.status !== '已锁定' ?
          '<button class="btn btn-c btn-s" onclick="PLM.lockBase(' + d.estimate.baseline_id + ')">🔒 锁定概算基线</button>' :
          '<span class="plm-chip green">概算基线已锁定</span>') +
        '</div></div>' +
        '<div class="plm-2col">' +
        (itemsTable('概算分项明细', d.estimate && d.estimate.items) ||
          '<div class="plm-card"><div class="plm-empty"><span class="e-ico">🧱</span>尚未录入概算分项</div></div>') +
        itemsTable('预算分项明细', d.budget && d.budget.items, '人力成本 / 其他费用') +
        '</div>';
    });
  }
  function editBaseline(pid, stage) {
    var cn = { estimate_locked: '概算', budget: '预算', accounting: '核算（预留）', final: '决算（预留）' }[stage];
    var cfg = baselineItemsCfg('bl_items', 'ie_bl', cn + '分项明细',
      stage === 'budget' ? dictOf('budget_category') : dictOf('cost_category'));
    ITEM_CFGS.bl_items = cfg;
    Promise.all([GET('/api/plm/projects/' + pid + '/baselines'), loadProjects()]).then(function (rs) {
      var list = (unwrap(rs[0]) || []).filter(function (b) { return b.stage === stage; });
      var b = list[list.length - 1] || {};
      showModal({
        title: '录入' + cn + ' · ' + projectName(pid),
        sub: stage === 'budget' ?
          '预算对标概算：超出概算时默认只提示；开启基线管控开关后被拒绝保存（FR-3）' :
          (stage === 'estimate_locked' ? '概算锁定后作为项目顶层管控基线（FR-2）' :
            '核算 / 决算本期仅占位存储，不参与计算与校验（FR-3）'),
        width: 800,
        fields: [{ k: 'total_income', l: '收入口径', t: 'num', unit: '元', def: b.total_income || 0,
                   hint: '留空则取合同签约金额' }],
        values: { total_income: b.total_income },
        itemsCfg: cfg,
        okText: '保存' + cn,
        onSubmit: function (p) {
          var items = collectItems(cfg);
          var body = { stage: stage, total_income: p.total_income, items: items, operator: OPERATOR };
          if (b.id) body.id = b.id;
          return POST('/api/plm/projects/' + pid + '/baselines', body).then(function (r) {
            if (r.success === false) { toast(r.error, false); return false; }
            return r;
          });
        },
        onDone: function () { renderBaseline(); ['pmo', 'finance', 'panorama'].forEach(function (v) { S.loaded[v] = false; }); }
      });
      if (b.items) setTimeout(function () {
        var tb = qs('#ie_bl_body');
        if (tb) tb.innerHTML = b.items.map(function (it) { return itemRowHtml(cfg, it); }).join('');
      }, 0);
    });
  }
  function lockBase(bid) {
    POST('/api/plm/baselines/' + bid + '/lock', { operator: OPERATOR }).then(function (r) {
      if (r.success === false) return toast(r.error, false);
      toast('概算基线已锁定'); renderBaseline();
    });
  }

  // ---------- 5 PMO 进度 ----------
  function viewPmo() {
    var el = qs('#v-pmo');
    ensureCtx('pmo');
    el.innerHTML = pageHead('🚩 PMO 项目执行管控',
      'PMO 为缰 · 按期进度与按预算进度双维度') +
      projSelector('pmo') +
      '<div class="plm-sub" id="sub-pmo-progress"><div id="pmoProgress">' +
      '<div class="plm-loading">加载中…</div></div></div>' +
      '<div class="plm-sub" id="sub-pmo-nodes"><div id="pmoNodes">' +
      '<div class="plm-loading">加载中…</div></div></div>';
    S.loaded.pmo = true;
    return renderPmo();
  }
  function renderPmo() {
    var prog = qs('#pmoProgress'), nodes = qs('#pmoNodes');
    if (!prog || !nodes) return Promise.resolve();
    var pid = S.ctx.pmo;
    if (!pid) {
      prog.innerHTML = noCtx('pmo'); nodes.innerHTML = noCtx('pmo');
      return Promise.resolve();
    }
    prog.innerHTML = '<div class="plm-loading">加载中…</div>';
    nodes.innerHTML = '<div class="plm-loading">加载中…</div>';
    return Promise.all([
      GET('/api/plm/projects/' + pid + '/progress'),
      GET('/api/plm/projects/' + pid + '/milestones'),
      GET('/api/plm/projects/' + pid + '/tasks')
    ]).then(function (rs) {
      var pr = unwrap(rs[0]), ms = unwrap(rs[1]) || [], tk = unwrap(rs[2]) || [];
      if (!pr) { prog.innerHTML = '<div class="plm-empty">加载失败</div>'; return; }
      S.milestones[pid] = ms;
      var sc = pr.schedule, bg = pr.budget;
      var late = sc.milestone_overdue + sc.task_overdue;
      var kpi = [
        ['里程碑完成', sc.milestone_done + '/' + sc.milestone_total, 'c', ''],
        ['按时完成率', pct(sc.on_time_rate), 'g', '按期完成 ÷ 已完成'],
        ['整体进度达成', pct(sc.progress_rate), 'c', '口径：' + sc.progress_caliber],
        ['延期节点', late, late ? 'r' : 'g', '最长超期 ' + sc.max_overdue_days + ' 天'],
        ['预算消耗占比', pct(bg.budget_usage_rate), bg.budget_usage_rate > 1 ? 'r' : 'o',
          money(bg.remaining) + ' 剩余'],
        ['进度-成本剪刀差', bg.time_vs_cost_gap === null ? '-' :
          ((bg.time_vs_cost_gap > 0 ? '+' : '') + pct(bg.time_vs_cost_gap)),
          bg.time_vs_cost_gap > 0 ? 'r' : 'g', '正=花钱快于干活']
      ].map(function (c) {
        return '<div class="k"><div class="kl">' + h(c[0]) + '</div><div class="kv ' + c[2] + '">' +
          h(c[1]) + '</div>' + (c[3] ? '<div class="kn">' + h(c[3]) + '</div>' : '') + '</div>';
      }).join('');
      prog.innerHTML = '<div class="plm-kpi">' + kpi + '</div>' +
        (bg.note ? '<div class="plm-card"><div class="plm-note warn">⚠️ ' + h(bg.note) +
          '，按预算进度暂不可计算；请到「四算基线」录入预算</div></div>' : '') +
        '<div class="plm-card"><h3>📈 完成进度 vs 预算消耗<span class="hc-sub">' +
          h(sc.progress_caliber) + '</span></h3><div id="pmoChart" style="height:250px"></div></div>' +
        (sc.overdue_nodes.length ?
          '<div class="plm-card"><h3>⏰ 延期节点清单<span class="hc-sub">共 ' +
          sc.overdue_nodes.length + ' 个</span></h3>' +
          renderTable([{ k: 'type', l: '类型', render: function (v) {
            return '<span class="plm-chip ' + (v === 'milestone' ? 'purple' : 'gray') + '">' +
              (v === 'milestone' ? '里程碑' : '任务') + '</span>';
          } }, { k: 'name', l: '节点' }, { k: 'owner', l: '负责人' },
          { k: 'plan_end', l: '计划完成', t: 'date' },
          { k: 'overdue_days', l: '超期天数', n: 1, render: function (v) {
            return '<span style="color:var(--red);font-family:var(--mono);font-weight:bold">' +
              v + ' 天</span>';
          } },
          { k: 'is_key', l: '关键', render: function (v) {
            return v ? '<span class="plm-chip orange">是</span>' : '-';
          } }], sc.overdue_nodes) + '</div>'
          : '<div class="plm-card"><div class="plm-note">✅ 当前无延期节点，按期与按预算进度均在阈值内。</div></div>');
      drawPmoChart(sc, bg);
      var flat = [];
      ms.filter(function (m) { return !m.parent_id; }).forEach(function (m) {
        flat.push({ row: m, isKid: false });
        (m.children || []).forEach(function (k) { flat.push({ row: k, isKid: true }); });
      });
      ms.filter(function (m) { return m.parent_id && flat.every(function (f) { return f.row.id !== m.id; }); })
        .forEach(function (m) { flat.push({ row: m, isKid: true }); });
      var msCols = [
        { l: '里程碑', render: function (x, f) {
          return (f.isKid ? '<span style="color:var(--text2)">└ </span>' : '<b>') + h(f.row.name) +
            (f.row.is_key ? ' <span class="plm-chip orange">关键</span>' : '') + '</b>';
        } },
        { l: '层级', render: function (x, f) {
          return '<span class="plm-chip ' + (f.row.level === '粗' ? 'purple' : 'gray') + '">' +
            h(f.row.level) + '</span>';
        } },
        { l: '负责人', render: function (x, f) { return h(f.row.owner || '-'); } },
        { l: '计划起止', render: function (x, f) {
          return h((f.row.plan_start || '-') + ' ~ ' + (f.row.plan_end || '-'));
        } },
        { l: '实际完成', render: function (x, f) {
          return h(f.row.actual_end || '-') + (f.row.is_overdue ?
            ' <span class="plm-chip red">超期' + f.row.overdue_days + '天</span>' : '');
        } },
        { l: '完成度', render: function (x, f) { return barHtml(f.row.progress); } },
        { l: '状态', render: function (x, f) {
          var m = { 未开始: 'gray', 进行中: 'orange', 已完成: 'green', 延期: 'red' };
          return '<span class="plm-chip ' + (m[f.row.status] || 'gray') + '">' + h(f.row.status) + '</span>';
        } },
        { l: '任务', render: function (x, f) { return num(f.row.task_count); } }
      ];
      var msTable = ms.length ? '<div class="plm-wrap"><table><thead><tr>' +
        msCols.map(function (c) { return '<th>' + h(c.l) + '</th>'; }).join('') +
        '<th class="act" style="text-align:right">操作</th></tr></thead><tbody>' +
        flat.map(function (f) {
          var r = f.row;
          return '<tr' + (f.isKid ? ' class="kid"' : ' class="grp"') + '>' + msCols.map(function (c) {
            return '<td>' + c.render(null, f) + '</td>';
          }).join('') + '<td class="act">' +
            (r.level === '粗' ? '<button class="row-act" onclick="PLM.newMs(' + pid + ',' + r.id + ')">拆细</button>' : '') +
            '<button class="row-act" onclick="PLM.editMs(' + pid + ',' + r.id + ')">编辑</button>' +
            '<button class="row-act del" onclick="PLM.delMs(' + r.id + ')">删除</button></td></tr>';
        }).join('') + '</tbody></table></div>'
        : '<div class="plm-empty"><span class="e-ico">🚩</span>尚未拆解里程碑<br>' +
          '<span style="font-size:11px">点击「新建粗里程碑」开始规划项目节奏</span></div>';
      nodes.innerHTML =
        '<div class="plm-card"><h3>🚩 里程碑（粗 → 细）<span class="hc-sub">' + ms.length +
        ' 个节点</span><span class="hc-act">' +
        '<button class="btn btn-o btn-s" onclick="PLM.newMs(' + pid + ',\'\')">＋ 新建粗里程碑</button></span></h3>' +
        msTable + '</div>' +
        '<div class="plm-card"><h3>🧩 执行任务<span class="hc-sub">' + tk.length + ' 项 · 已完成 ' +
        sc.task_done + '</span><span class="hc-act">' +
        '<button class="btn btn-c btn-s" onclick="PLM.newTask(' + pid + ')">＋ 新建任务</button></span></h3>' +
        renderTable([
          { k: 'name', l: '任务' }, { k: 'milestone_name', l: '所属里程碑' },
          { k: 'owner', l: '负责人' }, { k: 'plan_hours', l: '计划工时', n: 1, t: 'num' },
          { k: 'actual_hours', l: '实际工时', n: 1, t: 'num' },
          { k: 'progress', l: '完成度', render: function (v) { return barHtml(v); } },
          { k: 'plan_end', l: '计划完成', t: 'date', render: function (v, r) {
            return h(v || '-') + (r.is_overdue ? ' <span class="plm-chip red">超期' +
              r.overdue_days + '天</span>' : '');
          } },
          { k: 'status', l: '状态', t: 'badge', map: { 未开始: 'gray', 进行中: 'orange', 已完成: 'green', 延期: 'red', 已取消: 'gray' } },
          { k: 'deliverable', l: '交付要求' }
        ], tk, { icon: '🧩', empty: '尚未拆解任务', emptyHint: '在细里程碑下拆解可执行任务并绑定负责人',
          acts: function (r) {
            return '<button class="row-act" onclick="PLM.editTask(' + r.id + ',' + pid + ')">编辑</button>' +
              '<button class="row-act del" onclick="PLM.delTask(' + r.id + ')">删除</button>';
          } }) + '</div>';
    });
  }
  function drawPmoChart(sc, bg) {
    var el = document.getElementById('pmoChart');
    if (!el || typeof global.echarts === 'undefined') return;
    var chart = global.echarts.init(el);
    chart.setOption({
      grid: { left: 46, right: 24, top: 34, bottom: 26 },
      legend: { data: ['完成进度', '预算消耗'], top: 0, textStyle: { color: '#7d8db0', fontSize: 11 },
        itemWidth: 12, itemHeight: 8 },
      tooltip: { trigger: 'axis', valueFormatter: function (v) { return v + '%'; } },
      xAxis: { type: 'category', data: ['当前'], axisLine: { lineStyle: { color: '#24324d' } },
        axisLabel: { color: '#7d8db0' } },
      yAxis: { type: 'value', max: function (v) { return Math.max(120, v.max + 20); },
        axisLabel: { color: '#7d8db0', formatter: '{value}%' },
        splitLine: { lineStyle: { color: 'rgba(255,255,255,.06)' } } },
      series: [
        { name: '完成进度', type: 'bar', barMaxWidth: 60,
          data: [Number(((sc.progress_rate || 0) * 100).toFixed(1))],
          itemStyle: { color: '#4f8cff', borderRadius: [4, 4, 0, 0] },
          label: { show: true, position: 'top', color: '#dbe4f5', formatter: '{c}%' } },
        { name: '预算消耗', type: 'bar', barMaxWidth: 60,
          data: [Number(((bg.budget_usage_rate || 0) * 100).toFixed(1))],
          itemStyle: { color: '#fbbf24', borderRadius: [4, 4, 0, 0] },
          label: { show: true, position: 'top', color: '#dbe4f5', formatter: '{c}%' } }
      ]
    });
    global.addEventListener('resize', function () { chart.resize(); });
  }
  function msFields(pid, parentId) {
    var kids = (S.milestones[pid] || []);
    return [
      { k: 'name', l: '里程碑名称', req: 1 },
      { k: 'owner', l: '负责人' },
      parentId ? { k: 'parent_id', l: '上级里程碑', t: 'select', readonly: true, def: parentId } : null,
      { k: 'level', l: '层级', t: 'select', opts: dictOf('milestone_type') },
      { k: 'plan_start', l: '计划开始', t: 'date' }, { k: 'plan_end', l: '计划结束', t: 'date' },
      { k: 'actual_start', l: '实际开始', t: 'date' }, { k: 'actual_end', l: '实际完成', t: 'date' },
      { k: 'progress', l: '完成百分比', t: 'num', unit: '%', min: 0 },
      { k: 'status', l: '状态', t: 'select', opts: dictOf('milestone_status') },
      { k: 'plan_output', l: '计划产值', t: 'num', unit: '元', hint: '有产值时可改用产值加权口径' },
      { k: 'is_key', l: '关键节点', t: 'checkbox', cbText: '标记为关键里程碑' },
      { k: 'deliverable', l: '交付物' }, { k: 'remark', l: '备注', t: 'textarea', wide: 1 }
    ].filter(Boolean);
  }
  function newMs(pid, parentId) {
    var parent = parentId === '' ? null : parentId;
    showModal({
      title: '新建' + (parent ? '细' : '粗') + '里程碑',
      sub: projectName(pid) + (parent ? ' · 挂在粗里程碑下' : ''),
      fields: msFields(pid).filter(function (f) { return f.k !== 'parent_id'; }),
      values: { level: parent ? '细' : '粗', plan_start: today() },
      onSubmit: function (p) {
        p.project_id = pid;
        if (parent) { p.parent_id = parent; p.level = '细'; }
        p.is_key = p.is_key ? 1 : 0;
        p.operator = OPERATOR;
        return POST('/api/plm/projects/' + pid + '/milestones', p).then(function (r) {
          if (r.success === false) { toast(r.error, false); return false; }
          return r;
        });
      },
      onDone: function () { renderPmo(); }
    });
  }
  function editMs(pid, mid) {
    GET('/api/plm/projects/' + pid + '/milestones').then(function (res) {
      var ms = unwrap(res) || [];
      S.milestones[pid] = ms;
      var r = ms.filter(function (x) { return x.id === mid; })[0];
      if (!r) return;
      showModal({
        title: '编辑里程碑 · ' + r.name,
        sub: '维护计划/实际起止、完成百分比与状态（FR-4）',
        fields: msFields(pid).filter(function (f) { return f.k !== 'parent_id'; }),
        values: { name: r.name, owner: r.owner, level: r.level, plan_start: r.plan_start,
          plan_end: r.plan_end, actual_start: r.actual_start, actual_end: r.actual_end,
          progress: r.progress, status: r.status, plan_output: r.plan_output,
          is_key: !!r.is_key, deliverable: r.deliverable, remark: r.remark },
        onSubmit: function (p) {
          p.is_key = p.is_key ? 1 : 0;
          p.operator = OPERATOR;
          return PUT('/api/plm/milestones/' + mid, p).then(function (x) {
            if (x.success === false) { toast(x.error, false); return false; }
            return x;
          });
        },
        onDone: function () { renderPmo(); }
      });
    });
  }
  function delMs(mid) {
    if (!global.confirm('删除该里程碑？')) return;
    DEL('/api/plm/milestones/' + mid).then(function (r) {
      if (r.success === false) return toast(r.error + (r.refs ? ' ' + JSON.stringify(r.refs) : ''), false);
      toast('已删除'); renderPmo();
    });
  }
  function taskFields(pid) {
    var ms = [];
    (S.milestones[pid] || []).forEach(function (m) {
      if (!m.parent_id) { ms.push({ v: '', l: '【粗】' + m.name + '（请先挂到细里程碑）' }); return; }
    });
    (S.milestones[pid] || []).filter(function (m) { return m.level === '细'; })
      .forEach(function (m) { ms.push({ v: m.id, l: m.name }); });
    return [
      { k: 'name', l: '任务名称', req: 1 },
      { k: 'milestone_id', l: '所属细里程碑', t: 'select', opts: [{ v: '', l: '（暂不归属）' }].concat(ms) },
      { k: 'owner', l: '负责人', req: 1 },
      { k: 'plan_hours', l: '计划工时', t: 'num', unit: '小时', min: 0 },
      { k: 'actual_hours', l: '实际工时', t: 'num', unit: '小时', min: 0 },
      { k: 'plan_start', l: '计划开始', t: 'date' }, { k: 'plan_end', l: '计划完成', t: 'date' },
      { k: 'actual_end', l: '实际完成', t: 'date' },
      { k: 'progress', l: '完成百分比', t: 'num', unit: '%', min: 0 },
      { k: 'status', l: '状态', t: 'select', opts: dictOf('task_status') },
      { k: 'deliverable', l: '交付要求', t: 'textarea', wide: 1 },
      { k: 'remark', l: '备注', t: 'textarea', wide: 1 }
    ];
  }
  function newTask(pid) {
    GET('/api/plm/projects/' + pid + '/milestones').then(function (res) {
      S.milestones[pid] = unwrap(res) || [];
      showModal({
        title: '新建任务', sub: projectName(pid),
        fields: taskFields(pid), values: { status: '未开始' },
        onSubmit: function (p) {
          p.project_id = pid; p.operator = OPERATOR;
          return POST('/api/plm/tasks', p).then(function (r) {
            if (r.success === false) { toast(r.error, false); return false; }
            return r;
          });
        },
        onDone: function () { renderPmo(); }
      });
    });
  }
  function editTask(tid, pid) {
    Promise.all([GET('/api/plm/projects/' + pid + '/milestones'), GET('/api/plm/tasks/' + tid)])
      .then(function (rs) {
        S.milestones[pid] = unwrap(rs[0]) || [];
        var t = unwrap(rs[1]);
        if (!t) return;
        showModal({
          title: '编辑任务 · ' + t.name, sub: projectName(pid),
          fields: taskFields(pid), values: t,
          onSubmit: function (p) {
            p.operator = OPERATOR;
            return PUT('/api/plm/tasks/' + tid, p).then(function (r) {
              if (r.success === false) { toast(r.error, false); return false; }
              return r;
            });
          },
          onDone: function () { renderPmo(); }
        });
      });
  }
  function delTask(tid) {
    if (!global.confirm('删除该任务？')) return;
    DEL('/api/plm/tasks/' + tid).then(function (r) {
      if (r.success === false) return toast(r.error, false);
      toast('已删除'); renderPmo();
    });
  }

  // ---------- 6 人力与工时 ----------
  function viewLabor() {
    var el = qs('#v-labor');
    el.innerHTML = pageHead('👥 人力资源池与工时',
      '人力为本 · 人员池 → 精准分配 → 工时填报 → 自动归集实际人力成本') +
      '<div id="laborKpi"><div class="plm-loading">加载中…</div></div>' +
      '<div class="plm-sub" id="sub-labor-staff">' + crudHost('staff', MODULES.staff) + '</div>' +
      '<div class="plm-sub" id="sub-labor-asg">' + crudHost('assignment', MODULES.assignment) + '</div>' +
      '<div class="plm-sub" id="sub-labor-ts">' + crudHost('timesheet', MODULES.timesheet) + '</div>';
    S.loaded.labor = true;
    return Promise.all([crud('staff'), crud('assignment'), crud('timesheet')]).then(function (rs) {
      var load = rs[0] || [], asg = rs[1] || [], ts = rs[2] || [];
      var over = load.filter(function (x) { return x.load_state === '过载'; });
      var idle = load.filter(function (x) { return x.load_state === '闲置'; });
      var hours = ts.reduce(function (a, r) { return a + Number(r.hours || 0); }, 0);
      var laborCost = ts.length ? load.reduce(function (a, x) {
        return a + (Number(x.actual_hours) || 0) / 8 * (Number(x.cost_rate) || 0);
      }, 0) : 0;
      qs('#laborKpi').innerHTML = '<div class="plm-kpi">' +
        [['在册人员', load.length, 'c', '不含离职'],
         ['过载人数', over.length, over.length ? 'r' : 'g',
          over.map(function (x) { return x.name; }).join('、') || '无'],
         ['闲置人数', idle.length, idle.length ? 'o' : 'g', '未分配任何项目'],
         ['累计填报工时', num(hours) + ' h', 'c', '按人天单价折算成本'],
         ['归集人力成本', money(laborCost), 'p', '工时自动归集，不覆盖手工台账'],
         ['分配记录', asg.length, 'p', '可绑定到里程碑 / 任务']
        ].map(function (c) {
          return '<div class="k"><div class="kl">' + h(c[0]) + '</div><div class="kv ' + c[2] + '">' +
            h(c[1]) + '</div>' + (c[3] ? '<div class="kn">' + h(c[3]) + '</div>' : '') + '</div>';
        }).join('') + '</div>';
    });
  }
  // ---------- 7 成本与毛利 ----------
  function viewFinance() {
    var el = qs('#v-finance');
    ensureCtx('finance');
    el.innerHTML = pageHead('💹 成本与财务管控',
      '财经为尺 · 收入 / 成本 / 毛利量化与概算-预算-实际差异') +
      projSelector('finance', '<button class="btn btn-o btn-s" onclick="PLM.exportReport(\'cost\')">📥 成本毛利表</button>') +
      '<div class="plm-sub" id="sub-finance-summary"><div id="finBody">' +
      '<div class="plm-loading">加载中…</div></div></div>' +
      '<div class="plm-sub" id="sub-finance-ledger">' + crudHost('ledger', MODULES.ledger) + '</div>';
    S.loaded.finance = true;
    return Promise.all([renderFinance(), crud('ledger')]);
  }
  function renderFinance() {
    var pid = S.ctx.finance, body = qs('#finBody');
    if (!body) return Promise.resolve();
    if (!pid) { body.innerHTML = noCtx('finance'); return Promise.resolve(); }
    return GET('/api/plm/projects/' + pid + '/finance').then(function (res) {
      var d = unwrap(res);
      if (!d) { body.innerHTML = '<div class="plm-empty">加载失败</div>'; return; }
      var g = d.gross, v = d.variance;
      body.innerHTML = '<div class="plm-kpi">' +
        [['合同签约额', money(d.income.contract_sign_amount), 'c', ''],
         ['收入合计', money(d.income.total), 'c', '签单 ' + money(d.income.signed) + ' / 变更 ' + money(d.income.change)],
         ['概算成本', money(d.baseline.estimate_cost), 'p', '顶层基线'],
         ['预算总额', money(d.baseline.budget_total), 'p', '执行基线'],
         ['累计实际成本', money(d.cost.actual_cum), 'o', '含工时归集 ' + money(d.cost.labor_auto)],
         ['签单毛利', money(g.signed), (g.signed >= 0 ? 'g' : 'r'), '毛利率 ' + pct(g.signed_rate)],
         ['实际毛利', money(g.actual), (g.actual >= 0 ? 'g' : 'r'), '毛利率 ' + pct(g.actual_rate)],
         ['预算消耗占比', pct(v.budget_usage_rate), (v.budget_usage_rate > 1 ? 'r' : 'o'), v.direction]
        ].map(function (c) {
          return '<div class="k"><div class="kl">' + h(c[0]) + '</div><div class="kv ' + c[2] + '">' +
            h(c[1]) + '</div>' + (c[3] ? '<div class="kn">' + h(c[3]) + '</div>' : '') + '</div>';
        }).join('') + '</div>' +
        '<div class="plm-2col"><div class="chart-box plm-card" style="margin:0">' +
        '<h3>📊 概算 / 预算 / 实际 三线对比<span class="hc-sub">' + h(v.direction) + '</span></h3>' +
        '<div id="finChart" style="height:240px"></div></div>' +
        '<div class="plm-card" style="margin:0"><h3>🧾 差异分析</h3>' +
        '<div class="plm-kv">' +
        [['概算 vs 预算', diffCell(v.estimate_vs_budget)],
         ['预算 vs 实际', diffCell(v.budget_vs_actual)],
         ['概算 vs 实际', diffCell(v.estimate_vs_actual)],
         ['预算消耗占比', '<span class="plm-gauge"><span class="gv" style="color:var(--orange)">' +
          pct(v.budget_usage_rate) + '</span></span>'],
         ['概算消耗占比', pct(v.estimate_usage_rate)],
         ['累计工时', num(d.cost.hours_total) + ' 小时'],
         ['核算 / 决算', '<span class="plm-chip purple">预留</span> ' + h(d.reserved.note)]
        ].map(function (r) {
          return '<div class="r"><span class="l">' + h(r[0]) + '</span><span class="v">' + r[1] + '</span></div>';
        }).join('') + '</div></div></div>';
      drawFinChart(d);
    });
  }
  function drawFinChart(d) {
    var el = document.getElementById('finChart');
    if (!el || typeof global.echarts === 'undefined') {
      if (el) el.innerHTML = '<div class="plm-note" style="padding:20px">图表组件未加载（需联网加载 ECharts CDN）</div>';
      return;
    }
    var cats = ['概算', '预算', '实际成本', '收入合计', '实际毛利'];
    var vals = [d.baseline.estimate_cost, d.baseline.budget_total, d.cost.actual_cum,
                d.income.total, d.gross.actual];
    var colors = ['#4f8cff', '#a78bfa', '#fbbf24', '#22d3ee',
                  (Number(d.gross.actual) >= 0 ? '#34d399' : '#f87171')];
    var chart = global.echarts.init(el, null, { renderer: 'canvas' });
    chart.setOption({
      grid: { left: 70, right: 24, top: 18, bottom: 30 },
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: function (p) { return p[0].name + '：' + money(p[0].value) + ' 元'; } },
      xAxis: { type: 'category', data: cats, axisLabel: { color: '#7d8db0', fontSize: 10 },
        axisLine: { lineStyle: { color: '#24324d' } } },
      yAxis: { type: 'value', axisLabel: { color: '#7d8db0', fontSize: 10,
        formatter: function (v) { return v >= 10000 ? (v / 10000).toFixed(0) + '万' : v; } },
        splitLine: { lineStyle: { color: 'rgba(255,255,255,.06)' } } },
      series: [{ type: 'bar', data: vals.map(function (x, i) {
        return { value: x || 0, itemStyle: { color: colors[i], borderRadius: [4, 4, 0, 0] } };
      }), barMaxWidth: 44, label: { show: true, position: 'top', color: '#dbe4f5', fontSize: 10,
        formatter: function (p) { return money(p.value); } } }]
    });
    global.addEventListener('resize', function () { chart.resize(); });
  }

  // ---------- 8 项目全景（7 固定板块） ----------
  function viewPanorama() {
    var el = qs('#v-panorama');
    ensureCtx('panorama');
    el.innerHTML = '<div class="plm-page-hd"><h2>🔭 项目全景视图</h2>' +
      '<span class="pp-sub">模块六 · 一页看透项目所有核心信息（7 个固定板块）</span></div>' +
      projSelector('panorama', '<button class="btn btn-o btn-s" onclick="PLM.exportReport(\'panorama\',' +
        (S.ctx.panorama || 0) + ')">📥 导出全景报表</button>') +
      '<div id="panoBody"><div class="plm-loading">加载中…</div></div>';
    S.loaded.panorama = true;
    return renderPano();
  }
  function renderPano() {
    var pid = S.ctx.panorama, body = qs('#panoBody');
    if (!body) return Promise.resolve();
    if (!pid) { body.innerHTML = noCtx('panorama'); return Promise.resolve(); }
    return GET('/api/plm/projects/' + pid + '/panorama').then(function (res) {
      var d = unwrap(res);
      if (!d) { body.innerHTML = '<div class="plm-empty">项目不存在</div>'; return; }
      var b = d.base_info, ba = d.baseline_area, pm = d.pmo_area, hr = d.hr_area,
          fa = d.finance_area, al = d.alert_area, ql = d.quick_links;
      function kv(rows) {
        return '<div class="plm-kv">' + rows.filter(Boolean).map(function (r) {
          return '<div class="r"><span class="l">' + h(r[0]) + '</span><span class="v">' + r[1] + '</span></div>';
        }).join('') + '</div>';
      }
      var emptyBlock = function (ico, text) {
        return '<div class="plm-empty" style="padding:20px"><span class="e-ico">' + ico + '</span>' +
          h(text) + '</div>';
      };
      body.innerHTML = '<div class="plm-pano">' +
        // ① 基础信息区
        '<div class="plm-card span2"><h3>① 基础信息区' +
        '<span class="hc-sub">' + h(b.status) + ' · ' + h(b.period) + '</span>' +
        '<span class="hc-act"><button class="btn btn-o btn-s" onclick="PLM.exportReport(\'panorama\',' + pid + ')">📥 导出全景报表</button></span></h3>' +
        kv([['项目编号', '<b style="font-family:var(--mono)">' + h(b.project_no) + '</b>'],
            ['项目名称', h(b.project_name)], ['所属合同', h(b.contract_no || '-')],
            ['客户', h(b.customer || '-')], ['项目经理', h(b.manager || '-')],
            ['归属部门', h(b.dept || '-')], ['区域', h(b.region || '-')],
            ['执行周期', h(b.period)], ['立项日期', h(b.kickoff_date || '-')],
            ['来源商机', b.opportunity_no ? h(b.opportunity_no + ' ' + (b.opportunity_name || '')) : '-']]) +
        '</div>' +
        // ② 四算基线区
        '<div class="plm-card"><h3>② 四算基线区<span class="hc-sub">四算为纲</span></h3>' +
        '<div class="plm-wrap"><table><thead><tr><th>基线</th><th class="num">成本(元)</th>' +
        '<th class="num">毛利</th><th class="num">毛利率</th><th>状态</th></tr></thead><tbody>' +
        [['概算', ba.estimate, 0], ['预算', ba.budget, 0], ['核算', ba.accounting, 1], ['决算', ba.final, 1]]
          .map(function (x) {
            var it = x[1] || {};
            return '<tr><td>' + x[0] + (x[2] ? ' <span class="plm-chip purple">预留</span>' : '') + '</td>' +
              '<td class="num">' + money(it.total_cost) + '</td><td class="num">' + money(it.gross) +
              '</td><td class="num">' + (x[2] ? '-' : pct(it.gross_rate)) + '</td><td>' +
              '<span class="plm-chip ' + (it.status === '已锁定' ? 'green' : 'gray') + '">' +
              h(it.status || '未录入') + '</span></td></tr>';
          }).join('') + '</tbody></table></div>' +
        '<div style="margin-top:10px">' + kv([['概算 vs 预算', diffCell(ba.estimate_vs_budget)],
          ['提示', '<span class="plm-note' + (ba.budget_usage_note ? ' warn' : '') + '">' +
            h(ba.budget_usage_note || '预算在概算范围内') + '</span>']]) + '</div></div>' +
        // ③ PMO 进度区
        '<div class="plm-card"><h3>③ PMO 进度区<span class="hc-sub">PMO 为缰</span></h3>' +
        kv([['按期完成率', pct(pm.schedule.on_time_rate)], ['整体进度', pct(pm.schedule.progress_rate) +
          ' <span style="color:var(--text2)">(' + h(pm.schedule.progress_caliber) + ')</span>'],
          ['里程碑', pm.schedule.milestone_done + ' / ' + pm.schedule.milestone_total],
          ['任务', pm.schedule.task_done + ' / ' + pm.schedule.task_total],
          ['延期节点', pm.schedule.overdue_nodes.length ? '<span class="plm-chip red">' +
            pm.schedule.overdue_nodes.length + ' 个（最长超期 ' + pm.schedule.max_overdue_days + ' 天）</span>' :
            '<span class="plm-chip green">无</span>'],
          ['预算消耗', pct(pm.budget.budget_usage_rate) + (pm.budget.over_budget_nodes.length ?
            ' <span class="plm-chip red">超预算</span>' : '')]]) +
        (pm.milestones.length ? renderTable([{ k: 'name', l: '里程碑' },
          { k: 'plan_end', l: '计划完成', t: 'date' },
          { k: 'progress', l: '完成度', render: function (v) { return barHtml(v); } },
          { k: 'status', l: '状态', t: 'badge', map: { 未开始: 'gray', 进行中: 'orange', 已完成: 'green', 延期: 'red' } }],
          pm.milestones.slice(0, 8)) : emptyBlock('🚩', '尚未拆解里程碑')) + '</div>' +
        // ④ 人力资源区
        '<div class="plm-card"><h3>④ 人力资源区<span class="hc-sub">人力为本</span></h3>' +
        (hr.participants.length ? renderTable([
          { k: 'name', l: '人员' }, { k: 'role', l: '岗位' },
          { k: 'project_hours', l: '本项目工时', n: 1, t: 'num' },
          { k: 'actual_hours', l: '累计工时', n: 1, t: 'num' },
          { k: 'load_rate', l: '负荷率', n: 1, t: 'pct' },
          { k: 'load_state', l: '负荷', t: 'badge', map: { 过载: 'red', 正常: 'green', 闲置: 'gray' } }],
          hr.participants) : emptyBlock('👥', '尚未分配人员')) +
        kv([['累计工时', num(hr.hours_total) + ' 小时'],
            ['归集人力成本', money(hr.labor_cost) + ' 元'],
            ['人效/元效', '<span class="plm-chip purple">预留</span> ' + h(hr.efficiency.note)]]) + '</div>' +
        // ⑤ 财经数据区
        '<div class="plm-card"><h3>⑤ 财经数据区<span class="hc-sub">财经为尺</span></h3>' +
        kv([['合同收入', money(fa.income.contract_sign_amount)],
            ['收入合计', money(fa.income.total)],
            ['预估总成本(概算)', money(fa.baseline.estimate_cost)],
            ['预算总额', money(fa.baseline.budget_total)],
            ['累计实际成本', money(fa.cost.actual_cum)],
            ['签单毛利', money(fa.gross.signed) + ' · ' + pct(fa.gross.signed_rate)],
            ['当期(实际)毛利', '<b style="color:' + (fa.gross.actual >= 0 ? 'var(--green)' : 'var(--red)') +
              ';font-family:var(--mono)">' + money(fa.gross.actual) + '</b> · ' + pct(fa.gross.actual_rate)],
            ['成本偏差', diffCell(fa.variance.budget_vs_actual) + ' <span style="color:var(--text2)">' +
              h(fa.variance.direction) + '</span>']]) + '</div>' +
        // ⑥ 风险预警区
        '<div class="plm-card"><h3>⑥ 风险预警区<span class="hc-sub">未闭环 ' + al.total +
        ' · 待处理 ' + al.pending + '</span></h3>' +
        (al.items.length ? renderTable([
          { k: 'dim', l: '维度', render: function (v) {
            var cn = { cost: '成本', gross: '毛利', schedule: '进度', staff: '人员' }[v] || v;
            return '<span class="plm-chip gray">' + h(cn) + '</span>';
          } },
          { k: 'level', l: '等级', t: 'badge', map: { 严重: 'red', 警告: 'orange', 提醒: 'gray' } },
          { k: 'title', l: '预警内容' },
          { k: 'status', l: '状态', t: 'badge', map: { 待处理: 'red', 处理中: 'orange', 已闭环: 'green' } }],
          al.items, { icon: '✅', empty: '本项目暂无预警',
            acts: function (r) { return '<button class="row-act" onclick="PLM.handleAlert(' + r.id + ')">处置</button>'; } })
          : emptyBlock('✅', '本项目暂无预警')) + '</div>' +
        // ⑦ 快捷操作区
        '<div class="plm-card"><h3>⑦ 快捷操作区</h3><div style="display:flex;gap:10px;flex-wrap:wrap">' +
        ql.map(function (q) {
          var map = { opportunity: ['opportunity', ''], contract: ['project', 'contracts'],
                      pmo: ['pmo', 'nodes'], labor: ['labor', 'ts'], export: ['', ''] };
          var t = map[q.target] || ['', ''];
          var js = q.target === 'export' ? "PLM.exportReport('panorama'," + pid + ")" :
            (t[0] ? "PLM.go('" + t[0] + "','" + t[1] + "')" +
              (q.id && S.ctx[t[0]] !== undefined ? ";PLM.ctxChange('" + t[0] + "'," + q.id + ")" : '')
              : 'void 0');
          return '<button class="btn btn-o" onclick="' + js + '">' + h(q.label) + '</button>';
        }).join('') + '</div></div></div>';
    });
  }

  // ---------- 9 风险预警 ----------
  function viewAlert() {
    var el = qs('#v-alert');
    el.innerHTML = pageHead('⚠️ 风险预警管控',
      '模块七 · 成本超耗 / 毛利偏低 / 进度延期 / 人员过载四类自动预警与闭环处置',
      '<button class="btn btn-c btn-s" onclick="PLM.scanAlerts()">🔄 立即重算预警</button>') +
      '<div class="plm-sub" id="sub-alert-center">' +
      '<div class="plm-bar"><label>项目</label><select id="afProj" onchange="PLM.filterAlerts()">' +
      '<option value="">全部项目</option>' + S.projects.map(function (p) {
        return '<option value="' + p.id + '">' + h(p.project_no + ' ' + p.project_name) + '</option>';
      }).join('') + '</select>' +
      '<label>风险类型</label><select id="afDim" onchange="PLM.filterAlerts()"><option value="">全部</option>' +
      '<option value="cost">成本超耗</option><option value="gross">毛利偏低</option>' +
      '<option value="schedule">进度延期</option><option value="staff">人员过载</option></select>' +
      '<label>状态</label><select id="afStatus" onchange="PLM.filterAlerts()">' +
      '<option value="未闭环">未闭环</option><option value="待处理">待处理</option>' +
      '<option value="处理中">处理中</option><option value="已闭环">已闭环</option>' +
      '<option value="">全部</option></select>' +
      '<label>等级</label><select id="afLevel" onchange="PLM.filterAlerts()"><option value="">全部</option>' +
      '<option>严重</option><option>警告</option><option>提醒</option></select></div>' +
      '<div id="alertTable"><div class="plm-loading">加载中…</div></div></div>' +
      '<div class="plm-sub" id="sub-alert-rules"><div id="ruleTable"></div></div>';
    S.loaded.alert = true;
    return Promise.all([filterAlerts(), renderRules()]);
  }
  function filterAlerts() {
    var p = [];
    if (qs('#afProj') && qs('#afProj').value) p.push('project_id=' + qs('#afProj').value);
    if (qs('#afDim') && qs('#afDim').value) p.push('dim=' + qs('#afDim').value);
    if (qs('#afStatus') && qs('#afStatus').value) p.push('status=' + encodeURIComponent(qs('#afStatus').value));
    if (qs('#afLevel') && qs('#afLevel').value) p.push('level=' + encodeURIComponent(qs('#afLevel').value));
    var host = qs('#alertTable');
    if (!host) return Promise.resolve();
    host.innerHTML = '<div class="plm-loading">加载中…</div>';
    return GET('/api/plm/alerts' + (p.length ? '?' + p.join('&') : '')).then(function (res) {
      var rows = unwrap(res) || [];
      host.innerHTML = renderTable([
        { k: 'project_no', l: '项目', render: function (v, r) {
          return h(v || '-') + (r.project_status ? '<span class="plm-chip gray">' + h(r.project_status) + '</span>' : '');
        } },
        { k: 'dim', l: '维度', render: function (v) {
          var cn = { cost: '成本超耗', gross: '毛利偏低', schedule: '进度延期', staff: '人员过载' }[v] || v;
          return '<span class="plm-chip gray">' + h(cn) + '</span>';
        } },
        { k: 'level', l: '等级', t: 'badge', map: { 严重: 'red', 警告: 'orange', 提醒: 'gray' } },
        { k: 'title', l: '预警内容', render: function (v, r) {
          return '<div>' + h(v) + '</div>' + (r.detail && r.detail !== v ?
            '<div style="font-size:11px;color:var(--text2)">' + h(r.detail) + '</div>' : '');
        } },
        { k: 'status', l: '状态', t: 'badge', map: { 待处理: 'red', 处理中: 'orange', 已闭环: 'green' } },
        { k: 'handler', l: '处置人' }, { k: 'handle_note', l: '处置说明' },
        { k: 'last_scan_at', l: '最近扫描' }
      ], rows, { icon: '✅', empty: '没有符合条件的预警', emptyHint: '点击「立即重算预警」按启用规则扫描',
        acts: function (r) {
          return '<button class="row-act" onclick="PLM.handleAlert(' + r.id + ')">处置</button>' +
            (r.project_id ? '<button class="row-act" onclick="PLM.openProjPanorama(' + r.project_id + ')">看项目</button>' : '');
        } });
      return rows;
    });
  }
  function handleAlert(aid) {
    GET('/api/plm/alerts').then(function (res) {
      var rows = unwrap(res) || [];
      var a = rows.filter(function (x) { return x.id === aid; })[0];
      if (!a) { toast('预警记录未找到', false); return; }
      showModal({
        title: '预警处置 · ' + (a.rule_name || a.title),
        sub: '状态流转：待处理 → 处理中 → 已闭环，处置记录可溯源（FR-9）',
        bodyHtml: '<div class="plm-kv" style="margin-bottom:14px">' +
          '<div class="r"><span class="l">项目</span><span class="v">' + h(a.project_name || '-') + '</span></div>' +
          '<div class="r"><span class="l">当前</span><span class="v">' + h(a.title) + '</span></div>' +
          '<div class="r"><span class="l">明细</span><span class="v">' + h(a.detail) + '</span></div></div>',
        fields: [
          { k: 'status', l: '处置状态', t: 'select', opts: ['待处理', '处理中', '已闭环'], def: a.status },
          { k: 'handler', l: '处置人', def: OPERATOR },
          { k: 'note', l: '处置说明', t: 'textarea', wide: 1, req: 1, ph: '记录采取的风险应对措施' }
        ],
        okText: '提交处置',
        onSubmit: function (p) {
          return PUT('/api/plm/alerts/' + aid + '/handle',
            { status: p.status, note: p.note, operator: p.handler || OPERATOR }).then(function (r) {
            if (r.success === false) { toast(r.error, false); return false; }
            return r;
          });
        },
        onDone: function () {
          filterAlerts();
          ['overview', 'panorama'].forEach(function (v) { S.loaded[v] = false; });
        }
      });
    });
  }
  function renderRules() {
    var host = qs('#ruleTable');
    if (!host) return Promise.resolve();
    return GET('/api/plm/alert-rules').then(function (res) {
      var rows = unwrap(res) || [];
      host.innerHTML = '<div class="plm-card"><h3>⚙️ 预警规则<span class="hc-sub">阈值可后台自定义，保存后需重算预警生效</span></h3>' +
        renderTable([
          { k: 'rule_name', l: '规则' },
          { k: 'dim', l: '维度', render: function (v) {
            var cn = { cost: '成本', gross: '毛利', schedule: '进度', staff: '人员' }[v] || v;
            return '<span class="plm-chip gray">' + h(cn) + '</span>';
          } },
          { k: 'metric', l: '判定指标' },
          { k: 'op', l: '条件', render: function (v, r) {
            return '<span style="font-family:var(--mono)">' + h(v) + ' ' +
              (r.dim === 'schedule' ? r.threshold + ' 天' : pct(r.threshold, 0)) + '</span>';
          } },
          { k: 'level', l: '等级', t: 'badge', map: { 严重: 'red', 警告: 'orange', 提醒: 'gray' } },
          { k: 'enabled', l: '启用', render: function (v) {
            return v ? '<span class="plm-chip green">已启用</span>' : '<span class="plm-chip gray">已停用</span>';
          } },
          { k: 'description', l: '规则说明' }
        ], rows, { icon: '⚙️', empty: '无预警规则',
          acts: function (r) { return '<button class="row-act" onclick="PLM.editRule(\'' + r.rule_key + '\')">调整</button>'; } }) +
        '</div>';
      S.rules = rows;
      return rows;
    });
  }
  function editRule(key) {
    var r = (S.rules || []).filter(function (x) { return x.rule_key === key; })[0];
    if (!r) return;
    showModal({
      title: '调整预警规则 · ' + r.rule_name,
      sub: '指标：' + r.metric + '，判定条件 ' + r.op + ' 阈值' + (r.dim === 'schedule' ? '（单位：天）' : '（0~1 小数）'),
      fields: [
        { k: 'threshold', l: '阈值', t: 'num', req: 1, def: r.threshold,
          hint: r.dim === 'schedule' ? '超期天数' : '比例阈值，如 0.8 表示 80%' },
        { k: 'level', l: '风险等级', t: 'select', opts: ['提醒', '警告', '严重'], def: r.level },
        { k: 'enabled', l: '是否启用', t: 'select', opts: [{ v: 1, l: '启用' }, { v: 0, l: '停用' }], def: r.enabled ? 1 : 0 },
        { k: 'description', l: '规则说明', t: 'textarea', wide: 1, def: r.description }
      ],
      okText: '保存并生效',
      onSubmit: function (p) {
        return PUT('/api/plm/alert-rules/' + key, {
          threshold: Number(p.threshold), level: p.level, enabled: Number(p.enabled),
          description: p.description, operator: OPERATOR
        }).then(function (res) { if (res.success === false) { toast(res.error, false); return false; } return res; });
      },
      onDone: function () {
        renderRules();
        POST('/api/plm/alerts/scan', { operator: OPERATOR }).then(function () {
          filterAlerts();
          ['overview', 'panorama'].forEach(function (v) { S.loaded[v] = false; });
          toast('阈值已更新并完成预警重算');
        });
      }
    });
  }
  function scanAlerts() {
    toast('正在扫描全部项目…');
    return POST('/api/plm/alerts/scan', { operator: OPERATOR }).then(function (res) {
      var d = unwrap(res);
      if (!d) return;
      toast('扫描完成：新增 ' + d.created + '，更新 ' + d.updated + '，自动闭环 ' + d.auto_closed);
      ['alert', 'overview', 'panorama'].forEach(function (v) { S.loaded[v] = false; });
      refreshBadge();
      if (qs('#alertTable')) filterAlerts();
    });
  }
  function refreshBadge() {
    GET('/api/plm/alerts?status=' + encodeURIComponent('待处理')).then(function (res) {
      S.pendingAlerts = (unwrap(res) || []).length;
      var dot = qs('#navAlertDot');
      if (!dot) return renderNav();
      dot.textContent = S.pendingAlerts;
      dot.style.display = S.pendingAlerts ? '' : 'none';
    });
  }

  // ---------- 10 系统配置 ----------
  MODULES.dict = {
    title: '字典项', api: '/api/plm/dict', icon: '📚', noEdit: true,
    cols: [{ k: 'category', l: '分类' }, { k: 'key', l: '键值' }, { k: 'label', l: '显示名称' },
           { k: 'sort', l: '排序', n: 1, t: 'num' }, { k: 'remark', l: '备注' }],
    fields: function () {
      var cats = Object.keys(S.dicts).concat(['cost_category', 'income_category', 'role']);
      return [
        { k: 'category', l: '分类', req: 1, t: 'select', opts: cats.filter(function (x, i, a) { return a.indexOf(x) === i; }) },
        { k: 'key', l: '键值', req: 1 },
        { k: 'label', l: '显示名称', req: 1 },
        { k: 'sort', l: '排序', t: 'num', def: 99 },
        { k: 'remark', l: '备注', t: 'textarea', wide: 1 }
      ];
    }
  };
  function viewConfig() {
    var el = qs('#v-config');
    el.innerHTML = pageHead('⚙️ 系统配置',
      '模块九 · 参数与字典可配置、操作可溯源（本期不含登录鉴权，角色仅作留痕字段）') +
      '<div class="plm-sub" id="sub-config-params"><div id="paramBody"></div></div>' +
      '<div class="plm-sub" id="sub-config-dict">' + crudHost('dict', MODULES.dict) + '</div>' +
      '<div class="plm-sub" id="sub-config-logs"><div id="logBody"></div></div>';
    S.loaded.config = true;
    return Promise.all([renderParams(), crud('dict'), renderLogs()]);
  }
  function renderParams() {
    return GET('/api/plm/config').then(function (res) {
      var rows = unwrap(res) || [];
      qs('#paramBody').innerHTML = '<div class="plm-card"><h3>🎛 全局参数<span class="hc-sub">含四算基线管控开关</span></h3>' +
        renderTable([
          { k: 'key', l: '参数键' },
          { k: 'value', l: '当前值', render: function (v, r) {
            if (r.key === 'baseline_constraint') {
              return '<span class="plm-chip ' + (String(v).toLowerCase() === 'on' ? 'red' : 'gray') + '">' +
                (String(v).toLowerCase() === 'on' ? '开启（强约束）' : '关闭（仅提示）') + '</span>';
            }
            return '<b style="font-family:var(--mono)">' + h(v) + '</b>';
          } },
          { k: 'description', l: '说明' }, { k: 'updated_at', l: '更新时间' }
        ], rows, { icon: '🎛', empty: '无参数',
          acts: function (r) { return '<button class="row-act" onclick="PLM.editParam(\'' + r.key + '\')">修改</button>'; } }) +
        '</div>';
      S.params = rows;
    });
  }
  function editParam(key) {
    var r = (S.params || []).filter(function (x) { return x.key === key; })[0] || {};
    showModal({
      title: '修改参数 · ' + key, sub: r.description || '',
      fields: key === 'baseline_constraint' ?
        [{ k: 'value', l: '四算逐级约束开关', t: 'select', opts: [{ v: 'off', l: 'off（仅提示不拦截）' },
          { v: 'on', l: 'on（预算超概算拒绝保存）' }], def: r.value }] :
        [{ k: 'value', l: '参数值', t: 'num', def: Number(r.value), req: 1 }],
      okText: '保存',
      onSubmit: function (p) {
        return PUT('/api/plm/config', { key: key, value: p.value, operator: OPERATOR })
          .then(function (res) { if (res.success === false) { toast(res.error, false); return false; } return res; });
      },
      onDone: function () { renderParams(); toast('参数已更新，下次保存预算/工时即生效'); }
    });
  }
  function renderLogs() {
    var host = qs('#logBody');
    if (!host) return Promise.resolve();
    return GET('/api/plm/logs?limit=300').then(function (res) {
      var rows = unwrap(res) || [];
      host.innerHTML = '<div class="plm-card"><h3>🧾 操作日志<span class="hc-sub">新增 / 修改 / 锁定 / 处置全程留痕</span></h3>' +
        renderTable([
          { k: 'created_at', l: '时间' }, { k: 'operator', l: '操作人' },
          { k: 'target_type', l: '对象类型' },
          { k: 'action', l: '动作', render: function (v) { return '<span class="plm-chip">' + h(v) + '</span>'; } },
          { k: 'target_name', l: '对象' },
          { k: 'change', l: '变更内容', render: function (v) {
            var keys = Object.keys(v || {});
            if (!keys.length) return '<span style="color:var(--text2)">-</span>';
            return keys.slice(0, 4).map(function (kk) {
              var c = v[kk];
              if (c && typeof c === 'object' && 'before' in c) {
                return '<div><b>' + h(kk) + '</b>：<span style="color:var(--text2)">' + h(c.before) +
                  '</span> → <span style="color:var(--cyan2)">' + h(c.after) + '</span></div>';
              }
              return '<div><b>' + h(kk) + '</b>：' + h(c) + '</div>';
            }).join('');
          } }
        ], rows, { icon: '🧾', empty: '暂无操作日志' });
    });
  }

  // ---------- 报表导出 ----------
  function exportReport(name, pid) {
    if (name === 'panorama' && !pid) pid = S.ctx.panorama || S.ctx.finance || 0;
    if (name === 'panorama' && !pid) { toast('请先选择要导出的项目', false); return; }
    var url = '/api/plm/export/' + name + (pid ? '?project_id=' + pid : '');
    var a = document.createElement('a');
    a.href = url;
    a.download = '';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    toast('报表已开始下载');
  }

  // ---------------- 左侧菜单树与路由 ----------------
  var NAV = [
    { view: 'overview', icon: '📡', label: '经营驾驶舱' },
    { view: 'opportunity', icon: '🎯', label: '售前商机' },
    { view: 'project', icon: '📑', label: '合同与立项', kids: [
      { sub: 'projects', label: '项目立项' },
      { sub: 'contracts', label: '合同主数据' }
    ] },
    { view: 'baseline', icon: '🧱', label: '四算基线' },
    { view: 'pmo', icon: '🚩', label: 'PMO 进度', kids: [
      { sub: 'progress', label: '双维度进度' },
      { sub: 'nodes', label: '里程碑与任务' }
    ] },
    { view: 'labor', icon: '👥', label: '人力与工时', kids: [
      { sub: 'staff', label: '人员池与负荷' },
      { sub: 'asg', label: '人员分配' },
      { sub: 'ts', label: '工时填报' }
    ] },
    { view: 'finance', icon: '💹', label: '成本与毛利', kids: [
      { sub: 'summary', label: '毛利与差异' },
      { sub: 'ledger', label: '收支台账' }
    ] },
    { view: 'panorama', icon: '🔭', label: '项目全景' },
    { view: 'alert', icon: '⚠️', label: '风险预警', badge: true, kids: [
      { sub: 'center', label: '预警中心' },
      { sub: 'rules', label: '规则配置' }
    ] },
    { view: 'config', icon: '⚙️', label: '系统配置', kids: [
      { sub: 'params', label: '全局参数' },
      { sub: 'dict', label: '字典维护' },
      { sub: 'logs', label: '操作日志' }
    ] }
  ];
  var OPEN = {};
  function navOf(view) {
    for (var i = 0; i < NAV.length; i++) { if (NAV[i].view === view) return NAV[i]; }
    return null;
  }
  function renderNav() {
    var host = qs('#plmNav');
    if (!host) return;
    host.innerHTML = NAV.map(function (n) {
      var act = S.active.view === n.view;
      var open = OPEN[n.view] === undefined ? act : OPEN[n.view];
      var cls = 'plm-nav' + (n.kids ? (open ? ' open' : '') + (act ? ' has-open' : '')
                                    : (act ? ' active' : ''));
      var head = '<button class="' + cls + '" data-view="' + n.view + '" onclick="PLM.navClick(\'' +
        n.view + '\')">' +
        (n.kids ? '<span class="pn-caret">▶</span>' : '<span class="pn-caret" style="width:10px"></span>') +
        '<span class="pn-parent"><span class="pn-txt"><span class="pn-ico">' + n.icon + '</span>' +
        h(n.label) + '</span>' +
        (n.badge ? '<span class="pn-badge" id="navAlertDot"' +
          (S.pendingAlerts ? '' : ' style="display:none"') + '>' + S.pendingAlerts + '</span>' : '') +
        '</span></button>';
      if (!n.kids) return head;
      return head + '<div class="plm-nav-kids' + (open ? ' open' : '') + '">' +
        n.kids.map(function (k) {
          return '<button class="plm-leaf' + (act && S.active.sub === k.sub ? ' active' : '') +
            '" onclick="PLM.go(\'' + n.view + '\',\'' + k.sub + '\')">' + h(k.label) + '</button>';
        }).join('') + '</div>';
    }).join('');
  }
  function showSub() {
    var v = S.active.view, sub = S.active.sub;
    qsa('#v-' + v + ' .plm-sub').forEach(function (s) {
      s.classList.toggle('active', !sub || s.id === 'sub-' + v + '-' + sub);
    });
  }
  // 视图 → 面包屑 与 手风琴联动键
  var CRUMB = {
    overview: ['PMO', '项目管理', '项目概览'],
    milestone: ['PMO', '项目管理', '里程碑'],
    project: ['PMO', '项目管理', '合同与立项'],
    baseline: ['PMO', '进度管理', '四算基线'],
    pmo: ['PMO', '进度管理', 'PMO 进度'],
    labor: ['PMO', '人员管理', '人力与工时']
  };
  var VIEW_LINK_KEY = {
    overview: 'plm-overview', milestone: 'plm-milestone', project: 'plm-project',
    baseline: 'plm-baseline', pmo: 'plm-pmo', labor: 'plm-labor'
  };
  function updateAccordion(view) {
    if (global.NAV_CONFIG && CRUMB[view]) {
      global.NAV_CONFIG.renderBreadcrumb(document.getElementById('breadcrumb'), CRUMB[view]);
    }
    var key = VIEW_LINK_KEY[view];
    var acc = document.querySelector('#plmSidebar .accordion');
    if (!key || !acc) return;
    acc.querySelectorAll('.acc-link.active').forEach(function (x) { x.classList.remove('active'); });
    var links = acc.querySelectorAll('.acc-link');
    for (var i = 0; i < links.length; i++) {
      if ((links[i].getAttribute('onclick') || '').indexOf("go('" + view) >= 0) {
        links[i].classList.add('active');
        break;
      }
    }
  }
  function go(view, sub) {
    var n = navOf(view);
    if (!n) { n = (VIEWS[view] ? { view: view } : NAV[0]); }  // 兼容不在旧 NAV 的 leaf 视图（如 milestone）
    view = n.view;
    if (n.kids) {
      sub = sub || S.lastSub[view] || n.kids[0].sub;
      S.lastSub[view] = sub;
      // 手风琴：展开当前分组，收起其它分组，保持菜单树紧凑
      Object.keys(OPEN).forEach(function (k) { OPEN[k] = false; });
      OPEN[view] = true;
    } else {
      sub = '';
    }
    S.active = { view: view, sub: sub };
    qsa('.plm-view').forEach(function (v) {
      v.classList.toggle('active', v.id === 'v-' + view);
    });
    updateAccordion(view);
    renderNav();
    renderView(view, false, sub);
    refreshBadge();
  }
  function navClick(view) {
    var n = navOf(view);
    if (!n) return go('overview');
    if (!n.kids) return go(view);
    if (OPEN[view] === undefined) OPEN[view] = S.active.view === view;
    if (S.active.view === view && OPEN[view]) { OPEN[view] = false; return renderNav(); }
    OPEN[view] = true;
    go(view, S.lastSub[view]);
  }
  function renderView(view, force, sub) {
    if (!VIEWS[view]) return;
    var run = function () {
      var p;
      try { p = VIEWS[view](); } catch (e) { toast('视图加载失败：' + e.message, false); return; }
      Promise.resolve(p).then(function () { showSub(); })
        .catch(function (e) { toast('视图加载失败：' + e.message, false); });
    };
    if (force || !S.loaded[view]) run(); else showSub();
    if (sub && view !== 'milestone' && navOf(view) && navOf(view).kids) S.lastSub[view] = sub;
  }
  var VIEWS = {
    overview: viewOverview, opportunity: viewOpportunity, project: viewProject,
    baseline: viewBaseline, pmo: viewPmo, labor: viewLabor, finance: viewFinance,
    panorama: viewPanorama, alert: viewAlert, config: viewConfig
  };

  // 明细编辑器配置注册（须在 showModal 之前可用）
  ITEM_CFGS.estimate_items = {
    key: 'estimate_items', dom: 'ie_est', title: '投标概算分项', sumKey: 'plan_amount',
    nameKey: 'item_name', cats: [],
    cols: [{ k: 'category', l: '成本科目', t: 'select' }, { k: 'item_name', l: '分项名称' },
           { k: 'plan_amount', l: '概算金额(元)', t: 'num' }, { k: 'remark', l: '说明' }]
  };
  ITEM_CFGS.bl_items = baselineItemsCfg('bl_items', 'ie_bl', '基线分项明细', []);
  ITEM_CFGS.rough_milestones = roughMsCfg();
  crudHost = function (key, cfg) {
    return '<div class="plm-card"><h3>' + cfg.icon + ' ' + h(cfg.title) +
      '<span class="hc-sub" id="' + key + '_count"></span>' +
      '<span class="hc-act">' +
      (cfg.searchable === false ? '' :
        '<input id="' + key + '_kw" placeholder="搜索…" style="background:var(--bg3);border:1px solid var(--border);color:var(--text);padding:5px 9px;border-radius:7px;font-size:11px" onkeydown="if(event.key===\'Enter\')PLM.crud(\'' + key + '\')">') +
      (cfg.searchable === false ? '' : '<button class="btn btn-o btn-s" onclick="PLM.crud(\'' + key + '\')">🔍</button>') +
      (cfg.noCreate ? '' : '<button class="btn btn-c btn-s" onclick="PLM.crudNew(\'' + key + '\')">＋ 新建</button>') +
      '</span></h3><div id="' + key + '_table"><div class="plm-loading">加载中…</div></div></div>';
  };

  // ---------------- 对外暴露 ----------------
  global.PLM = {
    go: go, navClick: navClick, ctxChange: ctxChange, closeModal: closeModal,
    crud: crud, crudNew: crudNew, crudEdit: crudEdit, crudDel: crudDel,
    addItemRow: addItemRow, recalcItems: recalcItems, toast: toast,
    estOpp: estOpp, followOpp: followOpp, docOpp: docOpp, delDoc: delDoc, convertOpp: convertOpp,
    oppFilter: oppFilter, gotoBaseline: gotoBaseline, openProjPanorama: openProjPanorama,
    editBaseline: editBaseline, lockBase: lockBase,
    newMs: newMs, editMs: editMs, delMs: delMs, newTask: newTask, editTask: editTask, delTask: delTask,
    handleAlert: handleAlert, editRule: editRule, filterAlerts: filterAlerts, scanAlerts: scanAlerts,
    exportReport: exportReport, editParam: editParam, renderLogs: renderLogs
  };

  document.addEventListener('DOMContentLoaded', function () {
    loadDicts().then(refreshCaches).then(function () {
      go('overview');
      refreshBadge();
    }).catch(function (e) { toast('初始化失败：' + e.message, false); });
  });
})(window);
