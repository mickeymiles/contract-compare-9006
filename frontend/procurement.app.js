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

// ============ 全局页面 Loading（计数器，嵌套/并行请求不乱闪） ============
let __plStack = 0;
let __plHideTimer = null;
function showPageLoading(text = '加载中...', subText = null) {
  // 如果 hide 有延迟任务，取消（防止刚 show 又被 scheduled hide 秒撤）
  if (__plHideTimer) { clearTimeout(__plHideTimer); __plHideTimer = null; }
  __plStack += 1;
  const el = $('pageLoading');
  if (!el) return;
  $('pageLoadingText').textContent = text;
  const sub = $('pageLoadingSub');
  if (subText) { sub.style.display = ''; sub.textContent = subText; }
  else { sub.style.display = 'none'; }
  el.classList.add('show');
  el.setAttribute('aria-hidden', 'false');
  // 顺便把所有 .btn.disabled-like 效果：通过 pointer-events 已在遮罩层阻挡，不必单独 disable 每颗按钮
}
function hidePageLoading(force = false) {
  if (force) { __plStack = 0; }
  else { __plStack = Math.max(0, __plStack - 1); }
  if (__plStack > 0) return;
  // 延迟 60ms 隐藏：避免"请求极快"时闪一下，同时让用户确认真的点到了
  if (__plHideTimer) clearTimeout(__plHideTimer);
  __plHideTimer = setTimeout(() => {
    const el = $('pageLoading');
    if (!el) return;
    el.classList.remove('show');
    el.setAttribute('aria-hidden', 'true');
    __plHideTimer = null;
  }, 60);
}

/**
 * 统一 API 调用（自动加 Loading）
 * @param {string} path       相对路径，例如 /tasks
 * @param {string} [method='GET']
 * @param {any}    [body=null]      JSON body（自动序列化）
 * @param {string|false|null} [loadingMsg=null]
 *        - 默认 null：GET 不加 Loading（但 GET 的按钮点击场景会在调用方显式加），
 *          POST/PUT/DELETE 加默认文案"提交中..."
 *        - string：自定义文字
 *        - false：强制不加 Loading（例如静默轮询）
 */
