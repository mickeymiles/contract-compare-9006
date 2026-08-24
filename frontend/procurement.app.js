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

// ============ 页面切换（左侧菜单导航，单入口 + 唯一性校验） ============
const _SIDE_MENU_KEYS = ['tasks', 'sparepart', 'ledger', 'supplier', 'contract', 'mailcc'];

function __assertUniqueActive(selector, label) {
  const actives = document.querySelectorAll(selector);
  if (actives.length > 1) {
    console.warn(`[proc-sidebar] 检测到 ${label} 有 ${actives.length} 个 active，自动修复（仅保留最后一个）`);
    actives.forEach((n, i) => i < actives.length - 1 && n.classList.remove('active'));
  }
}

function initProcUI() {
  // 启动自检
  const menus = document.querySelectorAll('.menu-item');
  const panels = document.querySelectorAll('.proc-top-panel');
  console.info(`[proc-sidebar] 启动自检：菜单项=${menus.length}，面板=${panels.length}`);
  // 唯一性修正
  const panelsActive = document.querySelectorAll('.proc-top-panel.active');
  if (panelsActive.length !== 1) {
    const keep = document.getElementById('proc-tab-tasks');
    panelsActive.forEach(n => n.classList.remove('active'));
    keep && keep.classList.add('active');
  }
  const pagesActive = document.querySelectorAll('.page.active');
  if (pagesActive.length !== 1) {
    const keep = document.getElementById('page-proc-list');
    pagesActive.forEach(n => n.classList.remove('active'));
    keep && keep.classList.add('active');
  }
  // 菜单项 active 同步
  document.querySelectorAll('.menu-item').forEach(m => {
    m.classList.toggle('active', m.dataset.menu === 'tasks');
  });
  // 默认加载
  try { loadTaskList(); } catch (e) { console.error(e); }
}

function switchSidebar(name) {
  if (!_SIDE_MENU_KEYS.includes(name)) {
    console.warn(`[proc-sidebar] 非法菜单名称：${name}`);
    return;
  }
  const targetPanel = document.getElementById(`proc-tab-${name}`);
  if (!targetPanel) {
    console.warn(`[proc-sidebar] 目标面板 proc-tab-${name} 不存在`);
    return;
  }
  // 严格互斥
  document.querySelectorAll('.proc-top-panel').forEach(p => p.classList.remove('active'));
  targetPanel.classList.add('active');
  document.querySelectorAll('.menu-item').forEach(m => {
    m.classList.toggle('active', m.dataset.menu === name);
  });
  __assertUniqueActive('.proc-top-panel.active', 'proc-top-panel');

  // 各面板首次加载
  if (name === 'tasks') {
    showPage('list');
  } else if (name === 'sparepart') {
    try { initSparePartCategoryFilter(); loadSparePartList(); } catch (e) { console.error(e); }
  } else if (name === 'ledger') {
    try { initLedgerContractFilter(); loadLedger(); } catch (e) { console.error(e); }
  } else if (name === 'supplier') {
    try { loadSupplierList(); } catch (e) { console.error(e); }
  } else if (name === 'contract') {
    try { loadContractList(); } catch (e) { console.error(e); }
  } else if (name === 'mailcc') {
    try { loadMailCCList(); } catch (e) { console.error(e); }
  }
}
// 兼容旧函数名
const switchTopTab = switchSidebar;

function showPage(name) {
  // 严格互斥：一次性清空所有 .page 的 active，再只给目标加（避免出现列表+新建+详情同时显示）
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  let target = null;
  if (name === 'list') {
    target = $('page-proc-list');
    $('procCrumb').textContent = '🛒 备品备件采购询比价';
    try { loadTaskList(); } catch (e) { console.error(e); }
  } else if (name === 'new') {
    target = $('page-proc-new');
    $('procCrumb').textContent = '🛒 备品备件采购询比价 › 新建询价';
    try { loadNewInquiryData(); } catch (e) { console.error(e); }
  } else if (name === 'detail') {
    target = $('page-proc-detail');
    $('procCrumb').textContent = '🛒 备品备件采购询比价 › 任务详情';
  }
  target && target.classList.add('active');
  __assertUniqueActive('.page.active', 'page');
}

