/* ================================================================
 * 本体可观测（Ontology）前端模块 —— 系统 › 主数据 › 本体可观测
 *
 * 迁移说明：原挂在「运维 › 备件采购」下，且数据来自 neuops-agent-demo(9007)
 * 的只读外挂视图。现引擎与 ABox 库（contract_ontology.db）已整体迁入本工程，
 * 后端 /api/ontology/* 进程内直取 backend/ontology_engine，前台入口随之
 * 迁到「系统 › 主数据」下。procurement 页不再包含任何本体面板。
 *
 * 依赖：core.html 提供 6 个 #panel-ont* 容器 + #pageLoading 遮罩；
 *       样式统一在 common.css 的「本体可观测」段。
 * 本文件自备 DOM/转义/遮罩工具（ont* 前缀），不与 core.app.js 抢全局名。
 * ================================================================ */

// 执行历史 action 中文映射：让 009 的代码动作变成人话，便于判断"做了什么、对不对"
const ONT_ACTION_LABELS = {
  createTask: '创建询价任务', distributeInquiry: '发送询价函', submitApproval: '发起审批汇总',
  confirmOrderToSupplier: '下达订货', receiveTrackingNumber: '登记快递单号',
  requestTrackingNo: '索取发货单号', requestShippingTracking: '回复发货单号',
  requestQuoteClarification: '催补报价', requestMissingFields: '催补询价信息',
  receiveSupplierQuote: '收到供应商报价', finalizeQuoteCollection: '报价收尾',
  waitForSupplierShipment: '等待供应商发货', engineerFinalClose: '结算闭环',
  abortTask: '中止任务', manualCloseTask: '手动关闭',
  propose: '决策提议', claim: '认领询邮', select: '确认选型',
  test_pass: '验收通过', test_fail: '验收失败', cancel: '取消任务',
};

/* ---------- 本模块自备工具（前缀 ont，避免与宿主页脚本冲突） ---------- */
const ONT$ = (id) => document.getElementById(id);

function ontEsc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

/** 严格判空：面板 id 写错时立刻抛错定位，杜绝静默空白。 */
function ontSetHTML(id, html) {
  const el = ONT$(id);
  if (!el) {
    const msg = `[BUG] DOM 元素 #${id} 不存在，请检查 core.html 是否写入 id="${id}"`;
    console.error(msg);
    throw new Error(msg);
  }
  el.innerHTML = html == null ? '' : String(html);
}

function ontSetText(id, text) {
  const el = ONT$(id);
  if (!el) { console.error(`[BUG] DOM 元素 #${id} 不存在 (ontSetText)`); return; }
  el.textContent = text == null ? '' : String(text);
}

/** 提示：优先复用宿主页 toast（core.app.js 的签名为 (msg, ok:boolean)）。 */
function ontToast(msg, ok) {
  if (typeof window.toast === 'function') { window.toast(msg, !!ok); return; }
  console[ok ? 'info' : 'error']('[ontology]', msg);
}

/* 遮罩：计数器式，嵌套/并行请求不乱闪；无 #pageLoading 时安静降级。 */
let __ontBusy = 0;
let __ontBusyTimer = null;
function ontBusyOn(text = '加载中...') {
  if (__ontBusyTimer) { clearTimeout(__ontBusyTimer); __ontBusyTimer = null; }
  __ontBusy += 1;
  const el = ONT$('pageLoading');
  if (!el) return;
  const t = ONT$('pageLoadingText');
  if (t) t.textContent = text;
  el.classList.add('show');
  el.setAttribute('aria-hidden', 'false');
}
function ontBusyOff(force = false) {
  __ontBusy = force ? 0 : Math.max(0, __ontBusy - 1);
  if (__ontBusy > 0) return;
  if (__ontBusyTimer) clearTimeout(__ontBusyTimer);
  __ontBusyTimer = setTimeout(() => {
    const el = ONT$('pageLoading');
    __ontBusyTimer = null;
    if (!el) return;
    el.classList.remove('show');
    el.setAttribute('aria-hidden', 'true');
  }, 60);
}

/* ---------- 以下为从 procurement.app.js 迁入的本体面板渲染逻辑 ---------- */
const ONT_API = '/api/ontology';
// 概念 -> 可统计的 o_* 表（其余概念为抽象/派生，无独立表，实例数显示 —）
const ONT_CONCEPT_COUNT = {
  Person: 'o_person', InquiryTask: 'o_task', InquiryEmail: 'o_email', Quote: 'o_supplier_quote',
};
// 状态 -> chip 配色：g 完成 / o 进行中 / r 异常 / m 中性
const ONT_STATUS_TONE = {
  INIT: 'o', CLOSED: 'g', CLOSED_ABORT: 'm', CLOSED_MANUAL: 'r',
  R_INIT: 'o', R_APPROVAL: 'o', R_CLOSED: 'g',
  R_SEND: 'o', INVITE_QUOTE: 'o', QUOTE_COLLECT_DONE: 'o',
  ORDER_CONFIRM: 'o', WAIT_ENGINEER_CLOSE: 'o', R_SETTLE: 'g',
};
let ontLoaded = {};        // 各面板是否已首载（避免每次切菜单都重拉）
let ontAuditTimer = null;
let ontTaskTimer = null;

