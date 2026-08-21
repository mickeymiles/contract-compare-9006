/* 备品备件采购询比价 — 前端交互逻辑
 * 与本工程 backend/main.py 提供的 /api/procurement/* 接口交互
 * 不直接调 neuops-agent-demo（neuops 智能体由后端 routes_procurement_agent 触发）
 */

// ============ 通用工具 ============
const $ = (id) => document.getElementById(id);
const API = '/api/procurement';

function toast(msg, kind = 'ok') {
  const t = $('toast');
  t.textContent = msg;
  t.className = `toast ${kind} show`;
  setTimeout(() => t.classList.remove('show'), 2500);
}

async function api(path, method = 'GET', body = null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(API + path, opts);
  const data = await r.json().catch(() => ({ success: false, error: '响应解析失败' }));
  if (!r.ok || data.success === false) {
    throw new Error(data.error || data.message || `HTTP ${r.status}`);
  }
  return data;
}

function fmtStatus(s) {
  const m = {
    '询比价进行中': ['运行中', 'badge-proc-running'],
    '部分供应商超时': ['部分超时', 'badge-proc-timeout-p'],
    '全部供应商超时': ['全部超时', 'badge-proc-timeout-a'],
    '已选型确认': ['已选型', 'badge-proc-confirm'],
    '供应商发货中': ['发货中', 'badge-proc-shipping'],
    '流程闭环': ['已闭环', 'badge-proc-closed'],
    '收货测试失败': ['测试失败', 'badge-proc-failed'],
    '任务已取消': ['已取消', 'badge-proc-canceled'],
  };
  const [label, cls] = m[s] || [s, 'badge-o'];
  return `<span class="badge ${cls}">${label}</span>`;
}

// ============ 页面切换 ============
function showPage(name) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  if (name === 'list') {
    $('page-proc-list').classList.add('active');
    $('procCrumb').textContent = '🛒 备品备件采购询比价';
    loadTaskList();
  } else if (name === 'new') {
    $('page-proc-new').classList.add('active');
    $('procCrumb').textContent = '🛒 备品备件采购询比价 › 新建询价';
    loadMasterDataForNew();
  }
}

function switchDetailTab(tab) {
  document.querySelectorAll('.proc-tab').forEach(b => b.classList.remove('active'));
  document.querySelector(`.proc-tab[data-tab="${tab}"]`).classList.add('active');
  ['Base', 'Quote', 'Action'].forEach(t => {
    $(`detailTab${t}`).style.display = 'none';
  });
  if (tab === 'base') $('detailTabBase').style.display = 'block';
  if (tab === 'quote') $('detailTabQuote').style.display = 'block';
  if (tab === 'action') $('detailTabAction').style.display = 'block';
}

// ============ 任务列表 ============
let currentStatusFilter = '';

function filterStatus(btn) {
  currentStatusFilter = btn.dataset.status;
  document.querySelectorAll('#statusFilter .btn').forEach(b => {
    b.classList.remove('btn-c');
    b.classList.add('btn-o');
  });
  btn.classList.remove('btn-o');
  btn.classList.add('btn-c');
  loadTaskList();
}

