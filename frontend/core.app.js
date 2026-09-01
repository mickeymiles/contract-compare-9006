/* ================================================================
 * 主数据域 core 前端脚本 —— R4
 * 壳（手风琴/面包屑/图标）由共享 nav.config.js 提供，本页只接业务。
 * 数据源：/api/core/*（主数据 CRUD + 运维联系人，导入能力后续接入）
 * ================================================================ */
'use strict';
var NC = window.NAV_CONFIG;   // { ICONS, icon, renderAccordion, renderBreadcrumb }

/* ---- 工具：loading 防重复提交 ---- */
var Busy = { btn: null, label: '' };
function withLoading(btnId, busyLabel, fn) {
  var btn = document.getElementById(btnId);
  var label = btn.textContent;
  Busy.btn = btn; Busy.label = label;
  btn.disabled = true; btn.textContent = busyLabel || label; btn.classList.add('off');
  return fn().finally(function () {
    if (Busy.btn) { Busy.btn.disabled = false; Busy.btn.textContent = Busy.label; Busy.btn.classList.remove('off'); Busy.btn = null; }
  });
}
function toast(msg, ok) {
  var t = document.createElement('div');
  t.className = 'toast ' + (ok ? 'ok' : 'err'); t.textContent = msg;
  document.body.appendChild(t);
  requestAnimationFrame(function () { t.classList.add('show'); });
  setTimeout(function () { t.classList.remove('show'); setTimeout(function () { t.remove(); }, 400); }, 2200);
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

/* ---- 状态 badge ---- */
var STATUS = { active: ['进行中', 'badge-s'], planning: ['规划', 'badge-o'], done: ['已完成', 'badge-c'], archived: ['已归档', 'badge-p'] };
function statusBadge(s) {
  var d = STATUS[s] || [s || '—', 'badge-o'];
  return '<span class="badge ' + d[1] + '">' + d[0] + '</span>';
}
function fmtMoney(v) {
  if (v === null || v === undefined || v === '') return '—';
  var n = Number(v);
  return isNaN(n) ? '—' : n.toLocaleString('zh-CN');
}

/* ---- 数据加载 ---- */
function loadProjects() {
  var kw = (document.getElementById('kw').value || '').trim();
  return api('/api/core/projects' + (kw ? '?keyword=' + encodeURIComponent(kw) : '')).then(function (j) {
    var rows = (j.success ? j.data : []);
    document.getElementById('hdrSub').textContent = '共 ' + rows.length + ' 个项目 · 项目号为主数据唯一键（商机/合同/项目三号独立）';
    var tbl = document.getElementById('projTbl');
    if (!rows.length) { tbl.innerHTML = emptyRow('暂无项目数据，点击右上角「新建项目」录入。（商机/合同/项目支持飞书/Excel 导入为主）', 9); return; }
    tbl.innerHTML = '<thead><tr>'
      + '<th>项目号</th><th>商机号</th><th>合同号</th><th>项目名称</th><th>客户</th><th>状态</th>'
      + '<th>签订额</th><th>签订日期</th><th>部门</th><th style="width:110px">操作</th>'
      + '</tr></thead><tbody>' + rows.map(projRow).join('') + '</tbody>';
  });
}
function projRow(p) {
  return '<tr>'
    + '<td><span class="proj-no">' + esc(p.project_no) + '</span></td>'
    + '<td>' + esc(p.opportunity_no || '—') + '</td>'
    + '<td>' + esc(p.contract_no || '—') + '</td>'
    + '<td>' + esc(p.name || '—') + '</td>'
    + '<td>' + esc(p.customer_key || '—') + '</td>'
    + '<td>' + statusBadge(p.status) + '</td>'
    + '<td>' + fmtMoney(p.sign_amount) + '</td>'
    + '<td>' + esc(p.sign_date || '—') + '</td>'
    + '<td>' + esc(p.dept || '—') + '</td>'
    + '<div class="opt-cell">'
    + '<a class="icon-link" title="编辑" onclick="Core.editProject(' + p.project_id + ')">' + NC.icon('edit', 'sm') + '</a>'
    + '<a class="icon-link" title="删除" onclick="Core.delProject(' + p.project_id + ')">' + NC.icon('del', 'sm') + '</a>'
    + '</div></td></tr>';
}

/* ---- 项目弹窗 ---- */
function resetProjectForm() {
  ['f_project_no', 'f_opportunity_no', 'f_contract_no', 'f_name', 'f_customer_key',
   'f_sign_amount', 'f_sign_date', 'f_dept', 'f_owner_ref'].forEach(function (id) { document.getElementById(id).value = ''; });
  document.getElementById('f_status').value = 'active';
}
function openProjectModal() {
  window._editingProject = null;
  resetProjectForm();
  document.getElementById('projModalTitle').textContent = '新建项目';
  document.getElementById('btnProjSave').textContent = '保存';
  document.getElementById('projHint').textContent = '';
  document.getElementById('projModal').classList.add('show');
}
function collectProject() {
  return {
    project_no: document.getElementById('f_project_no').value.trim(),
    opportunity_no: document.getElementById('f_opportunity_no').value.trim(),
    contract_no: document.getElementById('f_contract_no').value.trim(),
    name: document.getElementById('f_name').value.trim(),
    customer_key: document.getElementById('f_customer_key').value.trim(),
    status: document.getElementById('f_status').value,
    sign_amount: document.getElementById('f_sign_amount').value,
    sign_date: document.getElementById('f_sign_date').value || null,
    dept: document.getElementById('f_dept').value.trim(),
    owner_ref: document.getElementById('f_owner_ref').value.trim()
  };
}
function saveProject() {
  var body = collectProject();
  if (!body.project_no) { toast('项目号必填', false); return; }
  var isEdit = !!window._editingProject;
  withLoading('btnProjSave', '保存中…', function () {
    var url = isEdit ? ('/api/core/projects/' + window._editingProject) : '/api/core/projects';
    var opts = { method: isEdit ? 'PUT' : 'POST', body: JSON.stringify(body) };
    return api(url, opts).then(function (j) {
      if (j.success) { toast(isEdit ? '已保存' : '项目已创建', true); closeModal('projModal'); return reload(); }
      toast(j.error || '保存失败', false); document.getElementById('projHint').textContent = (j.error || '');
    });
  });
}
function editProject(pid) {
  api('/api/core/projects/' + pid).then(function (j) {
    if (!j.success) { toast('加载失败', false); return; }
    var p = j.data;
    window._editingProject = pid;
    resetProjectForm();
    ['f_project_no', 'f_opportunity_no', 'f_contract_no', 'f_name', 'f_customer_key', 'f_sign_amount', 'f_sign_date', 'f_dept', 'f_owner_ref']
      .forEach(function (id) { document.getElementById(id).value = (p[id.replace('f_', '')] == null ? '' : p[id.replace('f_', '')]); });
    document.getElementById('f_status').value = p.status || 'active';
    document.getElementById('projModalTitle').textContent = '编辑项目';
    document.getElementById('btnProjSave').textContent = '保存';
    document.getElementById('projHint').textContent = '';
    document.getElementById('projModal').classList.add('show');
  });
}
function delProject(pid) {
  if (!confirm('确认删除该项目主数据？关联查询可能受影响。')) return;
  api('/api/core/projects/' + pid, { method: 'DELETE' }).then(function (j) {
    if (j.success) { toast('项目已删除', true); return reload(); }
    toast(j.error || '删除失败', false);
  });
}

/* ---- 导入合同 Excel（总合同表 → 主数据） ---- */
function importProjects(inp) {
  var f = inp.files && inp.files[0];
  if (!f) return;
  var btn = document.getElementById('btnImportProj');
  var ot = btn.textContent;
  btn.disabled = true; btn.textContent = '导入中…';
  var fd = new FormData();
  fd.append('file', f);
  fetch('/api/core/projects/import', { method: 'POST', body: fd })
    .then(function (r) { return r.json(); })
    .then(function (j) {
      if (j.success) {
        toast('导入成功：新增 ' + j.created + ' / 更新 ' + j.updated + ' / 跳过 ' + (j.errors || 0) + ' 条', true);
      } else {
        toast(j.error || '导入失败，请检查表头是否包含「合同编号」等列', false);
      }
    })
    .catch(function (e) { toast('导入失败：' + e.message, false); })
    .finally(function () { btn.disabled = false; btn.textContent = ot; inp.value = ''; reload(); });
}

/* ---- 通用 ---- */
function closeModal(id) {
  document.getElementById(id).classList.remove('show');
  if (id === 'projModal') window._editingProject = null;
}
function reload() { return loadProjects(); }

/* ================================================================
 * 面板路由（系统域单页多面板）
 * 主数据「项目」+ 本体可观测 6 个面板同页共存，靠 .core-panel.active 切换。
 * 入口来自 nav.config.js 的 /core?panel=xxx；同页内点击拦截为无刷新切换。
 * 本体面板的渲染逻辑在 ontology.app.js（window.loadOntPanel）。
 * ================================================================ */
var PANELS = {
  project:      { link: 'sys-project',       crumb: ['系统', '主数据', '项目'],           title: '项目主数据 · 经营业务工作台' },
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
  if (name === 'project') {
    var first = !window._projLoaded;
    window._projLoaded = true;
    reload().then(function () { if (first) toast('数据已加载', true); })
      .catch(function () { toast('加载失败', false); });
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
  var p = new URLSearchParams(location.search).get('panel') || 'project';
  return PANELS[p] ? p : 'project';
}

function init() {
  document.getElementById('projTitleIcon').innerHTML = NC.ICONS.project;
  NC.renderTopMenu(document.getElementById('topMenu'), { activeKey: 'sys' });
  bindPanelLinks();
  var panel = currentPanelFromUrl();
  // 项目列表始终预载一次（切回主数据面板即时可见），本体面板按需加载。
  if (panel !== 'project') {
    window._projLoaded = true;
    reload().catch(function () {});
  }
  switchPanel(panel, { keepUrl: true });
}

window.Core = {
  reload: reload, closeModal: closeModal, switchPanel: switchPanel,
  openProjectModal: openProjectModal, saveProject: saveProject, editProject: editProject, delProject: delProject,
  importProjects: importProjects
};
document.addEventListener('DOMContentLoaded', init);