async function ontApi(path, params = {}) {
  const qs = Object.entries(params)
    .filter(([, v]) => v !== '' && v !== null && v !== undefined)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join('&');
  const r = await fetch(`${ONT_API}${path}${qs ? '?' + qs : ''}`);
  const data = await r.json().catch(() => ({ success: false, error: '响应解析失败' }));
  if (!r.ok || data.success === false) {
    throw new Error(data.error || `HTTP ${r.status}`);
  }
  return data;
}

/** 面板按需加载入口：切菜单时调用，已加载过的直接跳过（有刷新按钮可强制重载）。 */
function loadOntPanel(name, force = false) {
  const fn = {
    ontEntities: loadOntEntities, ontKnowledge: loadOntKnowledge,
    ontActions: loadOntActions, ontTasks: loadOntTasks, ontLedger: loadOntLedger,
    ontTopology: loadOntTopology,
  }[name];
  if (!fn) return;
  if (ontLoaded[name] && !force) return;
  ontLoaded[name] = true;
  fn().catch(e => {
    ontLoaded[name] = false;   // 失败允许下次重试
    console.error(`[ontology] ${name} 加载失败`, e);
    ontToast(`本体数据加载失败：${e.message}`, false);
  });
}

function refreshOntPanel(name) {
  const fn = {
    ontEntities: loadOntEntities, ontKnowledge: loadOntKnowledge,
    ontActions: loadOntActions, ontTasks: loadOntTasks, ontLedger: loadOntLedger,
    ontTopology: loadOntTopology,
  }[name];
  fn && fn().catch(e => {
    console.error(`[ontology] ${name} 刷新失败`, e);
    ontToast(`刷新失败：${e.message}`, false);
  });
}

// 注：原 toggleOntAcc / setOntAccOpen（本体可观测手风琴的手动展开收起）已移除 ——
// R4 统一壳改用 nav.config.js 的 renderAccordion 渲染侧边栏，分组折叠由 NC 统一处理。

function ontChip(text, tone = '') {
  return `<span class="ont-chip ${tone}">${ontEsc(text)}</span>`;
}

function ontStatusChip(v) {
  const s = String(v || '-');
  return ontChip(s, ONT_STATUS_TONE[s] || 'm');
}

function ontEmptyRow(cols, text) {
  return `<tr><td colspan="${cols}" class="ont-empty">${ontEsc(text)}</td></tr>`;
}

/** 概览指标条（各面板共用，展示库状态与各表行数）。 */
function renderOntOverview(o) {
  const stat = (k, v, tone = '') =>
    `<div class="ont-stat"><div class="k">${ontEsc(k)}</div><div class="v ${tone}">${ontEsc(v)}</div></div>`;
  const c = o.counts || {};
  // 迁移后 TBox 直接来自本进程 ontology_engine 字面量（local）；unavailable 表示引擎包导入失败。
  const srcText = { local: '进程内引擎', unavailable: '不可用' }[o.spec_source] || o.spec_source;
  const es = o.engine_state || {};
  const gov = es.governor || {};
  const agent = es.agent || {};
  // 治理开关：ONT_MODE / ONT_EXEC / ONT_LLM 的合成态；emp-009 为数字员工启停。
  const govText = gov.mode ? `${gov.mode}${gov.exec ? '·执行' : '·只读'}${gov.llm ? '·LLM' : ''}` : '-';
  const empOn = agent.emp_enabled !== false && agent.skill_enabled !== false;
  return [
    stat('本体库', o.db_ok ? '已连接' : '不可用', o.db_ok ? '' : 'err'),
    ...Object.keys(c).map(t => stat(t, c[t] == null ? '-' : c[t], c[t] ? '' : 'mute')),
    stat('本体定义来源', srcText, o.spec_ok ? '' : 'warn'),
    stat('治理开关', govText, gov.exec ? '' : 'mute'),
    stat('emp-009', empOn ? '启用' : '停用', empOn ? '' : 'warn'),
    stat('邮箱渠道', agent.mail_channel_configured ? '已配置' : '未配置', agent.mail_channel_configured ? '' : 'warn'),
    stat('库更新时间', (o.db_mtime || '-').slice(5), 'mute'),
  ].join('');
}

