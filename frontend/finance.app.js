'use strict';
/* 财经 · 资金明细（回款明细/付款明细）页面脚本：统一壳 + 导入 + 列表。
 * - 壳：renderTopMenu(activeKey=fin)，renderAccordion(财经域 sections，
 *   回款/付款 为 action 切到页面内 section)，面包屑 财经/资金明细/回款付款。
 * - 数据：POST /api/core/finance/import?kind=pay|recv（落 finance_detail），
 *   GET /api/core/finance?kind=&keyword=（occur_date 倒序）。 */
(function (root) {
  var NC = root.NAV_CONFIG;
  var API = '';

  // 左栏 sections（财经域，回款明细/付款明细为两个独立入口 → 各自页面）
  var SECTIONS = [
    { sub: '资金运作', links: [
      { key: 'fin-cycle', label: '回款周期', icon: 'cycle', href: '/finance-cycle' },
      { key: 'fin-gross', label: '毛利率', icon: 'gross', href: '/gross' },
      { key: 'fin-fund',  label: '资金占用 · 周转率', icon: 'fund', href: '/finance-fund' }
    ] },
    { sub: '资金明细', links: [
      { key: 'fin-recv', label: '回款明细', icon: 'receipt', href: '/finance?kind=recv' },
      { key: 'fin-pay',  label: '付款明细', icon: 'pay', href: '/finance?kind=pay' }
    ] }
  ];

  // 当前页展示的收/付款类型：?kind=pay | recv；缺省都显示（兼容 /finance）
  var q = new URLSearchParams(location.search);
  var KIND = (q.get('kind') === 'pay') ? 'pay' : (q.get('kind') === 'recv' ? 'recv' : '');
  var OTHER = KIND === 'pay' ? 'recv' : (KIND === 'recv' ? 'pay' : '');

  function renderShell() {
    if (KIND) {
      // 只显示当前部分，隐藏另一部分
      var oth = document.getElementById('sec-' + OTHER);
      if (oth) oth.style.display = 'none';
    }
    var last = KIND === 'pay' ? '付款明细' : (KIND === 'recv' ? '回款明细' : '回款/付款明细');
    NC.renderBreadcrumb(document.getElementById('breadcrumb'), ['财经', '资金明细', last]);
    NC.renderTopMenu(document.getElementById('topMenu'), { activeKey: 'fin' });
    var activeLink = KIND === 'pay' ? 'fin-pay' : (KIND === 'recv' ? 'fin-recv' : 'fin-recv');
    NC.renderAccordion(document.getElementById('navRail'), {
      rootTitle: '经营业务工作台', domainLabel: '财经', activeKey: 'fin',
      activeLink: activeLink, sections: SECTIONS
    });
  }

  function goTab(kind) {
    var el = document.getElementById('sec-' + (kind === 'recv' ? 'recv' : 'pay'));
    if (el && el.scrollIntoView) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function setStatus(kind, msg) {
    var el = document.getElementById('status-' + kind);
    if (el) el.textContent = msg;
  }

  function setLoading(kind, on) {
    var btn = document.getElementById('importBtn-' + kind);
    if (!btn) return;
    btn.disabled = on;
    btn.textContent = on ? '⏳ 导入中...' : '📥 导入' + (kind === 'recv' ? '回款' : '付款') + '表';
  }

  function fmtNum(v) {
    if (v === null || v === undefined || v === '') return '-';
    var n = Number(v);
    return isNaN(n) ? String(v) : n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function renderRows(kind, rows) {
    var tbl = document.getElementById('tbl-' + kind);
    var cnt = document.getElementById('count-' + kind);
    if (!rows || !rows.length) {
      tbl.innerHTML = '<thead><tr><th>项目号/合同号</th><th>发生日期</th><th>金额</th><th>合同额</th></tr></thead>'
        + '<tbody><tr><td colspan="4" style="text-align:center;color:var(--text2);padding:24px">暂无数据，请先导入 ' + (kind === 'recv' ? '回款' : '付款') + '表</td></tr></tbody>';
      if (cnt) cnt.textContent = '';
      return;
    }
    var head = '<thead><tr><th>#</th><th>项目号/合同号</th><th>发生日期</th><th>金额</th><th>合同额</th><th>备注</th></tr></thead>';
    var body = '<tbody>';
    rows.forEach(function (r, i) {
      body += '<tr><td>' + (i + 1) + '</td>'
        + '<td>' + (r.project_no || r.contract_no || '-') + '</td>'
        + '<td>' + (r.occur_date || '-') + '</td>'
        + '<td class="num">' + fmtNum(r.amount) + '</td>'
        + '<td class="num">' + fmtNum(r.contract_amount) + '</td>'
        + '<td>' + (r.remark || '') + '</td></tr>';
    });
    body += '</tbody>';
    tbl.innerHTML = head + body;
    if (cnt) cnt.textContent = '共 ' + rows.length + ' 条';
  }

  async function reload(kind) {
    setStatus(kind, '读取中...');
    var kw = (document.getElementById('kw-' + kind) || {}).value || '';
    try {
      var r = await fetch(API + '/api/core/finance?kind=' + kind + '&keyword=' + encodeURIComponent(kw));
      var d = await r.json();
      if (d.success) {
        renderRows(kind, d.data);
        setStatus(kind, '数据来源：finance_detail（供资金占用计算复用）');
      } else {
        setStatus(kind, d.error || '读取失败');
      }
    } catch (e) {
      setStatus(kind, '读取失败: ' + e.message);
    }
  }

  async function importXls(ev, kind) {
    var input = ev && ev.target;
    var file = input && input.files && input.files[0];
    if (!file) return;
    setLoading(kind, true);
    setStatus(kind, '正在解析并导入...');
    var fd = new FormData();
    fd.append('file', file);
    try {
      var r = await fetch(API + '/api/core/finance/import?kind=' + kind, { method: 'POST', body: fd });
      var d = await r.json();
      if (d.success) {
        var cols = d.matched_columns ? Object.keys(d.matched_columns).join('、') : '无';
        setStatus(kind, '导入完成：新增 ' + d.inserted + ' 条，跳过 ' + d.skipped + ' 条（匹配列：' + cols + '）');
        reload(kind);
      } else {
        setStatus(kind, '导入失败: ' + (d.error || '未知错误'));
      }
    } catch (e) {
      setStatus(kind, '导入失败: ' + e.message);
    } finally {
      setLoading(kind, false);
      if (input) input.value = '';
    }
  }

  root.Finance = { renderShell: renderShell, goTab: goTab, reload: reload, importXls: importXls };

  renderShell();
  if (KIND) reload(KIND);
  else { reload('pay'); reload('recv'); }
})(window);