function switchDetailTab(tab) {
  // 详情页旧版 Tab1/Tab2/Tab3 已弃用，改垂直 5 步流程条；该函数为兼容性保留，不再操作不存在的 detailTabBase/Quote/Action
  const bs = document.querySelectorAll('.proc-tab');
  if (!bs.length) return;
  bs.forEach(b => b.classList.remove('active'));
  const hit = document.querySelector(`.proc-tab[data-tab="${tab}"]`);
  hit && hit.classList.add('active');
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

// ============ 新建询价（合同核心 → 备件 → 数量 → 资源池供应商全量带出 + 临时供应商） ============
let newContractCache = [];      // 合同下拉数据
let newSparePartCache = [];     // 备件下拉数据
let newSupplierPoolCache = [];  // 资源池全部供应商

async function loadNewInquiryData() {
  // 每个接口独立失败不互卡，单个失败只对应模块显示"暂无…"，避免一个失败 3 个下拉都空
  const errors = [];
  const [contractResp, partResp, supplierResp] = await Promise.all([
    api('/contracts').catch(e => { errors.push(`合同：${e.message}`); return { data: [] }; }),
    api('/spare-parts').catch(e => { errors.push(`备件：${e.message}`); return { data: [] }; }),
    api('/suppliers').catch(e => { errors.push(`供应商：${e.message}`); return { data: [] }; }),
  ]);
  newContractCache = contractResp.data || [];
  newSparePartCache = partResp.data || [];
  newSupplierPoolCache = supplierResp.data || [];
  renderNewContractOptions();
  renderNewPartOptions();
  renderSupplierPool();
  updateDeadlinePreview();
  if (errors.length) {
    toast('部分数据加载失败：' + errors.join('；'), 'err');
  }
}

function renderNewContractOptions() {
  const sel = $('newContract');
  if (!newContractCache.length) {
    sel.innerHTML = '<option value="">暂无合同，请先到 📄合同 菜单新增</option>';
    return;
  }
  sel.innerHTML = '<option value="">请选择合同</option>' +
    newContractCache.map(c => {
      const no = escapeHtml(c.contract_no || '');
      const name = escapeHtml(c.contract_name || no);
      const pm = c.pm_name ? ` · 项目经理：${escapeHtml(c.pm_name)}` : '';
      return `<option value="${no}">${name}　(${no})${pm}</option>`;
    }).join('');
}

function renderNewPartOptions() {
  const sel = $('newPart');
  if (!newSparePartCache.length) {
    sel.innerHTML = '<option value="">暂无备件，请先到 🔧备品备件 菜单新增</option>';
    return;
  }
  sel.innerHTML = '<option value="">请选择备件</option>' +
    newSparePartCache.map(p => {
      // value：优先 spec_model（备件型号）→ 否则 part_code（编码），对应 create_task 的 spare_part_model
      const value_ = p.spec_model || p.part_code || '';
      // label：备件名（规格）/ 品牌 · 编码 —— 即使 spec_model 为空也能看懂
      const partName = escapeHtml(p.part_name || value_ || '未知备件');
      const brand = p.brand ? ` / ${escapeHtml(p.brand)}` : '';
      const code = p.part_code ? ` · <span style="opacity:.55;font-family:var(--mono)">${escapeHtml(p.part_code)}</span>` : '';
      const spec = p.spec_model ? `（${escapeHtml(p.spec_model)}）` : '';
      return `<option value="${escapeHtml(value_)}">${partName}${spec}${brand}${code}</option>`;
    }).join('');
}

function renderSupplierPool() {
  const box = $('supplierList');
  if (!newSupplierPoolCache.length) {
    box.innerHTML = '<div class="empty-tip">资源池暂无供应商，可下方手动新增临时供应商</div>';
    return;
  }
  box.innerHTML = newSupplierPoolCache.map((s, i) => `
    <div class="proc-supplier-row">
      <input type="checkbox" data-idx="${i}" data-pool-id="${escapeHtml(s.id || '')}" checked>
      <span class="sp-name">${escapeHtml(s.name)}</span>
      <span class="sp-email">${escapeHtml(s.email)}</span>
      ${s.id ? `<span class="badge badge-o" style="margin-left:6px;font-size:10px;opacity:.75">#${escapeHtml(s.id)}</span>` : ''}
    </div>
  `).join('');
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
    const contractNo = $('newContract').value;
    if (!contractNo) { toast('请选择合同', 'err'); return; }
    const spare_part_model = $('newPart').value;
    if (!spare_part_model) { toast('请选择备件型号', 'err'); return; }
    const purchase_qty = parseFloat($('newQty').value);
    if (!purchase_qty || purchase_qty <= 0) { toast('请输入有效采购数量', 'err'); return; }
    const emergency_level = $('newEmergency').value;
    // 收集勾选的供应商（资源池 + 临时）
    const supplierRows = document.querySelectorAll('#supplierList .proc-supplier-row');
    const inquiry_supplier_list = [];
    supplierRows.forEach(row => {
      const cb = row.querySelector('input[type="checkbox"]');
      if (!cb.checked) return;
      // 临时供应商：name 不带"临时"标记；资源池：name 直接取文本
      const nameNode = row.querySelector('.sp-name');
      // 去掉"临时"badge 文本
      const name = nameNode.firstChild ? nameNode.firstChild.textContent.trim() : nameNode.textContent.replace('临时', '').trim();
      const email = row.querySelector('.sp-email').textContent.trim();
      const poolId = cb.dataset.poolId || null;
      const entry = { name, email };
      if (poolId) entry.id = poolId;
      inquiry_supplier_list.push(entry);
    });
    if (!inquiry_supplier_list.length) { toast('请至少选择一个询价供应商', 'err'); return; }

    // 后端 create_task 在 inquiry_supplier_list 为空时也会自动从资源池带出，这里已显式传值
    const d = await api('/tasks', 'POST', {
      contract_no: contractNo,
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
  $('newContract').value = '';
  $('newPart').value = '';
  $('newQty').value = '1';
  $('newEmergency').value = '4h';
  $('newSpName').value = '';
  $('newSpEmail').value = '';
  renderSupplierPool();
  updateDeadlinePreview();
}

// ============ 任务详情 ============
let currentDetailTaskId = null;
let currentDetailTask = null;

// 所有详情页渲染的基础工具：严格判空+报错定位，杜绝 Cannot set properties of null
function setHTML(id, html) {
  const el = $(id);
  if (!el) {
    const msg = `[BUG] DOM 元素 #${id} 不存在，请检查 HTML 是否正确写入 id="${id}"`;
    console.error(msg, new Error().stack);
    throw new Error(msg);
  }
  el.innerHTML = html == null ? '' : String(html);
}

function setText(id, text) {
  const el = $(id);
  if (!el) { console.error(`[BUG] DOM 元素 #${id} 不存在 (setText)`); return; }
  el.textContent = text == null ? '' : String(text);
}

// 规范化任务对象（所有字段兜底为默认值，避免 null.map / null.email 炸掉）
function normalizeTask(t0) {
  const t = { ...(t0 || {}) };
  t._op_logs = Array.isArray(t._op_logs) ? t._op_logs : [];
  t.inquiry_supplier_list = Array.isArray(t.inquiry_supplier_list) ? t.inquiry_supplier_list : [];
  t.replied_supplier_quotes = Array.isArray(t.replied_supplier_quotes) ? t.replied_supplier_quotes : [];
  t.no_reply_supplier = Array.isArray(t.no_reply_supplier) ? t.no_reply_supplier : [];
  if (t.selected_supplier && typeof t.selected_supplier === 'object') {
    t.selected_supplier = { name: t.selected_supplier.name || '', email: t.selected_supplier.email || '' };
  } else if (typeof t.selected_supplier === 'string') {
    try { t.selected_supplier = JSON.parse(t.selected_supplier); } catch (_) { t.selected_supplier = {}; }
  } else { t.selected_supplier = {}; }
  t.purchase_qty = Number(t.purchase_qty || 0);
  t.deal_unit_price = Number(t.deal_unit_price || 0);
  t.task_status = t.task_status || '-';
  t.contract_no = t.contract_no || '';
  t.spare_part_model = t.spare_part_model || '';
  return t;
}

// 5 步流程定义（详情页右侧垂直步骤条）
//  - state:  0=待做  1=进行中(current)  2=已完成(done)  3=失败(failed)
//  - title/desc: 这一步做什么
//  - renderAction(t): 进行中时，显示这一步需要操作的 UI（单选/按钮/表单）
//  - renderResult(t): 完成后，显示这一步的结果摘要（含「报价汇总明确列示选中供应商」）
const FLOW_STEPS = [
  {
    key: 'inquiry',
    title: '发起询价 · 邮件通知供应商',
    desc: '创建询价任务后，系统会自动给所有询价供应商发送【备品备件询价】邮件，并告知项目经理。供应商在报价截止时间前回复邮件即可。',
    shouldState(t){
      if (isUnclosed(t.task_status) || t.task_status === '流程闭环') return 2;   // 任何未取消/未失败的任务，询价一定已完成
      return 0;
    },
    renderResult(t){
      const inq = (t.inquiry_supplier_list||[]).map(s=>`· ${escapeHtml(s.name)}  <span style="font-family:var(--mono);color:var(--text2)">${escapeHtml(s.email)}</span>`).join('<br>') || '-';
      return `
        <div class="kv-grid">
          <div><div class="k">任务创建时间</div><div class="v">${t.create_time||'-'}</div></div>
          <div><div class="k">询价邮件</div><div class="v">✅ 已自动发送</div></div>
          <div style="grid-column:1 / -1"><div class="k">询价供应商 (共 ${(t.inquiry_supplier_list||[]).length} 家)</div>
            <div class="v" style="line-height:1.7">${inq}</div>
          </div>
        </div>`;
    },
  },
  {
    key: 'quote',
    title: '供应商报价 · 选型确认',
    desc: '供应商回复报价邮件后，系统会自动解析品牌、型号、报价，并在这里列出所有收到的报价。对比价格/品牌后选中一家供应商，录入实际成交单价并点【确认选型】。',
    shouldState(t){
      if (['已选型确认','供应商发货中','流程闭环'].includes(t.task_status)) return 2;
      if (t.task_status === '收货测试失败') return 2;
      if (['询比价进行中','部分供应商超时','全部供应商超时'].includes(t.task_status)) return 1;
      return 0;
    },
    renderAction(t){
      const replied = t.replied_supplier_quotes || [];
      const noReply = t.no_reply_supplier || [];
      let html = '';
      if (!replied.length) {
        html += '<div class="empty-tip" style="padding:14px">暂无供应商回复报价，请等待供应商回邮（系统每 2 分钟自动轮询一次邮箱）。</div>';
      } else {
        // 解析策略 -> 中文标签（黄色告警）
        const stratTag = q => {
          if (q.is_manual) return '<span class="tag tag-amber" title="已人工录入报价，再次收到邮件复解析不覆盖">✏️ 已人工录入</span>';
          if (!q.parse_strategy || q.parse_strategy.startsWith('P1') || q.parse_strategy.startsWith('P2') || q.parse_strategy.startsWith('P3')) return '<span class="tag tag-green" title="邮件关键字/货币符号/乘法三元组，解析结果置信度高">✅ 高置信</span>';
          if (q.parse_strategy.startsWith('P4')) return '<span class="tag tag-amber" title="邮件仅解析到 1-2 个金额数字，按数量反推，建议人工复核">⚠️ 自动推断</span>';
          if (q.parse_strategy.startsWith('P6') || Number(q.unit_price||0) <= 0) return '<span class="tag tag-red" title="邮件无法自动解析，请点击铅笔图标人工录入报价/货期">🔴 需人工录入</span>';
          return '<span class="tag tag-cyan" title="解析策略：'+escapeHtml(q.parse_strategy||'')+'">ℹ️ '+escapeHtml(q.parse_strategy||'')+'</span>';
        };
        const rowWarn = q => {
          if (q.is_manual) return 'background:rgba(255,193,7,.04)';
          if (!q.parse_strategy || q.parse_strategy.startsWith('P1') || q.parse_strategy.startsWith('P2') || q.parse_strategy.startsWith('P3')) return '';
          return 'background:rgba(255,193,7,.07)';
        };
        html += `<div class="twrap"><table><thead><tr>
          <th style="width:60px">选型</th><th>供应商</th><th>邮箱</th><th>品牌</th><th>型号</th>
          <th style="width:100px;text-align:right">报价(¥)</th>
          <th style="width:90px">货期</th>
          <th style="width:120px">解析</th>
          <th style="width:70px;text-align:center">操作</th>
        </tr></thead><tbody>`;
        replied.forEach((q, i) => {
          html += `<tr style="${rowWarn(q)}">
            <td><input type="radio" name="quoteRadio" value="${i}" ${Number(q.unit_price||0)<=0?'disabled title="该供应商报价未解析或为0，需先人工录入再选型"':''}></td>
            <td>${escapeHtml(q.supplier_name || q.name || '')}</td>
            <td style="font-family:var(--mono);font-size:11px">${escapeHtml(q.email || '')}</td>
            <td>${escapeHtml(q.brand || '')}</td>
            <td>${escapeHtml(q.model || '')}</td>
            <td style="text-align:right;font-weight:600">${Number(q.unit_price||0).toFixed(2)}</td>
            <td style="font-size:11px">${escapeHtml(q.lead_time||'-')}</td>
            <td>${stratTag(q)}</td>
            <td style="text-align:center"><button class="btn btn-o btn-s" title="人工修改报价 / 货期 / 品牌"
              onclick='openManualEditQuote(${JSON.stringify(t.task_id).replace(/"/g,'&quot;')}, ${i})'>✏️ 修改</button></td>
          </tr>`;
        });
        html += '</tbody></table></div>';
        // 若有"需人工录入"的报价 → 顶部红色警示条
        const needManual = replied.some(q => Number(q.unit_price||0) <= 0 || (q.parse_strategy||'').startsWith('P6'));
        if (needManual) {
          html += `<div style="margin-top:12px;padding:10px 12px;background:rgba(248,113,113,.07);border:1px dashed rgba(248,113,113,.4);border-radius:7px;font-size:12px;color:var(--red)">
            🔴 有 ${replied.filter(q=>Number(q.unit_price||0)<=0||(q.parse_strategy||'').startsWith('P6')).length} 家供应商的报价无法自动解析（邮件只回一个数字、或没有关键字），请点击每行右侧 ✏️ 人工录入报价后再确认选型。</div>`;
        }
        html += `
          <div style="margin-top:14px;display:flex;gap:12px;align-items:center;flex-wrap:wrap">
            <div style="display:flex;gap:8px;align-items:center">
              <span style="color:var(--text2);font-size:12px">成交单价：</span>
              <input type="number" id="dealPrice" min="0" step="0.01" placeholder="输入最终成交价" style="max-width:180px;background:var(--bg3);border:1px solid var(--border);padding:6px 10px;border-radius:5px">
              <span style="color:var(--text2);font-size:11px">（通常为选中的报价，可按议价结果手动调整）</span>
            </div>
            <button class="btn btn-c" onclick="submitSelection()">✅ 确认选型</button>
          </div>`;
      }
      if (noReply.length) {
        html += `<div style="margin-top:14px;padding:10px 12px;background:rgba(255,145,0,.06);border:1px dashed rgba(255,145,0,.35);border-radius:7px;font-size:12px;color:var(--orange)">
          ⚠️ 仍有 <b>${noReply.length}</b> 家供应商未回复报价：${noReply.map(s=>escapeHtml(s.name)).join('、')}，临期会自动提醒。</div>`;
      }
      return html;
    },
    renderResult(t){
      // 这里就是「报价汇总明确列示选中的供应商和成交价」的高亮卡
      const sel = t.selected_supplier || {};
      if (!sel || !sel.email) {
        return '<div class="step-result" style="color:var(--red)">状态异常：已选型确认但未记录选中的供应商，请联系管理员。</div>';
      }
      // 从报价列表里找到选中供应商那一条，拿到品牌/型号/报价
      const quotes = t.replied_supplier_quotes || [];
      const q = quotes.find(x => (x.email||'') === (sel.email||'')) || {};
      return `
        <div class="pick-summary">
          <h4>✅ 已确认选型 · 以下为本次采购的报价汇总（选中供应商高亮列示）</h4>
          <div class="kv-grid">
            <div><div class="k">选中供应商</div><div class="v highlight-green">${escapeHtml(sel.name||'')}</div></div>
            <div><div class="k">供应商邮箱</div><div class="v highlight-cyan" style="font-family:var(--mono)">${escapeHtml(sel.email||'')}</div></div>
            <div><div class="k">报价品牌</div><div class="v">${escapeHtml(q.brand||'-')}</div></div>
            <div><div class="k">报价型号</div><div class="v">${escapeHtml(q.model||'-')}</div></div>
            <div><div class="k">供应商原始报价</div><div class="v">${q.unit_price ? '¥ '+Number(q.unit_price).toFixed(2) : '-'}</div></div>
            <div><div class="k">最终成交单价</div><div class="v highlight-red" style="font-size:15px !important">${t.deal_unit_price ? '¥ '+Number(t.deal_unit_price).toFixed(2) : '-'}</div></div>
            <div><div class="k">成交采购量</div><div class="v">${t.purchase_qty || 0} 件</div></div>
            <div><div class="k">成交总额（估算）</div>
              <div class="v highlight-red" style="font-size:15px !important">${t.deal_unit_price && t.purchase_qty ? '¥ '+Number(t.deal_unit_price*t.purchase_qty).toFixed(2) : '-'}</div>
            </div>
            <div style="grid-column:1 / -1"><div class="k">其他参与比价供应商</div>
              <div class="v">共 ${quotes.length} 家报价。${quotes.filter(x=>(x.email||'')!==(sel.email||'')).map(x=>`${escapeHtml(x.supplier_name||x.name||'')} ¥${x.unit_price||0}`).join('；') || '无'}</div>
            </div>
          </div>
        </div>`;
    },
  },
  {
    key: 'confirm',
    title: '采购确认邮件 · 等待供应商备货发货',
    desc: '选型确认后，系统会自动给选中的供应商发【备品备件确认采购】邮件，明确采购内容、数量、成交价，并要求备货后回复发货时间和物流单号。',
    shouldState(t){
      if (['供应商发货中','流程闭环'].includes(t.task_status)) return 2;
      if (t.task_status === '收货测试失败') return 2;
      if (t.task_status === '已选型确认') return 1;
      return 0;
    },
    renderAction(t){
      const sel = t.selected_supplier || {};
      return `
        <div style="padding:12px 14px;background:var(--bg3);border-radius:7px;font-size:12px;color:var(--text2);line-height:1.7;border:1px dashed var(--border)">
          📩 已向 <b style="color:var(--cyan)">${escapeHtml(sel.name||'')} &lt;${escapeHtml(sel.email||'')}&gt;</b> 发送采购确认邮件。<br>
          请等待供应商回复邮件确认发货，系统每 5 分钟轮询一次邮箱并自动解析物流单号。
          <div style="margin-top:6px;color:var(--text3)">（如果供应商已发货但长时间没更新，可手动点页面顶部「🔄 刷新详情」或等下一轮自动轮询）</div>
        </div>`;
    },
    renderResult(t){
      const sel = t.selected_supplier || {};
      return `
        <div class="kv-grid">
          <div><div class="k">采购确认邮件收件人</div><div class="v">${escapeHtml(sel.name||'')} <span style="font-family:var(--mono);color:var(--text2)">&lt;${escapeHtml(sel.email||'')}&gt;</span></div></div>
          <div><div class="k">成交价</div><div class="v" style="font-weight:600">${t.deal_unit_price?'¥ '+Number(t.deal_unit_price).toFixed(2):'-'}</div></div>
          <div style="grid-column:1 / -1"><div class="k">状态</div>
            <div class="v" style="color:var(--green)">✅ 供应商已确认并回复发货信息（见下一步）</div>
          </div>
        </div>`;
    },
  },
  {
    key: 'shipping',
    title: '供应商发货 · 收货与测试',
    desc: '供应商回复发货邮件后，系统自动解析发货时间和物流单号，并同步显示在这里。现场凭单号取货完成硬件测试后，录入测试结果。',
    shouldState(t){
      if (t.task_status === '流程闭环') return 2;
      if (t.task_status === '收货测试失败') return 3;
      if (t.task_status === '供应商发货中') return 1;
      return 0;
    },
    renderAction(t){
      const dl = t.delivery_time;
      const no = t.logistics_no;
      let card = '';
      if (no || dl) {
        card = `
          <div class="supplier-pick-card" style="margin-bottom:12px">
            <h4>📦 发货信息（已自动解析供应商回复邮件）</h4>
            <div class="kv-grid">
              <div><div class="k">发货时间</div><div class="v">${dl||'-'}</div></div>
              <div><div class="k">物流单号</div><div class="v" style="font-family:var(--mono);font-weight:700">${no||'-'}</div></div>
            </div>
          </div>`;
      } else {
        card = `<div style="padding:10px 12px;background:rgba(255,145,0,.05);border:1px dashed rgba(255,145,0,.35);border-radius:7px;font-size:12px;color:var(--orange);margin-bottom:10px">
          ⏳ 物流信息尚未解析到，仍在等待供应商回复发货邮件…</div>`;
      }
      return `${card}
        <div style="padding:12px 14px;background:rgba(0,229,255,.05);border:1px solid rgba(0,229,255,.3);border-radius:7px">
          <h4 style="margin:0 0 6px;color:var(--cyan);font-size:13px">🔧 现场收货与硬件测试</h4>
          <p style="margin:0 0 10px;font-size:12px;color:var(--text2)">现场工程师已收货并完成通电/接口/业务联调测试后，请项目经理在此录入最终测试结果。测试通过自动写台账闭环，测试失败则飞书告警进入人工处置。</p>
          <button class="btn btn-c" onclick="openTestModal()">📝 录入测试结果</button>
        </div>`;
    },
    renderResult(t){
      const failed = t.task_status === '收货测试失败';
      const colorCls = failed ? 'style="color:var(--red)"' : '';
      const titleCls = failed ? 'color:var(--red)' : 'color:var(--green)';
      const resTag = failed ? '❌ 测试失败' : '✅ 测试通过';
      return `
        <div class="kv-grid">
          <div><div class="k">发货时间</div><div class="v">${t.delivery_time||'-'}</div></div>
          <div><div class="k">物流单号</div><div class="v" style="font-family:var(--mono);font-weight:600">${t.logistics_no||'-'}</div></div>
          <div><div class="k">测试结果</div><div class="v" ${colorCls}><b>${resTag}</b></div></div>
          <div><div class="k">处置说明</div><div class="v" style="${titleCls};font-weight:600">${failed?'已飞书告警，人工介入换货/重采。':'已录入测试通过，系统自动写台账 + 发送验收邮件给供应商'}</div></div>
        </div>`;
    },
  },
  {
    key: 'closed',
    title: '台账写入 · 流程闭环',
    desc: '测试通过后，系统自动：① 写入采购业务台账（SQLite 主 + 飞书多维表格副本双写）；② 给供应商发【验收通过】的邮件线程回复；③ 任务正式闭环，不再允许修改。',
    shouldState(t){
      if (t.task_status === '流程闭环') return 2;
      if (t.task_status === '收货测试失败') return 3;
      return 0;
    },
    renderResult(t){
      if (t.task_status === '收货测试失败') {
        return `<div class="step-result" style="background:rgba(255,82,82,.06);border-color:rgba(255,82,82,.4);color:var(--red)">
          ❌ 任务因测试失败未闭环（未写台账，未发验收邮件）。进入人工处置：换货或与供应商协商重新采购，处置完成后可重新录入测试结果。</div>`;
      }
      return `
        <div class="kv-grid">
          <div><div class="k">台账写入</div><div class="v">${t.ledger_written ? '✅ 已写入（SQLite 主 + 飞书多维表格副本）' : '⏳ 写入中…'}</div></div>
          <div><div class="k">验收邮件</div><div class="v">✅ 已 reply_to 报价邮件线程，通知供应商验收通过</div></div>
          <div><div class="k">任务关闭时间</div><div class="v">${t.updated_at||'-'}</div></div>
          <div style="grid-column:1 / -1"><div class="k">闭环摘要</div>
            <div class="v">
              备件 <b>${escapeHtml(t.spare_part_model||'')}</b> × ${t.purchase_qty||0} 件，
              成交供应商 <b style="color:var(--green)">${escapeHtml((t.selected_supplier||{}).name||'')}</b>，
              成交单价 <b style="color:var(--red)">${t.deal_unit_price?'¥ '+Number(t.deal_unit_price).toFixed(2):'-'}</b>，
              验收 <b>${escapeHtml(t.test_result||'-')}</b>，流程正式闭环。
            </div>
          </div>
        </div>`;
    },
  },
];

// 根据任务状态计算每一步的 state
function _stepStates(t){
  const states = FLOW_STEPS.map(s => s.shouldState(t));
  // 取消任务：所有已完成=done，未做的保持灰态
  if (t.task_status === '任务已取消') {
    return states.map(s => s === 2 ? 2 : 0);
  }
  // 失败态（测试失败）：第 4 步 failed
  if (t.task_status === '收货测试失败') {
    return states;
  }
  return states;
}

function _stepTime(t, stepKey){
  const logs = t._op_logs || [];
  const map = {
    inquiry: 'create_task',
    quote: 'confirm_selection',
    confirm: 'confirm_selection',
    shipping: 'update_task_delivery',
    closed: ['write_ledger','input_test_result'],
  };
  const keys = Array.isArray(map[stepKey]) ? map[stepKey] : [map[stepKey]];
  const l = logs.find(x => keys.includes(x.action));
  if (l) return l.action_time;
  if (stepKey === 'inquiry') return t.create_time || '';
  if (stepKey === 'closed' && t.task_status === '流程闭环') return t.updated_at || '';
  return '';
}

async function openDetail(taskId) {
  currentDetailTaskId = taskId;
  showPage('detail');
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  const pd = $('page-proc-detail'); if (pd) pd.classList.add('active');
  const crumb = $('procCrumb'); if (crumb) crumb.textContent = `🛒 备品备件采购询比价 › 任务详情 ${taskId}`;
  setText('detailTaskId', taskId);
  // 先占个位，防止渲染慢时显示错误区域
  setHTML('detailBaseBody', `<div class="empty-tip">加载中…</div>`);
  setHTML('detailStepFlow', `<div class="empty-tip">流程加载中…</div>`);
  setHTML('opLogBody', `<div class="empty-tip">加载中…</div>`);
  await loadDetail();
}

async function loadDetail() {
  try {
    const d = await api(`/tasks/${currentDetailTaskId}`);
    currentDetailTask = normalizeTask(d.data || {});
    const t = currentDetailTask;
    try { setHTML('detailStatusBadge', fmtStatus(t.task_status)); } catch (_) {}
    try { const btn = $('cancelBtn'); if (btn) btn.style.display = isUnclosed(t.task_status) ? '' : 'none'; } catch (_) {}
    renderDetailBase();
    renderStepFlow();
    loadOpLogs();
  } catch (e) {
    console.error('详情页加载失败', e);
    const stack = (e && e.stack) ? String(e.stack).replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\n/g,'<br>') : '';
    const msg = `<div style="padding:10px;border:1px dashed var(--red);border-radius:7px;background:rgba(255,82,82,.06);color:var(--red);line-height:1.7;font-size:12px">
                   加载失败: <b>${escapeHtml(e && e.message || String(e))}</b>
                   ${stack ? `<details style="margin-top:6px;color:var(--text2);"><summary>展开错误堆栈（发给我定位）</summary>${stack}</details>`:''}
                 </div>`;
    try { setHTML('detailBaseBody', msg); } catch (__) {}
    try { setHTML('detailStepFlow', msg); } catch (__) {}
  }
}