// ---------- 面板 1：实体与关系 ----------
async function loadOntEntities() {
  ontBusyOn('加载本体实例...');
  try {
    const [ov, sp, inst] = await Promise.all([
      ontApi('/overview'), ontApi('/spec'), ontApi('/instances'),
    ]);
    ontSetHTML('ontOverview', renderOntOverview(ov.data));

    // TBox 概念
    const concepts = sp.data.concepts || {};
    ontSetHTML('ontConceptsTbody', Object.keys(concepts).length
      ? Object.entries(concepts).map(([k, v]) => `<tr>
          <td><span class="ont-code">${ontEsc(k)}</span></td>
          <td>${ontEsc(v)}</td>
          <td class="num">${ONT_CONCEPT_COUNT[k]
            ? (inst.data[({ o_task: 'tasks', o_person: 'persons', o_email: 'emails', o_supplier_quote: 'quotes' })[ONT_CONCEPT_COUNT[k]]] || []).length
            : '<span style="color:var(--text2)">—</span>'}</td>
        </tr>`).join('')
      : ontEmptyRow(3, '未获取到概念定义'));

    // TBox 关系
    const relations = sp.data.relations || {};
    ontSetHTML('ontRelationsTbody', Object.keys(relations).length
      ? Object.entries(relations).map(([k, v]) => `<tr>
          <td><span class="ont-code">${ontEsc(k)}</span></td>
          <td>${ontEsc(v)}</td>
        </tr>`).join('')
      : ontEmptyRow(2, '未获取到关系定义'));

    // ABox 任务实例
    const tasks = inst.data.tasks || [];
    ontSetHTML('ontInstTasksTbody', tasks.length
      ? tasks.map(t => {
        const p = t.spare_info_parsed || {};
        return `<tr>
          <td><span class="ont-code">${ontEsc(t.task_id)}</span></td>
          <td>${ontEsc([p.brand, p.pn].filter(Boolean).join(' ') || '-')}
              <div style="color:var(--text2);font-size:11px">${ontEsc(p.spec || '')}</div></td>
          <td class="num">${ontEsc(p.count || '-')}</td>
          <td>${ontStatusChip(t.status)}</td>
          <td>${ontStatusChip(t.internal_status)}</td>
          <td>${ontStatusChip(t.external_status)}</td>
          <td>${ontEsc(t.target_supplier || '-')}</td>
          <td class="ont-mono">${ontEsc(t.from_email || '-')}</td>
          <td>${ontEsc(t.create_time || '-')}</td>
        </tr>`;
      }).join('')
      : ontEmptyRow(9, '本体轨暂无任务实例'));

    renderOntOtherEntities(inst.data);
  } finally {
    ontBusyOff();
  }
}

/** ABox 其余实体（人员 / 邮件 / 报价 / 预会话）分块渲染。 */
function renderOntOtherEntities(d) {
  const block = (title, tip, cols, rows, render) => {
    const body = rows.length
      ? `<div class="twrap"><table><thead><tr>${cols.map(c => `<th>${ontEsc(c)}</th>`).join('')}</tr></thead>
         <tbody>${rows.map(render).join('')}</tbody></table></div>`
      : `<div class="ont-empty">${ontEsc(tip)}</div>`;
    return `<div class="ont-sec-title">${ontEsc(title)}（${rows.length}）</div>${body}`;
  };

  const persons = d.persons || [];
  const emails = d.emails || [];
  const quotes = d.quotes || [];
  const sessions = d.sessions || [];

  ontSetHTML('ontInstOthers', [
    block('人员 o_person', '本体轨尚未登记人员实体（Person/Engineer/Approver/Supplier 均由邮箱直接引用）',
      ['Person ID', '姓名', '邮箱', '角色'],
      persons, p => `<tr><td class="ont-mono">${ontEsc(p.person_id)}</td><td>${ontEsc(p.name || '-')}</td>
        <td class="ont-mono">${ontEsc(p.email || '-')}</td><td>${ontChip(p.role || '-')}</td></tr>`),
    block('邮件 o_email', '本体轨尚未归档邮件（仅 inbound 询价邮件入库）',
      ['Message-ID', 'Task ID', '标题', '模板', '发件人', '发送时间'],
      emails, m => `<tr><td class="ont-mono">${ontEsc(m.email_message_id)}</td>
        <td class="ont-mono">${ontEsc(m.task_id || '-')}</td>
        <td>${ontEsc(m.title || '-')}</td><td>${ontChip(m.template_type || '-')}</td>
        <td class="ont-mono">${ontEsc(m.from_email || '-')}</td>
        <td>${ontEsc(m.send_time || '-')}</td></tr>`),
    block('供应商报价 o_supplier_quote', '暂无独立报价行（当前报价写在 o_task.spare_info.quotes 中）',
      ['Quote ID', 'Task ID', '供应商', '单价', '接收时间', '有效', '超时'],
      quotes, q => `<tr><td class="ont-mono">${ontEsc(q.quote_id)}</td>
        <td class="ont-mono">${ontEsc(q.task_id || '-')}</td>
        <td class="ont-mono">${ontEsc(q.supplier_person_id || '-')}</td>
        <td class="num">${ontEsc(q.unit_price || '-')}</td>
        <td>${ontEsc(q.receive_time || '-')}</td>
        <td>${q.is_valid ? ontChip('有效', 'g') : ontChip('无效', 'r')}</td>
        <td>${q.is_timeout ? ontChip('超时', 'o') : '<span style="color:var(--text2)">-</span>'}</td></tr>`),
    block('预会话 o_session', '暂无立项前预会话',
      ['Session ID', '发起人', '线程 ID', '状态', '创建时间', '放弃原因'],
      sessions, s => `<tr><td class="ont-mono">${ontEsc(s.session_id)}</td>
        <td class="ont-mono">${ontEsc(s.initiator_person_id || '-')}</td>
        <td class="ont-mono">${ontEsc(s.thread_id || '-')}</td>
        <td>${ontStatusChip(s.status)}</td>
        <td>${ontEsc(s.create_time || '-')}</td>
        <td>${ontEsc(s.abandon_reason || '-')}</td></tr>`),
  ].join(''));
}

