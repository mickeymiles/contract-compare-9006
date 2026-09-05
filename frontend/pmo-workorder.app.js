'use strict';
/* PMO 工单页（2026-09-06 落地）：总览 + 明细 双 Tab，样式对齐成本预警页；支持手工录入。
 * 数据源：/api/plm/workorders（薄壳 → plm_models.list_workorders，含 est_cost=Σ三分项）。
 * 录入：选订单自动带出 订单名/项目号/项目名（CRUD 只写数据）；自主/差旅/变动 为预算手填；
 *       完成时间用月选择器（YYYY-MM），成本按月划分。预估成本汇总与成本预警判定由本体负责。
 */
(function (root) {
  var NC = root.NAV_CONFIG;
  var API = '';

  // 说明：本模块作为 /plm 页的内部挂载单元使用（不再自建独立页面/侧栏）。
  // 由 /plm 的 PLM.go('workorder') 触发 PmoWo.mount('woMount') 渲染到 /plm 内容区。

  function status(msg) { var el = document.getElementById('woStatus'); if (el) el.textContent = msg; }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
    });
  }
  function money(v) { var n = Number(v); if (isNaN(n)) return '¥0'; return '¥' + n.toLocaleString(); }

  var WOS = [];
  var woPage = 1, woFilter = '';
  var WO_PAGE_SIZE = 12;

  function estOf(r) {
    return round(Number(r.self_cost || 0) + Number(r.travel_cost || 0) + Number(r.variable_cost || 0));
  }
  function round(v) { return Math.round(Number(v || 0) * 100) / 100; }

  function filterRows() {
    var f = (woFilter || '').trim().toLowerCase();
    if (!f) return WOS;
    return WOS.filter(function (r) {
      return ((r.wo_no || '') + ' ' + (r.name || '') + ' ' + (r.order_no || '') + ' ' + (r.project_no || '')).toLowerCase().indexOf(f) >= 0;
    });
  }

  function renderOverview(hostEl) {
    var projSet = {}, totalEst = 0;
    WOS.forEach(function (r) { if (r.project_no) projSet[r.project_no] = 1; totalEst += estOf(r); });
    var h = '<div class="cards" style="grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:16px;margin-bottom:16px;padding:20px 24px">';
    h += '<div class="card"><div class="lbl">工单数</div><div class="val" style="font-size:22px">' + WOS.length + ' 个</div></div>';
    h += '<div class="card"><div class="lbl">涉及项目</div><div class="val c" style="font-size:22px">' + Object.keys(projSet).length + ' 个</div></div>';
    h += '<div class="card"><div class="lbl">预估成本合计</div><div class="val r" style="font-size:22px">' + money(totalEst) + '</div></div>';
    h += '</div>';
    h += '<div class="panel"><h3>📋 工单总览</h3>';
    h += tableHtml(WOS.slice(0, 20));
    if (WOS.length > 20) h += '<div style="font-size:11px;color:var(--text2);margin-top:8px">仅显示前 20 条，完整列表见「明细」</div>';
    h += '</div>';
    hostEl.innerHTML = h;
  }

  function tableHtml(rows) {
    var h = '<div class="twrap"><table class="ana-table"><thead><tr>'
      + '<th>工单号</th><th>工单名</th><th>订单号</th><th>订单名</th><th>项目号</th><th>项目名</th>'
      + '<th class="num">自主</th><th class="num">差旅</th><th class="num">变动</th><th class="num">合计</th><th>完成月</th><th>操作</th>'
      + '</tr></thead><tbody>';
    if (!rows.length) {
      h += '<tr><td colspan="12" style="text-align:center;color:var(--text2);padding:20px">暂无工单</td></tr>';
    }
    rows.forEach(function (r) {
      h += '<tr><td>' + esc(r.wo_no) + '</td><td class="wrap">' + esc(r.name) + '</td>'
        + '<td>' + esc(r.order_no) + '</td><td class="wrap">' + esc(r.order_name) + '</td>'
        + '<td>' + esc(r.project_no) + '</td><td class="wrap">' + esc(r.project_name) + '</td>'
        + '<td class="num">' + money(r.self_cost) + '</td><td class="num">' + money(r.travel_cost) + '</td>'
        + '<td class="num">' + money(r.variable_cost) + '</td><td class="num">' + money(estOf(r)) + '</td>'
        + '<td>' + esc(r.complete_month) + '</td>'
        + '<td><a href="javascript:;" onclick="PmoWo.openEdit(' + r.id + ')" style="color:var(--cyan2)">编辑</a> '
        + '<a href="javascript:;" onclick="PmoWo.remove(' + r.id + ')" style="color:var(--red2)">删除</a></td></tr>';
    });
    return h + '</tbody></table></div>';
  }

  function renderDetail(hostEl) {
    var rows = filterRows();
    var pagesAll = Math.max(1, Math.ceil(rows.length / WO_PAGE_SIZE));
    woPage = Math.min(Math.max(1, woPage || 1), pagesAll);
    var start = (woPage - 1) * WO_PAGE_SIZE;
    var pageRows = rows.slice(start, start + WO_PAGE_SIZE);
    var h = '<div class="panel"><h3>📋 工单明细</h3>';
    h += '<div style="margin-bottom:8px;display:flex;gap:8px;align-items:center">'
      + '<input id="woFilterInput" type="text" placeholder="按 工单号/工单名/订单号/项目号 筛选…" value="' + esc(woFilter).replace(/"/g, '&quot;')
      + '" oninput="PmoWo.setFilter(this.value)" style="width:280px;padding:6px 10px;background:var(--bg3);border:1px solid var(--border);color:var(--text);border-radius:6px;font-size:12px">'
      + '<a href="javascript:;" onclick="PmoWo.setFilter(\'\')" style="color:var(--cyan2);font-size:12px">清空</a></div>';
    h += tableHtml(pageRows);
    h += pagerHtml(woPage, rows.length, WO_PAGE_SIZE, 'PmoWo.goPage');
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

  async function loadWorkorders() {
    status('正在读取工单…');
    try {
      var j = await (await fetch(API + '/api/plm/workorders')).json();
      WOS = (j && j.success && j.data) ? j.data : [];
      renderOverview(document.getElementById('woOverview'));
      renderDetail(document.getElementById('woDetailPane'));
      status('PMO 工单 · 共 ' + WOS.length + ' 个（预估成本汇入本体 F-workorder-cost-rollup）');
    } catch (e) { status('读取工单失败: ' + e.message); }
  }

  /* ── 录入弹窗 ── */
  var ORDERS = [];
  async function ensureOrders() {
    if (ORDERS.length) return;
    try {
      var j = await (await fetch(API + '/api/plm/orders')).json();
      ORDERS = (j && j.success && j.data) ? j.data : [];
    } catch (e) { ORDERS = []; }
  }
  function orderOptions(sel) {
    return '<option value="">— 选择订单 —</option>'
      + ORDERS.map(function (o) {
          return '<option value="' + esc(o.order_no) + '" data-name="' + esc(o.name) + '"'
            + ' data-pno="' + esc(o.project_no) + '" data-pname="' + esc(o.project_name) + '"'
            + (o.order_no === sel ? ' selected' : '') + '>' + esc(o.order_no) + ' ' + esc(o.name) + '</option>';
        }).join('');
  }

  function openModal(title, rec) {
    rec = rec || {};
    var isEdit = !!rec.id;
    var root = document.getElementById('modalRoot');
    root.innerHTML = '<div class="modal-mask" onclick="if(event.target===this)PmoWo.closeModal()">'
      + '<div class="modal" style="width:480px">'
      + '<div class="modal-head"><span>' + title + '</span><a href="javascript:;" onclick="PmoWo.closeModal()">✕</a></div>'
      + '<div class="modal-body"><div class="form-grid">'
      + field('工单号', '<input id="f_wo_no" value="' + esc(rec.wo_no) + '" ' + (isEdit ? 'readonly' : '') + '" placeholder="如 WO-2026-001">')
      + field('工单名', '<input id="f_name" value="' + esc(rec.name) + '" placeholder="工单名称/内容">')
      + field('订单', '<select id="f_order" onchange="PmoWo.onOrder()">' + orderOptions(rec.order_no) + '</select>')
      + field('订单名', '<input id="f_order_name" value="' + esc(rec.order_name) + '" readonly>')
      + field('项目号', '<input id="f_project_no" value="' + esc(rec.project_no) + '" readonly>')
      + field('项目名', '<input id="f_project_name" value="' + esc(rec.project_name) + '" readonly>')
      + field('自主成本', '<input id="f_self" type="number" step="0.01" value="' + esc(rec.self_cost) + '" oninput="PmoWo.calcEst()">')
      + field('差旅成本', '<input id="f_travel" type="number" step="0.01" value="' + esc(rec.travel_cost) + '" oninput="PmoWo.calcEst()">')
      + field('变动费用', '<input id="f_variable" type="number" step="0.01" value="' + esc(rec.variable_cost) + '" oninput="PmoWo.calcEst()">')
      + field('完成时间(月)', '<input id="f_month" type="month" value="' + esc(rec.complete_month) + '">')
      + field('预估成本合计', '<input id="f_est" value="' + (rec.id ? money(estOf(rec)) : '¥0') + '" readonly>')
      + '</div></div>'
      + '<div class="modal-foot"><button class="btn" onclick="PmoWo.closeModal()">取消</button>'
      + '<button class="btn btn-c" onclick="PmoWo.submit(' + (rec.id || 0) + ')">保存</button></div>'
      + '</div></div>';
  }
  function field(label, ctrl) {
    return '<label class="form-row"><span class="form-label">' + label + '</span>' + ctrl + '</label>';
  }
  function onOrder() {
    var sel = document.getElementById('f_order');
    var opt = sel.options[sel.selectedIndex];
    document.getElementById('f_order_name').value = opt ? opt.getAttribute('data-name') || '' : '';
    document.getElementById('f_project_no').value = opt ? opt.getAttribute('data-pno') || '' : '';
    document.getElementById('f_project_name').value = opt ? opt.getAttribute('data-pname') || '' : '';
  }
  function calcEst() {
    var v = round(Number(document.getElementById('f_self').value || 0)
      + Number(document.getElementById('f_travel').value || 0)
      + Number(document.getElementById('f_variable').value || 0));
    document.getElementById('f_est').value = money(v);
  }
  async function openCreate() { await ensureOrders(); openModal('新增工单', {}); }
  async function openEdit(id) {
    await ensureOrders();
    var rec = WOS.filter(function (r) { return r.id === id; })[0];
    if (!rec) return;
    openModal('编辑工单', rec);
  }
  function closeModal() { document.getElementById('modalRoot').innerHTML = ''; }

  async function submit(id) {
    var payload = {
      wo_no: document.getElementById('f_wo_no').value.trim(),
      name: document.getElementById('f_name').value.trim(),
      order_no: document.getElementById('f_order').value.trim(),
      self_cost: document.getElementById('f_self').value,
      travel_cost: document.getElementById('f_travel').value,
      variable_cost: document.getElementById('f_variable').value,
      complete_month: document.getElementById('f_month').value.trim()
    };
    if (!payload.wo_no || !payload.name || !payload.order_no) {
      alert('工单号 / 工单名 / 订单 为必填'); return;
    }
    var url = id ? ('/api/plm/workorders/' + id) : '/api/plm/workorders';
    var method = id ? 'PUT' : 'POST';
    try {
      var j = await (await fetch(API + url, {
        method: method, headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })).json();
      if (j && j.success) { closeModal(); await loadWorkorders(); }
      else alert('保存失败：' + ((j && j.error) || '未知错误'));
    } catch (e) { alert('保存异常：' + e.message); }
  }

  async function remove(id) {
    if (!confirm('确认删除该工单？')) return;
    try {
      var j = await (await fetch(API + '/api/plm/workorders/' + id, { method: 'DELETE' })).json();
      if (j && j.success) await loadWorkorders();
      else alert('删除失败：' + ((j && j.error) || '未知错误'));
    } catch (e) { alert('删除异常：' + e.message); }
  }

  function setFilter(v) { woFilter = v || ''; renderDetail(document.getElementById('woDetailPane')); }
  function goPage(p) { woPage = p; renderDetail(document.getElementById('woDetailPane')); }

  function mount(hostId) {
    var host = document.getElementById(hostId);
    if (!host) return;
    host.innerHTML = '<div id="woHost">'
      + NC.anaTabs([{ key: 'overview', label: '📊 总览' }, { key: 'detail', label: '📋 明细' }], 'overview', 'woHost')
      + NC.anaPane('overview', '<div id="woOverview"></div>', true)
      + NC.anaPane('detail', '<div id="woDetailPane"></div>', false)
      + '</div>';
    loadWorkorders();
  }

  root.PmoWo = {
    openCreate: openCreate, openEdit: openEdit, closeModal: closeModal, submit: submit, remove: remove,
    onOrder: onOrder, calcEst: calcEst, setFilter: setFilter, goPage: goPage, load: loadWorkorders, mount: mount
  };

})(window);