// —— 左侧：采购基础信息 ——
function renderDetailBase() {
  const t = currentDetailTask;
  if (!t) return;
  const fields = [
    ['任务ID', `<span style="font-family:var(--mono)">${escapeHtml(t.task_id||'-')}</span>`],
    ['合同号', escapeHtml(t.contract_no||'-')],
    ['备件型号', escapeHtml(t.spare_part_model||'-')],
    ['采购数量', `${t.purchase_qty ?? 0} 件`],
    ['紧急等级', `<span class="badge badge-o">${escapeHtml(t.emergency_level||'-')}</span>`],
    ['报价截止时间', escapeHtml(t.reply_deadline||'-')],
    ['询价供应商数量', `${t.inquiry_supplier_list.length} 家`],
    ['已收到报价', `${t.replied_supplier_quotes.length} 家`],
    ['未回复报价', `${t.no_reply_supplier.length} 家`],
    ['创建人', escapeHtml(t.creator||'-')],
    ['创建时间', escapeHtml(t.create_time||'-')],
    ['更新时间', escapeHtml(t.updated_at||'-')],
  ];
  if (t.task_status === '任务已取消') {
    fields.push(['取消原因', `<span style="color:var(--red)">${escapeHtml(t.cancel_reason||'-')}</span>`]);
  }
  setHTML('detailBaseBody', `
    <div style="display:grid;grid-template-columns:1fr;gap:2px 14px;font-size:13px">
      ${fields.map(([k,v])=>`
        <div style="display:flex;gap:8px;padding:5px 0;border-bottom:1px dashed var(--border)">
          <span style="color:var(--text2);width:110px;flex-shrink:0;font-size:12px">${k}</span>
          <span style="color:var(--text);flex:1;line-height:1.5;font-size:12.5px">${v}</span>
        </div>
      `).join('')}
    </div>
  `);
}