// ---------- 面板 2：知识 ----------
async function loadOntKnowledge() {
  ontBusyOn('加载本体知识...');
  try {
    const r = await ontApi('/knowledge');
    const d = r.data;
    ontSetText('ontKnowSource', { local: '本工程 ontology_engine（进程内）', unavailable: '引擎不可用' }[d.source] || d.source || '-');

    // 动作定义卡片
    const acts = d.actions || {};
    const ids = Object.keys(acts);
    ontSetHTML('ontActionDefs', ids.length ? ids.map(id => {
      const a = acts[id];
      const conds = a['条件'] || [];
      const invs = a['不变量'] || [];
      return `<div class="ont-card">
        <h4><span class="ont-code">${ontEsc(id)}</span>
          ${a['幂等'] ? ontChip('幂等', 'g') : ontChip('非幂等', 'o')}</h4>
        <div class="def">${ontEsc(a['定义'] || '-')}</div>
        <div class="ont-line cond"><span class="tag">条件</span><span class="body">${
          conds.length ? '<ul>' + conds.map(c => `<li>${ontEsc(c)}</li>`).join('') + '</ul>'
                       : '<span style="color:var(--text2)">无前置条件</span>'}</span></div>
        <div class="ont-line eff"><span class="tag">效果</span><span class="body">${ontEsc(a['效果'] || '-')}</span></div>
        <div class="ont-line inv"><span class="tag">不变量</span><span class="body">${
          invs.length ? '<ul>' + invs.map(c => `<li>${ontEsc(c)}</li>`).join('') + '</ul>'
                      : '<span style="color:var(--text2)">无</span>'}</span></div>
      </div>`;
    }).join('') : '<div class="ont-empty">未获取到动作定义</div>');

    // 全局不变量
    const invs = d.invariants || [];
    ontSetHTML('ontInvariants', invs.length ? invs.map(v => `
      <div class="ont-line inv" style="margin:6px 0">
        <span class="tag" style="min-width:150px"><span class="ont-code">${ontEsc(v.id || '-')}</span></span>
        <span class="body">${ontEsc(v.desc || '')}</span>
      </div>`).join('') : '<div class="ont-empty">未获取到全局不变量</div>');

    // 规则集
    const rules = d.rules || [];
    ontSetHTML('ontRulesTbody', rules.length ? rules.map(r => `<tr>
      <td><span class="ont-code">${ontEsc(r.id)}</span></td>
      <td><span class="ont-code">${ontEsc(r.target)}</span></td>
      <td><div class="ont-pre">${ontEsc(ontExpr(r.check))}</div></td>
      <td>${ontEsc(r.desc || '-')}</td>
    </tr>`).join('') : ontEmptyRow(4, '未获取到规则集'));
  } finally {
    ontBusyOff();
  }
}

/** 规则条件表达式：紧凑 JSON，便于人读。 */
function ontExpr(node) {
  try {
    return JSON.stringify(node);
  } catch (e) {
    return String(node);
  }
}

// ---------- 面板 3：动作 ----------
async function loadOntActions() {
  ontBusyOn('加载动作注册表...');
  try {
    const r = await ontApi('/actions');
    const reg = r.data.action_registry || {};
    const ids = Object.keys(reg);
    ontSetHTML('ontRegistryTbody', ids.length ? ids.map(id => {
      const a = reg[id];
      const st = a._stats || {};
      const next = [a.next_internal ? `内部 ${a.next_internal}` : '',
                    a.next_external ? `外部 ${a.next_external}` : ''].filter(Boolean);
      return `<tr>
        <td><span class="ont-code">${ontEsc(id)}</span></td>
        <td>${ontChip(a.kind || '-')}</td>
        <td>${ontEsc(a.desc || '-')}</td>
        <td>${next.length ? next.map(n => ontChip(n, 'g')).join(' ') : '<span style="color:var(--text2)">-</span>'}</td>
        <td class="num">${st.exec || 0}</td>
        <td class="num">${st.align || 0}</td>
        <td class="num">${st.noop || 0}</td>
        <td>${ontEsc(st.last_time || '-')}</td>
      </tr>`;
    }).join('') : ontEmptyRow(8, '未获取到动作注册表'));
    await loadOntAudit();
  } finally {
    ontBusyOff();
  }
}

async function loadOntAudit() {
  try {
    const r = await ontApi('/audit', {
      action: ($('ontAuditAction') || {}).value || '',
      biz_id: ($('ontAuditBizId') || {}).value || '',
      keyword: ($('ontAuditKeyword') || {}).value || '',
      limit: 200,
    });
    const rows = r.data || [];
    ontSetHTML('ontAuditTbody', rows.length ? rows.map(a => `<tr>
      <td class="num">${a.audit_log_id}</td>
      <td>${ontActionChip(a.action)}</td>
      <td class="ont-mono">${ontEsc(a.biz_id || '-')}</td>
      <td>${ontEsc(a.operator || '-')}</td>
      <td>${ontEsc(a.operate_time || '-')}</td>
      <td><div class="ont-pre">${ontEsc(ontSnap(a.content_snapshot_parsed))}</div></td>
      <td>${ontEsc(a.remark || '-')}</td>
    </tr>`).join('') : ontEmptyRow(7, '暂无审计流水'));
  } catch (e) {
    ontSetHTML('ontAuditTbody', ontEmptyRow(7, `审计流水加载失败：${e.message}`));
  }
}

/** 审计 action 带 align:/noop: 前缀，拆出来着色，并附中文动作说明。 */
function ontActionChip(action) {
  const raw = String(action || '-');
  if (raw.includes(':')) {
    const [prefix, name] = raw.split(':', 2);
    const label = ONT_ACTION_LABELS[name] || '';
    return `${ontChip(prefix, prefix === 'noop' ? 'm' : '')} <span class="ont-code">${ontEsc(name)}</span>${label ? ` <span style="color:var(--text2);font-size:11px">· ${ontEsc(label)}</span>` : ''}`;
  }
  const label = ONT_ACTION_LABELS[raw] || '';
  return `${ontChip('执行', 'g')} <span class="ont-code">${ontEsc(raw)}</span>${label ? ` <span style="color:var(--text2);font-size:11px">· ${ontEsc(label)}</span>` : ''}`;
}

