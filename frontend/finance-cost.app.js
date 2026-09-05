'use strict';
/* 财经 · 成本预警 独立页 —— 顶部 Tab：总览(默认) / 明细（统一 tab 组件，见 nav.config.js）。
 * 壳：renderTopMenu(activeKey=fin)、renderAccordion(财经域 sections)、面包屑。
 * 数据源：/api/core/metrics/cost-warning（★同源薄壳：后端直接调共享本体 ontos.abox_cost，
 *   与 9007 智能体 ontology_compute 同一份实现，平台侧不再自建取数 SQL）。
 * ★口径收敛到 ontos：预算=md_contract.累计实施成本预估、当前成本=md_contract.累计实施成本实际
 *   （均 ≡ 本体 COST_FORMULA_POLICY 声明的分项汇总），判定统一走 F-project-cost-warning。
 *   不再用平台自拼的 service_est 单分项 / finance_detail 付款口径。概算不参与成本预警。
 * ★预估成本(est_cost)：当前成本滞后约 2 个月(8月看6月底、9月看7月底)，需 PMO 按工单/人员投入/
 *   差旅等补估才反映当前真实状态；现阶段无预估源=0，不参与剩余成本/完成比/预警判定，后续接入展开。
 * 与四算页(同源预算/核算)差异：本页是「预算 vs 核算成本」的告警场景；四算页是各阶段展示。
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
    NC.renderBreadcrumb(document.getElementById('breadcrumb'), ['财经', '资金运作', '成本预警']);
    NC.renderTopMenu(document.getElementById('topMenu'), { activeKey: 'fin' });
    NC.renderAccordion(document.getElementById('navRail'), {
      rootTitle: '经营业务工作台', domainLabel: '财经', activeKey: 'fin',
      activeLink: 'fin-cost', sections: SECTIONS
    });
  }

  function status(msg) { var el = document.getElementById('costStatus'); if (el) el.textContent = msg; }

  /* 明细分页状态 */
  var costPage = 1, costFilter = '';
  var COST_PAGE_SIZE = 10;

  var STATUS_META = {
    '正常': { badge: 'badge-s', text: '正常' },
    '预警': { badge: 'badge-o', text: '预警' },
    '超支': { badge: 'badge-e', text: '超支' }
  };
  function statusBadge(s) {
    var m = STATUS_META[s] || { badge: 'badge-c', text: s || '-' };
    return '<span class="badge ' + m.badge + '">' + m.text + '</span>';
  }

  function money(v, plain) {
    if (v === null || v === undefined || v === '') return '-';
    var n = Number(v);
    if (isNaN(n)) return String(v);
    if (plain !== false) return '¥' + n.toLocaleString();
    return n.toLocaleString();
  }
  function ratioPct(v) {
    if (v === null || v === undefined || v === '') return '-';
    return (Number(v) * 100).toFixed(1) + '%';
  }

  /* ════ 总览 tab：汇总卡 + 状态分布 + 饼图 ════ */
  function renderOverview(data, hostEl) {
    var h = '';
    if (data.summary) {
      var s = data.summary;
      h += '<div class="cards" style="grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:16px;margin-bottom:16px;padding:20px 24px">';
      Object.keys(s).forEach(function (k) {
        var v = s[k];
        var cls = (k.indexOf('超支') >= 0) ? ' r' : (k.indexOf('预警') >= 0) ? ' o' : (k.indexOf('数额') >= 0 || k.indexOf('成本') >= 0) ? ' c' : '';
        h += '<div class="card"><div class="lbl">' + k + '</div><div class="val' + cls + '" style="font-size:22px">' + v + '</div></div>';
      });
      h += '</div>';
    }
    var sc = data.status_count || {};
    h += '<div class="panel"><h3>📊 预警状态分布</h3>';
    h += '<div class="cards" style="grid-template-columns:repeat(3,1fr);gap:14px;margin:0 0 16px;padding:0">';
    [['正常', 'g'], ['预警', 'o'], ['超支', 'r']].forEach(function (pair) {
      var k = pair[0], cls = pair[1], v = sc[k] || 0;
      h += '<div class="card" style="text-align:center"><div class="lbl">' + k + '</div>'
        + '<div class="val ' + cls + '" style="font-size:26px">' + v + ' 个</div></div>';
    });
    h += '</div>';
    h += '<div id="costStatusChart" style="width:100%;height:280px"></div></div>';
    (hostEl || document.body).innerHTML = h;
    renderStatusChart(sc);
  }

  function renderStatusChart(sc) {
    if (!root.echarts) return;
    var el = document.getElementById('costStatusChart');
    if (!el) return;
    var c = echarts.getInstanceByDom(el);
    if (c) { try { c.dispose(); } catch (e) {} }
    var chart = echarts.init(el);
    chart.setOption({
      tooltip: { trigger: 'item', formatter: '{b}: {c} 个 ({d}%)' },
      legend: { bottom: 0, textStyle: { color: '#8fa3bf' } },
      series: [{
        type: 'pie', radius: ['42%', '68%'], center: ['50%', '45%'],
        itemStyle: { borderRadius: 6, borderColor: '#1a1a2e', borderWidth: 2 },
        label: { color: '#e0e7f5', formatter: '{b}\n{c} 个' },
        data: [
          { value: sc['正常'] || 0, name: '正常', itemStyle: { color: '#34d399' } },
          { value: sc['预警'] || 0, name: '预警', itemStyle: { color: '#fbbf24' } },
          { value: sc['超支'] || 0, name: '超支', itemStyle: { color: '#f87171' } }
        ]
      }]
    });
  }

  /* ════ 明细 tab：分页表（项目/概算/预算/当前成本/剩余成本/完成比/状态/说明） ════ */
  function filterRows() {
    var all = (root.COST_ROWS || []);
    var f = (costFilter || '').trim().toLowerCase();
    if (!f) return all;
    return all.filter(function (r) {
      var x = ((r.project_no || '') + ' ' + (r.contract_no || '') + ' ' + (r.name || '')).toLowerCase();
      return x.indexOf(f) >= 0;
    });
  }
  function renderDetailPage(page) {
    var rows = filterRows();
    var pagesAll = Math.max(1, Math.ceil(rows.length / COST_PAGE_SIZE));
    costPage = Math.min(Math.max(1, page || 1), pagesAll);
    var tbody = document.getElementById('costDetailTbody');
    if (!tbody) return;
    var h = '';
    var start = (costPage - 1) * COST_PAGE_SIZE;
    var end = Math.min(start + COST_PAGE_SIZE, rows.length);
    for (var i = start; i < end; i++) {
      var r = rows[i];
      h += '<tr><td class="wrap">' + (r.project_no || '-') + '</td>'
        + '<td class="wrap">' + (r.contract_no || '-') + '</td>'
        + '<td class="wrap">' + (r.name || '-') + '</td>'
        + '<td class="num">' + money(r.budget) + '</td>'
        + '<td class="num">' + money(r.current_cost) + '</td>'
        + '<td class="num">' + money(r.est_cost) + '</td>'
        + '<td class="num">' + money(r.remaining) + '</td>'
        + '<td class="num">' + ratioPct(r.budget_ratio) + '</td>'
        + '<td>' + statusBadge(r.status) + '</td>'
        + '<td class="wrap">' + (r.note || '-') + '</td></tr>';
    }
    if (!h) h = '<tr><td colspan="10" style="text-align:center;color:var(--text2);padding:20px">暂无明细</td></tr>';
    tbody.innerHTML = h;
    var wrap = document.getElementById('costDetailPager');
    if (wrap) wrap.innerHTML = NC.anaPager(costPage, rows.length, COST_PAGE_SIZE, 'costDetailPager', 'CostWarning.setDetailPage');
  }

  function renderDetailPane(rows, updatedAt, refresh) {
    var pane = document.getElementById('costDetailPane');
    if (!pane) return;
    var h = '<div class="panel"><h3>📋 成本预警明细</h3>';
    h += '<div style="margin-bottom:8px;font-size:11px;color:var(--text2)">共 ' + rows.length
      + ' 个业务单元 · 数据源：/api/core/metrics/cost-warning（md_contract 权威列 + 本体 F-project-cost-warning）'
      + (updatedAt ? ' · 更新于 ' + updatedAt : '') + '</div>';
    h += '<div style="margin-bottom:8px;font-size:11px;color:var(--text3)">口径(ontos COST_FORMULA_POLICY)：预算=累计实施成本预估；当前成本=累计实施成本实际（均≡分项汇总）。'
      + '⚠ 当前成本滞后约 2 个月（如 8 月看 6 月底、9 月看 7 月底）——「预估成本」= ontos F-project-cost-warning 的 wo_est_cost（工单预估，来源 F-workorder-cost-rollup），'
      + '由 PMO 依据工单/人员投入/差旅等补估，补齐时差后「当前成本+预估成本」才是当前真实状态；剩余成本/完成比/状态均由 ontos 按当前预估口径计算。现阶段预估源未落地=0，故与滞后口径一致。</div>';
    h += '<div style="margin-bottom:8px;display:flex;gap:8px;align-items:center">'
      + '<input id="costFilterInput" type="text" placeholder="按 项目号/合同号/名称 筛选…" value="' + (costFilter || '').replace(/"/g, '&quot;')
      + '" oninput="CostWarning.setFilter(this.value)" '
      + 'style="width:260px;padding:6px 10px;background:var(--bg3);border:1px solid var(--border);color:var(--text);border-radius:6px;font-size:12px">'
      + '<a href="javascript:;" onclick="CostWarning.setFilter(\'\')" style="color:var(--cyan2);font-size:12px">清空</a></div>';
    h += '<div class="twrap"><table class="ana-table"><thead><tr>'
      + '<th style="text-align:left;padding-left:8px">项目编号</th>'
      + '<th style="text-align:left;padding-left:8px">合同编号</th>'
      + '<th style="text-align:left;padding-left:8px">项目名称</th>'
      + '<th class="num" title="累计实施成本预估(≡硬件集成费+服务预估成本+软件预估实施费)">预算</th>'
      + '<th class="num" title="累计实施成本实际(≡六分项实际)，滞后约2个月">当前成本</th>'
      + '<th class="num" title="PMO 按工单/人员投入/差旅等补估(= ontos wo_est_cost)，补齐当前成本滞后时差；现阶段未接入=0">预估成本</th>'
      + '<th class="num" title="剩余 = 预算 - 当前成本 - 预估成本（当前预估口径，ontos 计算）">剩余成本</th>'
      + '<th class="num" title="完成比 = (当前成本+预估成本) / 预算（当前预估口径，ontos 计算）">预算完成比</th>'
      + '<th>预警状态</th><th style="text-align:left;padding-left:8px">说明</th></tr></thead>'
      + '<tbody id="costDetailTbody"></tbody></table></div><div id="costDetailPager"></div></div>';
    pane.innerHTML = h;
    renderDetailPage(1);
  }

  async function loadMetrics(refresh) {
    var runBtn = document.getElementById('btnCostRun');
    if (runBtn) { runBtn.disabled = true; runBtn.textContent = '⏳ ' + (refresh ? '重算中...' : '加载中...'); }
    status(refresh ? '正在重算成本预警（刷新快照）...' : '读取成本预警（md_contract 权威列 + 本体 F-project-cost-warning）...');
    try {
      var r = await fetch(API + '/api/core/metrics/cost-warning' + (refresh ? '?refresh=1' : ''));
      var j = await r.json();
      if (j && j.success && j.data) {
        var data = j.data;
        root.COST_ROWS = data.rows || [];
        var sc = data.status_count || {};
        status('成本预警（ontos 口径）· ' + data.total + ' 个业务单元 · 正常 ' + (sc['正常'] || 0)
          + ' / 预警 ' + (sc['预警'] || 0) + ' / 超支 ' + (sc['超支'] || 0));
        renderOverview(data, document.getElementById('costOverview'));
        renderDetailPane(root.COST_ROWS, j.updated_at, refresh);
      } else {
        status((j && j.error) || '成本预警数据为空');
        var ov = document.getElementById('costOverview');
        if (ov) ov.innerHTML = '<div class="ana-empty"><div class="icon">⚠️</div><div>' + ((j && j.error) || '无成本预警数据') + '</div></div>';
        var dp = document.getElementById('costDetailPane');
        if (dp) dp.innerHTML = '<div class="ana-empty"><div>暂无明细</div></div>';
      }
    } catch (e) { status('读取成本预警失败: ' + e.message); }
    finally { if (runBtn) { runBtn.disabled = false; runBtn.textContent = '▶ 执行分析'; } }
  }

  function init() {
    document.getElementById('costContent').innerHTML = '<div id="costHost">'
      + NC.anaTabs([{ key: 'overview', label: '📊 总览' }, { key: 'detail', label: '📋 明细' }], 'overview', 'costHost')
      + NC.anaPane('overview', '<div id="costOverview"></div>', true)
      + NC.anaPane('detail', '<div id="costDetailPane"></div>', false)
      + '</div>';
    loadMetrics();
  }

  root.CostWarning = {
    run: function () { return loadMetrics(true); }, load: loadMetrics,
    setDetailPage: renderDetailPage,
    setFilter: function (v) { costFilter = v || ''; renderDetailPage(1); }
  };

  renderShell();
  init();
})(window);