'use strict';
/* PMO 订单页（2026-09-06 落地）：总览 + 明细 双 Tab，样式对齐成本预警页；支持手工录入。
 * 数据源：/api/plm/orders（薄壳 → plm_models.list_orders）。项目下拉取自 /api/plm/master-contracts
 * （md_contract 当前=合同表，project_no=合同编号；后续切 plm_project 项目表只改取数源）。
 * 录入只负责数据写入（CRUD），预估成本计算与预警判定由本体负责（见 ontos F-workorder-cost-rollup）。
 */
(function (root) {
  var NC = root.NAV_CONFIG;
  var API = '';

  var SECTIONS = [
    { sub: '计划执行', links: [
      { key: 'pmo-plm', label: '计划 / 任务 / 台账 / 预警', icon: 'lifecycle', href: '/plm' },
      { key: 'pmo-order', label: '订单', icon: 'receipt', href: '/pmo-order' },
      { key: 'pmo-workorder', label: '工单', icon: 'pay', href: '/pmo-workorder' }
    ] }
  ];

  function renderShell() {
    NC.renderBreadcrumb(document.getElementById('breadcrumb'), ['PMO', '计划执行', '订单']);
    NC.renderTopMenu(document.getElementById('topMenu'), { activeKey: 'pmo' });
    NC.renderAccordion(document.getElementById('navRail'), {
      rootTitle: '经营业务工作台', domainLabel: 'PMO', activeKey: 'pmo',
      activeLink: 'pmo-order', sections: SECTIONS
    });
  }

  function status(msg) { var el = document.getElementById('orderStatus'); if (el) el.textContent = msg; }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
    });
  }
  function money(v) {
    var n = Number(v); if (isNaN(n)) return '¥0';
    return '¥' + n.toLocaleString();
  }

  var ORDERS = [];
  var orderPage = 1, orderFilter = '';
  var ORDER_PAGE_SIZE = 12;

  function filterRows() {
    var f = (orderFilter || '').trim().toLowerCase();
    if (!f) return ORDERS;
    return ORDERS.filter(function (r) {
      return ((r.order_no || '') + ' ' + (r.name || '') + ' ' + (r.project_no || '') + ' ' + (r.project_name || '')).toLowerCase().indexOf(f) >= 0;
    });
  }

  function renderOverview(hostEl) {
    var projSet = {};
    ORDERS.forEach(function (r) { if (r.project_no) projSet[r.project_no] = 1; });
    var h = '<div class="cards" style="grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:16px;margin-bottom:16px;padding:20px 24px">';
    h += '<div class="card"><div class="lbl">订单数</div><div class="val" style="font-size:22px">' + ORDERS.length + ' 个</div></div>';
    h += '<div class="card"><div class="lbl">涉及项目</div><div class="val c" style="font-size:22px">' + Object.keys(projSet).length + ' 个</div></div>';
    h += '</div>';
    h += '<div class="panel"><h3>📋 订单总览</h3>';
    h += tableHtml(ORDERS.slice(0, 20));
    if (ORDERS.length > 20) h += '<div style="font-size:11px;color:var(--text2);margin-top:8px">仅显示前 20 条，完整列表见「明细」</div>';
    h += '</div>';
    hostEl.innerHTML = h;
  }

  function tableHtml(rows) {
    var h = '<div class="twrap"><table class="ana-table"><thead><tr>'
      + '<th>订单号</th><th>订单名</th><th>项目号</th><th>项目名</th><th>开始时间</th><th>结束时间</th><th>操作</th>'
      + '</tr></thead><tbody>';
    if (!rows.length) {
      h += '<tr><td colspan="7" style="text-align:center;color:var(--text2);padding:20px">暂无订单</td></tr>';
    }
    rows.forEach(function (r) {
      h += '<tr><td>' + esc(r.order_no) + '</td><td class="wrap">' + esc(r.name) + '</td>'
        + '<td>' + esc(r.project_no) + '</td><td class="wrap">' + esc(r.project_name) + '</td>'
        + '<td>' + esc(r.start_date) + '</td><td>' + esc(r.end_date) + '</td>'
        + '<td><a href="javascript:;" onclick="PmoOrder.openEdit(' + r.id + ')" style="color:var(--cyan2)">编辑</a> '
        + '<a href="javascript:;" onclick="PmoOrder.remove(' + r.id + ')" style="color:var(--red2)">删除</a></td></tr>';
    });
    return h + '</tbody></table></div>';
  }

  function renderDetail(hostEl) {
    var rows = filterRows();
    var pagesAll = Math.max(1, Math.ceil(rows.length / ORDER_PAGE_SIZE));
    orderPage = Math.min(Math.max(1, orderPage || 1), pagesAll);
    var start = (orderPage - 1) * ORDER_PAGE_SIZE;
    var pageRows = rows.slice(start, start + ORDER_PAGE_SIZE);
    var h = '<div class="panel"><h3>📋 订单明细</h3>';
    h += '<div style="margin-bottom:8px;display:flex;gap:8px;align-items:center">'
      + '<input id="orderFilterInput" type="text" placeholder="按 订单号/订单名/项目号 筛选…" value="' + esc(orderFilter).replace(/"/g, '&quot;')
      + '" oninput="PmoOrder.setFilter(this.value)" style="width:260px;padding:6px 10px;background:var(--bg3);border:1px solid var(--border);color:var(--text);border-radius:6px;font-size:12px">'
      + '<a href="javascript:;" onclick="PmoOrder.setFilter(\'\')" style="color:var(--cyan2);font-size:12px">清空</a></div>';
    h += tableHtml(pageRows);
    h += pagerHtml(orderPage, rows.length, ORDER_PAGE_SIZE, 'PmoOrder.goPage');
    h += '</div>';
    hostEl.innerHTML = h;
  }

  function pagerHtml(page, total, size, fn) {
    var pages = Math.max(1, Math.ceil(total / size));
    if (pages <= 1) return '';
    var h = '<div style="display:flex;gap:6px;justify-content:center;margin-top:12px">';
    for (var i = 1; i <= pages; i++) {
      h += '<button type="button" class="btn btn-sm' + (i === page ? ' btn-c' : '') + '" onclick="' + fn + '(' + i + ')">' + i + '</button>';
    }
    return h + '</div>';
  }

  async function loadOrders() {
    status('正在读取订单…');
    try {
      var j = await (await fetch(API + '/api/plm/orders')).json();
      ORDERS = (j && j.success && j.data) ? j.data : [];
      renderOverview(document.getElementById('orderOverview'));
      renderDetail(document.getElementById('orderDetailPane'));
      status('PMO 订单 · 共 ' + ORDERS.length + ' 个（project_no 当前=合同编号）');
    } catch (e) { status('读取订单失败: ' + e.message); }
  }

  /* ── 录入弹窗 ── */
  var PROJECTS = [];
  async function ensureProjects() {
    if (PROJECTS.length) return;
    try {
      var j = await (await fetch(API + '/api/plm/master-contracts')).json();
      PROJECTS = (j && j.success && j.data) ? j.data : [];
    } catch (e) { PROJECTS = []; }
  }
  function projectOptions(sel) {
    return '<option value="">— 选择项目（合同表）—</option>'
      + PROJECTS.map(function (p) {
          return '<option value="' + esc(p.contract_no) + '" data-name="' + esc(p.name) + '"'
            + (p.contract_no === sel ? ' selected' : '') + '>' + esc(p.contract_no) + ' ' + esc(p.name || p.customer) + '</option>';
        }).join('');
  }

  function openModal(title, rec) {
    rec = rec || {};
    var isEdit = !!rec.id;
    var root = document.getElementById('modalRoot');
    root.innerHTML = '<div class="modal-mask" onclick="if(event.target===this)PmoOrder.closeModal()">'
      + '<div class="modal" style="width:460px">'
      + '<div class="modal-head"><span>' + title + '</span><a href="javascript:;" onclick="PmoOrder.closeModal()">✕</a></div>'
      + '<div class="modal-body"><div class="form-grid">'
      + field('订单号', '<input id="f_order_no" value="' + esc(rec.order_no) + '" ' + (isEdit ? 'readonly' : '') + ' placeholder="如 ORD-2026-001">')
      + field('订单名', '<input id="f_name" value="' + esc(rec.name) + '" placeholder="订单名称">')
      + field('项目', '<select id="f_project" onchange="PmoOrder.onProject()">' + projectOptions(rec.project_no) + '</select>')
      + field('项目号', '<input id="f_project_no" value="' + esc(rec.project_no) + '" readonly placeholder="选项目后自动带出">')
      + field('项目名', '<input id="f_project_name" value="' + esc(rec.project_name) + '" readonly placeholder="选项目后自动带出">')
      + field('开始时间', '<input id="f_start" type="date" value="' + esc(rec.start_date) + '">')
      + field('结束时间', '<input id="f_end" type="date" value="' + esc(rec.end_date) + '">')
      + '</div></div>'
      + '<div class="modal-foot"><button class="btn" onclick="PmoOrder.closeModal()">取消</button>'
      + '<button class="btn btn-c" onclick="PmoOrder.submit(' + (rec.id || 0) + ')">保存</button></div>'
      + '</div></div>';
  }
  function field(label, ctrl) {
    return '<label class="form-row"><span class="form-label">' + label + '</span>' + ctrl + '</label>';
  }
  function onProject() {
    var sel = document.getElementById('f_project');
    var opt = sel.options[sel.selectedIndex];
    document.getElementById('f_project_no').value = sel.value;
    document.getElementById('f_project_name').value = opt ? (opt.getAttribute('data-name') || '') : '';
  }
  async function openCreate() { await ensureProjects(); openModal('新增订单', {}); }
  async function openEdit(id) {
    await ensureProjects();
    var rec = ORDERS.filter(function (r) { return r.id === id; })[0];
    if (!rec) return;
    openModal('编辑订单', rec);
  }
  function closeModal() { document.getElementById('modalRoot').innerHTML = ''; }

  async function submit(id) {
    var payload = {
      order_no: document.getElementById('f_order_no').value.trim(),
      name: document.getElementById('f_name').value.trim(),
      project_no: document.getElementById('f_project_no').value.trim(),
      project_name: document.getElementById('f_project_name').value.trim(),
      start_date: document.getElementById('f_start').value.trim(),
      end_date: document.getElementById('f_end').value.trim()
    };
    if (!payload.order_no || !payload.name || !payload.project_no) {
      alert('订单号 / 订单名 / 项目 为必填'); return;
    }
    var url = id ? ('/api/plm/orders/' + id) : '/api/plm/orders';
    var method = id ? 'PUT' : 'POST';
    try {
      var j = await (await fetch(API + url, {
        method: method, headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })).json();
      if (j && j.success) { closeModal(); await loadOrders(); }
      else alert('保存失败：' + ((j && j.error) || '未知错误'));
    } catch (e) { alert('保存异常：' + e.message); }
  }

  async function remove(id) {
    if (!confirm('确认删除该订单？其下工单需先删除。')) return;
    try {
      var j = await (await fetch(API + '/api/plm/orders/' + id, { method: 'DELETE' })).json();
      if (j && j.success) await loadOrders();
      else alert('删除失败：' + ((j && j.error) || '未知错误'));
    } catch (e) { alert('删除异常：' + e.message); }
  }

  function setFilter(v) { orderFilter = v || ''; renderDetail(document.getElementById('orderDetailPane')); }
  function goPage(p) { orderPage = p; renderDetail(document.getElementById('orderDetailPane')); }

  function init() {
    document.getElementById('orderContent').innerHTML = '<div id="orderHost">'
      + NC.anaTabs([{ key: 'overview', label: '📊 总览' }, { key: 'detail', label: '📋 明细' }], 'overview', 'orderHost')
      + NC.anaPane('overview', '<div id="orderOverview"></div>', true)
      + NC.anaPane('detail', '<div id="orderDetailPane"></div>', false)
      + '</div>';
    loadOrders();
  }

  root.PmoOrder = {
    openCreate: openCreate, openEdit: openEdit, closeModal: closeModal, submit: submit, remove: remove,
    onProject: onProject, setFilter: setFilter, goPage: goPage, load: loadOrders
  };

  renderShell();
  init();
})(window);