function ontSnap(obj) {
  if (!obj || (typeof obj === 'object' && !Object.keys(obj).length)) return '{}';
  try {
    return JSON.stringify(obj, null, 1);
  } catch (e) {
    return String(obj);
  }
}

function resetOntAuditFilters() {
  ['ontAuditAction', 'ontAuditBizId', 'ontAuditKeyword'].forEach(id => { const el = $(id); if (el) el.value = ''; });
  loadOntAudit();
}

// ---------- 面板 4：任务列表 ----------
async function loadOntTasks() {
  ontBusyOn('加载本体任务...');
  try {
    const r = await ontApi('/tasks', {
      status: ($('ontTaskStatus') || {}).value || '',
      keyword: ($('ontTaskKeyword') || {}).value || '',
    });
    const rows = r.data || [];
    ontFillStatusFilter(rows);
    ontSetHTML('ontTasksTbody', rows.length ? rows.map(t => {
      const m = t.milestones || {};
      const ms = [
        m.inquiry_sent ? ontChip('B 询价', 'g') : '',
        m.approval_sent ? ontChip('D 审批', 'g') : '',
        m.order_sent ? ontChip('E 订货', 'g') : '',
        m.tracking_no ? ontChip('运单', 'g') : '',
        m.settled ? ontChip('G 结算', 'g') : '',
      ].filter(Boolean).join(' ');
      const p = t.part || {};
      return `<tr>
        <td><span class="ont-code">${ontEsc(t.task_id)}</span>
            <div style="color:var(--text2);font-size:11px">${ontEsc(t.session_id || '')}</div></td>
        <td>${ontEsc([p.project_no, p.project_name].filter(Boolean).join(' · ') || '-')}
            <div style="color:var(--text2);font-size:11px">${ontEsc([p.brand, p.pn].filter(Boolean).join(' ') || '')}</div></td>
        <td class="num">${ontEsc(p.count || '-')}</td>
        <td>${ontStatusChip(t.status)}</td>
        <td>${ontStatusChip(t.internal_status)}</td>
        <td>${ontStatusChip(t.external_status)}</td>
        <td>${ontEsc(t.quote_deadline || t.urgency_raw || '-')}</td>
        <td class="ont-mono">${ontEsc(t.target_supplier || '-')}</td>
        <td class="num">${t.valid_quote_count}/${t.quote_count}</td>
        <td>${ms || '<span style="color:var(--text2)">-</span>'}</td>
        <td>${ontEsc(t.create_time || '-')}</td>
      </tr>`;
    }).join('') : ontEmptyRow(11, '没有符合条件的本体任务'));
  } finally {
    ontBusyOff();
  }
}

/** 状态下拉：用当前数据的取值填充，避免硬编码枚举漂移。 */
function ontFillStatusFilter(rows) {
  const sel = $('ontTaskStatus');
  if (!sel) return;
  const cur = sel.value;
  const set = new Set();
  rows.forEach(t => { [t.status, t.internal_status, t.external_status].forEach(s => s && set.add(s)); });
  sel.innerHTML = '<option value="">全部状态</option>' +
    [...set].sort().map(s => `<option value="${ontEsc(s)}">${ontEsc(s)}</option>`).join('');
  sel.value = cur;
}

function resetOntTaskFilters() {
  const el = $('ontTaskKeyword'); if (el) el.value = '';
  const st = $('ontTaskStatus'); if (st) st.value = '';
  loadOntTasks();
}

// ---------- 面板 5：台账 ----------
async function loadOntLedger() {
  ontBusyOn('加载本体台账...');
  try {
    const r = await ontApi('/ledger');
    const rows = r.data || [];
    ontSetHTML('ontLedgerTbody', rows.length ? rows.map(l => `<tr>
      <td><span class="ont-code">${ontEsc(l.task_id)}</span></td>
      <td>${ontEsc(l.project_no || '-')}</td>
      <td>${ontEsc(l.project_name || '-')}</td>
      <td>${ontEsc(l.part || '-')}
          <div style="color:var(--text2);font-size:11px">${ontEsc(l.spec || '')}</div></td>
      <td class="num">${ontEsc(l.count || '-')}</td>
      <td class="ont-mono">${ontEsc(l.supplier || '-')}</td>
      <td class="num">${ontEsc(l.unit_price || '-')}</td>
      <td class="num" style="color:#ff7089">${l.amount == null ? '-' : l.amount.toLocaleString('zh-CN')}</td>
      <td>${ontEsc(l.tracking_no || '-')}</td>
      <td>${ontEsc(l.close_time || '-')}</td>
      <td>${ontStatusChip(l.close_status)}</td>
      <td><div class="ont-pre">${ontEsc(l.close_feedback || '-')}</div></td>
    </tr>`).join('') : ontEmptyRow(12, '暂无已闭环任务，台账为空'));

    let qty = 0, amt = 0;
    rows.forEach(l => { qty += parseFloat(l.count) || 0; amt += parseFloat(l.amount) || 0; });
    ontSetText('ontLedgerCount', String(rows.length));
    ontSetText('ontLedgerQtySum', String(qty));
    ontSetText('ontLedgerAmtSum', amt.toLocaleString('zh-CN'));
  } finally {
    ontBusyOff();
  }
}