// —— 右侧：5 步垂直流程条（核心，替代原来的 tab 和顶部时间轴）——
function renderStepFlow() {
  const t = currentDetailTask;
  if (!t) return;
  const states = _stepStates(t);
  const clsMap = {0:'', 1:'current', 2:'done', 3:'failed'};
  const canceled = t.task_status === '任务已取消';
  const html = FLOW_STEPS.map((s, i) => {
    const cls = clsMap[states[i]] || '';
    const time = _stepTime(t, s.key);
    let badge = '';
    if (canceled && cls !== 'done') badge = ' <span class="badge badge-o" style="background:rgba(125,141,176,.18);color:var(--text2)">任务已取消，本步骤未执行</span>';
    else if (cls === 'current') badge = ' <span class="badge badge-o" style="background:rgba(0,229,255,.15);color:var(--cyan)">当前步骤 · 需要你操作</span>';
    else if (cls === 'failed') badge = ' <span class="badge badge-o badge-proc-failed">本步骤失败 · 待人工处置</span>';
    let block = '';
    try {
      if (cls === 'current') {
        const act = s.renderAction ? s.renderAction(t) : '';
        block = `<div class="step-action">${act}</div>`;
      } else if (cls === 'done' || cls === 'failed') {
        const res = s.renderResult ? s.renderResult(t) : '';
        block = res ? `<div class="step-result">${res}</div>` : '';
      } else {
        block = `<div style="font-size:11px;color:var(--text3);margin-top:2px">⏳ 待执行：到达上一步后系统自动推进到本步骤。</div>`;
      }
    } catch (err) {
      console.error('渲染步骤失败:', i, s.key, err);
      const st = (err && err.stack) ? String(err.stack).replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\n/g,'<br>') : '';
      block = `<div class="step-result" style="background:rgba(255,82,82,.06);border-color:var(--red);color:var(--red);line-height:1.7;font-size:12px">
                 渲染失败[步骤${i+1}·${s.key}]: <b>${escapeHtml(err.message)}</b>
                 ${st ? `<details style="margin-top:4px;color:var(--text2);"><summary>堆栈</summary>${st}</details>`:''}
               </div>`;
    }
    const timeHtml = time ? `<div style="font-size:11px;color:var(--text2);font-family:var(--mono);margin-bottom:6px">🕒 ${escapeHtml(time)}</div>` : '';
    return `
      <div class="step-card ${cls}">
        <div class="step-title">${s.title} ${badge}</div>
        ${timeHtml}
        <div class="step-desc">${s.desc}</div>
        ${block}
      </div>
    `;
  }).join('');
  setHTML('detailStepFlow', html);
}

