'use strict';
/* 财经 · 回款周期 独立页 —— 1:1 复刻旧门户 index.html openPaymentCycle / renderPaymentAnalysis。
 * 壳：renderTopMenu(activeKey=fin)、renderAccordion(财经域 sections)、面包屑。
 * 数据：/api/core/metrics/payment-cycle（core_project 主数据 + finance_detail 回款，见 backend/core/project_metrics.py）。
 * 内容逐一照搬旧门户：KPI 卡 / ICID 整体汇总 / 系统集成部门汇总 / 回款周期分区明细统计表(同比) /
 * 可视化(项目个数同比/平均回款周期同比/分区分布/气泡图) / 中国地图(六大区合并+省份着色) / 补充后数据明细表。
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

  var data = null;   // /api/core/metrics/payment-cycle 返回 data

  function renderShell() {
    NC.renderBreadcrumb(document.getElementById('breadcrumb'), ['财经', '资金运作', '回款周期']);
    NC.renderTopMenu(document.getElementById('topMenu'), { activeKey: 'fin' });
    NC.renderAccordion(document.getElementById('navRail'), {
      rootTitle: '经营业务工作台', domainLabel: '财经', activeKey: 'fin',
      activeLink: 'fin-cycle', sections: SECTIONS
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

  function status(msg) { var el = document.getElementById('anaStatus'); if (el) el.textContent = msg; }

  /* 中国地图：六大区合并 + 省份着色（Tab 切换） */
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

  /* 渲染工具（沿用旧页面口径） */
  function _val(v, d) { return v != null ? v : d; }
  function _fmt(n, d) { var v = _val(n, d); return typeof v === 'number' ? v.toLocaleString() : v; }
  function _diff(cur, prev) { if (cur == null || prev == null) return '-'; var d = cur - prev; if (d === 0) return '0'; var s = d > 0 ? '+' : ''; return s + d.toLocaleString(); }
  function _clr(v) { if (typeof v === 'number') return v < 0 ? 'neg' : v > 0 ? 'pos' : ''; return ''; }

  /* ════ 主渲染（1:1 照搬旧门户 renderPaymentAnalysis） ════ */
  function renderPaymentAnalysis(d, hostEl) {
    var months = d.months || [];
    function monthSubHeaders(label) {
      var h = '<th class="metric-col">' + label + '</th>';
      months.forEach(function (m) { h += '<th class="h-cur">' + m.current + '</th><th class="h-prev">' + m.last_year + '</th><th class="h-diff">增长额</th>'; });
      return h;
    }
    function monthCells(data, key) {
      var h = '';
      months.forEach(function (m) {
        var grp = (data[key] || {})[m.key] || {};
        var cur = _val(grp.current, '-'), prev = _val(grp.previous, '-');
        h += '<td class="td-cur">' + _fmt(cur, '-') + '</td><td class="td-prev">' + _fmt(prev, '-') + '</td><td class="' + _clr(grp.diff) + '">' + _diff(cur, prev) + '</td>';
      });
      return h;
    }
    function monthCellsRaw(data, key) {
      var h = '';
      months.forEach(function (m) {
        var grp = (data[key] || {})[m.key] || {};
        h += '<td>' + _val(grp.current, '-') + '</td><td>' + _val(grp.previous, '-') + '</td><td class="' + _clr(grp.diff) + '">' + _diff(grp.current, grp.previous) + '</td>';
      });
      return h;
    }

    var icid = d.icid || {}, dept = d.department || {}, zones = d.zones || [];

    var html = '';

    // ========== KPI 总览卡片区 ==========
    var kpiRows = d.enriched_rows || [];
    var kpiTotal = kpiRows.length;
    var kpiWith = 0, kpiNo = 0, kpiAmount = 0, kpiSumDays = 0;
    kpiRows.forEach(function (r) { var cd = r.cycle_days || 0; var amt = (r.amount || 0) / 10000; if (cd > 0) { kpiWith++; kpiSumDays += cd; } else { kpiNo++; } kpiAmount += amt; });
    var kpiAvg = kpiWith > 0 ? Math.round(kpiSumDays / kpiWith) : 0;
    var kpiSorted = kpiRows.map(function (r) { return r.cycle_days || 0; }).filter(function (v) { return v > 0; }).sort(function (a, b) { return a - b; });
    var kpiMed = kpiSorted.length > 0 ? (kpiSorted.length % 2 === 1 ? kpiSorted[(kpiSorted.length - 1) / 2] : (kpiSorted[kpiSorted.length / 2 - 1] + kpiSorted[kpiSorted.length / 2]) / 2) : 0;
    var kpiMapped = [
      { l: '签约合同（份）', v: kpiTotal, c: 'c', icon: '📄' },
      { l: '已有回款（份）', v: kpiWith, c: 'g', icon: '✅' },
      { l: '无回款（份）', v: kpiNo, c: kpiNo > 0 ? 'r' : '', icon: '⚠️' },
      { l: '平均回款周期（天）', v: kpiAvg, c: 'o', icon: '⏱️' },
      { l: '中位回款周期（天）', v: Math.round(kpiMed), c: 'p', icon: '📐' },
      { l: '合同总额（万元）', v: Math.round(kpiAmount), c: 'c', icon: '💰' }
    ];
    html += '<div class="cards" style="grid-template-columns:repeat(auto-fit,minmax(160px,1fr))">';
    kpiMapped.forEach(function (k) { html += '<div class="card"><div class="lbl">' + k.icon + ' ' + k.l + '</div><div class="val ' + k.c + '">' + k.v.toLocaleString() + '</div></div>'; });
    html += '</div>';

    // 区块1: ICID 整体汇总
    html += '<div class="ana-block"><div class="block-title">📊 ICID 整体汇总</div>';
    html += '<div class="twrap" style="max-height:none"><table class="ana-table">';
    html += '<thead><tr>' + monthSubHeaders('指标名称') + '</tr></thead><tbody>';
    html += '<tr><td class="metric-name">合同额（万元）</td>' + monthCells(icid, 'contract_amount') + '</tr>';
    html += '<tr><td class="metric-name">项目个数</td>' + monthCells(icid, 'project_count') + '</tr>';
    html += '<tr><td class="metric-name">当年累计回款周期（天）</td>' + monthCells(icid, 'cumulative_days') + '</tr>';
    html += '<tr class="gray-row"><td class="metric-name">平均合同回款周期（天）</td>' + monthCells(icid, 'avg_days') + '</tr>';
    html += '<tr class="gray-row"><td class="metric-name">平均合同回款周期（年）</td>' + monthCells(icid, 'avg_years') + '</tr>';
    html += '</tbody></table></div></div>';

    // 区块2: 系统集成 部门汇总
    html += '<div class="ana-block"><div class="block-title">🏢 系统集成 部门汇总</div>';
    html += '<div class="twrap" style="max-height:none"><table class="ana-table">';
    html += '<thead><tr>' + monthSubHeaders('指标名称') + '</tr></thead><tbody>';
    html += '<tr><td class="metric-name">合同额（万元）</td>' + monthCells(dept, 'contract_amount') + '</tr>';
    html += '<tr><td class="metric-name">项目个数</td>' + monthCells(dept, 'project_count') + '</tr>';
    html += '<tr><td class="metric-name">当年累计回款周期（天）</td>' + monthCells(dept, 'cumulative_days') + '</tr>';
    html += '<tr class="gray-row"><td class="metric-name">平均合同回款周期（天）</td>' + monthCells(dept, 'avg_days') + '</tr>';
    html += '<tr class="gray-row"><td class="metric-name">平均合同回款周期（年）</td>' + monthCells(dept, 'avg_years') + '</tr>';
    html += '</tbody></table></div></div>';

    // 区块3: 回款周期分区明细统计表
    html += '<div class="ana-block"><div class="block-title">📋 回款周期分区明细统计表</div>';
    html += '<div class="twrap" style="max-height:none"><table class="ana-table">';
    html += '<thead><tr class="zone-header"><th>回款周期分区</th>';
    months.forEach(function (m) { html += '<th class="h-cur">' + m.current + '</th><th class="h-prev">' + m.last_year + '</th><th class="h-diff">差值</th>'; });
    html += '</tr></thead><tbody>';
    var zoneLabels = ['0.5以内', '0.5-1年', '1年以上', '2年以上', '3年以上', '总计'];
    zones.forEach(function (z, i) {
      var cls = i === zones.length - 1 ? 'total-row' : '';
      html += '<tr class="' + cls + '"><td class="metric-name">' + zoneLabels[i] + '</td>' + monthCellsRaw(z, 'data') + '</tr>';
    });
    html += '</tbody></table></div></div>';

    // ========== 可视化图表区（2列布局） ==========
    var lastKey = months[months.length - 1].key;

    html += '<div class="ana-block"><div class="block-title">📈 可视化分析</div><div style="font-size:11px;color:var(--text2);margin-top:-6px;margin-bottom:12px">Average（每笔合同最后一笔回款日期-合同生效日期）</div></div>';

    html += '<div class="ana-grid">';

    // 左列: 项目个数同比（ECharts 柱状图）
    var uidCount = 'chart_count_' + Date.now();
    html += '<div class="ana-block"><div class="block-title">📊 项目个数 同比对比</div><div id="' + uidCount + '" class="chart-box" style="height:260px"></div></div>';

    // 右列: 平均回款周期同比（ECharts 柱状图）
    var uidDays = 'chart_days_' + Date.now();
    html += '<div class="ana-block"><div class="block-title">📊 平均回款周期 同比（天）</div><div id="' + uidDays + '" class="chart-box" style="height:260px"></div></div>';

    // 左列: 回款周期分区分布
    var zoneNames = ['0.5以内', '0.5-1年', '1年以上', '2年以上', '3年以上'];
    var zoneCols = ['#34d399', '#4f8cff', '#fbbf24', '#f87171', '#e5484d'];
    var zoneMax = 0;
    for (var zi = 0; zi < 5; zi++) { zoneMax = Math.max(zoneMax, zones[zi].data[lastKey].current); }
    html += '<div class="ana-block"><div class="block-title">📊 回款周期分区分布（' + months[months.length - 1].current + '）</div><div class="chart-box" style="min-height:180px;display:flex;flex-direction:column;justify-content:center">';
    for (var zj = 0; zj < 5; zj++) {
      var zv = zones[zj].data[lastKey].current;
      var zp = Math.round(zv / Math.max(zoneMax, 1) * 100);
      var showIn = zp >= 16;
      html += '<div style="display:flex;align-items:center;margin:6px 0;font-size:12px">';
      html += '<span style="width:78px;text-align:right;padding-right:10px;color:var(--text2);font-size:11px;white-space:nowrap">' + zoneNames[zj] + '</span>';
      html += '<div style="flex:1;background:var(--bg3);border-radius:6px;overflow:hidden;height:24px;border:1px solid var(--border);display:flex;align-items:center">';
      html += '<div style="width:' + zp + '%;background:' + zoneCols[zj] + ';height:100%;border-radius:6px;display:flex;align-items:center;justify-content:flex-end;padding-right:' + (showIn ? 8 : 0) + 'px;font-size:11px;color:#0b1220;font-weight:bold;box-shadow:inset 0 0 10px rgba(0,0,0,.1);white-space:nowrap">' + (showIn ? zv + '个' : '') + '</div>';
      if (!showIn) html += '<span style="margin-left:8px;color:var(--text);font-size:11px;font-weight:bold">' + zv + '个</span>';
      html += '</div></div>';
    }
    html += '</div></div>';

    // 右列: 回款周期 × 合同金额 气泡图
    var enriched = d.enriched_rows || [];
    var uid2 = '';
    if (enriched.length > 0) {
      uid2 = 'scatter_' + Date.now();
      html += '<div class="ana-block"><div class="block-title">🔵 回款周期 × 合同金额（共' + enriched.length + '个合同）</div><div id="' + uid2 + '" class="chart-box" style="height:380px"></div></div>';
    }

    html += '</div>';

    // 中国地图：独占一整行（六大区合并 + 省份着色，Tab 切换）
    var regions = d.regions || [];
    var provStats = d.province_stats || [];
    html += '<div class="ana-block" style="margin-top:20px"><div class="block-title">🗺️ 中国地图 · 平均回款周期（' + months[months.length - 1].current + '）</div>';
    html += renderChinaMap(regions, provStats);
    html += '</div>';

    if (hostEl) hostEl.innerHTML = html;
    if (hostEl) hostEl.querySelectorAll('.metric-name').forEach(function (td) {
      if (td.scrollWidth > td.clientWidth) td.setAttribute('title', td.textContent);
    });

    setTimeout(function () {
      var xData = months.map(function (m) { return m.current; });
      var elCount = document.getElementById(uidCount); if (elCount) {
        var chartCount = echarts.init(elCount);
        chartCount.setOption({
          tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
          legend: { data: ['2026', '2025'], bottom: 2, textStyle: { color: '#7d8db0', fontSize: 10 }, itemWidth: 12, itemHeight: 8 },
          grid: { left: 42, right: 12, top: 12, bottom: 40 },
          xAxis: { type: 'category', data: xData, axisLabel: { color: '#7d8db0', fontSize: 10, interval: 0 }, axisLine: { lineStyle: { color: '#24324d' } }, axisTick: { show: false } },
          yAxis: { type: 'value', axisLabel: { color: '#7d8db0', fontSize: 10 }, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } } },
          series: [
            { name: '2026', type: 'bar', data: months.map(function (m) { return icid.project_count[m.key].current; }), itemStyle: { color: '#22d3ee', borderRadius: [4, 4, 0, 0] }, barWidth: 14, barGap: '20%' },
            { name: '2025', type: 'bar', data: months.map(function (m) { return icid.project_count[m.key].previous; }), itemStyle: { color: '#7d8db0', borderRadius: [4, 4, 0, 0] }, barWidth: 14 }
          ]
        });
      }
      var elDays = document.getElementById(uidDays); if (elDays) {
        var chartDays = echarts.init(elDays);
        chartDays.setOption({
          tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
          legend: { data: ['2026', '2025'], bottom: 2, textStyle: { color: '#7d8db0', fontSize: 10 }, itemWidth: 12, itemHeight: 8 },
          grid: { left: 42, right: 12, top: 12, bottom: 40 },
          xAxis: { type: 'category', data: xData, axisLabel: { color: '#7d8db0', fontSize: 10, interval: 0 }, axisLine: { lineStyle: { color: '#24324d' } }, axisTick: { show: false } },
          yAxis: { type: 'value', axisLabel: { color: '#7d8db0', fontSize: 10 }, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } } },
          series: [
            { name: '2026', type: 'bar', data: months.map(function (m) { return icid.avg_days[m.key].current; }), itemStyle: { color: '#22d3ee', borderRadius: [4, 4, 0, 0] }, barWidth: 14, barGap: '20%' },
            { name: '2025', type: 'bar', data: months.map(function (m) { return icid.avg_days[m.key].previous; }), itemStyle: { color: '#7d8db0', borderRadius: [4, 4, 0, 0] }, barWidth: 14 }
          ]
        });
      }
      if (uid2) {
        var elScatter = document.getElementById(uid2); if (elScatter) {
          var chartScatter = echarts.init(elScatter);
          var zoneColors = { '0.5以内': '#34d399', '0.5-1年': '#4f8cff', '1年以上': '#fbbf24', '2年以上': '#f87171', '3年以上': '#e5484d' };
          var scatterData = enriched.map(function (r) {
            var amt = (r.amount || 0) / 10000;
            var color = zoneColors[r.zone] || '#7d8db0';
            return { value: [r.cycle_days || 0, amt, amt], name: r.contract_no || '', signDate: r.sign_date || '', dept: r.dept || '', zone: r.zone || '', itemStyle: { color: color, opacity: 0.75 } };
          });
          var maxAmt = 0; scatterData.forEach(function (dd) { maxAmt = Math.max(maxAmt, dd.value[2]); });
          chartScatter.setOption({
            tooltip: { trigger: 'item', formatter: function (p) { return '<b>' + p.data.name + '</b><br/>回款周期：' + p.data.value[0] + '天（' + p.data.zone + '）<br/>合同金额：' + (p.data.value[1]).toFixed(0) + '万元<br/>签约：' + p.data.signDate + '<br/>部门：' + p.data.dept; } },
            legend: { data: Object.keys(zoneColors), bottom: 2, textStyle: { color: '#7d8db0', fontSize: 10 }, itemWidth: 10, itemHeight: 10 },
            grid: { left: 78, right: 24, top: 22, bottom: 58 },
            xAxis: { type: 'value', name: '回款周期（天）', nameLocation: 'center', nameGap: 38, nameTextStyle: { color: '#7d8db0', fontSize: 10 }, axisLabel: { color: '#7d8db0', fontSize: 10 }, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } }, min: 0, max: function (v) { return Math.ceil(v.max / 300) * 300; } },
            yAxis: { type: 'value', name: '合同金额（万元）', nameLocation: 'middle', nameGap: 55, nameTextStyle: { color: '#7d8db0', fontSize: 10 }, axisLabel: { color: '#7d8db0', fontSize: 10 }, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } } },
            series: [{ type: 'scatter', data: scatterData, symbolSize: function (val) { var s = Math.max(6, Math.sqrt(val[2] / Math.max(maxAmt, 1)) * 26); return Math.min(s, 34); }, emphasis: { scale: 1.4 } }]
          });
        }
      }
      setTimeout(function () {
        var host = hostEl || document;
        host.querySelectorAll('.chart-box').forEach(function (el) {
          var cc = echarts.getInstanceByDom(el); if (cc) cc.resize();
        });
      }, 200);
    }, 300);
  }

  function renderChinaMap(regions, provinceStats) {
    var hasRegions = regions && regions.length > 0;
    var hasProvs = provinceStats && provinceStats.length > 0;
    if (!hasRegions && !hasProvs) return '<div style="color:var(--text2);font-size:11px;padding:12px">暂无区域/省份数据</div>';
    var uid = 'chinaMap_' + Date.now();
    var h = '<div style="display:flex;gap:10px;margin-bottom:8px;flex-wrap:wrap">';
    if (hasRegions) h += '<button class="pc-map-tab active" data-pc-tab="' + uid + '_area">🗺️ 六大区</button>';
    if (hasProvs) h += '<button class="pc-map-tab' + (hasRegions ? '' : ' active') + '" data-pc-tab="' + uid + '_prov">🧭 省份</button>';
    h += '</div>';
    h += '<div id="' + uid + '_area" class="map-chart" style="width:100%;height:500px' + (hasRegions ? '' : ';display:none') + '"></div>';
    h += '<div id="' + uid + '_prov" class="map-chart" style="width:100%;height:500px' + (hasRegions ? ';display:none' : '') + '"></div>';
    h += '<div style="display:flex;gap:12px;margin-top:4px;font-size:10px;color:var(--text2);flex-wrap:wrap"><span style="color:#22d3ee">● 回款快</span><span style="color:#a78bfa">● 回款慢</span></div>';
    setTimeout(function () {
      var tabs = document.querySelectorAll('.pc-map-tab[data-pc-tab^="' + uid + '"]');
      tabs.forEach(function (t) {
        t.onclick = function () {
          tabs.forEach(function (x) { x.classList.remove('active'); });
          t.classList.add('active');
          var k = t.getAttribute('data-pc-tab');
          document.getElementById(uid + '_area').style.display = (k === uid + '_area') ? 'block' : 'none';
          document.getElementById(uid + '_prov').style.display = (k === uid + '_prov') ? 'block' : 'none';
          var c1 = echarts.getInstanceByDom(document.getElementById(uid + '_area')); if (c1) c1.resize();
          var c2 = echarts.getInstanceByDom(document.getElementById(uid + '_prov')); if (c2) c2.resize();
        };
      });
      if (!chinaGeoJson) { document.getElementById(uid + '_area').innerHTML = '<div style="color:var(--text2);padding:20px;text-align:center">地图数据加载中...</div>'; return; }
      var srcGeo = chinaGeoJson;
      Promise.all([pcLoadScript(PC_POLYCLIP_URL)]).then(function (res) {
        var pc = res[0];
        if (hasRegions) {
          var elA = document.getElementById(uid + '_area'); if (!elA) return;
          var byArea = {}; regions.forEach(function (r) { if (r.region) byArea[r.region] = r; });
          var regionFeatures = [];
          Object.keys(PC_AREA_PROVINCES).forEach(function (area) {
            var provs = srcGeo.features.filter(function (f) { return PC_AREA_PROVINCES[area].indexOf(f.properties.name) >= 0; });
            if (!provs.length) return;
            var feat;
            if (pc) {
              var geoms = provs.map(function (f) { return f.geometry.type === 'Polygon' ? [f.geometry.coordinates] : f.geometry.coordinates; });
              var merged = [];
              try { merged = pc.union.apply(pc, geoms); } catch (e) { merged = []; }
              feat = { type: 'Feature', properties: {}, geometry: { type: 'MultiPolygon', coordinates: merged } };
            } else {
              var coords = [];
              provs.forEach(function (f) { var c = f.geometry.type === 'MultiPolygon' ? f.geometry.coordinates : [f.geometry.coordinates]; c.forEach(function (poly) { coords.push(poly); }); });
              feat = { type: 'Feature', properties: {}, geometry: { type: 'MultiPolygon', coordinates: coords } };
            }
            if (!feat || !feat.geometry) return;
            feat.properties = { name: area };
            var ctrs = provs.map(function (p) { return pcBBoxCenter(p.geometry.coordinates); }).filter(function (c) { return !!c; });
            var center = ctrs.length ? [ctrs.reduce(function (s, c) { return s + c[0]; }, 0) / ctrs.length, ctrs.reduce(function (s, c) { return s + c[1]; }, 0) / ctrs.length] : null;
            regionFeatures.push({ name: area, feature: feat, center: center });
          });
          ['台湾省', '南海诸岛'].forEach(function (nm) {
            var f = srcGeo.features.find(function (x) { return x.properties.name === nm; });
            if (f) regionFeatures.push({ name: nm, feature: f, center: pcBBoxCenter(f.geometry.coordinates) });
          });
          if (regionFeatures.length < 2) { elA.innerHTML = '<div style="color:var(--text2);padding:20px;text-align:center">区域数据不足</div>'; return; }
          echarts.registerMap('pc_regions', { type: 'FeatureCollection', features: regionFeatures.map(function (r) { return r.feature; }) });
          var values = regions.map(function (r) { return r.avg_days || 0; }).filter(function (v) { return v > 0; });
          var vmin = values.length ? Math.min.apply(null, values) : 0;
          var vmax = values.length ? Math.max.apply(null, values) : 1;
          var areaData = Object.keys(PC_AREA_PROVINCES).map(function (area) { var s = byArea[area]; return { name: area, value: s && s.avg_days > 0 ? s.avg_days : null }; });
          var labelData = regionFeatures.filter(function (r) { return PC_AREA_PROVINCES[r.name] && r.center; }).map(function (r) { var s = byArea[r.name]; return { name: r.name, center: r.center, cycle: s && s.avg_days > 0 ? Math.round(s.avg_days) : null }; });
          var chartA = echarts.init(elA);
          var activeArea = null;
          var applyLabel = function () {
            chartA.setOption({ series: [{ id: 'pc-area-label', data: labelData.map(function (d) { var on = activeArea === d.name; return { name: d.name, value: d.center, label: { show: true, fontSize: on ? 18 : 12, fontWeight: 'bold', color: on ? '#fbbf24' : '#dbe4f5', lineHeight: on ? 22 : 16, formatter: on ? (d.cycle == null ? d.name : d.name + '\n' + d.cycle + '天') : d.name, textBorderColor: '#0b1220', textBorderWidth: 2 } }; }) }] });
          };
          var selectArea = function (area) { activeArea = area; applyLabel(); chartA.dispatchAction({ type: 'downplay', seriesIndex: 0 }); if (area) chartA.dispatchAction({ type: 'highlight', seriesIndex: 0, name: area }); };
          chartA.setOption({
            tooltip: { trigger: 'item', formatter: function (p) {
              if (p.componentType !== 'series' || p.seriesType !== 'map' || !p.name) return '';
              var s = byArea[p.name];
              if (!s) return p.name;
              return pcEsc(p.name) + '<br>平均 ' + pcFmtNum(s.avg_days, 1) + ' 天<br>合同 ' + s.count + ' 份（有回款 ' + s.with_payment + ' / 无回款 ' + s.no_payment + '）<br>金额 ' + pcFmtNum((s.amount || 0) / 10000, 0) + ' 万元';
            } },
            visualMap: { min: vmin, max: vmax, left: 'center', bottom: 10, orient: 'horizontal', itemWidth: 14, itemHeight: 100, calculable: true, text: ['回款慢', '回款快'], textStyle: { color: '#7d8db0', fontSize: 11 }, inRange: { color: ['#22d3ee', '#60a5fa', '#4f8cff', '#a78bfa'] }, formatter: function (v) { return Math.round(v) + ' 天'; } },
            geo: { map: 'pc_regions', roam: false, zoom: 1.08, center: [104.5, 36.5], itemStyle: { areaColor: '#131c2e', borderColor: '#24324d', borderWidth: 1 }, emphasis: { itemStyle: { areaColor: '#fbbf24', borderColor: '#b45309', borderWidth: 1.6 } }, label: { show: false } },
            series: [
              { type: 'map', map: 'pc_regions', geoIndex: 0, data: areaData, label: { show: false }, emphasis: { label: { show: false }, itemStyle: { areaColor: '#f59e0b', borderColor: '#b45309', borderWidth: 1.6 } }, itemStyle: { borderWidth: 0 } },
              { type: 'scatter', id: 'pc-area-label', coordinateSystem: 'geo', silent: true, z: 10, symbol: 'circle', symbolSize: 1, itemStyle: { color: 'transparent' }, tooltip: { show: false }, data: [] }
            ]
          });
          applyLabel();
          chartA.on('click', function (p) { if (p.componentType === 'series' && p.seriesType === 'map') { selectArea(PC_AREA_PROVINCES[p.name] ? p.name : null); } });
        }
        if (hasProvs) {
          var elP = document.getElementById(uid + '_prov'); if (!elP) return;
          var byProv = {};
          provinceStats.forEach(function (s) { var full = PC_PROV_FULL[s.province] || s.province; if (full) byProv[full] = s; });
          echarts.registerMap('pc_provs', { type: 'FeatureCollection', features: srcGeo.features });
          var data = Object.keys(byProv).map(function (nm) { var s = byProv[nm]; return { name: nm, value: s && s.avg_days > 0 ? s.avg_days : null }; });
          var pvals = data.map(function (dd) { return dd.value; }).filter(function (v) { return v != null; });
          var pmin = pvals.length ? Math.min.apply(null, pvals) : 0;
          var pmax = pvals.length ? Math.max.apply(null, pvals) : 1;
          var chartP = echarts.init(elP);
          chartP.setOption({
            tooltip: { trigger: 'item', formatter: function (p) {
              if (p.componentType !== 'series' || p.seriesType !== 'map' || !p.name) return '';
              var s = byProv[p.name];
              if (!s || !s.avg_days) return pcEsc(p.name) + '<br>暂无回款数据';
              return pcEsc(p.name) + '<br>平均 ' + pcFmtNum(s.avg_days, 1) + ' 天（约 ' + pcFmtNum(s.avg_days / 365, 2) + ' 年）<br>合同 ' + s.count + ' 份 · 有回款 ' + s.with_payment + ' / 无回款 ' + s.no_payment + '<br>金额 ' + pcFmtNum((s.amount || 0) / 10000, 0) + ' 万元';
            } },
            visualMap: { min: pmin, max: pmax, left: 'center', bottom: 10, orient: 'horizontal', itemWidth: 14, itemHeight: 100, calculable: true, text: ['回款慢', '回款快'], textStyle: { color: '#7d8db0', fontSize: 11 }, inRange: { color: ['#22d3ee', '#60a5fa', '#4f8cff', '#a78bfa'] }, formatter: function (v) { return Math.round(v) + ' 天'; } },
            geo: { map: 'pc_provs', roam: false, zoom: 1.08, center: [104.5, 36.5], itemStyle: { areaColor: '#131c2e', borderColor: '#24324d', borderWidth: 0.8 }, emphasis: { label: { show: true, color: '#dbe4f5', fontWeight: 'bold' } } },
            series: [{ type: 'map', map: 'pc_provs', geoIndex: 0, data: data, label: { show: false }, emphasis: { label: { show: true, color: '#dbe4f5', fontWeight: 'bold' } } }]
          });
        }
      });
    }, 200);
    return h;
  }

  /* ════ 顶部 Tab：总览(默认) / 明细 ════
   * 总览 = 现 renderPaymentAnalysis 全部内容(KPI/维度汇总/图表/地图，缺逐条表)；
   * 明细 = 回款周期逐条(项目/合同、签订日期、回款周期(天)、来源、说明)分页表，
   *        数据源 /api/core/metrics/payment-cycle 的 data.rows。 */
  var cyclePage = 1;
  var CYCLE_PAGE_SIZE = 10;
  var CYCLE_SOURCE_LABEL = { plm: 'PLM里程碑', finance: '回款明细', core: '主数据', manual: '手工录入' };

  function renderCycleDetailPage(page) {
    var rows = (data && data.rows) || [];
    var pagesAll = Math.max(1, Math.ceil(rows.length / CYCLE_PAGE_SIZE));
    cyclePage = Math.min(Math.max(1, page || 1), pagesAll);
    var tbody = document.getElementById('cycleDetailTbody');
    if (!tbody) return;
    var h = '';
    var start = (cyclePage - 1) * CYCLE_PAGE_SIZE;
    var end = Math.min(start + CYCLE_PAGE_SIZE, rows.length);
    for (var i = start; i < end; i++) {
      var r = rows[i];
      var src = CYCLE_SOURCE_LABEL[r.source] || (r.source || '-');
      var days = r.cycle_days;
      var daysCls = days > 365 ? ' style="color:#e5484d;font-weight:600"' : ((days == null || days <= 0) ? ' style="color:var(--text2)"' : '');
      h += '<tr><td class="wrap">' + _val(r.contract_no, '-') + '</td><td class="wrap">' + _val(r.project_no, '-') + '</td>'
        + '<td class="wrap">' + _val(r.name, '-') + '</td><td>' + _val(r.sign_date, '-') + '</td>'
        + '<td class="num"' + daysCls + '>' + (days == null ? '-' : days) + '</td><td>' + src + '</td>'
        + '<td class="wrap">' + _val(r.note, '-') + '</td></tr>';
    }
    if (!h) h = '<tr><td colspan="7" style="text-align:center;color:var(--text2);padding:20px">暂无明细</td></tr>';
    tbody.innerHTML = h;
    var wrap = document.getElementById('cycleDetailPager');
    if (wrap) wrap.innerHTML = NC.anaPager(cyclePage, rows.length, CYCLE_PAGE_SIZE, 'cycleDetailPager', 'FinanceCycle.setCyclePage');
  }

  function renderCycleAna(d) {
    var detailHtml = '<div class="panel"><h3>📋 回款周期明细</h3>'
      + '<div class="twrap" style="max-height:none"><table class="ana-table"><thead><tr>'
      + '<th style="text-align:left;padding-left:8px">合同编号</th><th style="text-align:left;padding-left:8px">项目编号</th>'
      + '<th style="text-align:left;padding-left:8px">项目名称</th><th>签订日期</th>'
      + '<th style="text-align:right;padding-right:8px">回款周期(天)</th><th>来源</th>'
      + '<th style="text-align:left;padding-left:8px">说明</th></tr></thead>'
      + '<tbody id="cycleDetailTbody"></tbody></table></div>'
      + '<div id="cycleDetailPager"></div></div>';
    document.getElementById('anaContent').innerHTML = '<div id="cycleHost">'
      + NC.anaTabs([{ key: 'overview', label: '📊 总览' }, { key: 'detail', label: '📋 明细' }], 'overview', 'cycleHost')
      + NC.anaPane('overview', '<div id="cycleOverview"></div>', true)
      + NC.anaPane('detail', detailHtml, false)
      + '</div>';
    renderPaymentAnalysis(d, document.getElementById('cycleOverview'));
    renderCycleDetailPage(1);
  }

  /* ── 加载 / 导出 ──
   * GET 默认读快照（秒级，后端 /api/core/metrics/payment-cycle 不带 refresh）；
   * 仅点击「执行分析」等显式动作时传 refresh=1 强制全量重算。 */
  async function load(refresh) {
    var runBtn = document.getElementById('btnCycleRun');
    if (runBtn) { runBtn.disabled = true; runBtn.textContent = '⏳ ' + (refresh ? '重算中...' : '加载中...'); }
    status(refresh ? '正在全量重算回款周期分析（实时计算）...' : '读取回款周期分析数据（快照，秒级）...');
    try {
      document.getElementById('anaContent').innerHTML = '<div class="ana-empty"><div class="icon">📊</div><div>' + (refresh ? '正在重算...' : '加载中...') + '</div></div>';
      var r = await fetch(API + '/api/core/metrics/payment-cycle' + (refresh ? '?refresh=1' : ''));
      var j = await r.json();
      if (!j.success) { status(j.error || '读取失败'); document.getElementById('anaContent').innerHTML = '<div class="ana-empty"><div class="icon">📊</div><div>' + (j.error || '读取失败') + '</div></div>'; return; }
      data = j.data;
      status((refresh ? '重算完成（实时计算）' : '已读取快照（秒级）') + ' · 数据来源：核心主数据 core_project + finance_detail 回款'
        + (j.updated_at ? ' · 更新于 ' + j.updated_at : ''));
      var exp = document.getElementById('btnExport'); if (exp) exp.style.display = 'inline';
      renderCycleAna(data);
    } catch (e) { status('读取失败：' + e.message); }
    finally { if (runBtn) { runBtn.disabled = false; runBtn.textContent = '▶ 执行分析'; } }
  }
  function showError(msg) { document.getElementById('anaContent').innerHTML = '<div class="ana-empty"><div class="icon">⚠️</div><div>' + msg + '</div></div>'; }
  function csvText() {
    var enr = (data && data.enriched_rows) || [];
    var head = ['合同编号', '签约日期', '部门', '区域', '省份', '最后一笔回款日期', '回款周期(天)', '年', '分区', '合同金额'];
    var lines = [head.join(',')];
    enr.forEach(function (r) {
      var csv = function (s) { s = s === null || s === undefined ? '' : String(s); return '"' + s.replace(/"/g, '""') + '"'; };
      lines.push([csv(r.contract_no), csv(r.sign_date), csv(r.dept), csv(r.region), csv(r.province), csv(r.last_payback_date), csv(r.cycle_days), csv(r.years), csv(r.zone), csv(r.amount)].join(','));
    });
    return '\ufeff' + lines.join('\r\n');
  }
  function exportResult() {
    var enr = (data && data.enriched_rows) || [];
    if (!enr.length) { status('暂无数据可导出'); return; }
    var blob = new Blob([csvText()], { type: 'text/csv;charset=utf-8' });
    var a = document.createElement('a'); a.href = URL.createObjectURL(blob);
    a.download = '回款周期分析_' + new Date().toISOString().slice(0, 10) + '.csv';
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    status('已导出 ' + enr.length + ' 条');
  }

  root.FinanceCycle = { run: function () { return load(true); }, load: load, exportResult: exportResult, setCyclePage: renderCycleDetailPage };

  renderShell();
  load();
})(window);