// ============ 本体拓扑与一致性（地基视图） ============
// 纯字符串渲染器：概念×关系图 / 动作-状态映射图 / 声明↔执行一致性校验。
// 数据来自 /api/ontology/spec（本工程 ontology_engine 的真实 TBox 字面量）。
(function (global) {
  'use strict';
  function collectEq(node, out) {
    if (!node || typeof node !== 'object') return out;
    if (Array.isArray(node)) { node.forEach(function (n) { collectEq(n, out); }); return out; }
    var keys = Object.keys(node);
    if (keys.length === 1) {
      var op = keys[0], arg = node[op];
      if (op === 'eq' && Array.isArray(arg) && arg.length === 2) out.push({ field: arg[0], val: arg[1] });
      else if (op === 'and' || op === 'or' || op === 'not') collectEq(arg, out);
    }
    return out;
  }
  var ALIAS = { task: 'InquiryTask', supplier: 'Supplier', person: 'Person', quote: 'Quote',
    approval: 'Approval', order: 'Order', shipment: 'Shipment', tracking: 'Shipment', approver: 'Approver' };
  function resolve(token, validSet) {
    if (!token) return null;
    token = String(token).trim().replace(/[{}]/g, '');
    if (ALIAS[token]) token = ALIAS[token];
    if (validSet && validSet.indexOf(token) < 0) return null;
    return token;
  }
  function resolveRange(rangeStr, validSet) {
    var toks = String(rangeStr || '').split(/[,\s{}]+/).filter(Boolean), out = [];
    toks.forEach(function (t) { var r = resolve(t, validSet); if (r) out.push(r); });
    return Array.from(new Set(out));
  }
  function conceptGraph(spec) {
    var concepts = spec.CONCEPTS || {}, relations = spec.RELATIONS || {};
    var validSet = Object.keys(concepts);
    var nodes = validSet.map(function (id) { return { id: id, label: id, desc: concepts[id], group: 'concept' }; });
    var edges = [], unary = [], seenEdge = {};
    Object.keys(relations).forEach(function (sig) {
      var desc = relations[sig];
      var m = sig.match(/^([^(]+)\.([^()]+)\(([^)]*)\)$/);
      if (!m) { var um = sig.match(/^([^.]+)\.([^.]+)$/); if (um) { var un = resolve(um[1], validSet); if (un) unary.push({ node: un, prop: um[2], desc: desc }); } return; }
      var dom = resolve(m[1], validSet), rel = m[2], rngs = resolveRange(m[3], validSet);
      rngs.forEach(function (r) { if (!dom || !r) return; var key = dom + '|' + rel + '|' + r; if (seenEdge[key]) return; seenEdge[key] = 1; edges.push({ from: dom, to: r, label: rel }); });
    });
    var touched = {};
    edges.forEach(function (e) { touched[e.from] = 1; touched[e.to] = 1; });
    unary.forEach(function (u) { touched[u.node] = 1; });
    var isolated = nodes.filter(function (n) { return !touched[n.id]; }).map(function (n) { return n.id; });
    return { nodes: nodes, edges: edges, unary: unary, isolated: isolated };
  }
  var STATUS_ORDER = ['R_FR02_MISSING_FIELDS', 'R_INIT', 'R_SEND', 'INVITE_QUOTE', 'QUOTE_COLLECT_DONE',
    'R_APPROVAL', 'R_ORDER', 'R_WAIT_ENGINEER_CLOSE', 'R_CLOSED', 'R_SETTLE', 'CLOSED_ABORT', 'CLOSED_MANUAL'];
  function actionMap(spec) {
    var actions = spec.ACTIONS || {}, reg = spec.ACTION_REGISTRY || {}, rules = spec.RULES || [];
    var precond = {}, succ = {}, statuses = {};
    rules.forEach(function (r) { collectEq(r.check, []).forEach(function (e) { if ((e.field === 'internal_status' || e.field === 'external_status') && typeof e.val === 'string') { precond[r.target] = precond[r.target] || {}; precond[r.target][e.val] = 1; statuses[e.val] = 1; } }); });
    Object.keys(reg).forEach(function (name) { var r = reg[name]; [r.next_internal, r.next_external].forEach(function (s) { if (s) { succ[name] = succ[name] || {}; succ[name][s] = 1; statuses[s] = 1; } }); });
    var statusList = Object.keys(statuses).sort(function (a, b) { var ia = STATUS_ORDER.indexOf(a), ib = STATUS_ORDER.indexOf(b); if (ia < 0) ia = 999; if (ib < 0) ib = 999; return ia - ib; });
    return { statuses: statusList, actions: Object.keys(actions), precond: precond, succ: succ };
  }
  function health(spec) {
    var actions = Object.keys(spec.ACTIONS || {}), reg = Object.keys(spec.ACTION_REGISTRY || {});
    var rulesTargets = (spec.RULES || []).map(function (r) { return r.target; }), issues = [];
    actions.filter(function (a) { return reg.indexOf(a) < 0; }).forEach(function (a) { issues.push({ sev: 'warn', msg: '动作声明存在但未注册到 ACTION_REGISTRY：' + a + '（孤儿声明，运行时不执行）' }); });
    reg.filter(function (a) { return actions.indexOf(a) < 0; }).forEach(function (a) { issues.push({ sev: 'error', msg: '注册表存在但本体未声明：' + a }); });
    rulesTargets.filter(function (t) { return actions.indexOf(t) < 0; }).forEach(function (t) { issues.push({ sev: 'error', msg: '规则目标未声明动作：' + t }); });
    var ruleStatuses = {}, regStatuses = {};
    (spec.RULES || []).forEach(function (r) { collectEq(r.check, []).forEach(function (e) { if ((e.field === 'internal_status' || e.field === 'external_status') && typeof e.val === 'string') ruleStatuses[e.val] = 1; }); });
    Object.keys(spec.ACTION_REGISTRY || {}).forEach(function (name) { var rr = (spec.ACTION_REGISTRY || {})[name]; [rr.next_internal, rr.next_external].forEach(function (s) { if (s) regStatuses[s] = 1; }); });
    Object.keys(ruleStatuses).forEach(function (s) { if (!regStatuses[s]) issues.push({ sev: 'warn', msg: '状态命名漂移：规则前置引用「' + s + '」，但注册表后继状态中无此值（如 R_ORDER vs ORDER_CONFIRM、R_WAIT_ENGINEER_CLOSE vs WAIT_ENGINEER_CLOSE）——动作→状态链条在图上会断开' }); });
    Object.keys(regStatuses).forEach(function (s) { if (!ruleStatuses[s]) issues.push({ sev: 'info', msg: '注册表后继状态「' + s + '」未被任何规则前置引用（单向出口，仅作展示）' }); });
    var enforced = ['createTask'], uniq = Array.from(new Set(rulesTargets)), unenforced = uniq.filter(function (t) { return enforced.indexOf(t) < 0; });
    if (unenforced.length) issues.push({ sev: 'warn', msg: '声明式规则仅 ' + enforced.join('/') + ' 在运行时被校验器实际调用；其余 ' + unenforced.length + ' 条规则（' + unenforced.join('、') + '）当前不被决策器执行，流程由 decision.py 硬编码状态机驱动——属架构债/声明↔执行漂移' });
    return issues;
  }
  function esc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
  function radialSvg(g) {
    var W = 720, H = 480, cx = W / 2, cy = H / 2, R = 175, ns = g.nodes, n = ns.length, pos = {};
    ns.forEach(function (nd, i) { var ang = (Math.PI * 2 * i) / Math.max(n, 1) - Math.PI / 2; pos[nd.id] = { x: cx + R * Math.cos(ang), y: cy + R * Math.sin(ang) }; });
    var svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" class="ont-svg" width="100%">';
    g.edges.forEach(function (e) { var a = pos[e.from], b = pos[e.to]; if (!a || !b) return; var mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2; svg += '<g class="ont-edge" data-from="' + esc(e.from) + '" data-to="' + esc(e.to) + '"><line x1="' + a.x + '" y1="' + a.y + '" x2="' + b.x + '" y2="' + b.y + '"/><text x="' + mx + '" y="' + my + '" class="ont-edge-label">' + esc(e.label) + '</text></g>'; });
    ns.forEach(function (nd) { var p = pos[nd.id], iso = g.isolated.indexOf(nd.id) >= 0; svg += '<g class="ont-node ont-node-concept' + (iso ? ' ont-iso' : '') + '" data-id="' + esc(nd.id) + '" tabindex="0"><circle cx="' + p.x + '" cy="' + p.y + '" r="26"/><text x="' + p.x + '" y="' + (p.y + 4) + '" class="ont-node-label">' + esc(nd.label) + '</text></g>'; });
    return svg + '</svg>';
  }
  function bipartiteSvg(am) {
    var W = 760, rowH = 34, padT = 30, padB = 20, H = Math.max(am.statuses.length, am.actions.length) * rowH + padT + padB, colL = 170, colR = W - 170;
    var svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" class="ont-svg" width="100%">', sY = {}, aY = {};
    am.statuses.forEach(function (s, i) { sY[s] = padT + i * rowH + rowH / 2; });
    am.actions.forEach(function (a, i) { aY[a] = padT + i * rowH + rowH / 2; });
    am.actions.forEach(function (a) {
      var prec = am.precond[a] || {}; Object.keys(prec).forEach(function (s) { if (!sY[s] || !aY[a]) return; svg += '<g class="ont-edge ont-pre"><line x1="' + colL + '" y1="' + sY[s] + '" x2="' + colR + '" y2="' + aY[a] + '"/><text x="' + ((colL + colR) / 2) + '" y="' + ((sY[s] + aY[a]) / 2 - 4) + '" class="ont-edge-sub">前置</text></g>'; });
      var sc = am.succ[a] || {}; Object.keys(sc).forEach(function (s) { if (!sY[s] || !aY[a]) return; svg += '<g class="ont-edge ont-succ"><line x1="' + colR + '" y1="' + aY[a] + '" x2="' + colL + '" y2="' + sY[s] + '"/><text x="' + ((colL + colR) / 2) + '" y="' + ((aY[a] + sY[s]) / 2 - 4) + '" class="ont-edge-sub">后继</text></g>'; });
    });
    am.statuses.forEach(function (s) { svg += '<g class="ont-node ont-node-status" data-status="' + esc(s) + '"><rect x="' + (colL - 150) + '" y="' + (sY[s] - 12) + '" width="150" height="24" rx="6"/><text x="' + colL + '" y="' + (sY[s] + 4) + '" class="ont-node-label" text-anchor="middle">' + esc(s) + '</text></g>'; });
    am.actions.forEach(function (a) { svg += '<g class="ont-node ont-node-action" data-action="' + esc(a) + '" tabindex="0"><rect x="' + (colR - 90) + '" y="' + (aY[a] - 12) + '" width="180" height="24" rx="12"/><text x="' + colR + '" y="' + (aY[a] + 4) + '" class="ont-node-label" text-anchor="middle">' + esc(a) + '</text></g>'; });
    return svg + '</svg>';
  }
  function buildAll(spec) {
    var cg = conceptGraph(spec), am = actionMap(spec);
    return { conceptSvg: radialSvg(cg), conceptIsolated: cg.isolated, actionSvg: bipartiteSvg(am),
      health: health(spec), conceptCount: cg.nodes.length, edgeCount: cg.edges.length,
      statusCount: am.statuses.length, actionCount: am.actions.length };
  }
  global.OntTopo = { conceptGraph: conceptGraph, actionMap: actionMap, health: health, radialSvg: radialSvg, bipartiteSvg: bipartiteSvg, buildAll: buildAll, collectEq: collectEq, STATUS_ORDER: STATUS_ORDER };
})(typeof window !== 'undefined' ? window : globalThis);