async function loadOpLogs() {
  try {
    const d = await api(`/tasks/${currentDetailTaskId}/logs`);
    const logs = Array.isArray(d && d.data) ? d.data : [];
    if (!logs.length) {
      setHTML('opLogBody', '<div class="empty-tip">暂无操作日志</div>');
      return;
    }
    setHTML('opLogBody',
      '<table><thead><tr><th>时间</th><th>操作人</th><th>动作</th><th>备注</th></tr></thead><tbody>' +
      logs.map(l => `<tr>
        <td style="font-size:11px">${escapeHtml(l.action_time||'')}</td>
        <td>${escapeHtml(l.operator||'')}</td>
        <td><span class="badge badge-o">${escapeHtml(l.action||'')}</span></td>
        <td style="font-size:11px">${escapeHtml(l.remark || '')}</td>
      </tr>`).join('') + '</tbody></table>'
    );
  } catch (e) {
    console.error('oplog 加载失败', e);
    const st = (e && e.stack) ? String(e.stack).replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\n/g,'<br>') : '';
    setHTML('opLogBody', `<div style="padding:10px;border:1px dashed var(--red);border-radius:7px;background:rgba(255,82,82,.06);color:var(--red);font-size:12px;line-height:1.7">
                            日志加载失败: <b>${escapeHtml(e.message)}</b>
                            ${st ? `<details style="margin-top:4px;color:var(--text2);"><summary>堆栈</summary>${st}</details>`:''}
                          </div>`);
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

// ============ 人工修改报价弹窗（对应第 2 步 ✏️ 修改按钮） ============
let __mqContext = { taskId: '', replyIndex: -1 };
function openManualEditQuote(taskId, replyIndex) {
  const task = (taskListCache || []).find(t => t.task_id === taskId) || currentDetailTask;
  if (!task) { toast('任务数据未加载，请稍后再试', 'err'); return; }
  const q = (task.replied_supplier_quotes || [])[replyIndex];
  if (!q) { toast('未找到该供应商的报价条目', 'err'); return; }
  __mqContext = { taskId, replyIndex };
  $('manualQuoteTaskHint').textContent =
    `任务 ${taskId} · 备件 ${task.spare_part_model||'-'} × ${task.purchase_qty||0} · 第 ${replyIndex+1} 号供应商`;
  $('mqSupplier').value = `${q.supplier_name || q.name || '-'}  <${q.email || '-'}>`;
  $('mqUnitPrice').value = Number(q.unit_price||0) || '';
  $('mqTotalPrice').value = Number(q.total_price||0) || '';
  $('mqLeadTime').value = q.lead_time || '';
  $('mqBrand').value = q.brand || '';
  $('mqModel').value = q.model || task.spare_part_model || '';
  $('mqNote').value = '';
  $('manualQuoteModal').classList.add('show');
}
function closeManualQuoteModal() {
  $('manualQuoteModal').classList.remove('show');
  __mqContext = { taskId: '', replyIndex: -1 };
}
async function submitManualQuote() {
  const { taskId, replyIndex } = __mqContext;
  if (!taskId || replyIndex < 0) return;
  const unit = parseFloat($('mqUnitPrice').value);
  if (!(unit >= 0) || isNaN(unit)) { toast('请填写有效的成交单价', 'err'); return; }
  const totalRaw = $('mqTotalPrice').value.trim();
  const task = currentDetailTask && currentDetailTask.task_id === taskId ? currentDetailTask
             : (taskListCache || []).find(t => t.task_id === taskId);
  const qty = Number((task && task.purchase_qty) || 0) || 0;
  let total = totalRaw === '' ? null : parseFloat(totalRaw);
  if (total !== null && isNaN(total)) { toast('总价必须是数字', 'err'); return; }
  if (total === null || total === 0) total = Number((unit * qty).toFixed(2));

  const payload = {
    reply_index: replyIndex,
    unit_price: unit,
    total_price: total,
    lead_time: $('mqLeadTime').value.trim(),
    brand: $('mqBrand').value.trim(),
    model: $('mqModel').value.trim(),
    note: $('mqNote').value.trim(),
  };
  try {
    const r = await api(`/tasks/${taskId}/quote/manual`, 'PATCH', payload);
    toast('人工报价已保存，后续邮件复解析不会覆盖');
    closeManualQuoteModal();
    // 更新详情/列表缓存
    if (r && r.data) {
      if (currentDetailTask && currentDetailTask.task_id === taskId) currentDetailTask = r.data;
      if (taskListCache) {
        const idx = taskListCache.findIndex(t => t.task_id === taskId);
        if (idx >= 0) taskListCache[idx] = r.data;
      }
    }
    await loadDetail();
    loadTaskList();
  } catch (e) {
    toast('保存失败: ' + e.message, 'err');
  }
}

// ============ 帮助弹窗（业务系统说明 V1.0 纯业务文档） ============
function openHelp() {
  const el = $('helpOverlay');
  if (!el) return;
  el.classList.add('show');
  document.body.style.overflow = 'hidden';
}
function closeHelp() {
  const el = $('helpOverlay');
  if (!el) return;
  el.classList.remove('show');
  document.body.style.overflow = '';
}
function toggleHelp() { openHelp(); }
// ESC 关闭帮助
document.addEventListener('keydown', function (e) {
  if (e.key === 'Escape') {
    // 优先关最顶层"帮助"，如果其他 Modal 也支持 ESC，这里顺带关（只关 .show 中第一个）
    const help = $('helpOverlay');
    if (help && help.classList.contains('show')) { closeHelp(); return; }
    ['contractModal','contractLinkModal','mailCCModal','testResultModal','cancelModal','detailModal']
      .forEach(id => { const m = $(id); if (m && typeof m.classList !== 'undefined') m.classList.remove('show'); });
  }
});
// 页面加载完成后，如果 URL 里带 ?help=1 则自动弹出帮助（方便分享验收链接）
window.addEventListener('load', function () {
  if (new URLSearchParams(location.search).get('help') === '1') setTimeout(openHelp, 200);
});


// ================================================================
// 【合同主数据 Tab】 list / 搜索 / 新增 / 编辑 / 删除
// ================================================================
let contractTimer = null;

async function loadContractList() {
  const kw = $('contractFilterKeyword').value.trim();
  try {
    const d = await api('/contracts' + (kw ? `?keyword=${encodeURIComponent(kw)}` : ''));
    const rows = d.data || [];
    const body = $('contractTbody');
    if (!rows.length) {
      body.innerHTML = `<tr><td colspan="6" class="empty-tip">${kw ? '没有匹配的合同' : '暂无合同，请点击右上角「＋ 新增合同」'}</td></tr>`;
      return;
    }
    body.innerHTML = rows.map(c => {
      return `
        <tr>
          <td><b>${escapeHtml(c.contract_name || '-')}</b></td>
          <td style="font-family:var(--mono);color:var(--cyan);font-size:12px">${escapeHtml(c.contract_no)}</td>
          <td>${escapeHtml(c.pm_name || '-')}</td>
          <td style="color:#5ed7ff">${escapeHtml(c.pm_email || '-')}</td>
          <td style="font-size:11px;color:var(--text2)">${escapeHtml(c.updated_at || c.created_at || '-')}</td>
          <td>
            <button class="btn btn-o btn-s" onclick="openContractModal(${c.id})">✏️ 编辑</button>
            <button class="btn btn-o btn-s" style="color:var(--red)"
              onclick="confirmDeleteContract(${c.id},${JSON.stringify(c.contract_no).replace(/"/g,'&quot;')})">🗑</button>
          </td>
        </tr>
      `;
    }).join('');
  } catch (e) {
    $('contractTbody').innerHTML =
      `<tr><td colspan="6" class="empty-tip" style="color:var(--red)">加载失败: ${escapeHtml(e.message)}</td></tr>`;
  }
}

function openContractModal(contractId = null) {
  $('ctEditingId').value = contractId || '';
  $('contractModalTitle').textContent = contractId ? '编辑合同' : '新增合同';
  $('ctContractNo').value = '';
  $('ctContractName').value = '';
  $('ctPMName').value = '';
  $('ctPMEmail').value = '';
  $('ctNoChangeHint').style.display = contractId ? 'block' : 'none';
  if (contractId) {
    api(`/contracts/${contractId}`).then(d => {
      const c = d.data;
      $('ctContractNo').value = c.contract_no || '';
      $('ctContractName').value = c.contract_name || '';
      $('ctPMName').value = c.pm_name || '';
      $('ctPMEmail').value = c.pm_email || '';
    }).catch(e => toast('加载合同失败: ' + e.message, 'err'));
  }
  $('contractModal').classList.add('show');
}
function closeContractModal() { $('contractModal').classList.remove('show'); }
async function submitContract() {
  const contract_no = $('ctContractNo').value.trim();
  const contract_name = $('ctContractName').value;
  const pm_name = $('ctPMName').value;
  const pm_email = $('ctPMEmail').value;
  if (!contract_no) { toast('合同编号必填', 'err'); return; }
  try {
    const id = $('ctEditingId').value;
    if (id) {
      await api(`/contracts/${parseInt(id)}`, 'PUT', { contract_no, contract_name, pm_name, pm_email });
      toast('合同已更新');
    } else {
      await api('/contracts', 'POST', { contract_no, contract_name, pm_name, pm_email });
      toast('合同已创建');
    }
    closeContractModal();
    loadContractList();
  } catch (e) { toast('保存失败: ' + e.message, 'err'); }
}
async function confirmDeleteContract(id, no) {
  if (!confirm(`确认删除合同『${no}』?\n\n如果合同已被任务/台账/供应商关联引用，系统会拒绝删除以保留审计线索。`)) return;
  try {
    await api(`/contracts/${id}`, 'DELETE');
    toast('合同已删除');
    loadContractList();
  } catch (e) { toast('删除失败: ' + e.message, 'err'); }
}


// ================================================================
// 【全局抄送 Tab】列表 / 搜索 / 新增(名字+邮箱) / 删除
// ================================================================
let ccTimer = null;

async function loadMailCCList() {
  const kw = $('ccFilterKeyword').value.trim();
  try {
    const d = await api('/mail-cc' + (kw ? `?keyword=${encodeURIComponent(kw)}` : ''));
    const rows = d.data || [];
    $('ccSummary').textContent = `共 ${rows.length} 个抄送邮箱`;
    const body = $('mailCCTbody');
    if (!rows.length) {
      body.innerHTML = `<tr><td colspan="5" class="empty-tip">${kw ? '没有匹配的抄送' : '暂无抄送配置，在上方输入名字+邮箱后点「加入抄送」'}</td></tr>`;
      return;
    }
    body.innerHTML = rows.map((r, idx) => `
      <tr>
        <td>${idx + 1}</td>
        <td><b>${escapeHtml(r.name)}</b></td>
        <td style="color:#5ed7ff">${escapeHtml(r.email)}</td>
        <td style="font-size:11px;color:var(--text2)">${escapeHtml(r.created_at || '')}</td>
        <td>
          <button class="btn btn-o btn-s" style="color:var(--red)"
            onclick="confirmDeleteCC(${r.id},${JSON.stringify(r.name).replace(/"/g,'&quot;')})">移除</button>
        </td>
      </tr>
    `).join('');
  } catch (e) {
    $('mailCCTbody').innerHTML =
      `<tr><td colspan="5" class="empty-tip" style="color:var(--red)">加载失败: ${escapeHtml(e.message)}</td></tr>`;
  }
}

async function submitNewCC() {
  const name = $('ccNewName').value.trim();
  const email = $('ccNewEmail').value.trim();
  if (!name || !email) { toast('名字和邮箱必填', 'err'); return; }
  try {
    await api('/mail-cc', 'POST', { name, email });
    toast('已加入全局抄送');
    $('ccNewName').value = '';
    $('ccNewEmail').value = '';
    loadMailCCList();
  } catch (e) { toast('加入失败: ' + e.message, 'err'); }
}

async function confirmDeleteCC(id, name) {
  if (!confirm(`确认把『${name}』从全局抄送列表移除？移除后不影响已发邮件。`)) return;
  try {
    await api(`/mail-cc/${id}`, 'DELETE');
    toast('已从抄送列表移除');
    loadMailCCList();
  } catch (e) { toast('移除失败: ' + e.message, 'err'); }
}


// ================================================================
// 【需求①】采购台账表格：加载 / 渲染 / 筛选 / 统计
// ================================================================
let ledgerTimer = null;
let ledgerContractCache = null;   // [{contract_no, contract_name, pm_name}]

function formatYuan(v) {
  if (v == null || isNaN(+v)) return '-';
  const n = +v;
  return '¥ ' + n.toLocaleString('zh-CN', {
    minimumFractionDigits: (n === Math.round(n)) ? 2 : 2,
    maximumFractionDigits: 2,
  });
}

// 初始化"合同号筛选"下拉框：从合同主数据表查询所有合同
async function initLedgerContractFilter() {
  const sel = $('ledFilterContract');
  if (ledgerContractCache) return;  // 幂等，初始化一次
  try {
    const d = await api('/contracts');
    const list = d.data || [];
    ledgerContractCache = list;
    sel.innerHTML = '<option value="">全部合同</option>' +
      list.map(m => {
        const name = escapeHtml(m.contract_name || m.contract_no || '未命名合同');
        const no = escapeHtml(m.contract_no);
        const pm = m.pm_name ? ` · ${escapeHtml(m.pm_name)}` : '';
        return `<option value="${no}">${name} · ${no}${pm}</option>`;
      }).join('');
  } catch (e) {
    sel.innerHTML = '<option value="">全部合同</option>';
  }
}

function resetLedgerFilters() {
  $('ledFilterContract').value = '';
  $('ledFilterSupplier').value = '';
  $('ledFilterFrom').value = '';
  $('ledFilterTo').value = '';
  loadLedger();
}

async function loadLedger() {
  const params = new URLSearchParams();
  ['contract_no=' + $('ledFilterContract').value,
   'supplier_name=' + $('ledFilterSupplier').value.trim(),
   'from_date=' + $('ledFilterFrom').value,
   'to_date='   + $('ledFilterTo').value,
  ].forEach(s => {
    const [k, v] = s.split('=');
    if (v) params.append(k, v);
  });
  const qs = params.toString();
  try {
    const d = await api('/ledger' + (qs ? '?' + qs : ''));
    const rows = d.data || [];
    const body = $('ledgerTbody');
    if (!rows.length) {
      body.innerHTML =
        '<tr><td colspan="9" class="empty-tip">暂无闭环采购数据（台账会在测试通过后自动写入）</td></tr>';
    } else {
      body.innerHTML = rows.map(r => `
        <tr>
          <td><b style="color:#7bffbe">${escapeHtml(r.selected_supplier_name || '-')}</b></td>
          <td style="font-size:11.5px">${escapeHtml(r.delivery_time || '-')}</td>
          <td>${escapeHtml(r.spare_part_model || '-')}</td>
          <td class="num">${(r.purchase_qty == null) ? '-' : Number(r.purchase_qty)}</td>
          <td class="num">${formatYuan(r.deal_unit_price)}</td>
          <td class="num" style="color:#ff7089;font-weight:700">${formatYuan(r.total_price)}</td>
          <td style="font-size:11.5px">${escapeHtml(r.acceptance_time || '-')}</td>
          <td style="font-size:11px;line-height:1.7">
            <div style="color:var(--text2)">📄 ${escapeHtml(r.contract_no || '-')}</div>
            <div style="color:var(--text2);font-family:var(--mono)">🆔 ${escapeHtml(r.task_id || '')}</div>
            <div style="color:var(--cyan)">🚚 ${escapeHtml(r.logistics_no || '未填物流号')}</div>
          </td>
          <td style="font-size:11px;line-height:1.6">
            <span class="badge ${r.test_result === '通过' ? 'badge-proc-closed' : r.test_result === '失败' ? 'badge-proc-failed' : 'badge-o'}"
                  style="margin-right:4px">${escapeHtml(r.test_result || '未录入')}</span>
            <div style="color:var(--text2);margin-top:4px">${escapeHtml(r.remark || '-')}</div>
          </td>
        </tr>
      `).join('');
    }
    // 合计行
    const totalQty = rows.reduce((s, r) => s + (+r.purchase_qty || 0), 0);
    const totalAmt = rows.reduce((s, r) => s + (+r.total_price || 0), 0);
    $('ledgerCount').textContent = rows.length;
    const cur = $('ledFilterContract').value;
    const curContract = (ledgerContractCache || []).find(m => m.contract_no === cur);
    $('ledgerContractSummary').textContent = cur
      ? (curContract ? `${curContract.contract_name || cur} · ${cur}` : cur)
      : '全部';
    $('ledgerQtySum').textContent = Number.isFinite(totalQty) ? totalQty : '-';
    $('ledgerAmtSum').textContent = formatYuan(totalAmt);
  } catch (e) {
    $('ledgerTbody').innerHTML =
      `<tr><td colspan="9" class="empty-tip" style="color:var(--red)">台账加载失败: ${escapeHtml(e.message)}</td></tr>`;
  }
}


// ================================================================
// 【需求②】供应商主数据 列表 / 搜索 / 新增 / 编辑 / 删除
// ================================================================
let supplierTimer = null;

async function loadSupplierList() {
  const kw = $('supFilterKeyword').value.trim();
  try {
    const d = await api('/suppliers' + (kw ? `?keyword=${encodeURIComponent(kw)}` : ''));
    const rows = d.data || [];
    const body = $('supplierTbody');
    if (!rows.length) {
      body.innerHTML = `<tr><td colspan="5" class="empty-tip">${kw ? '没有匹配的供应商' : '暂无供应商，请点击右上角「＋ 新增供应商」'}</td></tr>`;
      return;
    }
    body.innerHTML = rows.map(s => {
      return `
        <tr>
          <td><b>${escapeHtml(s.name)}</b><br>
              <span style="font-size:10.5px;color:var(--text2);font-family:var(--mono)">id=${s.id}</span>
          </td>
          <td style="color:#5ed7ff">${escapeHtml(s.email)}</td>
          <td style="font-size:11.5px;line-height:1.7;color:var(--text)">${escapeHtml(s.capability || '-')}</td>
          <td style="font-size:11px;color:var(--text2)">${escapeHtml(s.updated_at || s.created_at || '-')}</td>
          <td>
            <button class="btn btn-o btn-s" onclick="openSupplierModal(${s.id})">✏️ 编辑</button>
            <button class="btn btn-o btn-s" style="color:var(--red)"
                    onclick="confirmDeleteSupplier(${s.id},${JSON.stringify(s.name).replace(/"/g, '&quot;')})">🗑</button>
          </td>
        </tr>`;
    }).join('');
  } catch (e) {
    $('supplierTbody').innerHTML =
      `<tr><td colspan="5" class="empty-tip" style="color:var(--red)">加载失败: ${escapeHtml(e.message)}</td></tr>`;
  }
}

// ---- D1 供应商 新增/编辑 弹窗 ----
function openSupplierModal(supplierId = null) {
  $('supEditingId').value = supplierId || '';
  $('supplierModalTitle').textContent = supplierId ? '编辑供应商' : '新增供应商';
  $('supName').value = '';
  $('supEmail').value = '';
  $('supCapability').value = '';
  if (supplierId) {
    api(`/suppliers/${supplierId}`).then(d => {
      const s = d.data;
      $('supName').value = s.name || '';
      $('supEmail').value = s.email || '';
      $('supCapability').value = s.capability || '';
    }).catch(e => toast('加载供应商失败: ' + e.message, 'err'));
  }
  $('supplierModal').classList.add('show');
}
function closeSupplierModal() { $('supplierModal').classList.remove('show'); }
async function submitSupplier() {
  const name = $('supName').value.trim();
  const email = $('supEmail').value.trim();
  const capability = $('supCapability').value;
  if (!name || !email) { toast('供应商名称和邮箱必填', 'err'); return; }
  try {
    const editingId = $('supEditingId').value;
    if (editingId) {
      await api(`/suppliers/${parseInt(editingId)}`, 'PUT', { name, email, capability });
      toast('供应商已更新');
    } else {
      await api('/suppliers', 'POST', { name, email, capability });
      toast('供应商已创建');
    }
    closeSupplierModal();
    loadSupplierList();
  } catch (e) { toast('保存失败: ' + e.message, 'err'); }
}
async function confirmDeleteSupplier(sid, sname) {
  if (!confirm(`确认删除供应商『${sname}』(id=${sid})？\n\n如果该供应商已出现在任何任务/台账中，系统会拒绝删除以保留审计线索。`)) return;
  try {
    await api(`/suppliers/${sid}`, 'DELETE');
    toast('供应商已删除');
    loadSupplierList();
  } catch (e) { toast('删除失败: ' + e.message, 'err'); }
}


// ============ 备品备件 CRUD ============
let spTimer = null;

async function initSparePartCategoryFilter() {
  try {
    const r = await api('/spare-parts/categories');
    const sel = $('spFilterCategory');
    const current = sel.value;
    sel.innerHTML = '<option value="">全部分类</option>' +
      (r.data || []).map(c => `<option value="${c}">${c}</option>`).join('');
    sel.value = current;
  } catch (e) { console.error(e); }
}

async function loadSparePartList() {
  try {
    const keyword = $('spFilterKeyword')?.value?.trim() || '';
    const category = $('spFilterCategory')?.value || '';
    const params = new URLSearchParams();
    if (keyword) params.set('keyword', keyword);
    if (category) params.set('category', category);
    const r = await api(`/spare-parts?${params}`);
    const tbody = $('sparePartTbody');
    const rows = r.data || [];
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="9" class="empty-tip">暂无备件，点击右上角「＋ 新增备件」添加</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map(r => `
      <tr>
        <td style="font-family:var(--mono);color:var(--cyan);font-size:12.5px">${r.part_code || ''}</td>
        <td style="color:#fff;font-weight:600">${r.part_name || ''}</td>
        <td style="color:var(--text2);font-size:12.5px">${r.spec_model || ''}</td>
        <td>${r.brand || ''}</td>
        <td>${r.unit || '个'}</td>
        <td><span class="tag-sup">${r.category || '通用'}</span></td>
        <td style="color:var(--text2);font-size:12px">${r.remark || ''}</td>
        <td style="color:var(--text2);font-size:11.5px">${r.updated_at || r.created_at || ''}</td>
        <td>
          <button class="btn btn-o btn-s" onclick='editSparePart(${r.id})'>✏️ 编辑</button>
          <button class="btn btn-o btn-s" style="color:var(--red)" onclick='deleteSparePart(${r.id},"${r.part_code}")'>🗑 删除</button>
        </td>
      </tr>
    `).join('');
  } catch (e) {
    $('sparePartTbody').innerHTML = `<tr><td colspan="9" class="empty-tip" style="color:var(--red)">加载失败: ${e.message}</td></tr>`;
  }
}

function openSparePartModal() {
  $('sparePartModalTitle').textContent = '新增备品备件';
  $('spEditingId').value = '';
  $('spCode').value = '';
  $('spName').value = '';
  $('spSpec').value = '';
  $('spBrand').value = '';
  $('spUnit').value = '个';
  $('spCategory').value = '通用';
  $('spRemark').value = '';
  $('sparePartModal').classList.add('show');
}

function closeSparePartModal() { $('sparePartModal').classList.remove('show'); }

async function editSparePart(id) {
  try {
    const r = await api(`/spare-parts/${id}`);
    const d = r.data;
    $('sparePartModalTitle').textContent = `编辑：${d.part_name}`;
    $('spEditingId').value = d.id;
    $('spCode').value = d.part_code || '';
    $('spName').value = d.part_name || '';
    $('spSpec').value = d.spec_model || '';
    $('spBrand').value = d.brand || '';
    $('spUnit').value = d.unit || '个';
    $('spCategory').value = d.category || '通用';
    $('spRemark').value = d.remark || '';
    $('sparePartModal').classList.add('show');
  } catch (e) { toast('加载失败: ' + e.message, 'err'); }
}

async function submitSparePart() {
  const id = $('spEditingId').value;
  const payload = {
    part_code: $('spCode').value.trim(),
    part_name: $('spName').value.trim(),
    spec_model: $('spSpec').value.trim(),
    brand: $('spBrand').value.trim(),
    unit: $('spUnit').value,
    category: $('spCategory').value,
    remark: $('spRemark').value.trim(),
  };
  if (!payload.part_code || !payload.part_name) {
    toast('备件编码和名称必填', 'err'); return;
  }
  try {
    if (id) {
      await api(`/spare-parts/${id}`, 'PUT', payload);
      toast('备件已更新');
    } else {
      await api('/spare-parts', 'POST', payload);
      toast('备件已新增');
    }
    closeSparePartModal();
    loadSparePartList();
  } catch (e) { toast('保存失败: ' + e.message, 'err'); }
}

async function deleteSparePart(id, code) {
  if (!confirm(`确定删除备件 ${code}？`)) return;
  try {
    await api(`/spare-parts/${id}`, 'DELETE');
    toast('已删除');
    loadSparePartList();
  } catch (e) { toast('删除失败: ' + e.message, 'err'); }
}


// ============ 启动 ============
document.addEventListener('DOMContentLoaded', () => {
  initProcUI();
});