async function loadTaskList() {
  try {
    const path = currentStatusFilter ? `/tasks?status=${encodeURIComponent(currentStatusFilter)}` : '/tasks';
    const d = await api(path);
    const rows = d.data || [];
    const body = $('taskListBody');
    if (!rows.length) {
      body.innerHTML = '<tr><td colspan="9" class="empty-tip">暂无询比价任务，点击「＋ 发起新询价」开始</td></tr>';
      return;
    }
    body.innerHTML = rows.map(t => `
      <tr>
        <td style="font-family:var(--mono);font-size:11px">${t.task_id}</td>
        <td>${escapeHtml(t.project_name || '')}</td>
        <td style="font-family:var(--mono)">${escapeHtml(t.contract_no || '')}</td>
        <td>${escapeHtml(t.spare_part_model || '')}</td>
        <td style="text-align:right">${t.purchase_qty}</td>
        <td>${fmtStatus(t.task_status)}</td>
        <td style="font-size:11px">${t.reply_deadline || '-'}</td>
        <td style="font-size:11px">${t.create_time || '-'}</td>
        <td>
          <button class="btn btn-o btn-s" onclick="openDetail('${t.task_id}')">查看</button>
          ${isUnclosed(t.task_status) ? `<button class="btn btn-o btn-s" style="color:var(--red)" onclick="openCancel('${t.task_id}')">取消</button>` : ''}
        </td>
      </tr>
    `).join('');
  } catch (e) {
    $('taskListBody').innerHTML = `<tr><td colspan="9" class="empty-tip" style="color:var(--red)">加载失败: ${escapeHtml(e.message)}</td></tr>`;
  }
}