// 面板加载：归一化 /spec 的小写键 → 渲染器期望的大写键
async function loadOntTopology() {
  ontBusyOn('加载本体拓扑...');
  try {
    const sp = (await ontApi('/spec')).data;
    const spec = {
      CONCEPTS: sp.concepts || {}, RELATIONS: sp.relations || {},
      ACTIONS: sp.actions || {}, INVARIANTS: sp.invariants || [],
      RULES: sp.rules || [], ACTION_REGISTRY: sp.action_registry || {}
    };
    const R = window.OntTopo.buildAll(spec);
    ontSetHTML('ontConceptGraph', R.conceptSvg);
    ontSetHTML('ontActionGraph', R.actionSvg);
    ontSetHTML('ontHealth', R.health.length ? R.health.map(issue => {
      const cls = issue.sev === 'error' ? 'error' : (issue.sev === 'warn' ? 'warn' : 'info');
      const tag = issue.sev === 'error' ? '错误' : (issue.sev === 'warn' ? '警告' : '提示');
      return `<div class="ont-health-item ${cls}"><span class="chip ${issue.sev === 'error' ? 'r' : (issue.sev === 'warn' ? 'w' : 'm')}">${tag}</span>${ontEsc(issue.msg)}</div>`;
    }).join('') : '<div class="ont-health-item info">未发现一致性问题。</div>');
    bindTopoHover(spec);
  } catch (e) {
    ontSetHTML('ontHealth', `<div class="ont-empty">加载失败：${ontEsc(e.message)}</div>`);
  } finally {
    ontBusyOff();
  }
}

