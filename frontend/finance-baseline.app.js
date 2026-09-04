'use strict';
/* 财经 · 四算基线 独立页（读 ontos CostBaseline，归集锚=合同）。
 * 壳：renderTopMenu(activeKey=fin)、renderAccordion(财经域 sections)、面包屑。
 * 数据源：
 *   - 合同清单  GET /api/plm/master-contracts   （md_contract 631 合同，非空表 plm_contract）
 *   - 四算对比  GET /api/plm/contracts/{cno}/baseline-compare
 *   - 阶段枚举  GET /api/ontos/cost-baseline     （读本体 calc_type，不再硬编码 stage）
 *   - 编辑保存  GET/POST /api/plm/contracts/{cno}/baselines
 *   - 锁定概算  POST /api/plm/baselines/{bid}/lock
 * 四算 = CostBaseline 五次实例化(概算/基准预算/生产预算/核算/决算) + version 链；合同为归集锚。
 * 一号可度量目标：决算毛利率 ≥ 签单毛利率（margin_goal）。
 */
(function (root) {
  var NC = root.NAV_CONFIG;
  var API = '';

  var SECTIONS = [
    { sub: '资金运作', links: [
      { key: 'fin-cycle', label: '回款周期', icon: 'cycle', href: '/finance-cycle' },
      { key: 'fin-gross', label: '毛利率', icon: 'gross', href: '/gross' },
      { key: 'fin-fund',  label: '资金占用 · 周转率', icon: 'fund', href: '/finance-fund' },
      { key: 'fin-baseline', label: '四算基线', icon: 'gross', href: '/finance-baseline' },
      { key: 'fin-cost',  label: '成本预警', icon: 'chart', href: '/finance-cost' }
    ] },
    { sub: '资金明细', links: [
      { key: 'fin-recv', label: '回款明细', icon: 'receipt', href: '/finance?kind=recv' },
      { key: 'fin-pay',  label: '付款明细', icon: 'pay', href: '/finance?kind=pay' }
    ] }
  ];

  function renderShell() {
    NC.renderBreadcrumb(document.getElementById('breadcrumb'), ['财经', '资金运作', '四算基线']);
    NC.renderTopMenu(document.getElementById('topMenu'), { activeKey: 'fin' });
    NC.renderAccordion(document.getElementById('navRail'), {
      rootTitle: '经营业务工作台', domainLabel: '财经', activeKey: 'fin',
      activeLink: 'fin-baseline', sections: SECTIONS
    });
  }

  function status(msg) { var el = document.getElementById('blMeta'); if (el) el.textContent = msg; }

  // 内部状态
  var CONTRACTS = [];        // 合同清单缓存（md_contract）
  var CALC_TYPES = [];       // ontos calc_types（读本体）
  var curCno = '';           // 当前归集合同号

  function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
  function money(v) { if (v === null || v === undefined || v === '') return '-'; var n = Number(v); if (isNaN(n)) return String(v); return '¥' + n.toLocaleString(); }
  function pct(v) { if (v === null || v === undefined || v === '') return '-'; return (Number(v) * 100).toFixed(2) + '%'; }

  function statusBadge(st) {
    var cls = st === '已锁定' ? 'badge-c' : (st === '已作废' ? 'badge' : 'badge-o');
    return '<span class="badge ' + cls + '">' + esc(st || '草稿') + '</span>';
  }

  /* ── 合同下拉 ── */
  function fillContractSelect(preserve) {
    var sel = document.getElementById('blContract');
    if (!sel) return;
    var opts = '<option value="">请选择归集合同…</option>' + CONTRACTS.map(function (c) {
      return '<option value="' + esc(c.contract_no) + '"' + (c.contract_no === curCno ? ' selected' : '') + '>' +
        esc(c.contract_no) + ' · ' + esc(String(c.customer || '').slice(0, 24)) +
        (c.amount ? ' · ¥' + Number(c.amount).toLocaleString() : '') + '</option>';
    }).join('');
    sel.innerHTML = opts;
    if (preserve && curCno && !CONTRACTS.some(function (c) { return c.contract_no === curCno; })) curCno = '';
    if (curCno) { sel.value = curCno; }
  }

  /* ── 加载合同清单 + 阶段枚举 ── */
  async function init() {
    var body = document.getElementById('blBody');
    try {
      var [cl, cs] = await Promise.all([
        fetch(API + '/api/plm/master-contracts').then(function (r) { return r.json(); }),
        fetch(API + '/api/ontos/cost-baseline').then(function (r) { return r.json(); })
      ]);
      if (cl && cl.success) {
        CONTRACTS = cl.data || [];
        CALC_TYPES = (cs && cs.data && cs.data.calc_types) || [];
        if (CALC_TYPES.length && !CONTRACTS.length) {
          body.innerHTML = '<div class="ana-empty"><div class="icon">📄</div><div>合同主数据为空——请先在「系统›主数据›合同」导入 md_contract。</div></div>';
          fillContractSelect(); return;
        }
        fillContractSelect();
        // 默认取首个有基线的合同
        curCno = CONTRACTS.length ? CONTRACTS[0].contract_no : '';
        status('归集合同共 ' + CONTRACTS.length + ' 条（读 md_contract 主数据）');
        await loadCompare();
      } else {
        body.innerHTML = '<div class="ana-empty"><div class="icon">⚠️</div><div>' + ((cl && cl.error) || '合同清单为空') + '</div></div>';
      }
    } catch (e) {
      body.innerHTML = '<div class="ana-empty"><div class="icon">⚠️</div><div>加载失败：' + esc(e.message) + '</div></div>';
    }
  }

  /* ── 渲染四算对比（当前合同） ── */
  async function loadCompare() {
    var body = document.getElementById('blBody');
    if (!body) return;
    if (!curCno) { body.innerHTML = '<div class="ana-empty"><div class="icon">👆</div><div>请选择归集合同</div></div>'; return; }
    body.innerHTML = '<div class="ana-empty"><div class="icon">⏳</div><div>加载四算基线…</div></div>';
    try {
      var r = await fetch(API + '/api/plm/contracts/' + encodeURIComponent(curCno) + '/baseline-compare');
      var j = await r.json();
      var d = j.success ? j.data : null;
      if (!d) { body.innerHTML = '<div class="ana-empty"><div class="icon">⚠️</div><div>' + ((j && j.error) || '无基线数据') + '</div></div>'; return; }
      renderCompare(d, body);
    } catch (e) {
      body.innerHTML = '<div class="ana-empty"><div class="icon">⚠️</div><div>加载失败：' + esc(e.message) + '</div></div>';
    }
  }

  function rowFor(t, d) {
    var b = d[t.calc_type];
    if (!b) return '<tr><td>' + esc(t.cn) + '</td><td class="num">-</td><td class="num">-</td><td class="num">-</td><td class="num">-</td><td>-</td>' +
      '<td class="act"><button class="btn btn-o btn-s" onclick="Baseline.edit(\'' + esc(curCno) + '\',\'' + esc(t.calc_type) + '\')">录入</button></td></tr>';
    return '<tr><td>' + esc(t.cn) + (b.version ? ' <span style="color:var(--text2);font-size:10px">v' + b.version + '</span>' : '') + '</td>' +
      '<td class="num">' + money(b.total_income) + '</td><td class="num">' + money(b.total_cost) + '</td>' +
      '<td class="num">' + money(b.gross) + '</td><td class="num">' + pct(b.gross_rate) + '</td>' +
      '<td>' + statusBadge(b.status) + '</td>' +
      '<td class="act">' + (t.calc_type === '概算' && b.status !== '已锁定' ?
        '<button class="btn btn-c btn-s" onclick="Baseline.lock(' + b.baseline_id + ')">锁定</button>' : '') +
      '<button class="btn btn-o btn-s" onclick="Baseline.edit(\'' + esc(curCno) + '\',\'' + esc(t.calc_type) + '\')">录入</button></td></tr>';
  }

  function renderCompare(d, body) {
    var types = CALC_TYPES.length ? CALC_TYPES : [];
    var ctRows = types.length ? types.map(function (t) { return rowFor(t, d); }).join('') : '';
    // 一号目标 = 决算毛利率 − 签单毛利率（≥0 达标）
    var goalNote = d.margin_goal_note ? d.margin_goal_note : '';
    var goalHtml = '';
    if (d.margin_goal != null) {
      var ok = d.margin_goal >= 0;
      goalHtml = '<span class="bl-goal ' + (ok ? 'ok' : 'bad') + '">一号目标（决算毛利率 − 签单毛利率）=' +
        pct(d.margin_goal) + ' ' + (ok ? '✓ 达标' : '⚠ 未达标') + '</span>';
    } else if (goalNote) {
      goalHtml = '<span class="plm-note">一号目标：' + esc(goalNote) + '（需录入概算+决算后对比）</span>';
    }
    var diff = d.estimate_vs_budget != null ? money(d.estimate_vs_budget) : '';
    body.innerHTML =
      '<div class="panel"><h3>📐 ' + esc(curCno) + ' · 四算基线对比' +
      '<span style="margin-left:auto;font-size:11px;color:var(--text2);font-weight:normal">读 ontos CostBaseline · 归集锚=合同 · calc_type 动态</span></h3>' +
      '<div class="twrap" style="margin-top:6px"><table class="ana-table"><thead><tr>' +
      '<th style="text-align:left;padding-left:8px">阶段</th><th class="num">收入(元)</th><th class="num">成本(元)</th>' +
      '<th class="num">毛利(元)</th><th class="num">毛利率</th><th>状态</th><th style="text-align:right;padding-right:8px">操作</th></tr></thead>' +
      '<tbody>' + ctRows + '</tbody></table></div>' +
      '<div style="display:flex;gap:16px;align-items:center;flex-wrap:wrap;margin-top:12px;font-size:12px">' +
      (diff !== '' ? '<span class="plm-note">概算 vs 基准预算差异：<b style="color:var(--cyan2)">' + diff + '</b></span>' : '') +
      goalHtml +
      '</div></div>';
    if (goalNote && !goalHtml) {
      var el = body.querySelector('.panel');
      if (el) el.insertAdjacentHTML('beforeend', '<div style="margin-top:10px;font-size:11px;color:var(--text2)">' + esc(goalNote) + '</div>');
    }
  }

  function pick(v) {
    curCno = v || '';
    if (curCno) { var sel = document.getElementById('blContract'); if (sel) sel.value = curCno; }
    loadCompare();
  }

  /* ── 录入某阶段基线 ── */
  async function edit(contract_no, calc_type) {
    var body = { calc_type: calc_type, total_income: 0, total_cost: 0, items: [], operator: 'admin' };
    try {
      var r = await fetch(API + '/api/plm/contracts/' + encodeURIComponent(contract_no) + '/baselines');
      var j = await r.json();
      var list = (j.success && j.data) ? j.data.filter(function (b) { return b.calc_type === calc_type; }) : [];
      var b = list[list.length - 1] || {};
      var income = b.total_income != null ? b.total_income : '';
      var cost = b.total_cost != null ? b.total_cost : '';
      var incomeTxt = window.prompt('『' + calc_type + '』收入口径(元) [留空=取合同签约金额/当前值]', income === '' ? '' : income);
      if (incomeTxt === null) return;
      var costTxt = window.prompt('『' + calc_type + '』成本(元) [留空=保持当前/0]', cost === '' ? '' : cost);
      if (costTxt === null) return;
      body.total_income = incomeTxt === '' ? (income === '' ? 0 : income) : Number(incomeTxt);
      body.total_cost = costTxt === '' ? (cost === '' ? 0 : cost) : Number(costTxt);
      if (b.id) body.id = b.id;
      var p = await fetch(API + '/api/plm/contracts/' + encodeURIComponent(contract_no) + '/baselines', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
      });
      var res = await p.json();
      if (res.success === false) { status('保存失败：' + (res.error || '')); return; }
      status('已保存『' + calc_type + '』 v' + ((b.version || 0) + 1));
      await loadCompare();
    } catch (e) { status('保存异常：' + e.message); }
  }

  async function lock(bid) {
    try {
      var p = await fetch(API + '/api/plm/baselines/' + bid + '/lock', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ operator: 'admin' }) });
      var j = await p.json();
      if (j.success === false) { status('锁定失败：' + (j.error || '')); return; }
      status('概算基线已锁定');
      await loadCompare();
    } catch (e) { status('锁定异常：' + e.message); }
  }

  /* ── 重灌种子（读 md_contract） ── */
  async function seed() {
    if (!window.confirm('从 md_contract 主数据重灌「基准预算(累计实施成本预估)+核算(累计实施成本实际)」种子？将覆盖同 calc_type 现有合同级基线。')) return;
    status('正在重灌种子…');
    try {
      var p = await fetch(API + '/api/plm/seed-baselines', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ operator: 'admin' }) });
      var j = await p.json();
      status((j.success === false ? '种子失败：' + (j.error || '') : '种子完成：' + (j.coverage_note || '')));
      await loadCompare();
    } catch (e) { status('种子异常：' + e.message); }
  }

  root.Baseline = { pick: pick, edit: edit, lock: lock, seed: seed, reload: loadCompare };

  renderShell();
  init();
})(window);