function isUnclosed(s) {
  return !['流程闭环', '任务已取消'].includes(s);
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// ============ 新建询价 ============
let masterDataCache = [];

async function loadMasterDataForNew() {
  try {
    const d = await api('/master');
    masterDataCache = d.data || [];
    const sel = $('newProject');
    sel.innerHTML = '<option value="">请选择项目</option>' +
      masterDataCache.map(m => `<option value="${m.id}">${escapeHtml(m.project_name)} (${escapeHtml(m.project_id)})</option>`).join('');
    onProjectChange();
  } catch (e) {
    toast('主数据加载失败: ' + e.message, 'err');
  }
}

function onProjectChange() {
  const pid = $('newProject').value;
  const contracts = [...new Set(masterDataCache.filter(m => String(m.id) === pid).map(m => m.contract_no))];
  const contractSel = $('newContract');
  contractSel.innerHTML = '<option value="">请选择合同</option>' +
    contracts.map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('');
  onContractChange();
}

function onContractChange() {
  const pid = $('newProject').value;
  const contractNo = $('newContract').value;
  const master = masterDataCache.find(m => String(m.id) === pid && m.contract_no === contractNo);
  const partSel = $('newPart');
  const supplierBox = $('supplierList');

  if (!master) {
    partSel.innerHTML = '<option value="">请先选择项目</option>';
    supplierBox.innerHTML = '<div class="empty-tip">请先选择项目和合同</div>';
    if (master) $('newEmergency').value = master.default_emergency_level || '4h';
    updateDeadlinePreview();
    return;
  }

  // 备件型号下拉
  partSel.innerHTML = (master.allow_spare_parts || [])
    .map(p => `<option value="${escapeHtml(p)}">${escapeHtml(p)}</option>`).join('') ||
    '<option value="">该合同未配置可采购备件</option>';

  // 紧急等级默认值
  $('newEmergency').value = master.default_emergency_level || '4h';

  // 供应商勾选列表（默认全选）
  const suppliers = master.default_suppliers || [];
  if (!suppliers.length) {
    supplierBox.innerHTML = '<div class="empty-tip">该合同未配置默认供应商，请手动添加临时供应商</div>';
  } else {
    supplierBox.innerHTML = suppliers.map((s, i) => `
      <div class="proc-supplier-row">
        <input type="checkbox" data-idx="${i}" checked>
        <span class="sp-name">${escapeHtml(s.name)}</span>
        <span class="sp-email">${escapeHtml(s.email)}</span>
      </div>
    `).join('');
  }
  updateDeadlinePreview();
}

function addTempSupplier() {
  const name = $('newSpName').value.trim();
  const email = $('newSpEmail').value.trim();
  if (!name || !email) {
    toast('请填写供应商名称和邮箱', 'err');
    return;
  }
  const box = $('supplierList');
  if (box.querySelector('.empty-tip')) box.innerHTML = '';
  const idx = box.querySelectorAll('.proc-supplier-row').length;
  const div = document.createElement('div');
  div.className = 'proc-supplier-row';
  div.innerHTML = `
    <input type="checkbox" data-idx="${idx}" data-temp="1" checked>
    <span class="sp-name">${escapeHtml(name)} <span class="badge badge-c" style="margin-left:4px">临时</span></span>
    <span class="sp-email">${escapeHtml(email)}</span>
    <button class="sp-del" onclick="this.parentElement.remove()">✕</button>
  `;
  box.appendChild(div);
  $('newSpName').value = '';
  $('newSpEmail').value = '';
}

function updateDeadlinePreview() {
  const lvl = $('newEmergency').value;
  const hours = parseInt(lvl) || 4;
  const dl = new Date(Date.now() + hours * 3600 * 1000);
  const fmt = dl.toLocaleString('zh-CN', { hour12: false });
  $('deadlinePreview').textContent = `报价截止时间：${fmt}`;
}

async function submitNewInquiry() {
  try {
    const masterId = $('newProject').value;
    const contractNo = $('newContract').value;
    const master = masterDataCache.find(m => String(m.id) === masterId && m.contract_no === contractNo);
    if (!master) { toast('请选择项目与合同', 'err'); return; }
    const spare_part_model = $('newPart').value;
    const purchase_qty = parseFloat($('newQty').value);
    if (!spare_part_model) { toast('请选择备件型号', 'err'); return; }
    if (!purchase_qty || purchase_qty <= 0) { toast('请输入有效采购数量', 'err'); return; }
    const emergency_level = $('newEmergency').value;
    // 收集勾选的供应商
    const supplierRows = document.querySelectorAll('#supplierList .proc-supplier-row');
    const inquiry_supplier_list = [];
    supplierRows.forEach(row => {
      const cb = row.querySelector('input[type="checkbox"]');
      if (!cb.checked) return;
      const name = row.querySelector('.sp-name').textContent.replace('临时', '').trim();
      const email = row.querySelector('.sp-email').textContent.trim();
      inquiry_supplier_list.push({ name, email });
    });
    if (!inquiry_supplier_list.length) { toast('请至少选择一个询价供应商', 'err'); return; }

    const d = await api('/tasks', 'POST', {
      master_id: parseInt(masterId),
      spare_part_model, purchase_qty, emergency_level,
      inquiry_supplier_list
    });
    toast(`询价任务已创建：${d.data.task_id}`);
    resetNewForm();
    showPage('list');
  } catch (e) {
    toast('创建失败: ' + e.message, 'err');
  }
}

function resetNewForm() {
  $('newPart').value = '';
  $('newQty').value = '1';
  $('newEmergency').value = '4h';
  $('newSpName').value = '';
  $('newSpEmail').value = '';
  onProjectChange();
  updateDeadlinePreview();
}

// ============ 任务详情 ============
let currentDetailTaskId = null;
let currentDetailTask = null;

async function openDetail(taskId) {
  currentDetailTaskId = taskId;
  showPage('detail');
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  $('page-proc-detail').classList.add('active');
  $('procCrumb').textContent = `🛒 备品备件采购询比价 › 任务详情 ${taskId}`;
  $('detailTaskId').textContent = taskId;
  switchDetailTab('base');
  await loadDetail();
}

async function loadDetail() {
  try {
    const d = await api(`/tasks/${currentDetailTaskId}`);
    currentDetailTask = d.data;
    renderTimeline();
    renderDetailBase();
    renderDetailQuote();
    renderDetailAction();
  } catch (e) {
    $('detailBaseBody').innerHTML = `<div class="empty-tip" style="color:var(--red)">加载失败: ${escapeHtml(e.message)}</div>`;
  }
}

// ============ 时间轴 ============
const TIMELINE_STEPS = [
  { key: 'created', label: '询价发起', icon: '🚀' },
  { key: 'quoting', label: '报价收集中', icon: '📊' },
  { key: 'selected', label: '选型确认', icon: '✅' },
  { key: 'shipping', label: '供应商发货', icon: '📦' },
  { key: 'testing', label: '收货测试', icon: '🔧' },
  { key: 'closed', label: '流程闭环', icon: '🎉' },
];

const STATUS_TO_STEP = {
  '询比价进行中': 1,
  '部分供应商超时': 1,
  '全部供应商超时': 1,
  '已选型确认': 2,
  '供应商发货中': 3,
  '流程闭环': 5,
  '收货测试失败': 4,
  '任务已取消': -1,
};

function renderTimeline() {
  const t = currentDetailTask;
  if (!t) return;
  const currentStep = STATUS_TO_STEP[t.task_status] ?? 0;
  const isCanceled = t.task_status === '任务已取消';
  const isFailed = t.task_status === '收货测试失败';

  // 从操作日志提取各环节时间
  const logs = t._op_logs || [];
  const stepTimes = {};
  logs.forEach(l => {
    if (l.action === 'create_task') stepTimes[0] = l.action_time;
    if (l.action === 'confirm_selection') stepTimes[2] = l.action_time;
    if (l.action === 'update_task_delivery') stepTimes[3] = l.action_time;
    if (l.action === 'input_test_result') stepTimes[4] = l.action_time;
    if (l.action === 'write_ledger') stepTimes[5] = l.action_time;
  });
  if (t.create_time) stepTimes[0] = t.create_time;
  if (t.task_status === '流程闭环' && t.updated_at) stepTimes[5] = t.updated_at;

  $('detailTimeline').innerHTML = TIMELINE_STEPS.map((step, i) => {
    let cls = '';
    if (isCanceled) {
      cls = i < currentStep ? 'done' : (i === currentStep ? 'canceled' : '');
    } else if (isFailed && i === 4) {
      cls = 'failed';
    } else if (i < currentStep) {
      cls = 'done';
    } else if (i === currentStep) {
      cls = 'current';
    }
    const icon = cls === 'done' ? '✓' : step.icon;
    const timeStr = stepTimes[i] ? stepTimes[i].substring(5, 16) : '';
    return `
      <div class="tl-step ${cls}">
        <div class="tl-line"></div>
        <div class="tl-node">${icon}</div>
        <div class="tl-label">${step.label}</div>
        <div class="tl-time">${timeStr}</div>
      </div>
    `;
  }).join('');
}

function renderDetailBase() {
  const t = currentDetailTask;
  if (!t) return;
  const sel = t.selected_supplier || {};
  const fields = [
    ['任务ID', t.task_id],
    ['项目', `${t.project_name} (${t.project_id})`],
    ['合同号', t.contract_no],
    ['备件型号', t.spare_part_model],
    ['采购数量', t.purchase_qty],
    ['紧急等级', t.emergency_level],
    ['报价截止时间', t.reply_deadline],
    ['询价供应商', (t.inquiry_supplier_list || []).map(s => s.name).join('、') || '-'],
    ['已回复', `${(t.replied_supplier_quotes || []).length} 家`],
    ['未回复', `${(t.no_reply_supplier || []).length} 家`],
    ['选中供应商', sel.name ? `${sel.name} <${sel.email}>` : '-'],
    ['成交单价', t.deal_unit_price || '-'],
    ['发货时间', t.delivery_time || '-'],
    ['物流单号', t.logistics_no || '-'],
    ['测试结果', t.test_result || '-'],
    ['任务状态', fmtStatus(t.task_status)],
    ['创建人', t.creator || '-'],
    ['创建时间', t.create_time],
    ['更新时间', t.updated_at || '-'],
  ];
  if (t.task_status === '任务已取消') {
    fields.push(['取消原因', t.cancel_reason || '-']);
  }
  $('detailBaseBody').innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px 24px;font-size:13px">
      ${fields.map(([k, v]) => `
        <div style="display:flex;gap:8px;padding:6px 0;border-bottom:1px solid var(--border)">
          <span style="color:var(--text2);width:90px;flex-shrink:0">${k}</span>
          <span style="color:var(--text)">${v}</span>
        </div>
      `).join('')}
    </div>
  `;
}

function renderDetailQuote() {
  const t = currentDetailTask;
  if (!t) return;
  const replied = t.replied_supplier_quotes || [];
  const noReply = t.no_reply_supplier || [];
  const canSelect = ['询比价进行中', '部分供应商超时', '全部供应商超时'].includes(t.task_status);

  let html = '';
  if (!replied.length) {
    html += '<div class="empty-tip">暂无供应商回复报价</div>';
  } else {
    html += '<div class="twrap"><table><thead><tr>';
    html += '<th>选型</th><th>供应商</th><th>邮箱</th><th>品牌</th><th>型号</th><th>单价</th><th>报价时间</th></tr></thead><tbody>';
    replied.forEach((q, i) => {
      const checked = t.selected_supplier && t.selected_supplier.email === q.email ? 'checked' : '';
      html += `<tr class="${checked ? 'selected' : ''}">
        <td><input type="radio" name="quoteRadio" value="${i}" ${checked} ${canSelect ? '' : 'disabled'}></td>
        <td>${escapeHtml(q.supplier_name || q.name || '')}</td>
        <td style="font-family:var(--mono);font-size:11px">${escapeHtml(q.email || '')}</td>
        <td>${escapeHtml(q.brand || '')}</td>
        <td>${escapeHtml(q.model || '')}</td>
        <td style="text-align:right">${q.unit_price || '-'}</td>
        <td style="font-size:11px">${q.reply_time || '-'}</td>
      </tr>`;
    });
    html += '</tbody></table></div>';

    if (canSelect) {
      html += `
        <div class="proc-field" style="margin-top:16px">
          <div class="l">成交单价</div>
          <input type="number" id="dealPrice" min="0" step="0.01" placeholder="录入实际成交单价" style="max-width:200px">
        </div>
        <button class="btn btn-c" onclick="submitSelection()">✅ 确认采购</button>
      `;
    }
  }

  if (noReply.length) {
    html += `<h3 style="margin-top:24px;color:var(--orange)">⚠️ 未回复供应商 (${noReply.length} 家)</h3>`;
    html += '<div style="font-size:12px;color:var(--text2)">' +
      noReply.map(s => escapeHtml(s.name)).join('、') + '</div>';
  }

  $('detailQuoteBody').innerHTML = html;
}

function renderDetailAction() {
  const t = currentDetailTask;
  if (!t) return;
  let html = '';
  const isShipping = t.task_status === '供应商发货中';
  const canCancel = isUnclosed(t.task_status);

  if (isShipping) {
    html += `
      <div style="padding:16px;background:var(--bg3);border:1px solid var(--border);border-radius:8px;margin-bottom:16px">
        <h3 style="color:var(--cyan);margin-bottom:10px">📦 录入测试结果</h3>
        <p style="font-size:12px;color:var(--text2);margin-bottom:12px">现场工程师已完成收货与硬件测试，请录入测试结果：</p>
        <button class="btn btn-c" onclick="openTestModal()">📝 录入测试结果</button>
      </div>
    `;
  }

  if (canCancel) {
    html += `
      <div style="padding:16px;background:rgba(255,82,82,.04);border:1px solid rgba(255,82,82,.2);border-radius:8px">
        <h3 style="color:var(--red);margin-bottom:10px">⚠️ 取消任务</h3>
        <p style="font-size:12px;color:var(--text2);margin-bottom:12px">取消后任务不再写入台账，已发送的询价邮件不可撤回。</p>
        <button class="btn btn-c" style="background:var(--red);color:#fff" onclick="openCancel('${t.task_id}')">❌ 取消任务</button>
      </div>
    `;
  }

  if (!isShipping && !canCancel) {
    html += `<div class="empty-tip">当前状态「${t.task_status}」，无可用处置操作。</div>`;
  }

  // 操作日志
  html += `<h3 style="margin-top:24px">📜 操作日志</h3><div id="opLogBody" class="twrap"><div class="empty-tip">加载中...</div></div>`;

  $('detailActionBody').innerHTML = html;
  loadOpLogs();
}

async function loadOpLogs() {
  try {
    const d = await api(`/tasks/${currentDetailTaskId}/logs`);
    const logs = d.data || [];
    const body = $('opLogBody');
    if (!logs.length) {
      body.innerHTML = '<div class="empty-tip">暂无操作日志</div>';
      return;
    }
    body.innerHTML = '<table><thead><tr><th>时间</th><th>操作人</th><th>动作</th><th>备注</th></tr></thead><tbody>' +
      logs.map(l => `<tr>
        <td style="font-size:11px">${l.action_time}</td>
        <td>${escapeHtml(l.operator)}</td>
        <td><span class="badge badge-o">${escapeHtml(l.action)}</span></td>
        <td style="font-size:11px">${escapeHtml(l.remark || '')}</td>
      </tr>`).join('') + '</tbody></table>';
  } catch (e) {
    $('opLogBody').innerHTML = `<div class="empty-tip" style="color:var(--red)">${escapeHtml(e.message)}</div>`;
  }
}

async function submitSelection() {
  const radio = document.querySelector('input[name="quoteRadio"]:checked');
  if (!radio) { toast('请先选择一个供应商', 'err'); return; }
  const idx = parseInt(radio.value);
  const q = currentDetailTask.replied_supplier_quotes[idx];
  const deal = parseFloat($('dealPrice').value);
  if (!deal || deal <= 0) { toast('请录入有效的成交单价', 'err'); return; }
  try {
    await api(`/tasks/${currentDetailTaskId}/select`, 'POST', {
      selected_supplier: { name: q.supplier_name || q.name, email: q.email },
      deal_unit_price: deal
    });
    toast('选型确认成功，已发送采购确认邮件');
    await loadDetail();
    loadTaskList();
  } catch (e) {
    toast('选型失败: ' + e.message, 'err');
  }
}

// ============ 录入测试结果弹窗 ============
function openTestModal() {
  $('testResultModal').classList.add('show');
}
function closeTestModal() {
  $('testResultModal').classList.remove('show');
  $('testRemark').value = '';
}
async function submitTestResult() {
  const result = document.querySelector('input[name="testResult"]:checked').value;
  const remark = $('testRemark').value.trim();
  try {
    await api(`/tasks/${currentDetailTaskId}/test`, 'POST', { test_result: result, remark });
    toast(result === '通过' ? '测试通过，台账已写入，任务闭环' : '已标记测试失败，已告警项目经理');
    closeTestModal();
    await loadDetail();
    loadTaskList();
  } catch (e) {
    toast('提交失败: ' + e.message, 'err');
  }
}

// ============ 取消任务弹窗 ============
function openCancel(taskId) {
  currentDetailTaskId = taskId;
  $('cancelModal').classList.add('show');
}
function closeCancelModal() {
  $('cancelModal').classList.remove('show');
  $('cancelReason').value = '';
}
async function submitCancelTask() {
  const reason = $('cancelReason').value.trim();
  if (!reason) { toast('请填写取消原因', 'err'); return; }
  try {
    await api(`/tasks/${currentDetailTaskId}/cancel`, 'POST', { cancel_reason: reason });
    toast('任务已取消');
    closeCancelModal();
    await loadDetail();
    loadTaskList();
  } catch (e) {
    toast('取消失败: ' + e.message, 'err');
  }
}

// ============ 帮助弹窗 ============
function toggleHelp() { $('helpModal').classList.add('show'); }
function closeHelp() { $('helpModal').classList.remove('show'); }

// ============ 启动 ============
document.addEventListener('DOMContentLoaded', () => {
  loadTaskList();
});
