'use strict';
/* 财经 · 毛利率 独立页 —— 顶部 Tab：总览(默认) / 明细（统一 tab 组件，见 nav.config.js）。
 * 壳：renderTopMenu(activeKey=fin)、renderAccordion(财经域 sections)、面包屑。
 * 总览：/api/gross/metrics（指标宽表，定时任务预计算）→ 年度/区域/部门 + 热力图。
 * 明细：/api/core/metrics/gross（主数据实时计算）rows → 逐条毛利率(项目/合同、金额、
 *       签单毛利、毛利率、口径、说明)分页表。
 */
(function (root) {
  var NC = root.NAV_CONFIG;
  var API = '';

  var SECTIONS = [
    { sub: '资金运作', links: [
      { key: 'fin-cycle', label: '回款周期', icon: 'cycle', href: '/finance-cycle' },
      { key: 'fin-gross', label: '毛利率', icon: 'gross', href: '/gross' },
      { key: 'fin-fund',  label: '资金占用 · 周转率', icon: 'fund', href: '/finance-fund' },
      { key: 'fin-cost',  label: '成本预警', icon: 'chart', href: '/finance-cost' }
    ] },
    { sub: '资金明细', links: [
      { key: 'fin-recv', label: '回款明细', icon: 'receipt', href: '/finance?kind=recv' },
      { key: 'fin-pay',  label: '付款明细', icon: 'pay', href: '/finance?kind=pay' }
    ] }
  ];

  function renderShell() {
    NC.renderBreadcrumb(document.getElementById('breadcrumb'), ['财经', '资金运作', '毛利率']);
    NC.renderTopMenu(document.getElementById('topMenu'), { activeKey: 'fin' });
    NC.renderAccordion(document.getElementById('navRail'), {
      rootTitle: '经营业务工作台', domainLabel: '财经', activeKey: 'fin',
      activeLink: 'fin-gross', sections: SECTIONS
    });
  }

  function status(msg) { var el = document.getElementById('grossStatus'); if (el) el.textContent = msg; }

  /* 明细分页状态 */
  var grossPage = 1;
  var GROSS_PAGE_SIZE = 10;

  function pct(v) { return (v != null) ? (v * 100).toFixed(2) + '%' : '-'; }
  function moneyWan(v) { if (v == null || v === '') return '-'; var n = Number(v); return isNaN(n) ? String(v) : Number(n.toFixed(2)).toLocaleString(); }

  /* ════ 总览 tab：/api/gross/metrics（现有内容：年度/区域/部门 + 热力图） ════ */
  function renderGrossResult(data, hostEl) {
    var h = '';
    if (data.summary) {
      var s = data.summary;
      var sizeFor = function (v) { var l = String(v).length; return l <= 6 ? '24px' : l <= 12 ? '20px' : '17px'; };
      h += '<div class="cards" style="grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:16px">';
      Object.keys(s).forEach(function (k) {
        var v = s[k];
        h += '<div class="card"><div class="lbl">' + k + '</div><div class="val c" style="font-size:' + sizeFor(v) + '">' + v + '</div></div>';
      });
      h += '</div>';
    }
    if (data.year_rows && data.year_rows.length) {
      h += '<div class="panel"><h3>📅 年度签单毛利率</h3>';
      h += '<div class="twrap"><table class="ana-table"><thead><tr><th>年份</th><th>合同额(万)</th><th>签单毛利(万)</th><th>签单毛利率</th></tr></thead><tbody>';
      data.year_rows.forEach(function (r) {
        h += '<tr><td>' + r['年份'] + '</td><td class="num">' + r['合同额(万)'] + '</td><td class="num">' + r['签单毛利(万)'] + '</td><td class="num">' + pct(r['签单毛利率']) + '</td></tr>';
      });
      h += '</tbody></table></div></div>';
    }
    if (data.region_rows && data.region_rows.length) {
      h += '<div class="panel"><h3>🗺️ 区域维度签单毛利率同比（2026 vs 2025）</h3>';
      h += '<div class="twrap"><table class="ana-table"><thead><tr><th>区域</th><th>2026合同额(万)</th><th>2026签单毛利率</th><th>2025合同额(万)</th><th>2025签单毛利率</th><th>同比(百分点)</th></tr></thead><tbody>';
      data.region_rows.forEach(function (r) {
        var diff = r['同比(百分点)'];
        var diffCls = (diff > 0) ? 'pos' : (diff < 0 ? 'neg' : '');
        var diffTxt = (diff == null) ? '-' : ((diff > 0 ? '+' : '') + diff);
        h += '<tr><td class="wrap">' + r['区域'] + '</td><td class="num">' + r['2026合同额(万)'] + '</td><td class="num">' + pct(r['2026签单毛利率']) + '</td><td class="num">' + r['2025合同额(万)'] + '</td><td class="num">' + pct(r['2025签单毛利率']) + '</td><td class="num ' + diffCls + '">' + diffTxt + '</td></tr>';
      });
      h += '</tbody></table></div></div>';
    }
    if (data.dept_rows && data.dept_rows.length) {
      h += '<div class="panel"><h3>🏢 部门维度签单毛利率（2026 vs 2025）</h3>';
      h += '<div class="twrap"><table class="ana-table"><thead><tr><th>部门</th><th>2026合同额(万)</th><th>2026签单毛利率</th><th>2025合同额(万)</th><th>2025签单毛利率</th></tr></thead><tbody>';
      data.dept_rows.forEach(function (r) {
        h += '<tr><td class="wrap">' + r['部门'] + '</td><td class="num">' + r['2026合同额(万)'] + '</td><td class="num">' + pct(r['2026签单毛利率']) + '</td><td class="num">' + r['2025合同额(万)'] + '</td><td class="num">' + pct(r['2025签单毛利率']) + '</td></tr>';
      });
      h += '</tbody></table></div></div>';
    }
    // 部门 × 区域 签单毛利率同比变化热力图 #CC-008
    h += renderHeatmap(data.dept_region_rows);
    if (!data.year_rows || !data.year_rows.length) {
      h += '<div class="ana-empty"><div class="icon">📈</div><div>宽表暂无数据</div></div>';
    }
    (hostEl || document.body).innerHTML = h;
  }

  function heatClass(diff) {
    if (diff === null || diff === undefined) return 'heat-empty';
    if (diff >= 20) return 'heat-up-20';
    if (diff >= 5) return 'heat-up-5';
    if (diff >= 2) return 'heat-up-2';
    if (diff > -2) return 'heat-flat';
    if (diff > -5) return 'heat-down-2';
    if (diff > -20) return 'heat-down-5';
    return 'heat-down-20';
  }

  function heatCellHtml(cell, extraClass) {
    var cls = ['heat-cell', heatClass(cell ? cell.diff : null), extraClass || ''].filter(Boolean).join(' ').trim();
    if (!cell || !cell.hasData || cell.rate === null || cell.rate === undefined) {
      return '<td class="' + cls + '"></td>';
    }
    var rateTxt = (cell.rate * 100).toFixed(1) + '%';
    var diffTxt = (cell.diff === null || cell.diff === undefined) ? '-' : ((cell.diff >= 0 ? '+' : '') + cell.diff.toFixed(1) + 'pct');
    return '<td class="' + cls + '"><div class="heat-rate">' + rateTxt + '</div><div class="heat-diff">' + diffTxt + '</div></td>';
  }

  function renderHeatmap(dr) {
    if (!dr || !dr.depts || !dr.depts.length) return '';
    var h = '<div class="panel"><h3>🏢×🗺️ 部门 × 区域 签单毛利率同比变化热力图</h3>';
    h += '<div class="heatmap-note">空白 = 未签约，不纳入比较</div>';
    h += '<div class="twrap"><table class="heatmap-table"><thead><tr><th class="heat-corner">部门 \\ 区域</th>';
    dr.regions.forEach(function (r) { h += '<th class="heat-col-header">' + r + '</th>'; });
    h += '<th class="heat-col-header heat-total-col">小计</th></tr></thead><tbody>';

    h += '<tr><td class="row-label row-total">小计</td>';
    dr.regions.forEach(function (r) { h += heatCellHtml(dr.totals.byRegion[r], 'col-total'); });
    h += '<td class="heat-cell heat-empty heat-corner"></td></tr>';

    dr.depts.forEach(function (d) {
      h += '<tr><td class="row-label">' + d + '</td>';
      dr.regions.forEach(function (r) { h += heatCellHtml(dr.cells[d][r], ''); });
      h += heatCellHtml(dr.totals.byDept[d], 'row-total');
      h += '</tr>';
    });
    h += '</tbody></table></div></div>';
    return h;
  }

  /* ════ 明细 tab：/api/core/metrics/gross rows（分页） ════ */
  function renderGrossDetailPage(page) {
    var rows = (root.GROSS_DETAIL_ROWS || []);
    var pagesAll = Math.max(1, Math.ceil(rows.length / GROSS_PAGE_SIZE));
    grossPage = Math.min(Math.max(1, page || 1), pagesAll);
    var tbody = document.getElementById('grossDetailTbody');
    if (!tbody) return;
    var h = '';
    var start = (grossPage - 1) * GROSS_PAGE_SIZE;
    var end = Math.min(start + GROSS_PAGE_SIZE, rows.length);
    for (var i = start; i < end; i++) {
      var r = rows[i];
      var rate = r.gross_rate;
      h += '<tr><td class="wrap">' + (r.contract_no || '-') + '</td><td class="wrap">' + (r.project_no || '-') + '</td>'
        + '<td class="wrap">' + (r.name || '-') + '</td><td class="num">¥' + moneyWan((r.sign_amount == null) ? '-' : r.sign_amount) + '</td>'
        + '<td class="num">¥' + moneyWan((r.sign_gross_profit == null) ? '-' : r.sign_gross_profit) + '</td>'
        + '<td class="num">' + pct(rate) + '</td><td>' + (r.method || '-') + '</td>'
        + '<td class="wrap">' + (r.note || '-') + '</td></tr>';
    }
    if (!h) h = '<tr><td colspan="8" style="text-align:center;color:var(--text2);padding:20px">暂无明细</td></tr>';
    tbody.innerHTML = h;
    var wrap = document.getElementById('grossDetailPager');
    if (wrap) wrap.innerHTML = NC.anaPager(grossPage, rows.length, GROSS_PAGE_SIZE, 'grossDetailPager', 'Gross.setDetailPage');
  }

  async function loadMetrics(refresh) {
    var runBtn = document.getElementById('btnGrossRun');
    if (runBtn) { runBtn.disabled = true; runBtn.textContent = '⏳ ' + (refresh ? '重算中...' : '加载中...'); }
    status(refresh ? '正在全量重算毛利率（实时计算）...' : '读取指标宽表...');
    try {
      var r = await fetch(API + '/api/gross/metrics');
      var d = await r.json();
      if (d.success) {
        status((refresh ? '重算完成（实时计算）' : '已读取快照（秒级）') + ' · 数据来源：指标宽表（定时任务「签单毛利指标计算」预计算）+ 主数据毛利率');
        renderGrossResult(d, document.getElementById('grossOverview'));
      } else {
        status(d.error || '宽表为空');
        document.getElementById('grossOverview').innerHTML = '<div class="ana-empty"><div class="icon">📈</div><div>' + (d.error || '指标宽表为空，请先在 9007 长期任务执行「签单毛利指标计算」') + '</div></div>';
      }
      await loadGrossDetail(refresh);
    } catch (e) { status('读取宽表失败: ' + e.message); }
    finally { if (runBtn) { runBtn.disabled = false; runBtn.textContent = '🔄 刷新宽表'; } }
  }

  async function loadGrossDetail(refresh) {
    var pane = document.getElementById('grossDetailPane');
    if (pane) pane.innerHTML = '<div class="ana-empty"><div>' + (refresh ? '正在重算...' : '读取主数据毛利率明细...') + '</div></div>';
    try {
      var r = await fetch(API + '/api/core/metrics/gross' + (refresh ? '?refresh=1' : ''));
      var j = await r.json();
      var rows = (j && j.success && j.data && j.data.rows) || [];
      root.GROSS_DETAIL_ROWS = rows;
      if (pane) {
        var h = '<div class="panel"><h3>📋 毛利率明细</h3>';
        h += '<div style="margin-bottom:8px;font-size:11px;color:var(--text2)">共 ' + rows.length + ' 条 · 数据源：/api/core/metrics/gross（主数据'
          + (refresh ? '实时计算' : '快照，秒级') + '）' + (j.updated_at ? ' · 更新于 ' + j.updated_at : '') + '</div>';
        h += '<div class="twrap"><table class="ana-table"><thead><tr>'
          + '<th style="text-align:left;padding-left:8px">合同编号</th><th style="text-align:left;padding-left:8px">项目编号</th>'
          + '<th style="text-align:left;padding-left:8px">项目名称</th><th style="text-align:right;padding-right:8px">合同额</th>'
          + '<th style="text-align:right;padding-right:8px">签单毛利</th><th style="text-align:right;padding-right:8px">毛利率</th>'
          + '<th>口径</th><th style="text-align:left;padding-left:8px">说明</th></tr></thead>'
          + '<tbody id="grossDetailTbody"></tbody></table></div><div id="grossDetailPager"></div></div>';
        pane.innerHTML = h;
        renderGrossDetailPage(1);
      }
    } catch (e) {
      status('读取毛利率明细失败: ' + e.message);
    }
  }

  function init() {
    document.getElementById('grossContent').innerHTML = '<div id="grossHost">'
      + NC.anaTabs([{ key: 'overview', label: '📊 总览' }, { key: 'detail', label: '📋 明细' }], 'overview', 'grossHost')
      + NC.anaPane('overview', '<div id="grossOverview"></div>', true)
      + NC.anaPane('detail', '<div id="grossDetailPane"></div>', false)
      + '</div>';
    loadMetrics();
  }

  root.Gross = {
    run: function () { return loadMetrics(true); }, load: loadMetrics,
    loadDetail: loadGrossDetail,
    setDetailPage: renderGrossDetailPage
  };

  renderShell();
  init();
})(window);