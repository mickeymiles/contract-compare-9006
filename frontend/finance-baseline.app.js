'use strict';
/* 财经 · 四算基线 独立页 —— 合同级只读投影体检（读 md_contract 主数据，去录入）。
 * 壳：renderTopMenu(activeKey=fin)、renderAccordion(财经域 sections)、面包屑。
 * 数据源：GET /api/plm/four-calc/projection（后端逐唯一业务单元投影，纯派生不改表）。
 * 语义：行=业务单元(合同)；列=签单收入 + 五阶段成本(概算/基准预算/生产预算/核算/决算)。
 *   - 预算=累计实施成本预估、核算=累计实施成本实际（均≡分项汇总，见工作记忆）
 *   - 概算/生产预算/决算 当前无独立数据源 → 数值 '-'（列仍保留）
 *   - 核算vs预算对标徽章：核算成本相对基准预算的偏差（预算内/接近/超），属四算内部对比，
 *     不承担「成本预警」场景告警（该场景独立于「成本预警」页）。
 * 本页无任何录入/锁定/种子按钮 —— 值是"取出"，不是"录入"。
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

  var STAGE_ORDER = ['概算', '基准预算', '生产预算', '核算', '决算'];   // 与后端 stages 一致
  var COLS_NUM = STAGE_ORDER.length;                                   // 成本列数（不含收入）

  function renderShell() {
    NC.renderBreadcrumb(document.getElementById('breadcrumb'), ['财经', '资金运作', '四算基线']);
    NC.renderTopMenu(document.getElementById('topMenu'), { activeKey: 'fin' });
    NC.renderAccordion(document.getElementById('navRail'), {
      rootTitle: '经营业务工作台', domainLabel: '财经', activeKey: 'fin',
      activeLink: 'fin-baseline', sections: SECTIONS
    });
  }

  function status(msg) { var el = document.getElementById('fcStatus'); if (el) el.textContent = msg; }

  var DETAIL_PAGE = 1, DETAIL_FILTER = '';
  var PAGE_SIZE = 12;
  var COST_BASIS_NOTE = '';

  /* 核算 vs 基准预算 对标徽章（四算内部对比；不承担成本预警场景告警） */
  var WARN_META = { '正常': 'badge-s', '预警': 'badge-o', '超支': 'badge-e' };
  var WARN_LBL = { '正常': '预算内', '预警': '接近预算', '超支': '超预算' };
  function warnBadge(s) {
    if (!s) return '<span class="badge badge">—</span>';
    var b = WARN_META[s] || 'badge-c';
    return '<span class="badge ' + b + '" title="核算成本相对基准预算的偏差">' + (WARN_LBL[s] || s) + '</span>';
  }

  function money(v) {
    if (v === null || v === undefined || v === '') return '<span style="color:var(--text3)">-</span>';
    var n = Number(v);
    if (isNaN(n)) return String(v);
    return '¥' + n.toLocaleString();
  }
  function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }

  function finalBadge(f) {
    return f ? '<span class="badge badge-s">已完工</span>' : '<span class="badge badge">未完</span>';
  }

  /* ════ 总览 tab：四算阶段覆盖体检 + 汇总卡（与成本预警场景分离） ════ */
  function renderOverview(summary, stageCoverage, hostEl) {
    var h = '';
    // 汇总小卡：业务单元 / 签单收入 / 有预算 / 有核算 / 已完工(近似决算条件)
    if (summary) {
      var cards = [];
      [['业务单元', summary['业务单元'] || '-', ''],
       ['签单收入合计', summary['签单收入合计'] || '-', 'c'],
       ['有预算成本(基准预算)', summary['有预算成本(基准预算)'] || '0', ''],
       ['有核算成本(核算)', summary['有核算成本(核算)'] || '0', ''],
       ['已完工(近似决算条件)', summary['已完工(近似决算条件)'] || '0', '']].forEach(function (p) {
        cards.push('<div class="card"><div class="lbl">' + p[0] + '</div><div class="val ' + p[1] + '" style="font-size:20px">' + p[2] + '</div></div>');
      });
      h += '<div class="cards" style="grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin-bottom:16px;padding:18px 22px">' + cards.join('') + '</div>';
    }
    // 主体：四算五阶段「覆盖体检」矩阵 —— 每阶段：是否接入 / 覆盖单元数 / 成本合计
    h += '<div class="panel"><h3>🧮 四算覆盖体检（概算 → 基准预算 → 生产预算 → 核算 → 决算）</h3>';
    h += '<div style="margin-bottom:10px;font-size:11px;color:var(--text2)">每行 = 一个四算阶段：反映该阶段当前「算到什么程度」——已接入数据源的阶段给覆盖数与成本合计，未接入的标 —（阶段列在明细中仍保留，数值待相应数据源接入后再投影）。</div>';
    h += '<div class="twrap"><table class="ana-table"><thead><tr>'
      + '<th style="text-align:left;padding-left:8px">四算阶段</th>'
      + '<th class="num">覆盖业务单元</th>'
      + '<th class="num">成本合计</th>'
      + '<th style="text-align:left">数据源 / 当前状态</th></tr></thead><tbody>';
    var rows = stageCoverage || [];
    for (var i = 0; i < rows.length; i++) {
      var s = rows[i];
      var covered = (s.covered || 0);
      var live = covered > 0;                       // 该阶段已实算
      var totalCell = (s.total === null || s.total === undefined)
        ? '<span style="color:var(--text3)">-</span>'
        : '¥' + Number(s.total).toLocaleString();
      var tag = live
        ? '<span class="badge badge-s">已实算</span>'
        : '<span class="badge badge">待接入</span>';
      var stageColor = live ? '' : ' style="color:var(--text3)"';
      h += '<tr>'
        + '<td class="wrap"><b' + stageColor + '>' + esc(s.stage) + '</b> ' + tag + '</div></td>'
        + '<td class="num"' + stageColor + '>' + covered + ' 个</td>'
        + '<td class="num"' + stageColor + '>' + totalCell + '</td>'
        + '<td style="text-align:left;color:var(--text2);font-size:12px">' + esc(s.source || '') + '</td></tr>';
    }
    h += '</tbody></table></div></div>';
    if (COST_BASIS_NOTE) h += '<div style="margin-top:12px;font-size:11px;color:var(--text2)">' + esc(COST_BASIS_NOTE) + '</div>';
    hostEl.innerHTML = h;
  }

  /* ════ 明细 tab：纵向表（行=业务单元；列=收入+五阶段成本+预警） ════ */
  function filterRows() {
    var all = (root.FC_ROWS || []);
    var f = (DETAIL_FILTER || '').trim().toLowerCase();
    if (!f) return all;
    return all.filter(function (r) {
      return ((r.contract_no || '') + ' ' + (r.customer || '')).toLowerCase().indexOf(f) >= 0;
    });
  }
  function renderDetailPage(page) {
    var rows = filterRows();
    var pagesAll = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
    DETAIL_PAGE = Math.min(Math.max(1, page || 1), pagesAll);
    var tbody = document.getElementById('fcDetailTbody');
    if (!tbody) return;
    var h = '';
    var start = (DETAIL_PAGE - 1) * PAGE_SIZE;
    var end = Math.min(start + PAGE_SIZE, rows.length);
    for (var i = start; i < end; i++) {
      var r = rows[i];
      var costs = r.costs || {};
      var stageCells = '';
      for (var j = 0; j < COLS_NUM; j++) {
        var st = STAGE_ORDER[j];
        var costVal = costs[st];
        var cell = (costVal === null || costVal === undefined) ? '-' : money(costVal);
        // 预警行给预算/核算列染色提示
        stageCells += '<td class="num">' + cell + '</td>';
      }
      h += '<tr>'
        + '<td class="wrap"><b>' + esc(r.contract_no || '-') + '</b><div style="font-size:10px;color:var(--text2)">' + esc((r.customer || '') + (r.biz_type ? ' · ' + r.biz_type : '')) + '</div></td>'
        + '<td class="num">' + money(r.contract_amount) + '</td>'
        + stageCells
        + '<td>' + warnBadge(r.cost_warning_status) + '</td>'
        + '<td>' + finalBadge(r.finalizable) + '</td>'
        + '<td>' + esc(r.status || '') + '</td></tr>';
    }
    if (!h) h = '<tr><td colspan="' + (5 + COLS_NUM) + '" style="text-align:center;color:var(--text2);padding:24px">无匹配业务单元</td></tr>';
    tbody.innerHTML = h;
    var pager = document.getElementById('fcDetailPager');
    if (pager) pager.innerHTML = NC.anaPager(DETAIL_PAGE, rows.length, PAGE_SIZE, 'fcDetailPager', 'FourCalc.setPage');
  }

  function renderDetailPane(rows, total, stages) {
    var pane = document.getElementById('fcDetailPane');
    if (!pane) return;
    var th = '';
    for (var j = 0; j < COLS_NUM; j++) {
      var st = STAGE_ORDER[j];
      var cls = (st === '基准预算' || st === '核算') ? '' : ' style="color:var(--text3)"';
      th += '<th class="num" title="' + esc(COST_TOOLTIP[st] || '') + '"' + cls + '>' + st + '</th>';
    }
    var h = '<div class="panel"><h3>📋 四算基线 · 合同级明细</h3>';
    h += '<div style="margin-bottom:8px;font-size:11px;color:var(--text2)">共 ' + rows.length
      + ' 个业务单元 · 数据源：md_contract 主数据（只读投影，无录入）' + ' · 列语义：' + COLS_SEM
      + ' · 阶段顺序读 ontos CostBaseline.calc_type</div>';
    h += '<div style="margin-bottom:8px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">'
      + '<input id="fcFilterInput" type="text" placeholder="按 合同号/甲方 筛选…" value="' + esc(DETAIL_FILTER)
      + '" oninput="FourCalc.setFilter(this.value)" '
      + 'style="width:260px;padding:6px 10px;background:var(--bg3);border:1px solid var(--border);color:var(--text);border-radius:6px;font-size:12px">'
      + '<a href="javascript:;" onclick="FourCalc.setFilter(\'\')" style="color:var(--cyan2);font-size:12px">清空</a>'
      + '<span style="margin-left:8px;font-size:11px;color:var(--text2)">灰字阶段 = 当前无独立数据源(待接入)</span></div>';
    h += '<div class="twrap"><table class="ana-table"><thead><tr>'
      + '<th style="text-align:left;padding-left:8px">业务单元(合同)</th>'
      + '<th class="num">签单收入</th>'
      + th
      + '<th>核算vs预算</th><th>完工</th><th>合同状态</th></tr></thead>'
      + '<tbody id="fcDetailTbody"></tbody></table></div>'
      + '<div id="fcDetailPager"></div>'
      + (COST_BASIS_NOTE ? '<div style="margin-top:8px;font-size:11px;color:var(--text2)">' + esc(COST_BASIS_NOTE) + '</div>' : '')
      + '</div>';
    pane.innerHTML = h;
    renderDetailPage(1);
  }

  /* 列语义说明 + 每阶段口径提示 */
  var COLS_SEM = '基准预算成本=累计实施成本预估；核算成本=累计实施成本实际（均≡分项汇总）';
  var COST_TOOLTIP = {
    '概算': '售前投标概算（本页当前无独立数据源 → -）',
    '基准预算': '累计实施成本预估 ≡ 硬件集成费+服务预估成本+软件预估实施费',
    '生产预算': '按里程碑拆解（CostBaselineLine 未落地 → -）',
    '核算': '累计实施成本实际 ≡ 硬件集成费实际+软件实际实施费+往年/当年服务直接/间接成本',
    '决算': '完工终态基线（无独立列，以完工标志提示 → -）'
  };

  async function load() {
    var btn = document.getElementById('btnFcReload');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ 加载中...'; }
    status('正在读取合同级四算投影（md_contract 主数据）...');
    try {
      var r = await fetch(API + '/api/plm/four-calc/projection');
      var j = await r.json();
      if (j && j.success) {
        // 后端平铺返回 {success,total,data:[rows],summary,stage_coverage,stages,cost_basis}
        root.FC_ROWS = j.data || [];
        COST_BASIS_NOTE = j.cost_basis || '';
        var summary = j.summary || {};
        var dataTotal = j.total || root.FC_ROWS.length;
        status('合同级只读投影 ' + dataTotal + ' 个业务单元 · 基准预算有值 ' + (summary['有预算成本(基准预算)'] || '0')
          + ' · 核算有值 ' + (summary['有核算成本(核算)'] || '0') + ' · 无录入');
        renderOverview(summary, j.stage_coverage || [], document.getElementById('fcOverview'));
        renderDetailPane(root.FC_ROWS, dataTotal, j.stages || STAGE_ORDER);
        if (j.stages && j.stages.length) STAGE_ORDER.length = 0, STAGE_ORDER.push.apply(STAGE_ORDER, j.stages);
      } else {
        status((j && j.error) || '四算投影为空');
        var ov = document.getElementById('fcOverview');
        if (ov) ov.innerHTML = '<div class="ana-empty"><div class="icon">⚠️</div><div>' + esc((j && j.error) || '无四算投影数据') + '</div></div>';
        var dp = document.getElementById('fcDetailPane');
        if (dp) dp.innerHTML = '<div class="ana-empty"><div>暂无明细</div></div>';
      }
    } catch (e) { status('读取四算投影失败: ' + e.message); }
    finally { if (btn) { btn.disabled = false; btn.textContent = '↻ 刷新投影'; } }
  }

  function init() {
    document.getElementById('fcContent').innerHTML = '<div id="fcHost">'
      + NC.anaTabs([{ key: 'overview', label: '📊 总览' }, { key: 'detail', label: '📋 明细' }], 'overview', 'fcHost')
      + NC.anaPane('overview', '<div id="fcOverview"></div>', true)
      + NC.anaPane('detail', '<div id="fcDetailPane"></div>', false)
      + '</div>';
    load();
  }

  root.FourCalc = {
    load: load, reload: load,
    setPage: renderDetailPage,
    setFilter: function (v) { DETAIL_FILTER = v || ''; renderDetailPage(1); }
  };

  renderShell();
  init();
})(window);