// 悬停交互：概念节点高亮关系；动作节点显示前置/后继
function bindTopoHover(spec) {
  const cg = window.OntTopo.conceptGraph(spec);
  document.querySelectorAll('#ontConceptGraph .ont-node-concept').forEach(g => {
    g.addEventListener('mouseenter', () => {
      const id = g.getAttribute('data-id');
      const rels = cg.edges.filter(e => e.from === id || e.to === id);
      const relHtml = rels.length ? rels.map(e => { const o = e.from === id ? e.to : e.from; return e.label + ' → ' + o; }).join('；') : '（无关系连接）';
      ontSetHTML('ontConceptInfo', `<b>${ontEsc(id)}</b>：${ontEsc((spec.CONCEPTS && spec.CONCEPTS[id]) || '')}<br>关系：${ontEsc(relHtml)}`);
      document.querySelectorAll('#ontConceptGraph .ont-edge').forEach(e => { e.style.opacity = (e.getAttribute('data-from') === id || e.getAttribute('data-to') === id) ? '1' : '0.12'; });
      document.querySelectorAll('#ontConceptGraph .ont-node-concept').forEach(n => { n.style.opacity = (n === g) ? '1' : '0.25'; });
    });
    g.addEventListener('mouseleave', () => {
      ontSetHTML('ontConceptInfo', '悬停任一概念节点查看其语义与关系。');
      document.querySelectorAll('#ontConceptGraph .ont-edge, #ontConceptGraph .ont-node-concept').forEach(n => { n.style.opacity = '1'; });
    });
  });
  const am = window.OntTopo.actionMap(spec);
  document.querySelectorAll('#ontActionGraph .ont-node-action').forEach(g => {
    g.addEventListener('mouseenter', () => {
      const id = g.getAttribute('data-action');
      const pre = Object.keys(am.precond[id] || {}), sc = Object.keys(am.succ[id] || {});
      ontSetHTML('ontActionInfo', `<b>${ontEsc(id)}</b><br>前置状态：${pre.length ? ontEsc(pre.join('、')) : '—'}<br>后继状态：${sc.length ? ontEsc(sc.join('、')) : '—'}`);
    });
    g.addEventListener('mouseleave', () => {
      ontSetHTML('ontActionInfo', '悬停任一动作查看其前置状态与后继状态。');
    });
  });
}