async function api(path, method = 'GET', body = null, loadingMsg = null) {
  const showLD = (() => {
    if (loadingMsg === false) return null;
    if (typeof loadingMsg === 'string' && loadingMsg.length > 0) return loadingMsg;
    // 默认规则：写操作一定显示 Loading；读操作默认不显示（避免频繁GET闪遮罩，由调用方在按钮级控制）
    if (method === 'POST' || method === 'PUT' || method === 'PATCH' || method === 'DELETE') {
      const map = {
        POST: '提交中...',
        PUT: '保存中...',
        PATCH: '更新中...',
        DELETE: '删除中...',
      };
      return map[method];
    }
    return null;
  })();
  if (showLD) showPageLoading(showLD);
  try {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    const r = await fetch(API + path, opts);
    const data = await r.json().catch(() => ({ success: false, error: '响应解析失败' }));
    if (!r.ok || data.success === false) {
      throw new Error(data.error || data.message || `HTTP ${r.status}`);
    }
    return data;
  } finally {
    if (showLD) hidePageLoading();
  }
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
const _SIDE_MENU_KEYS = ['tasks', 'ledger', 'mailinquiry', 'sparepart', 'supplier', 'contract', 'mailcc'];

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
  } else if (name === 'mailinquiry') {
    try { loadMailInquiryList(); } catch (e) { console.error(e); }
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
  showPageLoading('加载任务列表...');
  try {
    const path = currentStatusFilter ? `/tasks?status=${encodeURIComponent(currentStatusFilter)}` : '/tasks';
    const d = await api(path, 'GET', null, false);
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
  } finally {
    hidePageLoading();
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
  showPageLoading('正在加载询价表单...');
  try {
    // 每个接口独立失败不互卡，单个失败只对应模块显示"暂无…"，避免一个失败 3 个下拉都空
    const errors = [];
    const [contractResp, partResp, supplierResp] = await Promise.all([
      api('/contracts', 'GET', null, false).catch(e => { errors.push(`合同：${e.message}`); return { data: [] }; }),
      api('/spare-parts', 'GET', null, false).catch(e => { errors.push(`备件：${e.message}`); return { data: [] }; }),
      api('/suppliers', 'GET', null, false).catch(e => { errors.push(`供应商：${e.message}`); return { data: [] }; }),
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
  } finally {
    hidePageLoading();
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
  showPageLoading('正在发起询价并发送邮件，请稍候...');
  try {
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
  } finally {
    hidePageLoading();
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
  // 双流 / 备件明细 / 审批 / 邮件新列兜底
  t.internal_status = t.internal_status || '';
  t.external_status = t.external_status || '';
  t.approval_state = t.approval_state || '';
  t.approval_result = t.approval_result || '';
  t.approver_email = t.approver_email || '';
  t.target_supplier = t.target_supplier || '';
  t.project_no = t.project_no || '';
  t.project_name = t.project_name || '';
  t.brand = t.brand || '';
  t.pn = t.pn || '';
  t.spec = t.spec || '';
  t.condition = t.condition || '';
  t.address = t.address || '';
  t.urgent = t.urgent || '';
  t.inquiry_deadline = t.inquiry_deadline || '';
  t.from_email = t.from_email || '';
  t.latest_ship_time = t.latest_ship_time || '';
  t.source = t.source || '';
  t.mail_archive_json = Array.isArray(t.mail_archive_json) ? t.mail_archive_json : [];
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
      // 建立 email -> 报价 的索引，用于快速查找回复状态
      const replyByEmail = {};
      (t.replied_supplier_quotes || []).forEach(q => {
        if (q && q.email) replyByEmail[String(q.email).toLowerCase().trim()] = q;
      });
      const row_s = s => {
        const tempBadge = (s._is_temp || !s.id) ? `<span class="badge badge-c" style="margin-left:6px">临时</span>` : '';
        const idBadge = s.id ? `<span class="badge badge-o" style="margin-left:4px;font-size:10px;opacity:.75">#${escapeHtml(String(s.id))}</span>` : '';
        let sendBadge = '';
        if (s._sent_ok === true) sendBadge = `<span class="tag tag-green" title="询价邮件已成功发送" style="margin-left:6px">✅ 已发送</span>`;
        else if (s._sent_ok === false) sendBadge = `<span class="tag tag-red" title="询价邮件发送失败：${escapeHtml(s._sent_error||'未知原因')}" style="margin-left:6px">❌ 失败</span>`;
        else sendBadge = `<span class="tag tag-cyan" style="margin-left:6px">⏳ 发送中</span>`;
        // 回复状态徽章（从 replied_supplier_quotes 按 email 查找）
        const emailKey = String(s.email || '').toLowerCase().trim();
        const replyQ = replyByEmail[emailKey];
        let replyBadge = '';
        if (replyQ) {
          const price = Number(replyQ.unit_price || replyQ.total_price || 0);
          const priceStr = price > 0 ? ` ¥${price.toFixed(0)}` : '';
          replyBadge = `<span class="tag tag-green" title="供应商已回复报价${priceStr}" style="margin-left:4px">📨 已回复${priceStr}</span>`;
        } else if (s._sent_ok === true) {
          replyBadge = `<span class="tag tag-cyan" title="已发送询价邮件，等待供应商回复" style="margin-left:4px">⏳ 待回复</span>`;
        }
        return `<li style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
          <span>· ${escapeHtml(s.name)}${tempBadge}${idBadge}</span>
          <span style="font-family:var(--mono);color:var(--text2);font-size:12px">&lt;${escapeHtml(s.email)}&gt;</span>
          ${sendBadge}${replyBadge}
        </li>`;
      };
      const inq = (t.inquiry_supplier_list||[]).length
        ? `<ul style="margin:4px 0 0 0;padding:0;list-style:none;display:flex;flex-direction:column;gap:6px">${
              (t.inquiry_supplier_list||[]).map(row_s).join('')
           }</ul>`
        : '<span style="color:var(--muted)">（无）</span>';
      const okCnt = (t.inquiry_supplier_list||[]).filter(s=>s._sent_ok===true).length;
      const failCnt = (t.inquiry_supplier_list||[]).filter(s=>s._sent_ok===false).length;
      const mailSummary = okCnt===t.inquiry_supplier_list.length
        ? `✅ 已自动发送（${okCnt}/${t.inquiry_supplier_list.length}）`
        : (failCnt>0 ? `⚠️ 部分失败（成功${okCnt} / 失败${failCnt} / 总计${t.inquiry_supplier_list.length}）`
                       : '⏳ 发送中');
      return `
        <div class="kv-grid">
          <div><div class="k">任务创建时间</div><div class="v">${t.create_time||'-'}</div></div>
          <div><div class="k">询价邮件</div><div class="v">${mailSummary}</div></div>
          <div style="grid-column:1 / -1"><div class="k">询价供应商 (共 ${(t.inquiry_supplier_list||[]).length} 家)</div>
            <div class="v">${inq}</div>
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
        // 占位，避免 dealPrice 脚本找不到元素
        html += `<div style="margin-top:14px;display:flex;gap:12px;align-items:center;flex-wrap:wrap">
          <div style="display:flex;gap:8px;align-items:center">
            <span style="color:var(--text2);font-size:12px">成交单价：</span>
            <input type="number" id="dealPrice" min="0" step="0.01" placeholder="输入最终成交价" style="max-width:180px;background:var(--bg3);border:1px solid var(--border);padding:6px 10px;border-radius:5px;color:var(--text)">
          </div>
          <button class="btn btn-c" onclick="submitSelection()">✅ 确认选型</button>
        </div>`;
      } else {
        // —— 自动选中逻辑 ——
        // 筛选有有效报价（unit_price > 0）的条目
        const valid = replied.map((q, i) => ({ i, price: Number(q.unit_price || q.total_price || 0), q }))
                             .filter(x => x.price > 0);
        let autoIdx = -1;
        if (valid.length === 1) {
          autoIdx = valid[0].i;  // 只有一家回复，直接选中
        } else if (valid.length > 1) {
          // 多家回复，选最低价
          valid.sort((a, b) => a.price - b.price);
          autoIdx = valid[0].i;
        } else if (replied.length === 1) {
          autoIdx = 0;  // 只有一家但报价为0（需人工录入的情况）
        }

        // 解析策略 -> 中文标签
        const stratTag = q => {
          if (q.is_manual) return '<span class="tag tag-amber" title="已人工录入报价，再次收到邮件复解析不覆盖">✏️ 已人工录入</span>';
          const ps = String(q.parse_strategy || '');
          const manualKeywords = ['P6','failed','fallback_regex','regex_only','unknown'];
          if (!ps || ps.startsWith('P1') || ps.startsWith('P2') || ps.startsWith('P3')) return '<span class="tag tag-green" title="邮件关键字/货币符号/乘法三元组，解析结果置信度高">✅ 高置信</span>';
          if (ps.startsWith('P4')) return '<span class="tag tag-amber" title="邮件仅解析到 1-2 个金额数字，按数量反推，建议人工复核">⚠️ 自动推断</span>';
          if (manualKeywords.some(k => ps.includes(k)) || Number(q.unit_price||0) <= 0) return '<span class="tag tag-red" title="邮件无法自动解析，请点击铅笔图标人工录入报价/货期">🔴 需人工录入</span>';
          return '<span class="tag tag-cyan" title="解析策略：'+escapeHtml(ps)+'">ℹ️ '+escapeHtml(ps)+'</span>';
        };

        html += `<div class="twrap quote-twrap" data-task-id="${escapeHtml(t.task_id||'')}"><table><thead><tr>
          <th style="width:60px">选型</th><th>供应商</th><th>邮箱</th><th>品牌</th><th>型号</th>
          <th style="width:100px;text-align:right">单价(¥)</th>
          <th style="width:70px;text-align:center">数量</th>
          <th style="width:110px;text-align:right">总价(¥)</th>
          <th style="width:90px">货期</th>
          <th style="width:120px">解析</th>
          <th style="width:180px;text-align:center">操作</th>
        </tr></thead><tbody>`;
        const qty = Number(t.purchase_qty || 1);
        replied.forEach((q, i) => {
          const isAutoSel = i === autoIdx;
          const rowBg = isAutoSel ? 'background:rgba(255,64,129,.10)' : '';
          const priceStyle = isAutoSel ? 'color:var(--red);font-size:16px;font-weight:700' : '';
          const unitPrice = Number(q.unit_price || q.total_price || 0);
          // 若报价里已带 total_price 则用它，否则 unit × qty
          const totalPrice = Number(q.total_price || 0) > 0
            ? Number(q.total_price || 0)
            : unitPrice * qty;
          html += `<tr style="${rowBg}">
            <td><input type="radio" name="quoteRadio" value="${i}" ${isAutoSel ? 'checked' : ''} ${unitPrice<=0?'disabled title="该供应商报价未解析或为0，需先人工录入再选型"':''} onchange="onQuoteRadioChange(this)"></td>
            <td>${escapeHtml(q.supplier_name || q.name || '')}</td>
            <td style="font-family:var(--mono);font-size:11px">${escapeHtml(q.email || '')}</td>
            <td>${escapeHtml(q.brand || '')}</td>
            <td>${escapeHtml(q.model || '')}</td>
            <td style="text-align:right;${priceStyle}">${unitPrice.toFixed(2)}</td>
            <td style="text-align:center">${qty}</td>
            <td style="text-align:right;${priceStyle}">${totalPrice.toFixed(2)}</td>
            <td style="font-size:11px">${escapeHtml(q.lead_time||'-')}</td>
            <td>${stratTag(q)}</td>
            <td style="text-align:center">
              <div style="display:flex;gap:6px;justify-content:center;flex-wrap:nowrap">
                <button class="btn btn-o btn-s btn-quote-edit" data-reply-index="${i}" title="人工修改报价 / 货期 / 品牌" style="padding:5px 10px;font-size:12px">✏️ 修改</button>
                <button class="btn btn-c btn-s btn-quote-orig" data-reply-index="${i}" title="查看供应商回复的邮件原文（只读，可人工检验解析是否准确）" style="padding:5px 10px;font-size:12px">📄 详情</button>
              </div>
            </td>
          </tr>`;
        });
        html += '</tbody></table></div>';

        // 若有"需人工录入"的报价 → 顶部红色警示条
        const ps = qq => String((qq||{}).parse_strategy || '');
        const isManualNeed = q => {
          const ps_ = ps(q);
          return Number(q.unit_price||0) <= 0
            || ['P6','failed','fallback_regex','regex_only','unknown'].some(k => ps_.includes(k));
        };
        const needManual = replied.some(isManualNeed);
        if (needManual) {
          html += `<div style="margin-top:12px;padding:10px 12px;background:rgba(248,113,113,.07);border:1px dashed rgba(248,113,113,.4);border-radius:7px;font-size:12px;color:var(--red)">
            🔴 有 ${replied.filter(isManualNeed).length} 家供应商的报价无法自动解析（邮件只回一个数字、或没有关键字），请点击每行右侧 ✏️ 修改 人工录入报价；点 📄 详情 可查看原始邮件内容后再确认选型。</div>`;
        }

        // 自动填入最低价到成交单价
        const autoPrice = autoIdx >= 0 ? Number(replied[autoIdx]?.unit_price || 0) : '';
        html += `
          <div style="margin-top:14px;display:flex;gap:12px;align-items:center;flex-wrap:wrap">
            <div style="display:flex;gap:8px;align-items:center">
              <span style="color:var(--text2);font-size:12px">成交单价：</span>
              <input type="number" id="dealPrice" min="0" step="0.01" placeholder="输入最终成交价" value="${autoPrice}" style="max-width:180px;background:var(--bg3);border:1px solid var(--border);padding:6px 10px;border-radius:5px;color:var(--text);font-size:14px;font-weight:600">
              <span style="color:var(--text2);font-size:11px">${autoIdx >= 0 ? `（已自动填入最低价 ¥${autoPrice}，可手动调整）` : '（请选择供应商后手动填写）'}</span>
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
      const carrier = t.logistics_carrier;
      let card = '';
      if (no || dl) {
        card = `
          <div class="supplier-pick-card" style="margin-bottom:12px">
            <h4>📦 发货信息（已自动解析供应商回复邮件）</h4>
            <div class="kv-grid">
              <div><div class="k">发货时间</div><div class="v">${dl||'-'}</div></div>
              <div><div class="k">物流单号</div><div class="v" style="font-family:var(--mono);font-weight:700">${no||'-'}</div></div>
              ${carrier ? `<div><div class="k">承运商</div><div class="v">${carrier}</div></div>` : ''}
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
  showPageLoading('打开任务详情...');
  try {
      currentDetailTaskId = taskId;
      showPage('detail');
      document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
      const pd = $('page-proc-detail'); if (pd) pd.classList.add('active');
      const crumb = $('procCrumb'); if (crumb) crumb.textContent = `🛒 备品备件采购询比价 › 任务详情 ${taskId}`;
      setText('detailTaskId', taskId);
      // 先占个位，防止渲染慢时显示错误区域
      setHTML('detailBaseBody', `<div class="empty-tip">加载中…</div>`);
      setHTML('internalFlowBody', `<div class="empty-tip">流程加载中…</div>`);
      setHTML('externalFlowBody', `<div class="empty-tip">流程加载中…</div>`);
      setHTML('quoteSectionBody', `<div class="empty-tip">加载中…</div>`);
      setHTML('opLogBody', `<div class="empty-tip">加载中…</div>`);
      await loadDetail();
  } finally {
    hidePageLoading();
  }
}

async function loadDetail() {
  showPageLoading('加载任务详情...');
  try {
      try {
        const d = await api(`/tasks/${currentDetailTaskId}`);
        currentDetailTask = normalizeTask(d.data || {});
        const t = currentDetailTask;
        try { setHTML('detailStatusBadge', fmtStatus(t.task_status)); } catch (_) {}
        try {
          const fb = $('detailFlowBadge');
          if (fb) fb.innerHTML = `内部 <b class="badge badge-o" style="background:rgba(179,136,255,.16);color:var(--purple)">${escapeHtml(t.internal_status||'R_INIT')}</b>　外部 <b class="badge badge-o" style="background:rgba(0,229,255,.13);color:var(--cyan)">${escapeHtml(t.external_status||'R_SEND')}</b>`;
        } catch (_) {}
        try { const btn = $('cancelBtn'); if (btn) btn.style.display = isUnclosed(t.task_status) ? '' : 'none'; } catch (_) {}
        renderDetailBase();
        renderDualFlow();
        loadOpLogs();
      } catch (e) {
        console.error('详情页加载失败', e);
        const stack = (e && e.stack) ? String(e.stack).replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\n/g,'<br>') : '';
        const msg = `<div style="padding:10px;border:1px dashed var(--red);border-radius:7px;background:rgba(255,82,82,.06);color:var(--red);line-height:1.7;font-size:12px">
                       加载失败: <b>${escapeHtml(e && e.message || String(e))}</b>
                       ${stack ? `<details style="margin-top:6px;color:var(--text2);"><summary>展开错误堆栈（发给我定位）</summary>${stack}</details>`:''}
                     </div>`;
        try { setHTML('detailBaseBody', msg); } catch (__) {}
        try { setHTML('internalFlowBody', msg); } catch (__) {}
        try { setHTML('externalFlowBody', msg); } catch (__) {}
        try { setHTML('quoteSectionBody', msg); } catch (__) {}
      }
  } finally {
    hidePageLoading();
  }
}

// —— 顶部：采购基础信息（双流改造后保留在此，展示三入口统一后的备件明细） ——
function renderDetailBase() {
  const t = currentDetailTask;
  if (!t) return;
  const esc = escapeHtml;
  const srcLabel = (() => {
    const s = String(t.source || '').trim();
    if (s) { const L = s.toLowerCase(); if (L.includes('邮件')) return '邮件'; if (L.includes('agent')) return 'Agent对话'; if (L.includes('页面')) return '页面'; return s; }
    if (t.from_email) return '邮件';
    if ((t.creator||'').toLowerCase().includes('agent')) return 'Agent对话';
    return '页面';
  })();
  const srcCls = srcLabel === '邮件' ? 'badge-proc-shipping' : srcLabel === 'Agent对话' ? 'badge-proc-confirm' : 'badge-proc-running';
  const src = `<span class="badge ${srcCls}">${esc(srcLabel)}</span>`;
  const deadline = t.inquiry_deadline || t.reply_deadline || '-';
  const kv = (k, v) => `<div style="display:flex;gap:8px;padding:6px 0;border-bottom:1px dashed var(--border)">
      <span style="color:var(--text2);width:96px;flex-shrink:0;font-size:11.5px">${k}</span>
      <span style="color:var(--text);flex:1;line-height:1.55;font-size:12.5px">${v}</span>
    </div>`;
  const rows = [
    ['项目号', esc(t.project_no || '-')],
    ['项目名称', esc(t.project_name || '-')],
    ['备件', esc(t.spare_part_model || '-')],
    ['品牌', esc(t.brand || '-')],
    ['PN / 料号', esc(t.pn || '-')],
    ['规格', esc(t.spec || '-')],
    ['成色', esc(t.condition || '-')],
    ['采购数量', `${t.purchase_qty ?? 0} 件`],
    ['收货地址', esc(t.address || '-')],
    ['紧急', `<span class="badge badge-o">${esc(t.urgent || t.emergency_level || '-')}</span>`],
    ['报价截止', esc(deadline)],
    ['来源', src],
    ['合同号', esc(t.contract_no || '-')],
    ['询价供应商', `${t.inquiry_supplier_list.length} 家`],
    ['已收到报价', `${t.replied_supplier_quotes.length} 家`],
    ['未回复报价', `${t.no_reply_supplier.length} 家`],
    ['创建人', esc(t.creator || '-')],
    ['创建 / 更新', `${esc(t.create_time || '-')} / ${esc(t.updated_at || '-')}`],
  ];
  if (t.task_status === '任务已取消') {
    rows.push(['取消原因', `<span style="color:var(--red)">${esc(t.cancel_reason||'-')}</span>`]);
  }
  setHTML('detailBaseBody', `
    <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:2px 24px;font-size:13px">
      ${rows.map(([k,v]) => kv(k,v)).join('')}
    </div>
    <div style="margin-top:10px;font-size:11px;color:var(--text3)">老字段备用：备件型号 = ${esc(t.spare_part_model||'-')}，合同号 = ${esc(t.contract_no||'-')}，紧急等级 = ${esc(t.emergency_level||'-')}</div>
  `);
}

// ============ 双流详情渲染（内部流 / 外部流） ============
// state: 0=未开始, 1=进行中, 2=已完成
function _flowRank(map, v) {
  const m = String(v || '').toUpperCase();
  return map[m] || (v ? 3 : 0);
}
// 内部流进度（R_INIT→R_APPROVAL→R_CLOSED），兼容旧 task_status 推导
function procInternalRank(t) {
  const map = { R_INIT:1, R_APPROVAL:2, R_CLOSED:3 };
  let r = _flowRank(map, t.internal_status);
  const ts = t.task_status || '';
  if (['已选型确认','供应商发货中','流程闭环','收货测试失败'].includes(ts)) r = Math.max(r, 2);
  if (ts === '流程闭环') r = Math.max(r, 3);
  if (['approved','auto_approved'].includes(String(t.approval_state||'').toLowerCase())) r = Math.max(r, 2);
  return Math.max(r, 1);
}
// 外部流进度（R_SEND→R_WAIT_QUOTES→R_DECIDING→R_ORDER→R_WAIT_SHIPPING→R_CLOSED），兼容旧 task_status 推导
function procExternalRank(t) {
  const map = { R_SEND:1, R_WAIT_QUOTES:2, R_DECIDING:3, R_ORDER:4, R_WAIT_SHIPPING:5, R_CLOSED:6 };
  let r = _flowRank(map, t.external_status);
  const ts = t.task_status || '';
  if (['已选型确认','供应商发货中','流程闭环','收货测试失败'].includes(ts)) r = Math.max(r, 3);
  if (['供应商发货中','流程闭环'].includes(ts)) r = Math.max(r, 4);
  if (ts === '流程闭环') r = Math.max(r, 6);
  return Math.max(r, 1);
}
// 审批状态判定
function procApproval(t) {
  const a = String(t.approval_state || '').toLowerCase();
  const result = String(t.approval_result || '').toLowerCase();
  return {
    approved: ['approved','auto_approved'].includes(a),
    rejected: ['rejected','declined','all_rejected'].includes(a) || result.includes('reject'),
  };
}
// 双流步骤卡片
function dualStepCard(st) {
  const cls = { 0:'', 1:'current', 2:'done' }[st.state] || '';
  const badge = st.state === 2 ? ' <span class="badge badge-proc-closed">✅ 已完成</span>'
    : st.state === 1 ? ' <span class="badge badge-o" style="background:rgba(0,229,255,.15);color:var(--cyan)">⏳ 进行中</span>'
    : ' <span class="badge badge-o">未开始</span>';
  const time = st.time ? `<div style="font-size:11px;color:var(--text2);font-family:var(--mono);margin-bottom:6px">🕒 ${escapeHtml(st.time)}</div>` : '';
  return `<div class="step-card ${cls}">
    <div class="step-title">${st.title} ${badge}</div>
    ${time}
    <div class="step-desc">${st.desc}</div>
    ${st.detail ? `<div class="step-result">${st.detail}</div>` : ''}
  </div>`;
}
function _kvrows(rows) {
  return `<div style="display:flex;flex-direction:column;gap:2px">${rows.map(([k,v]) => `
    <div style="display:flex;gap:8px;padding:3px 0;border-bottom:1px dashed var(--border)">
      <span style="color:var(--text2);width:82px;flex-shrink:0;font-size:11px">${k}</span>
      <span style="color:#e6f0ff;flex:1;font-size:12.5px">${v}</span>
    </div>`).join('')}</div>`;
}
// —— 左列：内部流 ——
function renderInternalFlow(t) {
  const r = procInternalRank(t);
  const { approved, rejected } = procApproval(t);
  const closed = t.task_status === '流程闭环' || String(t.internal_status||'').toUpperCase() === 'R_CLOSED';
  const esc = escapeHtml;
  const apprHtml = _kvrows([
    ['审批状态', `<b style="color:${approved?'var(--green)':rejected?'var(--red)':'var(--amber)'}">${esc(t.approval_state||(r>=2?'待审批/审批中':'未发起'))}</b>${t.approval_result?` <span style="color:var(--text2)">(${esc(t.approval_result)})</span>`:''}`],
    ['审批人', esc(t.approver_email||'-')],
    ['目标供应商', esc(t.target_supplier||'-')],
  ]);
  const _u = t.updated_at || t.create_time || '';
  const steps = [
    { title:'R_INIT · 发起询价', desc:'工程师 / 页面 / 邮件任一入口创建任务，内部流程启动。', state: r>=1 ? 2 : 1,
      detail: _kvrows([['创建时间', esc(t.create_time||'-')], ['创建人', esc(t.creator||'-')], ['来源', esc(t.source||'-')]]) },
    { title:'R_APPROVAL · 内部审批', desc:'智能体汇总报价后提交内部审批（自动通过或审批人确认），确定目标供应商。', state: (approved||rejected) ? 2 : (r>=2 ? 1 : 0), detail: apprHtml },
    { title:'R_CLOSED · 内部闭环', desc:'审批通过 + 供货回单后，内部流程正式闭环（可写台账）。', state: closed ? 2 : (approved ? 1 : 0),
      detail: _kvrows([
        ['任务状态', `<b style="color:var(--cyan)">${esc(t.task_status||'-')}</b>`],
        ['台账写入', t.ledger_written ? '✅ 已写入' : '—'],
        ['闭环时间', esc(_u)],
      ]) },
  ];
  return steps.map(dualStepCard).join('');
}
// —— 右列：外部流 ——
function renderExternalFlow(t) {
  const r = procExternalRank(t);
  const esc = escapeHtml;
  const sel = t.selected_supplier || {};
  const quotes = Array.isArray(t.replied_supplier_quotes) ? t.replied_supplier_quotes : [];
  const inq = Array.isArray(t.inquiry_supplier_list) ? t.inquiry_supplier_list : [];
  const supList = inq.length
    ? `<ul style="margin:2px 0 0 0;padding:0;list-style:none;display:flex;flex-direction:column;gap:4px">${inq.map(s => `<li style="font-size:12px">· ${esc(s.name||'')} <span style="font-family:var(--mono);color:var(--text2)">&lt;${esc(s.email||'')}&gt;</span></li>`).join('')}</ul>`
    : '<span style="color:var(--text2)">（无）</span>';
  const quoteRows = quotes.map((q,i) =>
    `<div style="display:flex;align-items:center;gap:8px;padding:3px 0;border-bottom:1px dashed var(--border);font-size:12px">
      <span style="font-weight:600;color:var(--text);flex:1">${esc(q.supplier_name||q.name||'-')}</span>
      <span style="color:var(--green);font-family:var(--mono)">${Number(q.unit_price||q.total_price||0)>0?'¥ '+Number(q.unit_price||q.total_price||0).toFixed(0):'待定'}</span>
    </div>`).join('');
  const steps = [
    { title:'R_SEND · 发询价', desc:'向询价供应商发送【备品备件询价】邮件。', state: r>=1 ? 2 : 1,
      detail: _kvrows([['询价供应商 ('+inq.length+')', supList]]) },
    { title:'R_WAIT_QUOTES · 收集报价', desc:'等待供应商回邮报价，系统自动解析报价单。', state: r>=2 ? 2 : (r>=1 ? 1 : 0),
      detail: _kvrows([
        ['已收到报价', `${quotes.length} 家`],
        ['未回复', `${(Array.isArray(t.no_reply_supplier)?t.no_reply_supplier:[]).length} 家`],
        ['报价截止', esc(t.inquiry_deadline || t.reply_deadline || '-')],
        ['报价明细', quotes.length ? `<div style="display:flex;flex-direction:column">${quoteRows}</div>` : '<span style="color:var(--text2)">暂无</span>'],
      ]) },
    { title:'R_DECIDING · 比价选型', desc:'对比各供应商报价，确定成交供应商与成交价。', state: r>=3 ? 2 : (r===2 ? 1 : 0),
      detail: _kvrows([['选中供应商', sel && sel.name ? `<b style="color:var(--green)">${esc(sel.name)}</b> <span style="font-family:var(--mono);color:var(--text2)">&lt;${esc(sel.email||'')}&gt;</span>` : '—'],
        ['成交单价', t.deal_unit_price ? `¥ ${Number(t.deal_unit_price).toFixed(2)}` : '—']]) },
    { title:'R_ORDER · 下单', desc:'向选中供应商发送采购确认 / 订单。', state: r>=4 ? 2 : (r===3 ? 1 : 0),
      detail: _kvrows([['订单 / 合同', esc(t.contract_no||'-')], ['下单时间', esc((t.updated_at||'').slice(0,16))||'-']]) },
    { title:'R_WAIT_SHIPPING · 待发货 / 收货', desc:'供应商发货后回填发货时间与物流单号。', state: r>=5 ? 2 : (r===4 ? 1 : 0),
      detail: _kvrows([
        ['发货时间', esc(t.delivery_time || t.latest_ship_time || (r>=5?'待填':'—'))],
        ['物流单号', t.logistics_no ? `<b style="color:#5ed7ff;font-family:var(--mono)">${esc(t.logistics_no)}</b>` : '—'],
        ['测试结果', esc(t.test_result||'待测试')],
      ]) },
  ];
  return steps.map(dualStepCard).join('');
}
// —— 供应商报价与选型区（复用 FLOW_STEPS 的报价步骤渲染） ——
function renderQuoteSection(t) {
  const ts = t.task_status || '';
  const esc = escapeHtml;
  if (ts === '任务已取消') {
    return `<div class="empty-tip" style="padding:14px">任务已取消，不开放报价与选型操作。</div>`;
  }
  let html = '';
  try {
    const qs = FLOW_STEPS.find(s => s.key === 'quote');
    const selDone = ['已选型确认','供应商发货中','流程闭环','收货测试失败'].includes(ts);
    if (selDone) {
      html = qs.renderResult(t);
    } else {
      html = qs.renderAction(t);
    }
  } catch (e) {
    html = `<div style="padding:10px;border:1px dashed var(--red);border-radius:7px;background:rgba(255,82,82,.06);color:var(--red);font-size:12px">报价区渲染失败: ${esc(e && e.message || String(e))}</div>`;
  }
  // 现场测试入口保留（供应商发货中 / 收货测试失败时）
  if (ts === '供应商发货中' || ts === '收货测试失败') {
    html += `<div style="margin-top:12px;padding:12px 14px;background:rgba(0,229,255,.05);border:1px solid rgba(0,229,255,.3);border-radius:7px">
      <h4 style="margin:0 0 6px;color:var(--cyan);font-size:13px">🔧 现场收货与硬件测试</h4>
      <p style="margin:0 0 10px;font-size:12px;color:var(--text2)">现场工程师收货并完成通电/联调测试后，在此录入最终测试结果。</p>
      <button class="btn btn-c" onclick="openTestModal()">📝 录入测试结果</button>
    </div>`;
  }
  return html;
}
// —— 详情双流总渲染 ——
function renderDualFlow() {
  const t = currentDetailTask;
  if (!t) return;
  try { setHTML('internalFlowBody', renderInternalFlow(t)); } catch(e) { setHTML('internalFlowBody', '<div class="empty-tip">内部流渲染失败</div>'); }
  try { setHTML('externalFlowBody', renderExternalFlow(t)); } catch(e) { setHTML('externalFlowBody', '<div class="empty-tip">外部流渲染失败</div>'); }
  try { setHTML('quoteSectionBody', renderQuoteSection(t)); } catch(e) { setHTML('quoteSectionBody', '<div class="empty-tip">报价区渲染失败</div>'); }
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
  showPageLoading('加载操作日志...');
  try {
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
  } finally {
    hidePageLoading();
  }
}

async function submitSelection() {
  showPageLoading('正在确认成交并发送通知...');
  try {
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
  } finally {
    hidePageLoading();
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
  showPageLoading('正在提交验收结果...');
  try {
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
  } finally {
    hidePageLoading();
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
  showPageLoading('正在取消任务...');
  try {
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
  } finally {
    hidePageLoading();
  }
}

// ============ 供应商报价行 操作列 事件委托（修改 / 详情） ============
// 避免用内联 onclick + JSON.stringify 拼接 task_id 时，引号/特殊字符导致 JS 语法错误从而"按钮无反应"。
document.addEventListener('click', (ev) => {
  const el = ev && ev.target;
  if (!el || !el.classList) return;
  let tg = el.closest('.btn-quote-edit') || el.closest('.btn-quote-orig');
  if (!tg) return;
  const wrap = tg.closest('.quote-twrap');
  const taskId = (wrap && wrap.getAttribute('data-task-id')) || currentDetailTaskId;
  const replyIndex = parseInt(tg.getAttribute('data-reply-index') || '-1', 10);
  if (!taskId || replyIndex < 0) { toast('报价数据缺失，请刷新页面后重试', 'err'); return; }
  ev.preventDefault();
  ev.stopPropagation();
  if (el.closest('.btn-quote-edit')) openManualEditQuote(taskId, replyIndex);
  else if (el.closest('.btn-quote-orig')) openQuoteOrig(taskId, replyIndex);
}, true);

// ============ 报价单选联动成交单价 + 行高亮 ============
function onQuoteRadioChange(radioEl) {
  if (!radioEl) return;
  const idx = parseInt(radioEl.value, 10);
  const task = currentDetailTask;
  const quotes = (task && task.replied_supplier_quotes) || [];
  const q = quotes[idx];
  const price = Number(q?.unit_price || q?.total_price || 0);

  // 1. 更新成交单价输入框
  const deal = $('dealPrice');
  if (deal && price > 0) {
    deal.value = price.toFixed(2);
  }

  // 2. 高亮选中行（红色加大字体）
  // 列索引: 0=单选, 1=供应商, 2=邮箱, 3=品牌, 4=型号, 5=单价, 6=数量, 7=总价, 8=货期, 9=解析, 10=操作
  const PRICE_COL = 5;
  const TOTAL_COL = 7;
  const tbody = radioEl.closest('tbody');
  if (tbody) {
    tbody.querySelectorAll('tr').forEach(tr => {
      tr.style.background = '';
      tr.querySelectorAll('td').forEach((td, ci) => {
        if (ci === PRICE_COL || ci === TOTAL_COL) {
          td.style.color = '';
          td.style.fontSize = '';
          td.style.fontWeight = '';
        }
      });
    });
    const tr = radioEl.closest('tr');
    if (tr) {
      tr.style.background = 'rgba(255,64,129,.10)';
      const tds = tr.querySelectorAll('td');
      const qty = Number(currentDetailTask?.purchase_qty || 1);
      const total = Number(q?.total_price || 0) > 0
        ? Number(q.total_price)
        : price * qty;
      if (tds[PRICE_COL]) {
        tds[PRICE_COL].style.color = 'var(--red)';
        tds[PRICE_COL].style.fontSize = '16px';
        tds[PRICE_COL].style.fontWeight = '700';
      }
      if (tds[TOTAL_COL]) {
        tds[TOTAL_COL].style.color = 'var(--red)';
        tds[TOTAL_COL].style.fontSize = '16px';
        tds[TOTAL_COL].style.fontWeight = '700';
        tds[TOTAL_COL].textContent = total.toFixed(2);
      }
    }
  }

  // 3. 更新成交单价说明文字
  const hintEl = document.querySelector('.step-action');
  if (hintEl && price > 0) {
    const allSpans = hintEl.querySelectorAll('span');
    for (const sp of allSpans) {
      if (sp.textContent && sp.textContent.includes('已自动填入')) {
        sp.textContent = `（已选择 ${q?.supplier_name || q?.name || ''} 报价 ¥${price}，可手动调整）`;
        break;
      }
    }
  }
}

// ============ 人工修改报价弹窗（对应第 2 步 ✏️ 修改按钮） ============
let __mqContext = { taskId: '', replyIndex: -1 };
function openManualEditQuote(taskId, replyIndex) {
  if (!taskId || replyIndex == null || replyIndex < 0) { toast('参数错误，请刷新后重试', 'err'); return; }
  const task = (currentDetailTask && currentDetailTask.task_id === taskId) ? currentDetailTask
             : (taskListCache || []).find(t => t.task_id === taskId);
  if (!task) {
    const msg = `任务 ${taskId} 详情数据未加载，可能是页面缓存失效`;
    console.warn('[openManualEditQuote]', msg, { taskListCacheLen: (taskListCache||[]).length, currentDetailTaskId, currentDetailTask: !!currentDetailTask });
    toast(`${msg}，请先点击任务卡片的【查看】打开详情后再操作`, 'err');
    return;
  }
  const arr = Array.isArray(task.replied_supplier_quotes) ? task.replied_supplier_quotes : [];
  const q = arr[replyIndex];
  if (!q) { console.warn('[openManualEditQuote] 报价条目不存在', { taskId, replyIndex, arrLen: arr.length }); toast('未找到该供应商的报价条目，请刷新页面', 'err'); return; }
  __mqContext = { taskId, replyIndex };
  try {
    $('manualQuoteTaskHint').textContent =
      `任务 ${taskId} · 备件 ${task.spare_part_model||'-'} × ${task.purchase_qty||0} · 第 ${replyIndex+1} 号供应商`;
    $('mqSupplier').value = `${q.supplier_name || q.name || '-'}  <${q.email || '-'}>`;
    $('mqUnitPrice').value = Number(q.unit_price||0) || '';
    $('mqTotalPrice').value = Number(q.total_price||0) || '';
    $('mqLeadTime').value = q.lead_time || '';
    $('mqBrand').value = q.brand || '';
    $('mqModel').value = q.model || task.spare_part_model || '';
    $('mqNote').value = q.note || '';
    $('manualQuoteModal').classList.add('show');
  } catch (err) {
    console.error('[openManualEditQuote] 打开弹窗失败', err);
    toast(`打开弹窗失败: ${err && err.message ? err.message : String(err)}`, 'err');
  }
}
function closeManualQuoteModal() {
  const m = $('manualQuoteModal');
  if (m) m.classList.remove('show');
  __mqContext = { taskId: '', replyIndex: -1 };
}
async function submitManualQuote() {
  showPageLoading('保存人工录入的报价...');
  try {
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
  } finally {
    hidePageLoading();
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
  showPageLoading('加载合同列表...');
  try {
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
          const recvInfo = (c.receiver_name || c.receiver_address || c.receiver_phone)
            ? `<div style="font-size:11px;color:var(--text2);margin-top:3px">📦 ${escapeHtml([c.receiver_address, c.receiver_name, c.receiver_phone].filter(Boolean).join(' · '))}</div>`
            : '';
          return `
            <tr>
              <td><b>${escapeHtml(c.contract_name || '-')}</b></td>
              <td style="font-family:var(--mono);color:var(--cyan);font-size:12px">${escapeHtml(c.contract_no)}</td>
              <td>${escapeHtml(c.pm_name || '-')}</td>
              <td style="color:#5ed7ff">${escapeHtml(c.pm_email || '-')}${recvInfo}</td>
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
  } finally {
    hidePageLoading();
  }
}

function openContractModal(contractId = null) {
  $('ctEditingId').value = contractId || '';
  $('contractModalTitle').textContent = contractId ? '编辑合同' : '新增合同';
  $('ctContractNo').value = '';
  $('ctContractName').value = '';
  $('ctPMName').value = '';
  $('ctPMEmail').value = '';
  $('ctReceiverName').value = '';
  $('ctReceiverPhone').value = '';
  $('ctReceiverAddress').value = '';
  $('ctNoChangeHint').style.display = contractId ? 'block' : 'none';
  if (contractId) {
    api(`/contracts/${contractId}`).then(d => {
      const c = d.data;
      $('ctContractNo').value = c.contract_no || '';
      $('ctContractName').value = c.contract_name || '';
      $('ctPMName').value = c.pm_name || '';
      $('ctPMEmail').value = c.pm_email || '';
      $('ctReceiverName').value = c.receiver_name || '';
      $('ctReceiverPhone').value = c.receiver_phone || '';
      $('ctReceiverAddress').value = c.receiver_address || '';
    }).catch(e => toast('加载合同失败: ' + e.message, 'err'));
  }
  $('contractModal').classList.add('show');
}
function closeContractModal() { $('contractModal').classList.remove('show'); }
async function submitContract() {
  showPageLoading('保存合同信息...');
  try {
      const contract_no = $('ctContractNo').value.trim();
      const contract_name = $('ctContractName').value;
      const pm_name = $('ctPMName').value;
      const pm_email = $('ctPMEmail').value;
      const receiver_name = $('ctReceiverName').value;
      const receiver_phone = $('ctReceiverPhone').value;
      const receiver_address = $('ctReceiverAddress').value;
      if (!contract_no) { toast('合同编号必填', 'err'); return; }
      try {
        const id = $('ctEditingId').value;
        const payload = { contract_no, contract_name, pm_name, pm_email, receiver_name, receiver_phone, receiver_address };
        if (id) {
          await api(`/contracts/${parseInt(id)}`, 'PUT', payload);
          toast('合同已更新');
        } else {
          await api('/contracts', 'POST', payload);
          toast('合同已创建');
        }
        closeContractModal();
        loadContractList();
      } catch (e) { toast('保存失败: ' + e.message, 'err'); }
  } finally {
    hidePageLoading();
  }
}
async function confirmDeleteContract(id, no) {
  showPageLoading('删除合同...');
  try {
      if (!confirm(`确认删除合同『${no}』?\n\n如果合同已被任务/台账/供应商关联引用，系统会拒绝删除以保留审计线索。`)) return;
      try {
        await api(`/contracts/${id}`, 'DELETE');
        toast('合同已删除');
        loadContractList();
      } catch (e) { toast('删除失败: ' + e.message, 'err'); }
  } finally {
    hidePageLoading();
  }
}


// ================================================================
// 【全局抄送 Tab】列表 / 搜索 / 新增(名字+邮箱) / 删除
// ================================================================
let ccTimer = null;

async function loadMailCCList() {
  showPageLoading('加载抄送列表...');
  try {
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
  } finally {
    hidePageLoading();
  }
}

async function submitNewCC() {
  showPageLoading('新增抄送人...');
  try {
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
  } finally {
    hidePageLoading();
  }
}

async function confirmDeleteCC(id, name) {
  showPageLoading('删除抄送人...');
  try {
      if (!confirm(`确认把『${name}』从全局抄送列表移除？移除后不影响已发邮件。`)) return;
      try {
        await api(`/mail-cc/${id}`, 'DELETE');
        toast('已从抄送列表移除');
        loadMailCCList();
      } catch (e) { toast('移除失败: ' + e.message, 'err'); }
  } finally {
    hidePageLoading();
  }
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
  showPageLoading('加载采购台账...');
  try {
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
  } finally {
    hidePageLoading();
  }
}


// ================================================================
// 【需求②】供应商主数据 列表 / 搜索 / 新增 / 编辑 / 删除
// ================================================================
let supplierTimer = null;

async function loadSupplierList() {
  showPageLoading('加载供应商列表...');
  try {
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
  } finally {
    hidePageLoading();
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
  showPageLoading('保存供应商信息...');
  try {
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
  } finally {
    hidePageLoading();
  }
}
async function confirmDeleteSupplier(sid, sname) {
  showPageLoading('删除供应商...');
  try {
      if (!confirm(`确认删除供应商『${sname}』(id=${sid})？\n\n如果该供应商已出现在任何任务/台账中，系统会拒绝删除以保留审计线索。`)) return;
      try {
        await api(`/suppliers/${sid}`, 'DELETE');
        toast('供应商已删除');
        loadSupplierList();
      } catch (e) { toast('删除失败: ' + e.message, 'err'); }
  } finally {
    hidePageLoading();
  }
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
  showPageLoading('加载备件列表...');
  try {
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
            <td>${r.condition || '-'}</td>
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
  } finally {
    hidePageLoading();
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
  $('spCondition').value = '';
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
    $('spCondition').value = d.condition || '';
    $('spRemark').value = d.remark || '';
    $('sparePartModal').classList.add('show');
  } catch (e) { toast('加载失败: ' + e.message, 'err'); }
}

async function submitSparePart() {
  showPageLoading('保存备件信息...');
  try {
      const id = $('spEditingId').value;
      const payload = {
        part_code: $('spCode').value.trim(),
        part_name: $('spName').value.trim(),
        spec_model: $('spSpec').value.trim(),
        brand: $('spBrand').value.trim(),
        unit: $('spUnit').value,
        category: $('spCategory').value,
        condition: $('spCondition').value.trim(),
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
  } finally {
    hidePageLoading();
  }
}

async function deleteSparePart(id, code) {
  showPageLoading('删除备件...');
  try {
      if (!confirm(`确定删除备件 ${code}？`)) return;
      try {
        await api(`/spare-parts/${id}`, 'DELETE');
        toast('已删除');
        loadSparePartList();
      } catch (e) { toast('删除失败: ' + e.message, 'err'); }
  } finally {
    hidePageLoading();
  }
}


// ============ 报价邮件原文详情弹窗（对应操作列 📄 详情按钮） ============
let __qoContext = { taskId: '', replyIndex: -1, rawText: '' };
function __qoParseTagHTML(q) {
  const ps = String((q && q.parse_strategy) || '');
  if (q && q.is_manual) return `<span class="tag tag-amber">✏️ 已人工录入</span>`;
  if (!ps) return `<span class="tag tag-green">✅ 自动解析（高置信）</span>`;
  if (ps.includes('P1') || ps.includes('P2') || ps.includes('P3')) return `<span class="tag tag-green">✅ 自动解析（${escapeHtml(ps)}）</span>`;
  if (ps.includes('P4') || ps.includes('P5')) return `<span class="tag tag-amber">⚠️ 自动推断（${escapeHtml(ps)}）</span>`;
  if (['P6','failed','fallback_regex','regex_only','unknown'].some(k => ps.includes(k)))
    return `<span class="tag tag-red">🔴 解析失败，需人工录入（${escapeHtml(ps)}）</span>`;
  if (ps === 'manual_entry') return `<span class="tag tag-amber">✏️ 已人工录入</span>`;
  if (ps.startsWith('llm')) return `<span class="tag tag-cyan">🧠 LLM 解析（${escapeHtml(ps)}）</span>`;
  return `<span class="tag tag-cyan">ℹ️ ${escapeHtml(ps)}</span>`;
}
function openQuoteOrig(taskId, replyIndex) {
  if (!taskId || replyIndex == null || replyIndex < 0) { toast('参数错误，请刷新后重试', 'err'); return; }
  const task = (currentDetailTask && currentDetailTask.task_id === taskId) ? currentDetailTask
             : (taskListCache || []).find(t => t.task_id === taskId);
  if (!task) {
    const msg = `任务 ${taskId} 详情数据未加载`;
    console.warn('[openQuoteOrig]', msg);
    toast(`${msg}，请先点击任务卡片的【查看】打开详情后再操作`, 'err');
    return;
  }
  const arr = Array.isArray(task.replied_supplier_quotes) ? task.replied_supplier_quotes : [];
  const q = arr[replyIndex];
  if (!q) { toast('未找到该供应商的报价条目，请刷新页面', 'err'); return; }
  __qoContext = {
    taskId, replyIndex,
    rawText: String(q.raw_reply_excerpt || q.raw_reply || q.raw_mail_body || q.email_text || q.raw_body || '（该条回复没有保存原文，可能为旧数据或系统创建的手动报价条目）'),
  };
  window.__lastQuoteCtx = { taskId, replyIndex }; // 供弹窗底部"继续：人工录入报价"按钮跳转到修改弹窗
  try {
    $('quoteOrigHint').textContent = `任务 ${taskId} · 备件 ${task.spare_part_model||'-'} × ${task.purchase_qty||0} · 第 ${replyIndex+1} 号供应商`;
    $('qoParseTag').innerHTML = __qoParseTagHTML(q);
    setText('qoSupplier', `${q.supplier_name || q.name || '-'}  <${q.email || '-'}>`);
    setText('qoEmail', q.email || '-');
    setText('qoReplyTime', q.reply_time || '-');
    const mid = String(q.message_id || q.msg_id || q.in_reply_to || '');
    const midEl = $('qoMsgId');
    midEl.textContent = mid || '-';
    midEl.setAttribute('title', mid || '');
    setText('qoParseNote', String(q.parse_note || '（该条报价无解析说明）'));
    setText('qoRawText', __qoContext.rawText);
    $('quoteOrigModal').classList.add('show');
  } catch (err) {
    console.error('[openQuoteOrig] 打开详情失败', err);
    toast(`打开详情失败: ${err && err.message ? err.message : String(err)}`, 'err');
  }
}
function closeQuoteOrigModal() {
  const m = $('quoteOrigModal');
  if (m) m.classList.remove('show');
  __qoContext = { taskId: '', replyIndex: -1, rawText: '' };
}
function __copyQuoteOrig() {
  const text = __qoContext.rawText || '';
  if (!text) { toast('没有可复制的内容', 'err'); return; }
  const done = (ok) => {
    if (ok) toast(`✅ 已复制 ${text.length} 字符原文到剪贴板`, 'ok');
    else toast('复制失败，请手动全选复制', 'err');
  };
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(() => done(true), () => done(false));
      return;
    }
  } catch (_) { /* ignore */ }
  try {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.left = '-99999px';
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(ta);
    done(ok);
  } catch (e) { done(false); }
}


// ============ 备件邮件询价（只读观察，neuops 引擎写入 mail_inquiry_task） ============
let miTimer = null;              // 搜索防抖
let currentMailTaskId = null;    // 当前选中的邮件询价任务
let currentMailTask = null;      // 当前详情数据

function mailInqLevelBadge(v, label) {
  const s = String(v || '');
  if (!s) return '';
  const L = s.toUpperCase();
  let cls = 'badge-o';
  if (L === 'SENDING_B' || L === 'R_SEND') cls = 'badge-proc-running';
  else if (L === 'R_WAIT_QUOTES' || L === 'R_DECIDING' || L === 'DECIDING_LOWEST' || L === 'DECIDING') cls = 'badge-proc-timeout-p';
  else if (L === 'R_ORDER' || L === 'ORDERING') cls = 'badge-proc-confirm';
  else if (L === 'R_WAIT_SHIPPING' || L === 'SHIPPING') cls = 'badge-proc-shipping';
  else if (L === 'DONE' || L.includes('CLOSED')) cls = 'badge-proc-closed';
  else if (L.includes('REJECT') || L.includes('ABORT')) cls = 'badge-proc-canceled';
  return `<span class="badge ${cls}">${escapeHtml(s)}${label ? ' · ' + escapeHtml(label) : ''}</span>`;
}

// 5 步双流状态判定：返回值 2=已完成 / 1=进行中 / 0=未开始
// 依据 external_status（外部供应商流）线性推进 + internal_status（内部审批/结算流）+ approval_state
function mailStepStates(t) {
  const extUp = String(t.external_status || '').toUpperCase();
  const intUp = String(t.internal_status || '').toUpperCase();
  const appr = String(t.approval_state || '').toLowerCase();
  const status = String(t.status || '').toUpperCase();
  const EX = {
    R_SEND:1, SENDING_B:1,
    R_WAIT_QUOTES:2, WAITING_QUOTES:2, COLLECTING_QUOTES:2,
    R_DECIDING:3, DECIDING_LOWEST:3, DECIDING:3,
    R_ORDER:4, ORDERING:4,
    R_WAIT_SHIPPING:5, SHIPPING:5,
    R_CLOSED:6, DONE:6,
  };
  let extRank = EX[extUp] || (extUp ? 3 : 0); // 未知外部状态保守按『报价已收集』
  const closedFinal = extRank >= 6 || status === 'DONE' || extUp.includes('CLOSED');
  const approved = ['approved', 'auto_approved'].includes(appr);
  const rejected = ['rejected', 'declined', 'all_rejected'].includes(appr)
    || String(t.approval_result || '').toLowerCase().includes('reject');
  return {
    ar: [
      extRank >= 1 ? 2 : 1,                                                      // 1 发起报价
      extRank >= 3 ? 2 : (extRank >= 2 ? 1 : 0),                                 // 2 报价
      (approved || rejected) ? 2 : (extRank >= 3 || intUp.includes('APPROVAL') ? 1 : 0), // 3 审批
      extRank >= 5 ? 2 : (extRank === 4 ? 1 : 0),                                // 4 订货
      (closedFinal && intUp.includes('CLOSED')) ? 2 : (extRank >= 5 ? 1 : 0),    // 5 回单/结算
    ],
    closedFinal, approved, rejected, extRank, intUp, extUp,
  };
}

function renderMailStepper(t, st) {
  const clsMap = { 2: 'done', 1: 'current', 0: 'pending' };
  const DEFS = [
    { title: '发起报价', in: '内部：接收询价请求', ex: '外部：R_SEND 发询价邮件' },
    { title: '报价',     in: '',                   ex: '外部：WAIT_QUOTES→DECIDING 收集并算最低价' },
    { title: '审批',     in: '内部：R_APPROVAL 审批', ex: '外部：目标供应商待定' },
    { title: '订货',     in: '内部：审批通过定目标', ex: '外部：R_ORDER 发订货单' },
    { title: '回单/结算', in: '内部：R_CLOSED 确认·结算', ex: '外部：WAIT_SHIPPING→CLOSED 收单号' },
  ];
  return st.ar.map((s, i) => {
    const def = DEFS[i];
    const dot = s === 2 ? '&#10003;' : String(i + 1);
    const inRow = def.in ? `<div class="f-in">${def.in}</div>` : '';
    const exRow = `<div class="f-ex">${def.ex}</div>`;
    return `<div class="mi-step ${clsMap[s] || 'pending'}">
      ${i > 0 ? '<div class="connector"></div>' : ''}
      <div class="dot">${dot}</div>
      <div class="mi-step-title">${def.title}</div>
      <div class="mi-flow2">${inRow}${exRow}</div>
    </div>`;
  }).join('');
}

function renderMailInqCard(t) {
  const sel = t.task_id === currentMailTaskId ? ' sel' : '';
  const proj = (t.project_name || '') + (t.project_no ? ' (' + t.project_no + ')' : '');
  // procurement_task 来源：已收到报价数（替代原 mail_inquiry_task 的 lowest_* 快照）
  const quotes = Array.isArray(t.replied_supplier_quotes) ? t.replied_supplier_quotes : [];
  const snap = quotes.length
    ? `<span class="mi-snap"><b>已收报价</b> ${quotes.length} 家</span>`
    : `<span class="mi-snap" style="color:var(--text3)">尚无报价</span>`;
  return `<div class="mi-card${sel}" onclick="openMailInquiryDetail('${escapeHtml(t.task_id)}')">
    <div class="mi-card-head">
      <span class="mi-task-id">${escapeHtml(t.task_id)}</span>
      ${fmtStatus(t.task_status)}
      ${t.from_email ? `<span class="badge badge-proc-shipping">来源邮件</span>` : ''}
    </div>
    <div class="mi-snap" style="font-size:13px"><b>${escapeHtml(t.pn || '-')}</b> · ${escapeHtml(t.brand || '-')} ${escapeHtml(t.spec || '')} ×${escapeHtml(t.count ?? t.purchase_qty ?? '-')}</div>
    <div class="mi-snap">${escapeHtml(proj) || '<span style="color:var(--text3)">未命名项目</span>'}</div>
    <div class="mi-card-foot">
      <span class="mi-kv"><b>外部</b> ${escapeHtml(t.external_status || '-')}</span>
      <span class="mi-kv"><b>内部</b> ${escapeHtml(t.internal_status || '-')}</span>
      <span class="mi-kv"><b>审批</b> ${escapeHtml(t.approval_state || '-')}</span>
    </div>
    <div class="mi-card-foot">
      ${snap}
      <span style="flex:1"></span>
      <span>更新 ${escapeHtml(String(t.updated_at || t.create_time || '').slice(5, 16) || '-')}</span>
    </div>
  </div>`;
}

async function loadMailInquiryList() {
  // 2026-08-29 起「备件邮件询价」观察面板改读 procurement_task（与主清单同表），
  // 按 source=email 过滤邮件来源任务，不再读 mail_inquiry_task。
  showPageLoading('加载备件邮件询价...');
  try {
    const kw = ($('mailInqKeyword') || {}).value || '';
    const st = ($('mailInqStatus') || {}).value || '';
    const qs = new URLSearchParams();
    qs.set('source', 'email');
    if (kw) qs.set('keyword', kw);
    if (st) qs.set('status', st);
    const d = await api(`/tasks?${qs.toString()}`);
    const arr = Array.isArray(d && d.data) ? d.data : [];
    setText('mailInqSummary', `共 ${arr.length} 个邮件询价任务`);
    if (!arr.length) {
      setHTML('mailInquiryList', '<div class="empty-tip">暂无「邮件」来源的备件询价任务</div>');
      setHTML('mailInqDetailBody', '');
      $('mailInquiryDetailPanel').style.display = 'none';
      return;
    }
    setHTML('mailInquiryList', arr.map(renderMailInqCard).join(''));
    if (currentMailTaskId && arr.some(x => x.task_id === currentMailTaskId)) {
      openMailInquiryDetail(currentMailTaskId);
    } else {
      openMailInquiryDetail(arr[0].task_id);
    }
  } finally {
    hidePageLoading();
  }
}

async function openMailInquiryDetail(taskId) {
  // 复用主清单的统一详情（采购基础信息 + 内部/外部双流 + 报价与操作日志），避免两套详情实现。
  showPageLoading('打开邮件询价详情...');
  try {
    currentMailTaskId = taskId;
    // 高亮当前选中卡片
    document.querySelectorAll('.mi-card').forEach(c => c.classList.remove('sel'));
    const card = [...document.querySelectorAll('.mi-card')]
      .find(c => String(c.getAttribute('onclick') || '').includes(taskId));
    if (card) card.classList.add('sel');
    // 详情页挂在「询比价任务」tab 下，先切到该 tab 再打开共享详情
    switchSidebar('tasks');
    openDetail(taskId);
  } finally {
    hidePageLoading();
  }
}

function mailCvGrid(rows) {
  return rows.map(([k, v]) => `<div><div class="k">${k}</div><div class="v">${v}</div></div>`).join('');
}

function mailApprovalHtml(t) {
  const as = t.approval_state || '';
  const ar = t.approval_result || '';
  const ae = t.approver_email || '';
  const a = String(as).toLowerCase();
  let color = 'var(--amber)';
  if (['approved', 'auto_approved'].includes(a)) color = 'var(--green)';
  else if (a.includes('reject') || a.includes('decline')) color = 'var(--red)';
  let html = `<span style="color:${color}">${escapeHtml(as || '-')}</span>`;
  if (ar) html += ` <span style="color:var(--text2)">(${escapeHtml(ar)})</span>`;
  if (ae) html += ` <span style="color:var(--text2)">${escapeHtml(ae)}</span>`;
  return html;
}

function renderMailQuotes(t) {
  const qs = Array.isArray(t.quotes_json) ? t.quotes_json : [];
  if (!qs.length) return '';
  const rows = qs.map(q => {
    const name = q.supplier || q.email || q.name || '-';
    const price = (q.unit_price != null && q.unit_price !== '') ? `¥${q.unit_price}` : '';
    return `<div class="mi-quote-row">
      <span class="mi-quote-supp">${escapeHtml(name)}</span>
      ${price ? `<span class="mi-quote-price">${escapeHtml(price)}</span>` : ''}
      ${q.ship_time ? `<span class="mmeta">发货 ${escapeHtml(q.ship_time)}</span>` : ''}
      ${q.is_late ? '<span class="tag tag-red">超时</span>' : ''}
    </div>`;
  }).join('');
  return `<div class="mi-mails-title">供应商报价 (${qs.length})</div><div class="mi-mails">${rows}</div>`;
}

function renderMailArchives(mails) {
  const arr = Array.isArray(mails) ? mails : [];
  if (!arr.length) {
    return `<div class="mi-mails-title">邮件原文 (0)</div>
      <div class="mi-worker" style="margin:6px 0 0">暂无邮件原文归档（引擎将在关键邮件往来后自动追加）。</div>`;
  }
  const items = arr.map((m, i) => {
    const sub = m.subject || m.subject_text || `（第 ${i + 1} 封邮件）`;
    const from = m.from_email || m.from || m.sender || '-';
    const to = ([]).concat(m.to || m.to_email || []).filter(Boolean).join(', ') || '-';
    const cc = ([]).concat(m.cc || []).filter(Boolean).join(', ');
    const date = m.date || m.sent_at || m.time || '';
    const body = m.body_text || m.body || m.content || m.raw_text || '';
    const meta = [`发件 ${escapeHtml(from)}`, `收件 ${escapeHtml(to)}`, cc ? `抄送 ${escapeHtml(cc)}` : '', date ? escapeHtml(date) : ''].filter(Boolean);
    return `<div class="mi-mail-item">
      <div class="mh"><span class="msub">${escapeHtml(sub)}</span>
        <span class="mmeta">${meta.join(' · ')}</span>
      </div>
      ${body ? `<pre>${escapeHtml(body)}</pre>` : ''}
    </div>`;
  }).join('');
  return `<div class="mi-mails-title">邮件原文 (${arr.length})</div><div class="mi-mails">${items}</div>`;
}

function renderMailInquiryDetail(t) {
  const st = mailStepStates(t);
  const stepper = renderMailStepper(t, st);
  const latestStep = t.latest_step
    ? `<div class="mi-worker">引擎步骤（latest_step）：<b>${escapeHtml(t.latest_step)}</b></div>` : '';
  const kv = mailCvGrid([
    ['项目', [t.project_name, t.project_no ? '(' + t.project_no + ')' : ''].filter(Boolean).join(' ').trim() || '-'],
    ['备件', [t.part_type, t.brand, t.spec].filter(Boolean).join(' · ').trim() || '-'],
    ['料号 / 数量 / 成色', `${t.pn || '-'} × ${t.count || '-'}（${t.condition || '-'}）`],
    ['收货地址', t.address || '-'],
    ['紧急 / 报价截止', [t.urgent, t.inquiry_deadline].filter(Boolean).join(' / ') || '-'],
    ['最低报价供应商', t.lowest_supplier ? `<b style="color:var(--green)">${escapeHtml(t.lowest_supplier)} · ${escapeHtml(t.lowest_quote || '-')}</b>` : '-'],
    ['目标供应商', escapeHtml(t.target_supplier || '-')],
    ['审批状态', mailApprovalHtml(t)],
    ['快递单号', t.shipped_no ? `<b style="color:#5ed7ff">${escapeHtml(t.shipped_no)}</b>` : '-'],
    ['发起人邮箱', t.from_email || '-'],
    ['线程 Message-ID', t.thread_msg_id ? `<span style="font-family:var(--mono);font-size:11px">${escapeHtml(t.thread_msg_id)}</span>` : '-'],
    ['创建 / 更新', `${t.created_at || '-'} / ${t.updated_at || '-'}`],
  ]);
  return `
    ${latestStep}
    <div class="mi-legend">
      <span class="lg-done"><i></i>已完成</span>
      <span class="lg-cur"><i></i>进行中</span>
      <span class="lg-pen"><i></i>未开始</span>
    </div>
    <div class="mi-stepper">${stepper}</div>
    <div class="mi-kv-grid">${kv}</div>
    ${renderMailQuotes(t)}
    ${renderMailArchives(t.mail_archive_json)}
  `;
}


// ============ 启动 ============
document.addEventListener('DOMContentLoaded', () => {
  initProcUI();
});
