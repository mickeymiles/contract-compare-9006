'use strict';
/* 财经 · 四算基线 独立页 —— 合同级只读投影体检（读 md_contract 主数据，去录入）。
 * 壳：renderTopMenu(activeKey=fin)、renderAccordion(财经域 sections)、面包屑。
 * 数据源：GET /api/plm/four-calc/projection（后端逐唯一业务单元投影，纯派生不改表）。
 * 语义：行=业务单元(合同)；列=签单收入 + 五阶段成本(概算/基准预算/生产预算/核算/决算)。
 *   - 预算=累计实施成本预估、核算=累计实施成本实际（均≡分项汇总，见工作记忆）
 *   - 概算/生产预算/决算 当前无独立数据源 → 数值 '-'（列仍保留）
 *   - 成本预警状态 = 本体 F-project-cost-warning（预算 vs 核算）
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

  /* 预警状态徽章 */
  var WARN_META = { '正常': 'badge-s', '预警': 'badge-o', '超支': 'badge-e' };
  function warnBadge(s) {
    if (!s) return '<span class="badge badge">—</span>';
    var b = WARN_META[s] || 'badge-c';
    return '<span class="badge ' + b + '">' + s + '</span>';
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

  /* ════ 总览 tab：汇总卡 + 预警状态分布 + 饼图 ════ */
  function renderOverview(summary, warnCount, hostEl) {
    var h = '';
    if (summary) {
      var s = summary;
      var cards = [];
      Object.keys(s).forEach(function (k) {
        var v = s[k];
        var cls = '';
        if (k.indexOf('超支') >= 0 || k.indexOf('预警') >= 0) cls = ' r';
        else if (k.indexOf('收入') >= 0 || k.indexOf('成本') >= 0) cls = ' c';
        cards.push('<div class="card"><div class="lbl">' + k + '</div><div class="val' + cls + '" style="font-size:21px">' + v + '</div></div>');
      });
      h += '<div class="cards" style="grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin-bottom:16px;padding:18px 22px">' + cards.join('') + '</div>';
    }
    // 预警状态分布（基于行内本体判定）
    h += '<div class="panel"><h3>⚠ 成本预警状态分布（预算 vs 核算 · 本体 F-project-cost-warning）</h3>';
    h += '<div class="cards" style="grid-template-columns:repeat(3,1fr);gap:14px;margin:0 0 14px;padding:0">';
    [['正常', 'g'], ['预警', 'o'], ['超支', 'r']].forEach(function (p) {
      var v = (warnCount && warnCount[p[0]]) || 0;
      h += '<div class="card" style="text-align:center"><div class="lbl">' + p[0] + '</div>'
        + '<div class="val ' + p[1] + '" style="font-size:26px">' + v + ' 个</div></div>';
    });
    h += '</div><div id="fcWarnChart" style="width:100%;height:250px"></div></div>';
    if (COST_BASIS_NOTE) h += '<div style="margin-top:12px;font-size:11px;color:var(--text2)">' + esc(COST_BASIS_NOTE) + '</div>';
    hostEl.innerHTML = h;
    renderWarnChart(warnCount);
  }

  function renderWarnChart(warnCount) {
    if (!root.echarts) return;
    var el = document.getElementById('fcWarnChart');
    if (!el) return;
    var c = echarts.getInstanceByDom(el);
    if (c) { try { c.dispose(); } catch (e) {} }
    var chart = echarts.init(el);
    chart.setOption({
      tooltip: { trigger: 'item', formatter: '{b}: {c} 个 ({d}%)' },
      legend: { bottom: 0, textStyle: { color: '#8fa3bf' } },
      series: [{
        type: 'pie', radius: ['42%', '68%'], center: ['50%', '44%'],
        itemStyle: { borderRadius: 6, borderColor: '#1a1a2e', borderWidth: 2 },
        label: { color: '#e0e7f5', formatter: '{b}\n{c} 个' },
        data: [
          { value: warnCount['正常'] || 0, name: '正常', itemStyle: { color: '#34d399' } },
          { value: warnCount['预警'] || 0, name: '预警', itemStyle: { color: '#fbbf24' } },
          { value: warnCount['超支'] || 0, name: '超支', itemStyle: { color: '#f87171' } }
        ]
      }]
    });
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
      + '<th>成本预警</th><th>完工</th><th>合同状态</th></tr></thead>'
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
        var data = j.data || {};
        root.FC_ROWS = data.data || [];
        COST_BASIS_NOTE = data.cost_basis || '';
        var summary = data.summary || {};
        // 从行内计算预警分布（更可靠，含无预算不判）
        var warnCount = { '正常': 0, '预警': 0, '超支': 0 };
        (root.FC_ROWS).forEach(function (x) {
          if (warnCount[x.cost_warning_status] !== undefined) warnCount[x.cost_warning_status]++;
          else warnCount['正常']++;
        });
        status('合同级只读投影 ' + (data.total || 0) + ' 个业务单元 · 预算有值 ' + (summary['有预算成本'] || '0')
          + ' · 核算有值 ' + (summary['有核算成本'] || '0') + ' · 无录入');
        renderOverview(summary, warnCount, document.getElementById('fcOverview'));
        renderDetailPane(root.FC_ROWS, data.total, data.stages || STAGE_ORDER);
        if (data.stages && data.stages.length) STAGE_ORDER.length = 0, STAGE_ORDER.push.apply(STAGE_ORDER, data.stages);
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
