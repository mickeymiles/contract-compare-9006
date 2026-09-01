'use strict';
/* 财经 · 资金占用 · 周转率 独立页 —— 1:1 复刻旧门户 index.html openFundOccupancy。
 * 壳：renderTopMenu(activeKey=fin)、renderAccordion(财经域 sections)、面包屑。
 * 数据：/api/core/metrics/fund（finance_detail FIFO 冲抵 + core_project 维度，见 backend/core/project_metrics.py）。
 * 内容逐一照搬旧门户：汇总卡(summary) / 多维 Tab(总览/区域/客户集合/时间/风险预警) /
 * 明细表(合同编号/累计付款/累计收款/净现金流/当前占用/片段数…/同比) / 详情弹窗(垫资片段/流水/现金流)。
 * 说明：年化成本率按旧门户常量 3% 补齐；客户键沿用旧门户确定性脱敏编码。
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

  var data = null;                 // /api/core/metrics/fund 返回 data
  var fundDimCharts = {}, fundRiskData = null;

  function renderShell() {
    NC.renderBreadcrumb(document.getElementById('breadcrumb'), ['财经', '资金运作', '资金占用 · 周转率']);
    NC.renderTopMenu(document.getElementById('topMenu'), { activeKey: 'fin' });
    NC.renderAccordion(document.getElementById('navRail'), {
      rootTitle: '经营业务工作台', domainLabel: '财经', activeKey: 'fin',
      activeLink: 'fin-fund', sections: SECTIONS
    });
  }

  /* ── echarts 暗色主题 + 中国地图 GeoJSON（与旧门户 index.html 一致） ── */
  if (window.echarts) {
    echarts.registerTheme('cc-dark', {
      textStyle: { color: '#dbe4f5' },
      legend: { textStyle: { color: '#a3b3d6', fontSize: 11 }, pageTextStyle: { color: '#a3b3d6' }, inactiveColor: '#3a4a6a' },
      title: { textStyle: { color: '#e0e6f5', fontWeight: 600, fontSize: 13 }, subtextStyle: { color: '#8893aa' } },
      tooltip: { backgroundColor: 'rgba(10,18,41,.96)', borderColor: '#2a3a60', textStyle: { color: '#e0e6f5' } },
      categoryAxis: { axisLine: { lineStyle: { color: '#2a3a60' } }, axisTick: { lineStyle: { color: '#2a3a60' } }, axisLabel: { color: '#a3b3d6' }, splitLine: { show: false, lineStyle: { color: '#16223f' } } },
      valueAxis: { axisLine: { show: false, lineStyle: { color: '#2a3a60' } }, axisTick: { show: false }, axisLabel: { color: '#a3b3d6' }, splitLine: { lineStyle: { color: '#16223f', type: 'dashed' } } }
    });
  }
  var chinaGeoJson = null;
  fetch('/china.json').then(function (r) { return r.json(); }).then(function (d) {
    chinaGeoJson = d;
    if (window.echarts) { try { echarts.registerMap('china', d); } catch (e) {} }
  }).catch(function () {});

  /* 六大区/省份映射 + 地图工具（与旧门户回款周期块一致） */
  var PC_AREA_PROVINCES = {
    '华北': ['北京市', '天津市', '河北省', '山西省', '内蒙古自治区'],
    '华东': ['上海市', '江苏省', '浙江省', '安徽省', '福建省', '江西省', '山东省'],
    '东北': ['辽宁省', '吉林省', '黑龙江省'],
    '华中': ['河南省', '湖北省', '湖南省'],
    '华南': ['广东省', '广西壮族自治区', '海南省'],
    '西部': ['重庆市', '四川省', '贵州省', '云南省', '西藏自治区', '陕西省', '甘肃省', '青海省', '宁夏回族自治区', '新疆维吾尔自治区']
  };
  var PC_PROV_FULL = { '北京': '北京市', '天津': '天津市', '河北': '河北省', '山西': '山西省', '内蒙古': '内蒙古自治区', '辽宁': '辽宁省', '吉林': '吉林省', '黑龙江': '黑龙江省', '上海': '上海市', '江苏': '江苏省', '浙江': '浙江省', '安徽': '安徽省', '福建': '福建省', '江西': '江西省', '山东': '山东省', '河南': '河南省', '湖北': '湖北省', '湖南': '湖南省', '广东': '广东省', '广西': '广西壮族自治区', '海南': '海南省', '重庆': '重庆市', '四川': '四川省', '贵州': '贵州省', '云南': '云南省', '西藏': '西藏自治区', '陕西': '陕西省', '甘肃': '甘肃省', '青海': '青海省', '宁夏': '宁夏回族自治区', '新疆': '新疆维吾尔自治区', '台湾': '台湾省', '香港': '香港特别行政区', '澳门': '澳门特别行政区' };
  var PC_POLYCLIP_URL = 'https://cdn.jsdelivr.net/npm/polygon-clipping@0.15.3/dist/polygon-clipping.umd.min.js';
  function pcLoadScript(src) { return new Promise(function (resolve) { var s = document.createElement('script'); s.src = src; s.onload = function () { resolve(window.polygonClipping || null); }; s.onerror = function () { resolve(null); }; document.head.appendChild(s); }); }
  function pcFlatten(coords, out) { coords.forEach(function (c) { if (typeof c[0] === 'number') out.push(c); else pcFlatten(c, out); }); return out; }
  function pcBBoxCenter(coords) { var pts = []; pcFlatten(coords, pts); if (!pts.length) return null; var xs = pts.map(function (p) { return p[0]; }), ys = pts.map(function (p) { return p[1]; }); return [(Math.min.apply(null, xs) + Math.max.apply(null, xs)) / 2, (Math.min.apply(null, ys) + Math.max.apply(null, ys)) / 2]; }
  function pcFmtNum(n, d) { d = d === undefined ? 0 : d; if (n == null) return '-'; return Number(n).toLocaleString('zh-CN', { minimumFractionDigits: d, maximumFractionDigits: d }); }
  function pcEsc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }

  /* ── 工具 ── */
  function status(msg) { var el = document.getElementById('fundStatus'); if (el) el.textContent = msg; }
  function fundMoney(v) {
    var n = Number(v || 0);
    if (Math.abs(n) >= 100000000) return (n / 100000000).toFixed(1) + '亿';
    if (Math.abs(n) >= 10000) return (n / 10000).toFixed(0) + '万';
    return String(n || 0);
  }
  function num(v) {
    if (v === null || v === undefined || v === '') return '-';
    var n = Number(v);
    return isNaN(n) ? String(v) : n.toLocaleString('zh-CN');
  }
  async function fundFetch(url) {
    try { var r = await fetch(url); return await r.json(); } catch (e) { return { success: false, error: e.message }; }
  }

  /* ── 表格同比变化率单元格（CC-006 FR-13） ── */
  function fundOccYoyTd(cur, prev) {
    var c = Number(cur || 0), p = Number(prev || 0);
    if (p === 0 && c === 0) return '<td class="num" style="color:var(--text2)">—</td>';
    if (p === 0) return '<td class="num" style="color:#ff4d4f;font-weight:600">↥ 新增占用</td>';
    var pct = (c - p) / p * 100;
    var color = 'var(--text2)', arrow = '—', txt = '0.0%';
    if (pct > 0) { color = '#ff4d4f'; arrow = '↥'; txt = '+' + pct.toFixed(1) + '%'; }
    else if (pct < 0) { color = '#52c41a'; arrow = '↧'; txt = pct.toFixed(1) + '%'; }
    return '<td class="num" style="color:' + color + ';font-weight:600">' + arrow + ' ' + txt + '</td>';
  }

  /* ── 主渲染（1:1 照搬旧门户 renderFundResult，内容按顶部 Tab 归位） ──
   * 顶部 Tab（统一组件，见 nav.config.js anaTabs/anaPane/anaSwitch）：
   * 总览(默认) / 区域 / 客户集合 / 时间 / 风险预警 / 明细。
   * 总览 = 汇总卡 + 同比卡 + 图表(loadFundDimOverview 渲染)；
   * 明细 = 逐条资金占用(合同/项目号、累计付/收、当前占用、周转、片段数、风险)分页表。 */
  var detailCols = null;   // 明细表列（构建时缓存，供分页渲染）
  var detailPage = 1;      // 明细表当前页
  var DETAIL_PAGE_SIZE = 10;

  /* 明细表 表头：数据列 + 补充列（最后一次回款/上年同期占用/同比/风险/操作） */
  function fundDetailHead(cols) {
    var textCols = new Set(['合同编号', '周期起始日', '年化成本率']);
    var numCols = new Set(['合同额', '累计付款', '累计收款', '净现金流', '当前资金占用', '元天合计', '周期总天数', '平均资金占用', '预估资金成本', '片段数', '已结清片段', '占用中片段']);
    var h = '<tr>';
    cols.forEach(function (c) {
      var align = '';
      if (textCols.has(c)) align = 'text-align:left;padding-left:8px';
      else if (numCols.has(c)) align = 'text-align:right;padding-right:8px';
      h += '<th style="' + align + '">' + c + '</th>';
    });
    // 补充旧门户表格在校验里要求的列：最后一次回款 / 风险等级
    h += '<th style="text-align:left;padding-left:8px">最后一次回款</th>';
    h += '<th style="text-align:right;padding-right:8px">上年同期占用</th>';
    h += '<th style="text-align:right;padding-right:8px">同比变化率</th>';
    h += '<th>风险</th>';
    h += '<th style="min-width:90px;white-space:nowrap">操作</th></tr>';
    return h;
  }

  /* 明细表 表体：仅渲染第 page 页（配合前端分页） */
  function fundDetailBody(cols, page) {
    var rows = fundRows();
    var textCols = new Set(['合同编号', '周期起始日', '年化成本率']);
    var numCols = new Set(['合同额', '累计付款', '累计收款', '净现金流', '当前资金占用', '元天合计', '周期总天数', '平均资金占用', '预估资金成本', '片段数', '已结清片段', '占用中片段']);
    var payCols = new Set(['累计付款', '当前资金占用', '平均资金占用', '预估资金成本', '周期总天数']);
    var recvCols = new Set(['累计收款']);
    var cfCols = new Set(['净现金流']);
    var h = '';
    var start = (page - 1) * DETAIL_PAGE_SIZE;
    var end = Math.min(start + DETAIL_PAGE_SIZE, rows.length);
    for (var i = start; i < end; i++) {
      var row = rows[i];
      h += '<tr>';
      cols.forEach(function (c) {
        var v = row[c];
        var cls = '';
        if (textCols.has(c)) cls = 'wrap';
        else if (numCols.has(c)) cls = 'num';
        if (payCols.has(c)) cls += ' pay-green';
        else if (recvCols.has(c)) cls += ' recv-red';
        else if (cfCols.has(c)) cls += ' cf-balance';
        if (typeof v === 'number' && v > 0 && numCols.has(c) && !payCols.has(c) && !recvCols.has(c) && !cfCols.has(c)) cls += ' pos';
        h += '<td class="' + cls.trim() + '">' + (v != null ? v : '-') + '</td>';
      });
      var rk = { healthy: '🟢 健康', yellow: '🟡 关注', orange: '🟠 预警', red: '🔴 高危' }[row['风险等级']] || row['风险等级'];
      h += '<td class="wrap">' + (row['最后一次回款'] || '-') + '</td>';
      h += '<td class="num">' + fundMoney(row['上年同期占用'] || 0) + '</td>';
      h += fundOccYoyTd(row['当前资金占用'], row['上年同期占用']);
      h += '<td>' + rk + '</td>';
      var cno = row['合同编号'] || row['contract_id'] || '';
      h += '<td style="white-space:nowrap"><button class="btn btn-o btn-sm" style="white-space:nowrap" onclick="FinanceFund.showFundDetail(\'' + String(cno).replace(/'/g, '\\\'') + '\')">查看详情</button></td>';
      h += '</tr>';
    }
    if (!h) h = '<tr><td colspan="' + (cols.length + 5) + '" style="text-align:center;color:var(--text2);padding:20px">暂无明细</td></tr>';
    return h;
  }

  /* 重渲染明细表第 page 页（含分页条） */
  function renderFundDetailPage(page) {
    var rows = fundRows();
    var pagesAll = Math.max(1, Math.ceil(rows.length / DETAIL_PAGE_SIZE));
    detailPage = Math.min(Math.max(1, page || 1), pagesAll);
    var tbody = document.getElementById('fundDetailTbody');
    if (tbody) tbody.innerHTML = fundDetailBody(detailCols, detailPage);
    var wrap = document.getElementById('fundDetailPager');
    if (wrap) wrap.innerHTML = NC.anaPager(detailPage, rows.length, DETAIL_PAGE_SIZE, 'fundDetailPager', 'FinanceFund.setFundPage');
    var cnt = document.getElementById('fundFilterCount');
    if (cnt) cnt.textContent = '共 ' + rows.length + ' 条';
  }

  function renderResult() {
    var html = '';
    // Summary cards（按维度分行：累计类 / 占用类 / 元数据类）—— 归入「总览」tab
    var summaryHtml = '';
    if (data && data.summary) {
      var s = data.summary;
      var getVal = function (k) { var v = s[k]; return (v && v.value != null) ? v.value : v; };
      var sizeFor = function (v) { var l = String(v).length; return l <= 5 ? '24px' : l <= 10 ? '22px' : l <= 15 ? '19px' : '16px'; };
      var rows = [
        ['累计付款总额', '累计收款总额'],
        ['当前资金占用总额', '总加权资金占用', '预估资金成本'],
        ['合同总数', '年化成本率', '报表截止日']
      ];
      rows.forEach(function (row) {
        summaryHtml += '<div class="cards" style="margin-bottom:12px;grid-template-columns:repeat(' + row.length + ',1fr);gap:16px">';
        row.forEach(function (k) {
          var val = getVal(k);
          if (val === undefined || val === null) return;
          summaryHtml += '<div class="card"><div class="lbl">' + k + '</div><div class="val c" style="font-size:' + sizeFor(val) + '">' + val + '</div></div>';
        });
        summaryHtml += '</div>';
      });
    }
    // 明细 pane 内容（逐条资金占用分页表）—— 归入「明细」tab
    var fundRowsD = (data && data.rows) || [];
    detailCols = (data && data.columns) || ['合同编号', '累计付款', '累计收款', '净现金流', '当前资金占用', '平均资金占用', '预估资金成本', '周期总天数', '片段数'];
    var detailHtml = '';
    if (fundRowsD.length) {
      detailHtml += '<div class="panel"><h3>📋 资金占用明细</h3>';
      detailHtml += '<div style="margin-bottom:12px;display:flex;align-items:center;gap:8px">';
      detailHtml += '<span style="font-size:12px;color:var(--text2)">🔍</span>';
      detailHtml += '<input id="fundFilter" placeholder="输入合同编号模糊筛选..." style="flex:1;max-width:320px;padding:6px 10px;border:1px solid var(--border);border-radius:6px;background:var(--bg2);color:var(--text);font-size:12px" oninput="FinanceFund.filterFundTable()">';
      detailHtml += '<span id="fundFilterCount" style="font-size:11px;color:var(--text2)"></span>';
      detailHtml += '</div>';
      detailHtml += '<div class="twrap" id="fundTableWrap"><table class="ana-table" id="fundTable"><thead>' + fundDetailHead(detailCols) + '</thead><tbody id="fundDetailTbody"></tbody></table></div>';
      detailHtml += '<div id="fundDetailPager"></div>';
      detailHtml += '</div>';
    }
    // 组装顶部 Tab（总览默认 active）+ 各维度 pane + 明细 pane
    html = NC.anaTabs([
      { key: 'overview', label: '📊 总览' },
      { key: 'region', label: '🗺️ 区域' },
      { key: 'customer', label: '👥 客户集合' },
      { key: 'time', label: '📅 时间' },
      { key: 'risk', label: '⚠️ 风险预警' },
      { key: 'detail', label: '📋 明细' }
    ], 'overview', 'fundHost');
    html += '<span style="font-size:11px;color:var(--text2);margin:0 24px 16px;display:block" id="fundDimLoading"></span>';
    html += NC.anaPane('overview', summaryHtml + '<div id="fundDimOverview"></div>', true);
    html += NC.anaPane('region', '<div id="fundDimRegion"></div>', false);
    html += NC.anaPane('customer', '<div id="fundDimCustomer"></div>', false);
    html += NC.anaPane('time', '<div id="fundDimTime"></div>', false);
    html += NC.anaPane('risk', '<div id="fundDimRisk"></div>', false);
    html += NC.anaPane('detail', detailHtml, false);
    if (!html) html = '<div class="ana-empty"><div>暂无分析结果</div></div>';
    var host = document.createElement('div');
    host.id = 'fundHost';
    host.setAttribute('data-on-switch', 'FinanceFund.onDimTab');
    host.innerHTML = html;
    var container = document.getElementById('fundContent');
    container.innerHTML = '';
    container.appendChild(host);
    // 渲染明细第 1 页
    if (fundRowsD.length) renderFundDetailPage(1);
    // 加载多维度图表
    loadFundDimOverview();
    loadFundDimCharts();
  }

  function fundChartDiv(id, height) {
    return '<div id="' + id + '" style="width:100%;height:' + height + 'px"></div>';
  }

  /* 切顶部 tab 后的回调（统一 tab 组件 anaSwitch 已处理 pane 显隐；此处补各维度图表 resize）
   * 通过 fundHost 的 data-on-switch 注入，key = overview|region|customer|time|risk|detail */
  function onDimTab(key) {
    var doResize = function () {
      Object.keys(fundDimCharts).forEach(function (k) {
        var c = fundDimCharts[k];
        if (c && typeof c.resize === 'function') { try { c.resize(); } catch (e) {} }
      });
    };
    requestAnimationFrame(function () { doResize(); setTimeout(doResize, 120); });
  }

  function fundBarColors(riskCount) {
    if (riskCount && riskCount.red > 0) return '#ff4d4f';
    if (riskCount && riskCount.orange > 0) return '#fa8c16';
    if (riskCount && riskCount.yellow > 0) return '#faad14';
    return '#52c41a';
  }

  /* ── Tab1 总览 ── */
  function fundYoY(flows, occNow, prevOcc) {
    var P0 = '2026-01-01', CUT = '2026-08-12', P1 = '2025-01-01', P2 = '2025-08-12';
    var agg = function (sel, e, type) { var t = 0; (flows || []).forEach(function (f) { if (f.type !== type) return; if (f.date >= sel && f.date <= e) t += f.amount; }); return t; };
    var curPay = -agg(P0, CUT, 'PAY'), prevPay = -agg(P1, P2, 'PAY');
    var curRecv = agg(P0, CUT, 'RECEIVE'), prevRecv = agg(P1, P2, 'RECEIVE');
    var curNet = curRecv - curPay, prevNet = prevRecv - prevPay;
    var pct = function (c, p) { return p === 0 ? null : ((c - p) / p * 100); };
    return { curPay: curPay, prevPay: prevPay, curRecv: curRecv, prevRecv: prevRecv, curNet: curNet, prevNet: prevNet, occNow: occNow, prevOcc: prevOcc,
      payPct: pct(curPay, prevPay), recvPct: pct(curRecv, prevRecv), netPct: pct(curNet, prevNet), occPct: pct(occNow, prevOcc) };
  }
  function yoyCard(lbl, val, fmt, pct, kind) {
    var up = kind === 'semantic';
    var arrow = '—', cls = 'yoy-flat', txt = '无同比数据（上年同期为 0）';
    if (pct !== null) {
      arrow = pct > 0 ? '↥' : (pct < 0 ? '↧' : '—');
      cls = up ? (pct > 0 ? 'yoy-red' : (pct < 0 ? 'yoy-green' : 'yoy-flat')) : (pct > 0 ? 'yoy-up' : (pct < 0 ? 'yoy-down' : 'yoy-flat'));
      txt = '较上年同期 ' + (pct > 0 ? '+' : '') + pct.toFixed(1) + '%' + (up ? (pct > 0 ? '（占用增加）' : (pct < 0 ? '（占用减少）' : '')) : '');
    }
    return '<div class="card"><div class="lbl">' + lbl + '</div><div class="val" style="font-size:20px">' + fmt(val) + '</div>'
      + '<div class="yoy ' + cls + '" title="' + txt + '">' + arrow + (pct !== null ? ' ' + (pct > 0 ? '+' : '') + pct.toFixed(1) + '%' : '') + '<span>vs 上年同期</span></div></div>';
  }
  function fundChartMonthCompare(flows) {
    var el = document.getElementById('chartMonthCompare');
    if (!el || !window.echarts) return;
    var chart = echarts.init(el, 'cc-dark');
    var by = {};
    (Array.isArray(flows) ? flows : []).forEach(function (f) {
      var d = f.date || ''; if (d.length < 7) return;
      var yr = d.slice(0, 4), mo = d.slice(5, 7);
      if (yr !== '2025' && yr !== '2026') return;
      var k = by[mo] = by[mo] || { p25: 0, r25: 0, p26: 0, r26: 0 };
      if (f.type === 'PAY') { yr === '2025' ? k.p25 += f.amount : k.p26 += f.amount; }
      else { yr === '2025' ? k.r25 += f.amount : k.r26 += f.amount; }
    });
    var months = [], p25 = [], p26 = [], r25 = [], r26 = [];
    for (var i = 1; i <= 8; i++) {
      var kk = String(i).padStart(2, '0'), m = by[kk] || {};
      months.push(i + '月'); p25.push(-(m.p25 || 0)); p26.push(-(m.p26 || 0)); r25.push(m.r25 || 0); r26.push(m.r26 || 0);
    }
    var pct = function (a, b) { return b === 0 ? null : ((a - b) / b * 100); };
    chart.setOption({
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: function (ps) {
        var i = ps[0].dataIndex;
        var pp = pct(p26[i], p25[i]), rp = pct(r26[i], r25[i]);
        var h = '<b>' + months[i] + '</b>';
        h += '<div>2026付款：' + fundMoney(p26[i]) + '</div><div>2025付款：' + fundMoney(p25[i]) + '</div>';
        h += '<div style="color:' + (pp === null ? '#8893aa' : (pp > 0 ? '#ff6b6b' : '#52c41a')) + '">付款同比 ' + (pp === null ? '—' : (pp > 0 ? '+' : '') + pp.toFixed(1) + '%') + '</div>';
        h += '<div style="margin-top:4px">2026回款：' + fundMoney(r26[i]) + '</div><div>2025回款：' + fundMoney(r25[i]) + '</div>';
        h += '<div style="color:' + (rp === null ? '#8893aa' : (rp > 0 ? '#52c41a' : '#ff6b6b')) + '">回款同比 ' + (rp === null ? '—' : (rp > 0 ? '+' : '') + rp.toFixed(1) + '%') + '</div>';
        return h;
      } },
      legend: { data: ['2025付款', '2026付款', '2025回款', '2026回款'], textStyle: { fontSize: 10 } },
      grid: { left: 60, right: 20, top: 30, bottom: 24 },
      xAxis: { type: 'category', data: months, axisLabel: { fontSize: 10 } },
      yAxis: { type: 'value', axisLabel: { fontSize: 10, formatter: fundMoney } },
      series: [
        { name: '2025付款', type: 'bar', data: p25, itemStyle: { color: '#3a4a6a' }, barGap: '20%' },
        { name: '2026付款', type: 'bar', data: p26, itemStyle: { color: '#4f8cff' } },
        { name: '2025回款', type: 'bar', data: r25, itemStyle: { color: '#2f5d4a' } },
        { name: '2026回款', type: 'bar', data: r26, itemStyle: { color: '#22c55e' } }
      ]
    });
    fundDimCharts['chartMonthCompare'] = chart;
  }
  function fundRows() { return (data && data.rows) || []; }
  function loadFundDimOverview() {
    var panel = document.getElementById('fundDimOverview');
    if (!panel) return;
    var html = '';
    var rows = fundRows();
    if (data && data.summary) {
      var occNow = rows.reduce(function (s, r) { return s + (r['当前资金占用'] || 0); }, 0);
      var y = fundYoY(data.flows || [], occNow, (data.yoy && data.yoy.occupy_prev) || 0);
      html += '<div class="cards" style="margin-bottom:12px;grid-template-columns:repeat(4,1fr);gap:14px">';
      html += yoyCard('📤 累计付款（今年累计）', y.curPay, fundMoney, y.payPct);
      html += yoyCard('📥 累计回款（今年累计）', y.curRecv, fundMoney, y.recvPct);
      html += yoyCard('⚖️ 净现金流（今年累计）', y.curNet, fundMoney, y.netPct);
      html += yoyCard('💰 当前资金占用', y.occNow, fundMoney, y.occPct, 'semantic');
      html += '</div>';
    }
    html += '<div class="cards" style="grid-template-columns:repeat(3,1fr);gap:16px">';
    html += '<div class="card" style="padding:12px"><div style="font-size:13px;font-weight:600;margin-bottom:4px">风险等级分布</div>' + fundChartDiv('chartRiskPie', 260) + '</div>';
    html += '<div class="card" style="padding:12px"><div style="font-size:13px;font-weight:600;margin-bottom:4px">项目状态资金分布</div>' + fundChartDiv('chartStatusPie', 260) + '</div>';
    html += '<div class="card" style="padding:12px"><div style="font-size:13px;font-weight:600;margin-bottom:4px">资金成本构成 TOP</div>' + fundChartDiv('chartCostPie', 260) + '</div>';
    html += '</div>';
    html += '<div style="height:20px"></div>';
    html += '<div class="card" style="padding:12px"><div style="font-size:13px;font-weight:600;margin-bottom:4px">月度付款 / 回款同比（2026 vs 2025）</div>' + fundChartDiv('chartMonthCompare', 340) + '</div>';
    html += '<div style="height:20px"></div>';
    html += '<div class="card" style="padding:12px"><div style="font-size:13px;font-weight:600;margin-bottom:4px">月度付款 / 收款 / 占用余额趋势</div>' + fundChartDiv('chartMonthLine', 340) + '</div>';
    panel.innerHTML = html;
    fundChartMonthCompare(data.flows || []);
    if (rows.length) {
      var riskCount = { healthy: 0, yellow: 0, orange: 0, red: 0 };
      var statusAgg = {};
      var costRows = rows.map(function (r) { return { name: r['合同编号'], value: r['预估资金成本'] || 0 }; }).filter(function (x) { return x.value > 0; }).sort(function (a, b) { return b.value - a.value; }).slice(0, 8);
      rows.forEach(function (r) {
        var lv = r['风险等级'] || 'healthy';
        riskCount[lv] = (riskCount[lv] || 0) + 1;
        var st = r['项目状态'] || '未知';
        statusAgg[st] = (statusAgg[st] || 0) + (r['当前资金占用'] || 0);
      });
      fundChartPie('chartRiskPie', [
        { name: '健康', value: riskCount.healthy, itemStyle: { color: '#52c41a' } },
        { name: '关注', value: riskCount.yellow, itemStyle: { color: '#faad14' } },
        { name: '预警', value: riskCount.orange, itemStyle: { color: '#fa8c16' } },
        { name: '高危', value: riskCount.red, itemStyle: { color: '#ff4d4f' } }
      ].filter(function (x) { return x.value > 0; }), '个合同');
      var stArr = Object.keys(statusAgg).sort(function (a, b) { return statusAgg[b] - statusAgg[a]; }).slice(0, 8).map(function (k) { return { name: k, value: statusAgg[k] }; });
      fundChartPie('chartStatusPie', stArr, fundMoney);
      fundChartPie('chartCostPie', costRows, fundMoney);
      fundChartMonthLine(data.flows || [], rows);
    }
  }
  function fundChartPie(id, series, labelFmt) {
    var el = document.getElementById(id);
    if (!el || !window.echarts) return;
    var chart = echarts.init(el, 'cc-dark');
    chart.setOption({
      tooltip: { trigger: 'item', formatter: function (p) { return p.name + '：' + (typeof labelFmt === 'function' ? labelFmt(p.value) : (p.value || 0)); } },
      legend: { type: 'scroll', orient: 'vertical', right: 0, top: 'middle', textStyle: { fontSize: 10 } },
      series: [{ type: 'pie', radius: ['35%', '68%'], center: ['38%', '50%'], itemStyle: { borderRadius: 4 }, label: { show: false }, data: series || [] }]
    });
    fundDimCharts[id] = chart;
  }
  function fundChartMonthLine(flows, rows) {
    var el = document.getElementById('chartMonthLine');
    if (!el || !window.echarts) return;
    var chart = echarts.init(el, 'cc-dark');
    var monthAgg = {};
    var flowAgg = Array.isArray(flows) ? flows.reduce(function (m, f) {
      var mo = (f.date || '').slice(0, 7); if (!mo) return m;
      m[mo] = m[mo] || { pay: 0, recv: 0 }; f.type === 'PAY' ? m[mo].pay += (f.amount || 0) : m[mo].recv += (f.amount || 0);
      return m;
    }, {}) : {};
    rows.forEach(function (r) {
      var mo = (r['周期起始日'] || '').slice(0, 7) || '未知';
      var b = monthAgg[mo] = monthAgg[mo] || { occupy: 0 };
      b.occupy += (r['当前资金占用'] || 0);
    });
    var months = Array.from(new Set([].concat(Object.keys(monthAgg), Object.keys(flowAgg)))).sort();
    var pay = months.map(function (m) { return flowAgg[m] ? flowAgg[m].pay : null; });
    var recv = months.map(function (m) { return flowAgg[m] ? flowAgg[m].recv : null; });
    var occupy = months.map(function (m) { return monthAgg[m] ? monthAgg[m].occupy : null; });
    chart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['付款', '回款', '占用余额'], textStyle: { fontSize: 10 } },
      grid: { left: 60, right: 20, top: 30, bottom: 24 },
      xAxis: { type: 'category', data: months, axisLabel: { fontSize: 10 } },
      yAxis: { type: 'value', axisLabel: { fontSize: 10, formatter: fundMoney } },
      series: [
        { name: '付款', type: 'bar', stack: 'cash', data: pay, itemStyle: { color: '#4f8cff' } },
        { name: '回款', type: 'bar', stack: 'cash', data: recv, itemStyle: { color: '#52c41a' } },
        { name: '占用余额', type: 'line', data: occupy, itemStyle: { color: '#fa8c16' }, smooth: true }
      ]
    });
    fundDimCharts['chartMonthLine'] = chart;
  }

  /* ── Tab2 区域 / Tab3 客户集合 / Tab4 时间 / Tab5 风险 ── */
  async function loadFundDimCharts() {
    var loading = document.getElementById('fundDimLoading');
    if (loading) loading.textContent = '维度数据加载中...';
    await Promise.all([loadFundRegion(), loadFundCustomer(), loadFundTime(), loadFundRisk()]);
    if (loading) loading.textContent = '';
  }
  async function loadFundRegion() {
    var panel = document.getElementById('fundDimRegion');
    if (!panel) return;
    panel.innerHTML = '<div class="ana-empty"><div>加载中...</div></div>';
    var r = await fundFetch('/api/core/metrics/fund/dim?dim=region');
    var rp = await fundFetch('/api/core/metrics/fund/dim?dim=province');
    if (!r.success) { panel.innerHTML = '<div class="ana-empty"><div>' + r.error + '</div></div>'; return; }
    var rows = r.rows || [];
    var provRows = (rp && rp.success) ? (rp.rows || []) : [];
    var html = '<div class="cards" style="grid-template-columns:2fr 1fr;gap:16px">';
    html += '<div class="card" style="padding:12px"><div style="font-size:13px;font-weight:600;margin-bottom:4px">区域资金占用 × 回款率（点击下钻）</div>' + fundChartDiv('chartRegionBar', 320) + '</div>';
    html += '<div class="card" style="padding:12px"><div style="font-size:13px;font-weight:600;margin-bottom:4px">区域风险等级分布</div>' + fundChartDiv('chartRegionRisk', 320) + '</div>';
    html += '</div>';
    html += '<div style="height:20px"></div>';
    html += '<div class="card" style="padding:12px"><div style="font-size:13px;font-weight:600;margin-bottom:4px">资金占用分布地图</div>';
    html += '<div style="margin-bottom:8px"><button class="btn btn-c btn-sm" id="fundMapBtnArea" onclick="FinanceFund.fundMapSwitch(\'area\')">🗺️ 六大区</button> <button class="btn btn-o btn-sm" id="fundMapBtnProv" onclick="FinanceFund.fundMapSwitch(\'prov\')">🧭 省份</button></div>';
    html += fundChartDiv('chartRegionMapArea', 340) + fundChartDiv('chartRegionMapProv', 340) + '</div>';
    html += '<div style="height:12px"></div>';
    html += '<div class="twrap"><table class="ana-table"><thead><tr><th style="text-align:left;padding-left:8px">区域</th><th style="text-align:right;padding-right:8px">合同数</th><th style="text-align:right;padding-right:8px">当前占用</th><th style="text-align:right;padding-right:8px">回款率</th><th style="text-align:right;padding-right:8px">占用强度</th><th>风险</th><th>操作</th></tr></thead><tbody>';
    rows.forEach(function (x) {
      var riskName = { healthy: '健康', yellow: '关注', orange: '预警', red: '高危' }[x.risk_level] || x.risk_level;
      html += '<tr><td class="wrap">' + x.name + '</td><td class="num">' + x.contract_count + '</td><td class="num pay-green">¥' + fundMoney(x.current_occupy) + '</td><td class="num">' + (x.recv_rate * 100).toFixed(1) + '%</td><td class="num">' + (x.occupy_intensity * 100).toFixed(1) + '%</td><td>' + riskName + '</td><td><button class="btn btn-o btn-sm" onclick="FinanceFund.fundDrill(\'region\',\'' + String(x.name).replace(/'/g, '\\\'') + '\',\'' + String(x.name).replace(/'/g, '\\\'') + '\')">下钻</button></td></tr>';
    });
    html += '</tbody></table></div>';
    panel.innerHTML = html;
    if (rows.length) {
      fundChartRegionBar(rows);
      fundChartRegionRisk(rows);
      fundChartRegionMapArea(rows);
      fundChartRegionMapProv(provRows.length ? provRows : rows);
      fundMapSwitch('area');
    }
  }
  function fundMapSwitch(which) {
    var a = document.getElementById('chartRegionMapArea'), p = document.getElementById('chartRegionMapProv');
    var ba = document.getElementById('fundMapBtnArea'), bp = document.getElementById('fundMapBtnProv');
    if (a) a.style.display = (which === 'area') ? '' : 'none';
    if (p) p.style.display = (which === 'prov') ? '' : 'none';
    if (ba) ba.className = 'btn btn-sm ' + (which === 'area' ? 'btn-c' : 'btn-o');
    if (bp) bp.className = 'btn btn-sm ' + (which === 'prov' ? 'btn-c' : 'btn-o');
    var c = fundDimCharts[(which === 'area') ? 'chartRegionMapArea' : 'chartRegionMapProv'];
    if (c && typeof c.resize === 'function') { try { c.resize(); } catch (e) {} }
  }
  function fundChartRegionBar(rows) {
    var el = document.getElementById('chartRegionBar');
    if (!el || !window.echarts) return;
    var chart = echarts.init(el, 'cc-dark');
    chart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['当前占用', '回款率'], textStyle: { fontSize: 10 } },
      grid: { left: 80, right: 60, top: 30, bottom: 28 },
      xAxis: { type: 'category', data: rows.map(function (r) { return r.name; }), axisLabel: { fontSize: 10, interval: 0, rotate: rows.length > 6 ? 35 : 0 } },
      yAxis: [{ type: 'value', axisLabel: { fontSize: 10, formatter: fundMoney } }, { type: 'value', min: 0, max: 1, axisLabel: { fontSize: 10, formatter: function (v) { return (v * 100) + '%'; } } }],
      series: [
        { name: '当前占用', type: 'bar', data: rows.map(function (r) { return r.current_occupy; }), itemStyle: { color: '#fa8c16' }, barWidth: '45%' },
        { name: '回款率', type: 'line', yAxisIndex: 1, data: rows.map(function (r) { return r.recv_rate; }), itemStyle: { color: '#4f8cff' }, smooth: true }
      ]
    });
    chart.on('click', function (p) { if (p.componentType === 'series') fundDrill('region', p.name, p.name); });
    fundDimCharts['chartRegionBar'] = chart;
  }
  function fundChartRegionRisk(rows) {
    var el = document.getElementById('chartRegionRisk');
    if (!el || !window.echarts) return;
    var chart = echarts.init(el, 'cc-dark');
    var cats = ['red', 'orange', 'yellow', 'healthy'];
    var series = cats.map(function (lv) { return {
      name: { red: '高危', orange: '预警', yellow: '关注', healthy: '健康' }[lv],
      type: 'bar', stack: 'risk', data: rows.map(function (r) { return r.risk_count ? r.risk_count[lv] : 0; }),
      itemStyle: { color: { red: '#ff4d4f', orange: '#fa8c16', yellow: '#faad14', healthy: '#52c41a' }[lv] }
    }; });
    chart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { textStyle: { fontSize: 10 } },
      grid: { left: 60, right: 20, top: 30, bottom: 24 },
      xAxis: { type: 'category', data: rows.map(function (r) { return r.name; }), axisLabel: { fontSize: 10, interval: 0 } },
      yAxis: { type: 'value', axisLabel: { fontSize: 10 } },
      series: series
    });
    fundDimCharts['chartRegionRisk'] = chart;
  }
  function fundChartRegionMapArea(regionRows) {
    var el = document.getElementById('chartRegionMapArea');
    if (!el || !window.echarts) return;
    el.innerHTML = '';
    var byArea = {};
    (regionRows || []).forEach(function (r) { if (r.name && r.name !== '未知') byArea[r.name] = r; });
    setTimeout(function () {
      if (!chinaGeoJson) { el.innerHTML = '<div style="color:var(--text2);padding:20px;text-align:center">地图数据加载中...</div>'; return; }
      var srcGeo = chinaGeoJson;
      var draw = function () {
        var areaKeys = Object.keys(byArea).filter(function (a) { return PC_AREA_PROVINCES[a]; });
        if (!areaKeys.length) { el.innerHTML = '<div style="color:var(--text2);padding:20px;text-align:center">暂无区域数据</div>'; return; }
        var mapReady = false;
        try { mapReady = echarts.getMap ? !!echarts.getMap('pc_regions') : false; } catch (e) {}
        var chart = echarts.init(el, 'cc-dark');
        if (mapReady) {
          var values = areaKeys.map(function (a) { return byArea[a].current_occupy || 0; }).filter(function (v) { return v > 0; });
          var vmin = values.length ? Math.min.apply(null, values) : 0;
          var vmax = values.length ? Math.max.apply(null, values) : 1;
          var areaData = areaKeys.map(function (a) { return { name: a, value: byArea[a].current_occupy || 0 }; });
          chart.setOption({
            tooltip: { trigger: 'item', formatter: function (p) {
              if (p.componentType !== 'series' || p.seriesType !== 'map' || !p.name) return '';
              var s = byArea[p.name]; if (!s) return pcEsc(p.name);
              return pcEsc(p.name) + '<br>当前占用 ¥' + fundMoney(s.current_occupy) + '<br>合同 ' + s.contract_count + ' 份 · 回款率 ' + (s.recv_rate * 100).toFixed(1) + '%<br>占用强度 ' + (s.occupy_intensity * 100).toFixed(1) + '%';
            } },
            visualMap: { min: vmin, max: vmax, left: 'center', bottom: 10, orient: 'horizontal', itemWidth: 14, itemHeight: 100, calculable: true, text: ['占用低', '占用高'], textStyle: { color: '#7d8db0', fontSize: 11 }, inRange: { color: ['#22d3ee', '#60a5fa', '#4f8cff', '#a78bfa'] }, formatter: function (v) { return '¥' + fundMoney(v); } },
            geo: { map: 'pc_regions', roam: false, zoom: 1.08, center: [104.5, 36.5], itemStyle: { areaColor: '#131c2e', borderColor: '#24324d', borderWidth: 1 }, emphasis: { itemStyle: { areaColor: '#f59e0b', borderColor: '#b45309', borderWidth: 1.6 } }, label: { show: false } },
            series: [{ type: 'map', map: 'pc_regions', geoIndex: 0, data: areaData, label: { show: false }, emphasis: { label: { show: false }, itemStyle: { areaColor: '#f59e0b', borderColor: '#b45309', borderWidth: 1.6 } }, itemStyle: { borderWidth: 0 } }]
          });
          chart.on('click', function (p) { if (p.componentType === 'series' && p.seriesType === 'map' && p.name && byArea[p.name]) fundDrill('region', p.name, p.name); });
        } else {
          chart.setOption({
            tooltip: { trigger: 'axis' },
            grid: { left: 80, right: 20, top: 10, bottom: 24 },
            xAxis: { type: 'value', axisLabel: { fontSize: 10, formatter: fundMoney } },
            yAxis: { type: 'category', data: areaKeys.slice().reverse(), axisLabel: { fontSize: 10 } },
            series: [{ type: 'bar', data: areaKeys.map(function (a) { return byArea[a].current_occupy || 0; }).reverse(), itemStyle: { color: '#4f8cff' }, barWidth: '55%' }]
          });
          chart.on('click', function (p) { fundDrill('region', p.name, p.name); });
        }
        fundDimCharts['chartRegionMapArea'] = chart;
      };
      Promise.all([pcLoadScript(PC_POLYCLIP_URL)]).then(function () {
        if (echarts.getMap && echarts.getMap('pc_regions')) { draw(); return; }
        var regionFeatures = [];
        Object.keys(PC_AREA_PROVINCES).forEach(function (area) {
          var provs = srcGeo.features.filter(function (f) { return PC_AREA_PROVINCES[area].indexOf(f.properties.name) >= 0; });
          if (!provs.length) return;
          var feat;
          if (window.polygonClipping) {
            var geoms = provs.map(function (f) { return f.geometry.type === 'Polygon' ? [f.geometry.coordinates] : f.geometry.coordinates; });
            var merged = []; try { merged = window.polygonClipping.union.apply(window.polygonClipping, geoms); } catch (e) { merged = []; }
            feat = { type: 'Feature', properties: { name: area }, geometry: { type: 'MultiPolygon', coordinates: merged } };
          } else {
            var coords = [];
            provs.forEach(function (f) { var c = f.geometry.type === 'MultiPolygon' ? f.geometry.coordinates : [f.geometry.coordinates]; c.forEach(function (poly) { coords.push(poly); }); });
            feat = { type: 'Feature', properties: { name: area }, geometry: { type: 'MultiPolygon', coordinates: coords } };
          }
          if (feat && feat.geometry) regionFeatures.push(feat);
        });
        ['台湾省', '南海诸岛'].forEach(function (nm) {
          var f = srcGeo.features.find(function (x) { return x.properties.name === nm; });
          if (f) regionFeatures.push({ type: 'Feature', properties: { name: nm }, geometry: f.geometry });
        });
        if (regionFeatures.length >= 2) { try { echarts.registerMap('pc_regions', { type: 'FeatureCollection', features: regionFeatures }); } catch (e) {} }
        draw();
      });
    }, 200);
  }
  function fundChartRegionMapProv(provRows) {
    var el = document.getElementById('chartRegionMapProv');
    if (!el || !window.echarts) return;
    el.innerHTML = '';
    setTimeout(function () {
      if (!chinaGeoJson) { el.innerHTML = '<div style="color:var(--text2);padding:20px;text-align:center">地图数据加载中...</div>'; return; }
      var srcGeo = chinaGeoJson;
      var byProv = {};
      (provRows || []).forEach(function (r) {
        if (r.name && r.name !== '未知') { var full = PC_PROV_FULL[r.name] || r.name; byProv[full] = r; }
      });
      var keys = Object.keys(byProv);
      if (!keys.length) { el.innerHTML = '<div style="color:var(--text2);padding:20px;text-align:center">暂无省份数据</div>'; return; }
      var mapReady = false;
      try { mapReady = echarts.getMap ? !!echarts.getMap('pc_provs') : false; } catch (e) {}
      if (!mapReady) { try { echarts.registerMap('pc_provs', srcGeo); mapReady = true; } catch (e) { mapReady = false; } }
      var chart = echarts.init(el, 'cc-dark');
      var revProv = Object.keys(PC_PROV_FULL).reduce(function (m, k) { m[PC_PROV_FULL[k]] = k; return m; }, {});
      if (mapReady) {
        var data = keys.map(function (nm) { return { name: nm, value: byProv[nm].current_occupy || 0 }; });
        var pvals = data.map(function (d) { return d.value; }).filter(function (v) { return v != null && v > 0; });
        var pmin = pvals.length ? Math.min.apply(null, pvals) : 0;
        var pmax = pvals.length ? Math.max.apply(null, pvals) : 1;
        chart.setOption({
          tooltip: { trigger: 'item', formatter: function (p) {
            if (p.componentType !== 'series' || p.seriesType !== 'map' || !p.name) return '';
            var s = byProv[p.name]; if (!s) return pcEsc(p.name) + '<br>暂无资金占用数据';
            return pcEsc(p.name) + '<br>当前占用 ¥' + fundMoney(s.current_occupy) + '<br>合同 ' + s.contract_count + ' 份 · 回款率 ' + (s.recv_rate * 100).toFixed(1) + '%';
          } },
          visualMap: { min: pmin, max: pmax, left: 'center', bottom: 10, orient: 'horizontal', itemWidth: 14, itemHeight: 100, calculable: true, text: ['占用低', '占用高'], textStyle: { color: '#7d8db0', fontSize: 11 }, inRange: { color: ['#22d3ee', '#60a5fa', '#4f8cff', '#a78bfa'] }, formatter: function (v) { return '¥' + fundMoney(v); } },
          geo: { map: 'pc_provs', roam: false, zoom: 1.08, center: [104.5, 36.5], itemStyle: { areaColor: '#131c2e', borderColor: '#24324d', borderWidth: 0.8 }, emphasis: { label: { show: true, color: '#dbe4f5', fontWeight: 'bold' } } },
          series: [{ type: 'map', map: 'pc_provs', geoIndex: 0, data: data, label: { show: false }, emphasis: { label: { show: true, color: '#dbe4f5', fontWeight: 'bold' } } }]
        });
        chart.on('click', function (p) { if (p.componentType === 'series' && p.seriesType === 'map' && p.name && byProv[p.name]) { var short = revProv[p.name] || p.name; fundDrill('province', short, p.name); } });
      } else {
        chart.setOption({
          tooltip: { trigger: 'axis' },
          grid: { left: 80, right: 20, top: 10, bottom: 24 },
          xAxis: { type: 'value', axisLabel: { fontSize: 10, formatter: fundMoney } },
          yAxis: { type: 'category', data: keys.slice().reverse(), axisLabel: { fontSize: 10 } },
          series: [{ type: 'bar', data: keys.map(function (k) { return byProv[k].current_occupy || 0; }).reverse(), itemStyle: { color: '#4f8cff' }, barWidth: '55%' }]
        });
        chart.on('click', function (p) { var short = revProv[p.name] || p.name; fundDrill('province', short, p.name); });
      }
      fundDimCharts['chartRegionMapProv'] = chart;
    }, 200);
  }
  async function loadFundCustomer() {
    var panel = document.getElementById('fundDimCustomer');
    if (!panel) return;
    panel.innerHTML = '<div class="ana-empty"><div>加载中...</div></div>';
    var r = await fundFetch('/api/core/metrics/fund/dim?dim=customer_key');
    if (!r.success) { panel.innerHTML = '<div class="ana-empty"><div>' + r.error + '</div></div>'; return; }
    var rows = (r.rows || []).filter(function (x) { return x.name && x.name !== '未知'; }).slice(0, 20);
    if (!rows.length) { panel.innerHTML = '<div class="ana-empty"><div>📭 暂无客户集合维度数据</div></div>'; return; }
    var html = '<div class="cards" style="grid-template-columns:1fr 1fr;gap:16px">';
    html += '<div class="card" style="padding:12px"><div style="font-size:13px;font-weight:600;margin-bottom:4px">客户集合占用 TOP10（点击下钻）</div>' + fundChartDiv('chartCustomerTop', 320) + '</div>';
    html += '<div class="card" style="padding:12px"><div style="font-size:13px;font-weight:600;margin-bottom:4px">客户集合风险等级分布</div>' + fundChartDiv('chartCustomerRisk', 320) + '</div>';
    html += '</div>';
    html += '<div style="height:20px"></div>';
    html += '<div class="twrap"><table class="ana-table"><thead><tr><th style="text-align:left;padding-left:8px">客户键</th><th style="text-align:right;padding-right:8px">合同数</th><th style="text-align:right;padding-right:8px">当前占用</th><th style="text-align:right;padding-right:8px">上年同期占用</th><th style="text-align:right;padding-right:8px">同比变化率</th><th style="text-align:right;padding-right:8px">回款率</th><th>风险</th><th>操作</th></tr></thead><tbody>';
    rows.forEach(function (x) {
      var riskName = { healthy: '健康', yellow: '关注', orange: '预警', red: '高危' }[x.risk_level] || x.risk_level;
      html += '<tr><td class="wrap">' + x.name + '</td><td class="num">' + x.contract_count + '</td><td class="num pay-green">¥' + fundMoney(x.current_occupy) + '</td>';
      html += '<td class="num">¥' + fundMoney(x.prev_occupy) + '</td>';
      html += fundOccYoyTd(x.current_occupy, x.prev_occupy);
      html += '<td class="num">' + (x.recv_rate * 100).toFixed(1) + '%</td><td>' + riskName + '</td><td><button class="btn btn-o btn-sm" onclick="FinanceFund.fundDrill(\'customer_key\',\'' + String(x.name).replace(/'/g, '\\\'') + '\',\'' + String(x.name).replace(/'/g, '\\\'') + '\')">下钻</button></td></tr>';
    });
    html += '</tbody></table></div>';
    panel.innerHTML = html;
    if (rows.length) { fundChartCustomerTop(rows); fundChartCustomerRisk(rows); }
  }
  function fundChartCustomerTop(rows) {
    var el = document.getElementById('chartCustomerTop');
    if (!el || !window.echarts) return;
    var chart = echarts.init(el, 'cc-dark');
    var top = rows.slice(0, 10).slice().reverse();
    chart.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: 70, right: 60, top: 10, bottom: 24 },
      xAxis: { type: 'value', axisLabel: { fontSize: 10, formatter: fundMoney } },
      yAxis: { type: 'category', data: top.map(function (r) { return r.name; }), axisLabel: { fontSize: 10 } },
      series: [{ name: '当前占用', type: 'bar', data: top.map(function (r) { return r.current_occupy; }), barWidth: '55%', itemStyle: { color: function (p) { return fundBarColors(top[p.dataIndex].risk_count); } } }]
    });
    chart.on('click', function (p) { fundDrill('customer_key', top[p.dataIndex].name, top[p.dataIndex].name); });
    fundDimCharts['chartCustomerTop'] = chart;
  }
  function fundChartCustomerRisk(rows) {
    var el = document.getElementById('chartCustomerRisk');
    if (!el || !window.echarts) return;
    var chart = echarts.init(el, 'cc-dark');
    var cats = ['red', 'orange', 'yellow', 'healthy'];
    var revRows = rows.slice().reverse();
    var series = cats.map(function (lv) { return {
      name: { red: '高危', orange: '预警', yellow: '关注', healthy: '健康' }[lv],
      type: 'bar', stack: 'risk', data: revRows.map(function (r) { return r.risk_count ? r.risk_count[lv] : 0; }),
      itemStyle: { color: { red: '#ff4d4f', orange: '#fa8c16', yellow: '#faad14', healthy: '#52c41a' }[lv] }
    }; });
    chart.setOption({
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      legend: { textStyle: { fontSize: 10 } },
      grid: { left: 140, right: 20, top: 30, bottom: 30 },
      xAxis: { type: 'value', axisLabel: { fontSize: 10 } },
      yAxis: { type: 'category', data: revRows.map(function (r) { return r.name; }), axisLabel: { fontSize: 9, width: 120, overflow: 'truncate' } },
      series: series
    });
    fundDimCharts['chartCustomerRisk'] = chart;
  }
  async function loadFundTime() {
    var panel = document.getElementById('fundDimTime');
    if (!panel) return;
    panel.innerHTML = '<div class="ana-empty"><div>加载中...</div></div>';
    var a = await fundFetch('/api/core/metrics/fund/dim?dim=sign_year');
    var rows = a.success ? a.rows : [];
    var yearRows = (rows || []).filter(function (x) { return x.name && x.name !== '未知'; }).sort(function (a, b) { return String(a.name).localeCompare(String(b.name)); });
    if (!yearRows.length) { panel.innerHTML = '<div class="ana-empty"><div>📭 暂无时间维度数据</div></div>'; return; }
    var html = '<div class="cards" style="grid-template-columns:1fr 1fr;gap:16px">';
    html += '<div class="card" style="padding:12px"><div style="font-size:13px;font-weight:600;margin-bottom:4px">签约年份资金占用分布</div>' + fundChartDiv('chartYearBar', 320) + '</div>';
    html += '<div class="card" style="padding:12px"><div style="font-size:13px;font-weight:600;margin-bottom:4px">占用时长分段（合同数）</div>' + fundChartDiv('chartDaysHist', 320) + '</div>';
    html += '</div>';
    panel.innerHTML = html;
    fundChartYearBar(yearRows);
    fundChartDaysHist();
  }
  function fundChartYearBar(rows) {
    var el = document.getElementById('chartYearBar');
    if (!el || !window.echarts) return;
    var chart = echarts.init(el, 'cc-dark');
    chart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['当前占用', '回款率'], textStyle: { fontSize: 10 } },
      grid: { left: 60, right: 60, top: 30, bottom: 24 },
      xAxis: { type: 'category', data: rows.map(function (r) { return r.name; }), axisLabel: { fontSize: 10 } },
      yAxis: [{ type: 'value', axisLabel: { fontSize: 10, formatter: fundMoney } }, { type: 'value', min: 0, max: 1, axisLabel: { fontSize: 10, formatter: function (v) { return (v * 100) + '%'; } } }],
      series: [
        { name: '当前占用', type: 'bar', data: rows.map(function (r) { return r.current_occupy; }), itemStyle: { color: '#4f8cff' }, barWidth: '45%' },
        { name: '回款率', type: 'line', yAxisIndex: 1, data: rows.map(function (r) { return r.recv_rate; }), itemStyle: { color: '#52c41a' }, smooth: true }
      ]
    });
    fundDimCharts['chartYearBar'] = chart;
  }
  function fundChartDaysHist() {
    var el = document.getElementById('chartDaysHist');
    if (!el || !window.echarts) return;
    var chart = echarts.init(el, 'cc-dark');
    // 直接基于全量 data.rows 计算（明细已前段分页，避免只统计当前页导致降级）
    var buckets = [0, 30, 90, 180, 365, Infinity];
    var labels = ['≤30天', '31-90天', '91-180天', '181-365天', '>365天'];
    var count = labels.map(function () { return 0; });
    var all = fundRows();
    all.forEach(function (r) {
      var days = Number(r['周期总天数']) || 0;
      for (var i = 0; i < labels.length; i++) {
        if (days > buckets[i] && days <= buckets[i + 1]) { count[i]++; break; }
      }
    });
    chart.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: 60, right: 20, top: 20, bottom: 24 },
      xAxis: { type: 'category', data: labels, axisLabel: { fontSize: 10 } },
      yAxis: { type: 'value', axisLabel: { fontSize: 10 } },
      series: [{ name: '合同数', type: 'bar', data: count, itemStyle: { color: '#722ed1' }, barWidth: '50%' }]
    });
    fundDimCharts['chartDaysHist'] = chart;
  }
  async function loadFundRisk() {
    var panel = document.getElementById('fundDimRisk');
    if (!panel) return;
    panel.innerHTML = '<div class="ana-empty"><div>加载中...</div></div>';
    var risk = await fundFetch('/api/core/metrics/fund/risk/list');
    var trend = await fundFetch('/api/core/metrics/fund/risk/trend?dim=region');
    var cfg = await fundFetch('/api/core/metrics/fund/risk/config');
    fundRiskData = risk;
    var rows = risk.success ? (risk.rows || []) : [];
    var warnings = trend.success ? (trend.warnings || []) : [];
    var config = cfg.success ? (cfg.config || []) : [];
    var cfgMap = {}; config.forEach(function (c) { cfgMap[c.key] = c.value; });
    var html = '<div class="cards" style="grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:16px">';
    html += '<div class="card"><div class="lbl">🔴 高危</div><div class="val c" style="font-size:22px;color:#ff4d4f">' + (risk.stat ? risk.stat.red : 0) + '</div></div>';
    html += '<div class="card"><div class="lbl">🟠 预警</div><div class="val c" style="font-size:22px;color:#fa8c16">' + (risk.stat ? risk.stat.orange : 0) + '</div></div>';
    html += '<div class="card"><div class="lbl">🟡 关注</div><div class="val c" style="font-size:22px;color:#faad14">' + (risk.stat ? risk.stat.yellow : 0) + '</div></div>';
    html += '<div class="card"><div class="lbl">🟢 健康</div><div class="val c" style="font-size:22px;color:#52c41a">' + (risk.stat ? risk.stat.healthy : 0) + '</div></div>';
    html += '</div>';
    html += '<div class="panel" style="margin-bottom:16px"><h3>⚙️ 预警阈值配置（默认值，可调整）</h3>';
    html += '<div style="display:flex;gap:16px;flex-wrap:wrap;align-items:center;font-size:12px">';
    html += '<label>健康≤<input type="number" id="cfgDaysGreen" value="' + (cfgMap.days_green || 30) + '" style="width:60px">天</label>';
    html += '<label>关注≤<input type="number" id="cfgDaysYellow" value="' + (cfgMap.days_yellow || 90) + '" style="width:60px">天</label>';
    html += '<label>预警> <input type="number" id="cfgDaysOrange" value="' + (cfgMap.days_orange || 180) + '" style="width:60px">天</label>';
    html += '<label>回款率≥<input type="number" id="cfgRecvRate" value="' + (cfgMap.recv_rate || 0.5) + '" step="0.05" style="width:60px"></label>';
    html += '<label>占用强度><input type="number" id="cfgIntensity" value="' + (cfgMap.intensity || 0.5) + '" step="0.05" style="width:60px"></label>';
    html += '<label>高危金额≥<input type="number" id="cfgAmountHigh" value="' + (cfgMap.amount_high || 1000000) + '" style="width:90px">元</label>';
    html += '<label>环比连续<input type="number" id="cfgTrendMonths" value="' + (cfgMap.trend_months || 2) + '" style="width:50px">月上升</label>';
    html += '<button class="btn btn-c btn-sm" onclick="FinanceFund.saveRiskConfig()">保存并重算</button>';
    html += '</div></div>';
    html += '<div class="panel" style="margin-bottom:16px"><h3>📈 趋势预警（占用金额环比连续上升）</h3>';
    if (warnings.length) {
      html += '<div class="twrap"><table class="ana-table"><thead><tr><th>维度</th><th>对象</th><th>说明</th></tr></thead><tbody>';
      warnings.forEach(function (w) { html += '<tr><td>' + (w.dim === 'region' ? '区域' : '客户集合') + '</td><td class="wrap">' + w.dim_value + '</td><td style="color:#fa8c16">' + w.message + '</td></tr>'; });
      html += '</tbody></table></div>';
    } else { html += '<div style="padding:12px;color:var(--text2);font-size:12px">当前无趋势预警</div>'; }
    html += '</div>';
    html += '<div class="card" style="padding:12px;margin-bottom:16px"><div style="font-size:13px;font-weight:600;margin-bottom:4px">风险矩阵（占用金额 × 占用强度，红=高危）</div>' + fundChartDiv('chartRiskScatter', 320) + '</div>';
    html += '<div class="panel"><h3>⚠️ 预警清单（TOP 50）</h3>';
    if (rows.length) {
      html += '<div style="margin-bottom:8px;display:flex;gap:8px;align-items:center">';
      html += '<select id="fundRiskLevelFilter" style="padding:4px 8px;font-size:12px" onchange="FinanceFund.filterRiskTable()">';
      html += '<option value="">全部等级</option><option value="red">高危</option><option value="orange">预警</option><option value="yellow">关注</option><option value="healthy">健康</option></select>';
      html += '<span style="font-size:11px;color:var(--text2)" id="riskFilterCount"></span>';
      html += '</div>';
      html += '<div class="twrap"><table class="ana-table" id="fundRiskTable"><thead><tr><th style="text-align:left;padding-left:8px">合同编号</th><th style="text-align:left;padding-left:8px">客户键</th><th style="text-align:left;padding-left:8px">区域</th><th style="text-align:left;padding-left:8px">部门</th><th style="text-align:left;padding-left:8px">项目状态</th><th style="text-align:right;padding-right:8px">当前占用</th><th style="text-align:right;padding-right:8px">回款率</th><th style="text-align:right;padding-right:8px">占用强度</th><th>风险</th><th style="text-align:left;padding-left:8px">干预建议</th></tr></thead><tbody>';
      rows.slice(0, 50).forEach(function (x) {
        var color = { red: '#ff4d4f', orange: '#fa8c16', yellow: '#faad14', healthy: '#52c41a' }[x.risk_level] || 'var(--text)';
        html += '<tr data-level="' + x.risk_level + '"><td class="wrap">' + x.contract_no + '</td><td>' + x.customer_key + '</td><td>' + x.region + '</td><td>' + x.dept + '</td><td>' + x.project_status + '</td><td class="num pay-green">¥' + fundMoney(x.current_occupy) + '</td><td class="num">' + (x.recv_rate * 100).toFixed(1) + '%</td><td class="num">' + (x.occupy_intensity * 100).toFixed(1) + '%</td><td style="color:' + color + ';font-weight:600">' + x.risk_name + '</td><td style="font-size:11px">' + x.suggestion + '</td></tr>';
      });
      html += '</tbody></table></div>';
      html += '<div style="margin-top:8px;font-size:11px;color:var(--text2)">共 ' + rows.length + ' 条预警记录</div>';
    } else { html += '<div style="padding:12px;color:var(--text2);font-size:12px">暂无预警记录</div>'; }
    html += '</div>';
    panel.innerHTML = html;
    if (rows.length) fundChartRiskScatter(rows);
    if (document.getElementById('riskFilterCount')) document.getElementById('riskFilterCount').textContent = '共 ' + rows.length + ' 条';
  }
  function fundChartRiskScatter(rows) {
    var el = document.getElementById('chartRiskScatter');
    if (!el || !window.echarts) return;
    var chart = echarts.init(el, 'cc-dark');
    var data = rows.slice(0, 100).map(function (r) { return {
      value: [r.current_occupy || 0, r.occupy_intensity || 0, r.contract_no],
      itemStyle: { color: { red: '#ff4d4f', orange: '#fa8c16', yellow: '#faad14', healthy: '#52c41a' }[r.risk_level] || '#52c41a' }
    }; });
    chart.setOption({
      tooltip: { formatter: function (p) { return p.value[2] + '<br/>占用：¥' + fundMoney(p.value[0]) + '<br/>强度：' + (p.value[1] * 100).toFixed(1) + '%'; } },
      grid: { left: 70, right: 20, top: 20, bottom: 30 },
      xAxis: { type: 'value', name: '占用金额', nameTextStyle: { fontSize: 10 }, axisLabel: { fontSize: 10, formatter: fundMoney } },
      yAxis: { type: 'value', name: '占用强度', min: 0, max: 1, nameTextStyle: { fontSize: 10 }, axisLabel: { fontSize: 10, formatter: function (v) { return (v * 100) + '%'; } } },
      series: [{ type: 'scatter', data: data, symbolSize: 12 }]
    });
    fundDimCharts['chartRiskScatter'] = chart;
  }
  function filterRiskTable() {
    var lv = document.getElementById('fundRiskLevelFilter').value;
    var rows = document.querySelectorAll('#fundRiskTable tbody tr');
    var cnt = 0;
    rows.forEach(function (tr) {
      var ok = !lv || tr.getAttribute('data-level') === lv;
      tr.style.display = ok ? '' : 'none';
      if (ok) cnt++;
    });
    document.getElementById('riskFilterCount').textContent = cnt + ' / ' + rows.length + ' 条';
  }
  async function saveRiskConfig() {
    var payload = {
      days_green: parseFloat(document.getElementById('cfgDaysGreen').value || 30),
      days_yellow: parseFloat(document.getElementById('cfgDaysYellow').value || 90),
      days_orange: parseFloat(document.getElementById('cfgDaysOrange').value || 180),
      recv_rate: parseFloat(document.getElementById('cfgRecvRate').value || 0.5),
      intensity: parseFloat(document.getElementById('cfgIntensity').value || 0.5),
      amount_high: parseFloat(document.getElementById('cfgAmountHigh').value || 1000000),
      trend_months: parseInt(document.getElementById('cfgTrendMonths').value || 2, 10)
    };
    var loading = document.getElementById('fundDimLoading');
    if (loading) loading.textContent = '保存并重算中...';
    try {
      var r = await fetch('/api/core/metrics/fund/risk/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      var j = await r.json();
      if (loading) loading.textContent = j.message || '已保存';
      await FinanceFund.run();
    } catch (e) { if (loading) loading.textContent = '保存失败: ' + e.message; }
  }
  async function fundDrill(dim, value, label) {
    var modal = document.getElementById('fundDrillModal');
    if (!modal) { modal = document.getElementById('fundDrillModal'); }
    modal.style.display = 'flex';
    modal.innerHTML = '<div style="background:var(--bg);border-radius:10px;max-width:1000px;width:92%;max-height:88vh;overflow-y:auto;padding:20px;border:1px solid var(--border)">'
      + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px"><h3 style="margin:0">🔍 ' + pcEsc(label) + ' — 合同清单</h3>'
      + '<button class="btn btn-o" onclick="FinanceFund.closeDrill()" style="padding:4px 12px">✕ 关闭</button></div>'
      + '<div id="fundDrillContent" style="min-height:100px">加载中...</div></div>';
    var r = await fundFetch('/api/core/metrics/fund/drill?dim=' + encodeURIComponent(dim) + '&value=' + encodeURIComponent(value));
    var box = document.getElementById('fundDrillContent');
    if (!r.success) { box.innerHTML = '<div style="color:var(--text2)">' + r.error + '</div>'; return; }
    if (!r.rows.length) { box.innerHTML = '<div style="color:var(--text2)">该维度下暂无合同</div>'; return; }
    var h = '<div style="margin-bottom:12px;font-size:13px">当前占用合计：<b style="color:#fa8c16">¥' + fundMoney(r.total_occupy) + '</b></div>';
    h += '<div class="twrap"><table class="ana-table"><thead><tr><th>合同编号</th><th>客户键</th><th>部门</th><th>业务线</th><th>项目状态</th><th>合同额</th><th>当前占用</th><th>回款率</th><th>风险</th><th>操作</th></tr></thead><tbody>';
    r.rows.forEach(function (x) {
      var color = { red: '#ff4d4f', orange: '#fa8c16', yellow: '#faad14', healthy: '#52c41a' }[x['风险等级']] || 'var(--text)';
      var riskName = { healthy: '健康', yellow: '关注', orange: '预警', red: '高危' }[x['风险等级']] || x['风险等级'];
      h += '<tr><td class="wrap">' + x['合同编号'] + '</td><td>' + x['客户键'] + '</td><td>' + x['部门'] + '</td><td>' + x['业务线'] + '</td><td>' + x['项目状态'] + '</td><td class="num">¥' + fundMoney(x['合同额']) + '</td><td class="num pay-green">¥' + fundMoney(x['当前资金占用']) + '</td><td class="num">' + (x['回款率'] * 100).toFixed(1) + '%</td><td style="color:' + color + ';font-weight:600">' + riskName + '</td><td><button class="btn btn-o btn-sm" onclick="FinanceFund.closeDrill();FinanceFund.showFundDetail(\'' + String(x['合同编号']).replace(/'/g, '\\\'') + '\')">片段明细</button></td></tr>';
    });
    h += '</tbody></table></div>';
    box.innerHTML = h;
  }
  function closeDrill() { var m = document.getElementById('fundDrillModal'); if (m) m.style.display = 'none'; }
  function filterFundTable() {
    var kw = document.getElementById('fundFilter').value.toUpperCase();
    var rows = document.querySelectorAll('#fundTable tbody tr');
    var cnt = 0;
    rows.forEach(function (tr) {
      var cno = tr.cells && tr.cells[0] ? (tr.cells[0].textContent || '').toUpperCase() : '';
      var match = !kw || cno.indexOf(kw) >= 0;
      tr.style.display = match ? '' : 'none';
      if (match) cnt++;
    });
    document.getElementById('fundFilterCount').textContent = cnt + ' / ' + rows.length + ' 条';
  }

  /* ── 详情弹窗（垫资片段 / 流水 / 现金流）共 3 tab ── */
  var fundDetailData = null, fundDetailCno = '';
  async function showFundDetail(cno) {
    fundDetailCno = cno;
    document.getElementById('fundDetailModal').style.display = 'flex';
    document.getElementById('fundDetailTitle').textContent = '📋 ' + cno + ' — 垫资冲抵明细';
    document.getElementById('fundDetailContent').innerHTML = '<div class="ana-empty"><div>加载中...</div></div>';
    var btns = ['tabBtnSegments', 'tabBtnFlows', 'tabBtnCashflow'];
    btns.slice(1).forEach(function (b) { var e = document.getElementById(b); if (e) e.className = 'btn btn-o btn-sm'; });
    var b0 = document.getElementById('tabBtnSegments'); if (b0) b0.className = 'btn btn-c btn-sm';
    try {
      var r = await fetch('/api/core/metrics/fund/segments?key=' + encodeURIComponent(cno));
      fundDetailData = await r.json();
      renderFundSegments();
    } catch (e) { document.getElementById('fundDetailContent').innerHTML = '<div class="ana-empty"><div>加载失败: ' + e.message + '</div></div>'; }
  }
  function closeFundDetail() { document.getElementById('fundDetailModal').style.display = 'none'; fundDetailData = null; }
  function switchFundTab(tab) {
    ['tabBtnSegments', 'tabBtnFlows', 'tabBtnCashflow'].forEach(function (b) {
      var e = document.getElementById(b); if (e) e.className = 'btn ' + ((tab === 'segments' && b === 'tabBtnSegments') || (tab === 'flows' && b === 'tabBtnFlows') || (tab === 'cashflow' && b === 'tabBtnCashflow') ? 'btn-c' : 'btn-o') + ' btn-sm';
    });
    if (tab === 'segments') renderFundSegments();
    else if (tab === 'flows') renderFundFlows();
    else renderFundCashflow();
  }
  function renderFundSegments() {
    var d = fundDetailData;
    var box = document.getElementById('fundDetailContent');
    if (!d || !d.segments || !d.segments.length) {
      box.innerHTML = '<div class="ana-empty"><div>该合同无垫资记录（纯收款合同）</div></div>';
      return;
    }
    var h = '<div class="twrap"><table class="ana-table"><thead><tr>';
    h += '<th>状态</th><th>原付款日期</th><th>片段金额</th><th>结束日期</th><th>占用天数</th><th>加权占用</th></tr></thead><tbody>';
    d.segments.forEach(function (s) {
      var st;
      if (s.segment_status === 'SETTLED') st = '✅ 已结清';
      else if (s.segment_status === 'PRESETTLED') st = '🔵 预收冲抵';
      else st = '🔴 占用中';
      h += '<tr><td>' + st + '</td><td>' + s.pay_occur_date + '</td><td class="pos">¥' + (s.segment_amount || 0).toLocaleString() + '</td><td>' + s.end_date + '</td><td>' + (s.occupy_days || 0) + '</td><td class="pos">' + (s.amount_day || 0).toLocaleString() + '</td></tr>';
    });
    h += '</tbody></table></div>';
    if (d.local_summary) {
      h += '<div class="cards" style="margin-top:16px">';
      h += '<div class="card"><div class="lbl">当前占用金额</div><div class="val c">¥' + (d.local_summary.current_occupy || 0).toLocaleString() + '</div></div>';
      h += '<div class="card"><div class="lbl">总加权资金占用</div><div class="val c">' + (d.local_summary.sum_amount_day || 0).toLocaleString() + '</div></div>';
      h += '<div class="card"><div class="lbl">片段总数</div><div class="val c">' + (d.local_summary.total_segments || 0) + '</div></div>';
      h += '</div>';
    }
    box.innerHTML = h;
  }
  function renderFundFlows() {
    var d = fundDetailData;
    var box = document.getElementById('fundDetailContent');
    if (!d || !d.flows) { box.innerHTML = '<div class="ana-empty"><div>无流水数据</div></div>'; return; }
    var flows = d.flows;
    var h = '<h4 style="margin:0 0 8px 0">💳 付款流水 (' + (flows.payments || []).length + '条)</h4>';
    if (flows.payments && flows.payments.length) {
      h += '<div class="twrap"><table class="ana-table"><thead><tr><th>流水ID</th><th>日期</th><th>金额</th></tr></thead><tbody>';
      flows.payments.forEach(function (p) { h += '<tr><td>' + p.flow_id + '</td><td>' + p.occur_date + '</td><td class="neg">¥' + (p.amount || 0).toLocaleString() + '</td></tr>'; });
      h += '</tbody></table></div>';
    } else { h += '<div style="color:var(--text2)">无付款记录</div>'; }
    h += '<h4 style="margin:16px 0 8px 0">💰 回款流水 (' + (flows.collections || []).length + '条)</h4>';
    if (flows.collections && flows.collections.length) {
      h += '<div class="twrap"><table class="ana-table"><thead><tr><th>流水ID</th><th>日期</th><th>金额</th></tr></thead><tbody>';
      flows.collections.forEach(function (c) { h += '<tr><td>' + c.flow_id + '</td><td>' + c.occur_date + '</td><td class="pos">¥' + (c.amount || 0).toLocaleString() + '</td></tr>'; });
      h += '</tbody></table></div>';
    } else { h += '<div style="color:var(--text2)">无回款记录</div>'; }
    box.innerHTML = h;
  }
  function renderFundCashflow() {
    var d = fundDetailData;
    var box = document.getElementById('fundDetailContent');
    if (!d) return;
    var cf = d.cashflow || [];
    var cm = d.cashflow_monthly || [];
    if (!cf.length && !cm.length) { box.innerHTML = '<div class="ana-empty"><div>该合同无现金流记录</div></div>'; return; }
    var h = '';
    h += '<div class="chart-box"><h3>📈 累计现金流曲线（净现金余额，负=垫资中）</h3><div id="cashflowChart" style="height:300px"></div></div>';
    if (cm.length) {
      var latest = cm[cm.length - 1];
      h += '<div style="margin-bottom:16px;padding:16px;background:var(--card);border:1px solid var(--cyan);border-radius:8px">';
      h += '<div style="font-size:12px;color:var(--text2)">💵 当前现金流（截至 ' + latest.month + '，负值=垫资中）</div>';
      h += '<div style="font-size:28px;font-weight:bold;color:var(--cyan);margin-top:4px">¥' + (latest.balance || 0).toLocaleString() + '</div></div>';
    }
    if (cm.length) {
      var reversed = cm.slice().reverse();
      h += '<div class="panel"><h3>📅 按月现金流汇总（时间倒序）</h3><div class="twrap"><table class="ana-table"><thead><tr>';
      h += '<th>月份</th><th>付款</th><th>回款</th><th>净现金流</th><th>月末累计余额</th></tr></thead><tbody>';
      reversed.forEach(function (m, idx) {
        var isFirst = idx === 0;
        var rowStyle = isFirst ? ' style="background:rgba(79,140,255,0.10)"' : '';
        h += '<tr' + rowStyle + '>';
        h += '<td>' + (isFirst ? '<b>' + m.month + ' 🔴当前</b>' : m.month) + '</td>';
        h += '<td class="pay-green">¥' + Math.abs(m.pay_amount || 0).toLocaleString() + '</td>';
        h += '<td class="recv-red">¥' + (m.recv_amount || 0).toLocaleString() + '</td>';
        h += '<td class="cf-balance">¥' + (m.net || 0).toLocaleString() + '</td>';
        h += '<td class="cf-balance">¥' + (m.balance || 0).toLocaleString() + '</td></tr>';
      });
      h += '</tbody></table></div></div>';
    }
    if (cf.length) {
      var reversedCf = cf.slice().reverse();
      h += '<div class="panel"><h3>📄 逐笔现金流明细（' + cf.length + '笔，倒序）</h3><div class="twrap"><table class="ana-table"><thead><tr>';
      h += '<th>日期</th><th>类型</th><th>金额</th><th>累计余额</th></tr></thead><tbody>';
      reversedCf.forEach(function (e) {
        var t = e.type === 'PAY' ? '💳 付款' : '💰 回款';
        var amtCls = e.type === 'PAY' ? 'pay-green' : 'recv-red';
        var amt = e.type === 'PAY' ? Math.abs(e.amount || 0) : (e.amount || 0);
        h += '<tr><td>' + e.date + '</td><td>' + t + '</td><td class="' + amtCls + '">¥' + amt.toLocaleString() + '</td><td class="cf-balance">¥' + (e.balance || 0).toLocaleString() + '</td></tr>';
      });
      h += '</tbody></table></div></div>';
    }
    box.innerHTML = h;
    setTimeout(function () { drawCashflowChart(cm); }, 100);
  }
  function drawCashflowChart(cm) {
    var el = document.getElementById('cashflowChart');
    if (!el || !window.echarts) return;
    var chart = echarts.init(el, 'cc-dark');
    var months = cm.map(function (m) { return m.month; });
    var balances = cm.map(function (m) { return m.balance; });
    chart.setOption({
      tooltip: { trigger: 'axis', formatter: function (p) { var v = p[0]; return '<b>' + v.axisValue + '</b><br/>累计现金流：¥' + (v.value || 0).toLocaleString(); } },
      grid: { left: 70, right: 20, top: 30, bottom: 50 },
      xAxis: { type: 'category', data: months, axisLabel: { color: '#7d8db0', fontSize: 10, rotate: 35 } },
      yAxis: { type: 'value', axisLabel: { color: '#7d8db0', formatter: function (v) { return (v / 10000).toFixed(0) + '万'; } } },
      series: [{ name: '累计现金流', type: 'line', data: balances, smooth: true, symbol: 'circle', symbolSize: 6, lineStyle: { width: 2, color: '#4f8cff' }, itemStyle: { color: '#4f8cff' }, areaStyle: { color: 'rgba(79,140,255,0.14)' } }]
    });
  }

  /* ── 加载 / 导出 ──
   * GET 默认读快照（秒级，后端 /api/core/metrics/fund 不带 refresh）；
   * 仅点击「执行分析」或「保存并重算」时传 refresh=1 强制全量重算。 */
  async function load(refresh) {
    var runBtn = document.getElementById('btnFundRun');
    if (runBtn) { runBtn.disabled = true; runBtn.textContent = '⏳ ' + (refresh ? '重算中...' : '加载中...'); }
    status(refresh ? '正在全量重算资金占用（实时计算）...' : '读取资金占用分析数据（快照，秒级）...');
    try {
      var r = await fetch(API + '/api/core/metrics/fund' + (refresh ? '?refresh=1' : ''));
      var j = await r.json();
      if (!j.success) { status(j.error || '读取失败'); showError((j.error || '读取失败') + '。'); return; }
      data = j.data;
      status((refresh ? '重算完成（实时计算）' : '已读取快照（秒级）') + ' · 数据来源：finance_detail 收付款明细（按 project_no 归集回落 contract_no）· FIFO 冲抵 · 分析完成'
        + (j.updated_at ? ' · 更新于 ' + j.updated_at : ''));
      var exp = document.getElementById('btnFundExport'); if (exp) exp.style.display = 'inline';
      var expR = document.getElementById('btnFundRiskExport'); if (expR) expR.style.display = 'inline';
      renderResult();
    } catch (e) { status('读取失败: ' + e.message); showError('读取失败: ' + e.message); }
    finally { if (runBtn) { runBtn.disabled = false; runBtn.textContent = '▶ 执行分析'; } }
  }
  function showError(msg) {
    document.getElementById('fundContent').innerHTML = '<div class="ana-empty"><div class="icon">⚠️</div><div>' + msg + '</div></div>';
  }
  function csvOf(items, head, cols, fmt) {
    var lines = [head.join(',')];
    items.forEach(function (r) {
      var csv = function (s) { s = (s === null || s === undefined) ? '' : String(s); return '"' + s.replace(/"/g, '""') + '"'; };
      lines.push(cols.map(function (c, i) { return csv(fmt[i](r)); }).join(','));
    });
    return '\ufeff' + lines.join('\r\n');
  }
  function download(filename, text) {
    var blob = new Blob([text], { type: 'text/csv;charset=utf-8' });
    var a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = filename;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
  }
  function exportResult() {
    var rows = (data && data.rows) || [];
    if (!rows.length) { status('暂无数据可导出'); return; }
    download('资金占用分析_' + new Date().toISOString().slice(0, 10) + '.csv', csvOf(rows,
      ['合同编号', '合同额', '累计付款', '累计收款', '净现金流', '当前资金占用', '上年同期占用', '元天合计', '周期起始日', '周期总天数', '平均资金占用', '预估资金成本', '年化成本率', '片段数', '已结清片段', '占用中片段', '回款率', '占用强度', '风险等级', '最后一次回款'],
      ['合同编号', '合同额', '累计付款', '累计收款', '净现金流', '当前资金占用', '上年同期占用', '元天合计', '周期起始日', '周期总天数', '平均资金占用', '预估资金成本', '年化成本率', '片段数', '已结清片段', '占用中片段', '回款率', '占用强度', '风险等级', '最后一次回款'],
      ['合同编号', '合同额', '累计付款', '累计收款', '净现金流', '当前资金占用', '上年同期占用', '元天合计', '周期起始日', '周期总天数', '平均资金占用', '预估资金成本', '年化成本率', '片段数', '已结清片段', '占用中片段', '回款率', '占用强度', '风险等级', '最后一次回款'].map(function () { return function (r) { return r; }; })));
    status('已导出 ' + rows.length + ' 条');
  }
  function exportRisk() {
    var rows = (data && data.rows) || [];
    var warn = rows.filter(function (r) { return r['风险等级'] === 'red' || r['风险等级'] === 'orange'; });
    download('资金占用预警清单_' + new Date().toISOString().slice(0, 10) + '.csv', csvOf(warn,
      ['合同编号', '客户键', '区域', '部门', '当前占用', '回款率', '占用强度', '风险等级', '风险建议'],
      ['合同编号', '客户键', '区域', '部门', '当前占用', '回款率', '占用强度', '风险等级', '风险建议'],
      ['合同编号', '客户键', '区域', '部门', '当前占用', '回款率', '占用强度', '风险等级', '风险建议'].map(function () { return function (r, i) { return [r['合同编号'], r['客户键'], r['区域'], r['部门'], r['当前资金占用'], r['回款率'], r['占用强度'], r['风险等级'], r['风险建议']][i]; }; })));
    status('已导出预警 ' + warn.length + ' 条');
  }

  /* 暴露给视图/内联事件的统一接口 */
  root.FinanceFund = {
    run: function () { return load(true); }, load: load,
    setFundPage: renderFundDetailPage, onDimTab: onDimTab,
    filterFundTable: filterFundTable, filterRiskTable: filterRiskTable,
    fundDrill: fundDrill, closeDrill: closeDrill, fundMapSwitch: fundMapSwitch,
    saveRiskConfig: saveRiskConfig,
    showFundDetail: showFundDetail, closeFundDetail: closeFundDetail, switchFundTab: switchFundTab,
    exportResult: exportResult, exportRisk: exportRisk
  };

  renderShell();
  load();
})(window);