/* ================================================================
 * 采购域 · 合同硬件采购比对（独立页 contrast.app.js）
 * 由 /contrast 页面驱动；业务逻辑复刻自 index.html 对比工作台，
 * 接口对接后端真实 API，所有按钮操作带 loading 指示。
 * ================================================================ */
'use strict';
const API = '';
let currentCid = null, currentCname = null, currentVer = null;

// ── 暗色图表主题（解决 ECharts 默认文字 #333 在深色背景上不可见）──
if (window.echarts) {
  echarts.registerTheme('cc-dark', {
    textStyle: { color: '#dbe4f5' },
    legend: { textStyle: { color: '#a3b3d6', fontSize: 11 }, pageTextStyle: { color: '#a3b3d6' }, inactiveColor: '#3a4a6a' },
    title: { textStyle: { color: '#e0e6f5', fontWeight: 600, fontSize: 13 }, subtextStyle: { color: '#8893aa' } },
    tooltip: { backgroundColor: 'rgba(10,18,41,.96)', borderColor: '#2a3a60', textStyle: { color: '#e0e6f5' }, axisPointer: { lineStyle: { color: '#4f8cff' }, crossStyle: { color: '#4f8cff' }, label: { backgroundColor: '#0a1229', color: '#e0e6f5', borderColor: '#2a3a60', borderWidth: 1 } } },
    categoryAxis: { axisLine: { lineStyle: { color: '#2a3a60' } }, axisTick: { lineStyle: { color: '#2a3a60' } }, axisLabel: { color: '#a3b3d6' }, splitLine: { show: false, lineStyle: { color: '#16223f' } }, splitArea: { show: false } },
    valueAxis: { axisLine: { show: false, lineStyle: { color: '#2a3a60' } }, axisTick: { show: false, lineStyle: { color: '#2a3a60' } }, axisLabel: { color: '#a3b3d6' }, splitLine: { lineStyle: { color: '#16223f', type: 'dashed' } }, splitArea: { show: false } },
    timeAxis: { axisLine: { lineStyle: { color: '#2a3a60' } }, axisLabel: { color: '#a3b3d6' }, splitLine: { lineStyle: { color: '#16223f' } } },
    visualMap: { textStyle: { color: '#a3b3d6' } },
    calendar: { itemStyle: { color: '#0d1530' }, yearLabel: { color: '#a3b3d6' }, dayLabel: { color: '#8893aa' }, monthLabel: { color: '#a3b3d6' }, splitLine: { lineStyle: { color: '#2a3a60' } } }
  });
}

// ===== 页面切换（视图1 对比分析 / 视图2 上传资料 / 视图3 工作区） =====
const CONTRAST_PAGES = ['page-home', 'page-upload', 'page-workspace'];
function showPage(id) {
  CONTRAST_PAGES.forEach(function (x) {
    const el = document.getElementById(x);
    if (el) el.classList.toggle('active', x === id);
  });
}
function showSelect(p) {
  if (p === 'upload') {
    showPage('page-upload');
    const back = document.getElementById('btnBackList');
    if (back) back.style.display = '';
  } else {
    showPage('page-home');
    const back = document.getElementById('btnBackList');
    if (back) back.style.display = 'none';
  }
}
function enterFromPortal() { showSelect('home'); loadContracts(); }
function enterContract(cid, cname) {
  currentCid = cid; currentCname = cname || ('合同 #' + cid);
  showPage('page-workspace');
  const label = document.getElementById('currentContractLabel');
  if (label) label.textContent = '》' + currentCname;
  const back = document.getElementById('btnBackList');
  if (back) back.style.display = '';
  switchWsTab('dashboard', document.querySelector('#wsNav .nav-btn'));
}
function switchWsTab(n, btn) {
  document.querySelectorAll('#page-workspace .page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('#wsNav .nav-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('ws-' + n).classList.add('active');
  if (btn) btn.classList.add('active');
  if (n === 'dashboard') loadWsStats();
  if (n === 'contract') loadContract();
  if (n === 'supplier') loadVersions();
  if (n === 'results') loadResults();
}
function toast(m, ok) {
  const t = document.getElementById('toast');
  t.textContent = m;
  t.className = 'toast ' + (ok === false ? 'err' : 'ok') + ' show';
  setTimeout(() => t.classList.remove('show'), 2500);
}

// ===== 按钮 loading 工具 =====
function _spin(btn, on, loadingText) {
  if (!btn) return;
  if (on) {
    if (!btn.dataset.ot) btn.dataset.ot = btn.textContent;
    btn.disabled = true;
    if (loadingText) btn.textContent = loadingText;
  } else {
    btn.disabled = false;
    if (btn.dataset.ot) { btn.textContent = btn.dataset.ot; }
  }
}

// ===== 合同列表 =====
async function loadContracts() {
  const s = document.getElementById('ctSearch').value, st = document.getElementById('ctStatusFilter').value;
  const p = new URLSearchParams();
  if (s) p.set('keyword', s);
  if (st !== '全部') p.set('status', st);
  const r = await fetch(API + '/api/contracts?' + p).then(res => res.json()).catch(e => ({}));
  const stats = r.stats || {};
  document.getElementById('globalStats').innerHTML = `
    <div class="card"><div class="lbl">📑 合同总数</div><div class="val c">${stats.total || 0}</div></div>
    <div class="card"><div class="lbl">✅ 已闭环</div><div class="val g">${stats.closed || 0}</div></div>
    <div class="card"><div class="lbl">🔄 进行中</div><div class="val o">${stats.active || 0}</div></div>
    <div class="card"><div class="lbl">💰 总采购金额</div><div class="val c">${(stats.total_amount || 0).toLocaleString()}</div></div>`;
  const cs = r.contracts || [];
  document.getElementById('contractList').innerHTML = cs.map(c => {
    const sb = { '已闭环(100%)': 'badge-s', '待供应商整改': 'badge-w', '比对进行中': 'badge-c', '未上传基准': 'badge-e' }[c.status] || '';
    const pq = c.progress || 0;
    const pc = pq >= 70 ? '#34d399' : pq >= 30 ? '#4f8cff' : '#fbbf24';
    const safeName = (c.contract_name || '').replace(/'/g, '\\\'');
    return `<div class="ct-list" style="--p:${pq}%;--pc:${pc}" onclick="enterContract(${c.id},'${safeName}')">
      <div style="display:flex;align-items:center;gap:12px">
        <div style="flex:1">
          <div style="font-weight:bold;font-size:14px">${c.contract_name || '未命名合同'}</div>
          <div style="font-size:11px;color:var(--text2);margin-top:2px">编号: ${c.contract_no || '-'} | 签订: ${c.sign_date || '-'} | 金额: ¥${(c.total_amount || 0).toLocaleString()}` +
           (c.supplier_count ? ` | 供应商: ${c.supplier_count}家` : ``) + `</div>
        </div>
        <span class="badge ${sb}">${c.status}</span>
        <span style="font-size:12px;font-weight:bold;color:${pc};min-width:36px;text-align:right">${pq}%</span>
        <button class="btn btn-c btn-s" onclick="event.stopPropagation();enterContract(${c.id},'${safeName}')">进入 →</button>
      </div></div>`;
  }).join('') || '<div style="color:var(--text2);padding:20px;text-align:center">暂无合同，点击上方「＋ 新建合同」</div>';
}

function showCreateContract() { document.getElementById('createModal').classList.add('show'); }
function closeCreate() { document.getElementById('createModal').classList.remove('show'); }
async function createContract(btn) {
  const n = document.getElementById('newCtName').value.trim(),
        no = document.getElementById('newCtNo').value.trim(),
        d = document.getElementById('newCtDate').value;
  if (!n) return toast('请输入合同名称', false);
  _spin(btn, true, '创建中...');
  try {
    const r = await fetch(API + '/api/contracts?name=' + encodeURIComponent(n) + '&no=' + encodeURIComponent(no) + '&sign_date=' + d, { method: 'POST' }).then(r => r.json());
    if (r.success) { toast('合同已创建'); closeCreate(); loadContracts(); loadUpContracts(); enterContract(r.contract_id, n); }
    else toast(r.error, false);
  } catch (e) { toast('创建失败：' + e.message, false); }
  _spin(btn, false);
}

// ===== 合同工作区看板（echarts） =====
async function loadWsStats() {
  if (!currentCid) return;
  const r = await fetch(API + '/api/contract/' + currentCid + '/stats').then(r => r.json());
  const s = r.stats;
  document.getElementById('wsStatCards').innerHTML = `
    <div class="card"><div class="lbl">📄 合同条目</div><div class="val c">${s.contract_total || 0}</div></div>
    <div class="card"><div class="lbl">✅ 匹配成功</div><div class="val g">${s.matched_count || 0}</div></div>
    <div class="card"><div class="lbl">🟠 判断符合</div><div class="val o" style="color:#fbbf24">${s.judged_count || 0}</div></div>
    <div class="card"><div class="lbl">⚠️ 匹配异常</div><div class="val o">${s.anomaly_count || 0}</div></div>
    <div class="card"><div class="lbl">🔴 待采购</div><div class="val r">${s.pending_count || 0}</div></div>
    <div class="card"><div class="lbl">🟣 供应商增项</div><div class="val p">${s.extra_count || 0}</div></div>
    <div class="card"><div class="lbl">📊 采购进度</div><div class="val c">${s.progress || 0}%</div><div class="prog"><div class="f" style="width:${s.progress || 0}%"></div></div></div>`;
  try {
    const pie = echarts.init(document.getElementById('pieChart'));
    pie.setOption({ tooltip: { trigger: 'item' }, series: [{ type: 'pie', radius: ['40%', '65%'], data: [
      { value: s.matched_count || 0, name: '匹配成功', itemStyle: { color: '#34d399' } }, { value: s.judged_count || 0, name: '判断符合', itemStyle: { color: '#fbbf24' } }, { value: s.anomaly_count || 0, name: '匹配异常', itemStyle: { color: '#f87171' } }, { value: s.pending_count || 0, name: '待采购', itemStyle: { color: '#60a5fa' } }, { value: s.extra_count || 0, name: '增项', itemStyle: { color: '#a78bfa' } }], label: { color: '#7d8db0', fontSize: 10 } }] });
    const tr = echarts.init(document.getElementById('trendChart'));
    tr.setOption({ tooltip: { trigger: 'axis' }, xAxis: { type: 'category', data: r.versions.map(v => 'v' + v.id), axisLabel: { color: '#7d8db0' } }, yAxis: { max: 100, axisLabel: { color: '#7d8db0' } }, series: [{ type: 'line', data: r.versions.map(v => v.progress), smooth: true, lineStyle: { color: '#22d3ee', width: 2 }, itemStyle: { color: '#22d3ee' }, areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(34,211,238,.3)' }, { offset: 1, color: 'rgba(34,211,238,0)' }] } } }] });
  } catch (e) {}
}

// ===== 合同基准 =====
async function loadContract() {
  if (!currentCid) return;
  const r = await fetch(API + '/api/contract/' + currentCid + '/items').then(r => r.json());
  const hdr = r.headers || [];
  document.getElementById('ctTableHead').innerHTML = '<tr>' + hdr.map(h => `<th>${h}</th>`).join('') + '</tr>';
  document.getElementById('ctTable').innerHTML = r.items.map(i => {
    let row = '<tr>';
    for (const h of hdr) { try { const raw = JSON.parse(i.raw_columns || '{}'); row += `<td>${raw[h] || ''}</td>`; } catch (e) { row += '<td></td>'; } }
    row += '</tr>'; return row;
  }).join('');
}
async function uploadContract(inp) {
  if (!currentCid) return;
  const f = inp.files[0]; if (!f) return;
  toast('正在上传合同基准...');
  inp.disabled = true;
  const fd = new FormData(); fd.append('file', f);
  try {
    const r = await fetch(API + '/api/contract/' + currentCid + '/upload', { method: 'POST', body: fd }).then(r => r.json());
    if (r.success) { toast(`已导入 ${r.count} 条`); loadContract(); loadWsStats(); loadContracts(); }
    else toast(r.error, false);
  } catch (e) { toast('上传失败：' + e.message, false); }
  inp.disabled = false; inp.value = '';
}

// ===== 供应商版本 =====
async function loadVersions() {
  if (!currentCid) return;
  const sf = document.getElementById('verSupplierFilter').value;
  const p = new URLSearchParams(); if (sf) p.set('supplier_name', sf);
  const r = await fetch(API + '/api/contract/' + currentCid + '/supplier/versions?' + p).then(r => r.json());
  const sel = document.getElementById('verSupplierFilter');
  const curVal = sel.value;
  sel.innerHTML = '<option value="">全部供应商</option>' + r.suppliers.map(s => `<option value="${s.supplier_name}">${s.supplier_name} (${s.version_count}版本)</option>`).join('');
  sel.value = curVal;
  document.getElementById('verTable').innerHTML = r.versions.map(v => {
    const sname = v.supplier_name ? `<span class="badge badge-p">${v.supplier_name}</span>` : '<span style="color:var(--text2)">-</span>';
    const activeTag = v.is_active ? `<span class="badge badge-s" style="font-size:10px">🔵 生效中</span>` : '';
    const delBtn = v.is_active ? '' : `<button class="btn btn-o btn-s" onclick="delVer(${v.id})" style="color:#f44;border-color:#f44">🗑</button>`;
    return `<tr><td><span class="badge badge-c">v${v.id}</span>${activeTag}</td><td>${sname}</td><td>${(v.upload_time || '').substring(0, 16)}</td><td>${v.total_items}</td><td>${v.matched_count}</td><td>${v.anomaly_count}</td><td>${v.pending_count}</td><td>${v.extra_count}</td><td><span class="badge ${v.progress >= 100 ? 'badge-s' : 'badge-w'}">${v.progress}%</span></td><td><button class="btn btn-o btn-s" onclick="showVerDetail(${v.id})">详情</button>${delBtn}</td></tr>`;
  }).join('');
  if (r.versions.length > 0) { currentVer = r.versions[0].id; }
}
async function uploadSupplier(inp) {
  if (!currentCid) return;
  const f = inp.files[0]; if (!f) return;
  const snInput = document.getElementById('supplierName');
  if (!snInput.value.trim()) { snInput.value = f.name.replace(/\.[^.]+$/, ''); }
  const sn = snInput.value.trim();
  if (!sn) { toast('请先填写供应商名称', false); inp.value = ''; return; }
  toast('正在上传并比对...');
  inp.disabled = true;
  const fd = new FormData(); fd.append('file', f);
  try {
    const r = await fetch(API + '/api/contract/' + currentCid + '/supplier/upload?supplier_name=' + encodeURIComponent(sn), { method: 'POST', body: fd }).then(r => r.json());
    if (r.success) { toast(`v${r.version_id} (${sn}) 比对完成！进度 ${r.progress}%`); currentVer = r.version_id; loadVersions(); loadWsStats(); loadResults(); loadContracts(); }
    else toast(r.error, false);
  } catch (e) { toast('上传失败：' + e.message, false); }
  inp.disabled = false; inp.value = '';
}
async function delVer(vid) {
  if (!confirm('确定删除版本 v' + vid + '？将同时删除该版本的比对结果和供应商报价数据。')) return;
  const r = await fetch(API + '/api/contract/' + currentCid + '/supplier/versions/' + vid, { method: 'DELETE' }).then(r => r.json());
  if (r.success) { toast('版本 v' + vid + ' 已删除'); loadVersions(); loadWsStats(); loadContracts(); }
  else toast(r.error || '删除失败', false);
}

// ===== 比对结果（表格对照，动态列名） =====
function _highDiff(txt, anomalyDetail, side) {
  if (!anomalyDetail || !txt) return txt || '';
  let out = txt;
  const miss = anomalyDetail.match(/合同要求「([^」]+)」/g);
  if (miss && side === 'ct') miss.forEach(m => { const w = m.match(/「([^」]+)」/); if (w && w[1]) out = out.replace(w[1], `<span class="diff">${w[1]}</span>`); });
  const arrows = anomalyDetail.match(/合同「([^」]+)」.*?→.*?报价「([^」]+)」/g);
  if (arrows) arrows.forEach(m => { const w = m.match(/合同「([^」]+)」.*?报价「([^」]+)」/); if (w) out = out.replace(side === 'ct' ? w[1] : w[2], `<span class="diff">${side === 'ct' ? w[1] : w[2]}</span>`); });
  return out;
}
function _html(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
function _tryRaw(raw, key, fallback) {
  try {
    const o = JSON.parse(raw || '{}');
    if (Object.keys(o).length > 0 && o[key] !== undefined) return o[key] !== null && o[key] !== '' ? String(o[key]) : '';
  } catch (e) {}
  const v = (fallback || {})[key];
  return v !== null && v !== undefined && v !== '' ? String(v) : '';
}
async function rerunCompare(btn) {
  if (!currentCid) return;
  if (!currentVer) { toast('请先在「供应商版本」上传报价或选择版本', false); return; }
  if (btn) _spin(btn, true, '比对中...');
  try {
    const r = await fetch(API + '/api/contract/' + currentCid + '/compare/run?version_id=' + currentVer, { method: 'POST' }).then(r => r.json());
    if (r.success) { toast(`重新比对完成！进度 ${r.progress}%`); loadResults(); loadWsStats(); loadContracts(); }
    else toast(r.error || '比对失败', false);
  } catch (e) { toast('比对失败：' + e.message, false); }
  if (btn) _spin(btn, false);
}
async function loadResults() {
  if (!currentCid) { return; }
  const st = document.getElementById('filterStatus').value,
        kw = document.getElementById('filterKeyword').value.trim().toLowerCase();
  const p = new URLSearchParams();
  if (currentVer) p.set('version_id', currentVer);
  if (st !== '全部') p.set('status', st);
  const r = await fetch(API + '/api/contract/' + currentCid + '/compare/results?' + p).then(r => r.json());
  let results = r.results;
  const ctHdr = r.ct_headers || [], spHdr = r.sp_headers || [];
  if (kw) results = results.filter(x => {
    const raw = ((x.ct_raw || x.sp_raw || '').toLowerCase());
    return (x.ct_name || x.sp_name || '').toLowerCase().includes(kw) || (x.ct_model || x.sp_model || '').toLowerCase().includes(kw) || raw.includes(kw);
  });
  const total = results.length, ok = results.filter(x => x.match_status === '匹配成功').length,
        rc = results.filter(x => x.match_status === '判断符合').length,
        err = results.filter(x => x.match_status === '匹配异常').length,
        miss = results.filter(x => x.match_status === '待采购').length,
        extra = results.filter(x => x.match_status === '供应商增项').length;
  document.getElementById('resSummary').innerHTML = `共 ${total} 条 | <span style="color:var(--green)">✓完全匹配 ${ok}</span> <span style="color:var(--orange)">🟠判断符合 ${rc}</span> <span style="color:var(--red)">✗异常 ${err}</span> <span style="color:var(--red)">待采购 ${miss}</span> <span style="color:var(--purple)">增项 ${extra}</span>`;
  const labelCt = ctHdr.length ? ctHdr : ['设备名称', '型号', '数量', '参数'];
  const labelSp = spHdr.length ? spHdr : ['设备名称', '型号', '数量', '参数'];
  document.getElementById('resThead').innerHTML = `<tr>
    <th colspan="${labelCt.length}" class="ct-hdr" style="text-align:center">📄 合同要求</th>
    <th class="sep-hdr" style="width:3px;padding:0"></th>
    <th colspan="${labelSp.length}" class="sp-hdr" style="text-align:center">📦 供应商报价</th>
    <th colspan="3">匹配结果</th>
  </tr><tr>
    ${labelCt.map(h => `<th class="ct-hdr">${_html(h)}</th>`).join('')}
    <th class="sep-hdr"></th>
    ${labelSp.map(h => `<th class="sp-hdr">${_html(h)}</th>`).join('')}
    <th>状态</th><th>匹配说明</th><th>操作</th>
  </tr>`;
  setTimeout(function () {
    const thRows = document.querySelectorAll('#resThead tr');
    if (thRows.length >= 2) {
      const firstH = thRows[0].offsetHeight;
      thRows[1].querySelectorAll('th').forEach(th => { th.style.top = firstH + 'px'; });
    }
  }, 0);
  const rowCls = { '匹配成功': '', '判断符合': 'style="background:rgba(251,191,36,.04)"', '匹配异常': 'style="background:rgba(248,113,113,.08)"', '待采购': 'style="background:rgba(248,113,113,.1)"', '供应商增项': 'style="background:rgba(167,139,250,.06)"' };
  const sb = { '匹配成功': 'badge-s', '判断符合': 'badge-o', '匹配异常': 'badge-w', '待采购': 'badge-e', '供应商增项': 'badge-p' };
  document.getElementById('resTable').innerHTML = results.map(d => {
    const anom = d.anomaly_detail || '';
    const mn = d.match_note || '';
    const badgeCls = sb[d.match_status] || '';
    const stLabel = d.match_status + (d.confirmed ? ' ✓' : '');
    const rowStyle = rowCls[d.match_status] || '';
    const btn = d.match_status === '判断符合' && !d.confirmed ? `<button class="btn btn-s" style="background:#34d399;font-size:10px;padding:2px 6px;white-space:nowrap" onclick="confirmAnomaly(${d.id},1)">✓ 确认</button>` :
             d.match_status === '匹配异常' && !d.confirmed ? `<button class="btn btn-s" style="background:#34d399;font-size:10px;padding:2px 6px;white-space:nowrap" onclick="confirmAnomaly(${d.id},1)">✓ 确认</button>` :
             d.confirmed ? `<button class="btn btn-o btn-s" style="font-size:10px;padding:2px 6px;white-space:nowrap" onclick="confirmAnomaly(${d.id},0)">↩ 撤销</button>` : '';
    let matchNoteHtml = '';
    function _colorize(mn) {
      if (!mn) return '';
      return mn.split(String.fromCharCode(10)).map(function (line) {
        let c = '#7d8db0';
        let t = line;
        if (t.indexOf('不一致') >= 0) c = '#f87171';
        else if (t.indexOf('模糊匹配') >= 0) c = '#fbbf24';
        else if (t.indexOf('精确匹配') >= 0 || t.indexOf('一致') >= 0) c = '#34d399';
        else if (t.indexOf('未填写') >= 0) c = '#7d8db0';
        else c = '#fbbf24';
        return '<span style="color:' + c + '">' + _html(t) + '</span>';
      }).join('<br>');
    }
    if (d.match_status === '判断符合') {
      matchNoteHtml = '<span style="font-size:10px">🟠 ' + _colorize(mn) + '</span>';
    } else if (d.match_status === '匹配成功' && d.confirmed && mn) {
      matchNoteHtml = '<span style="font-size:10px">✅ 已确认:<br>' + _colorize(mn) + '</span>';
    } else if (d.match_status === '匹配成功' && mn) {
      matchNoteHtml = '<span style="font-size:10px">' + _colorize(mn) + '</span>';
    } else if (d.match_status === '匹配成功' && anom && anom.startsWith('[模糊匹配]')) {
      matchNoteHtml = '<span style="color:#a78bfa;font-size:10px">🔮 ' + anom.replace(/</g, '&lt;') + '</span>';
    } else if (d.match_status === '匹配异常') {
      matchNoteHtml = '<span style="font-size:10px">' + _colorize(mn || anom) + '</span>';
    } else if (d.match_status === '待采购' || d.match_status === '供应商增项') {
      matchNoteHtml = '<span style="color:var(--text2);font-size:10px">' + anom + '</span>';
    } else {
      matchNoteHtml = '<span style="color:var(--text2);font-size:10px">—</span>';
    }
    const ctRaw = d.ct_raw || '{}', spRaw = d.sp_raw || '{}';
    const ctFall = { '设备名称': d.ct_name, '型号': d.ct_model, '规格型号': d.ct_model, '数量': d.contract_qty, '单位': d.contract_unit, '单价': d.contract_unit_price, '金额': d.contract_amount, '参数': d.ct_specs, '规格参数': d.ct_specs, '备注': d.remark };
    const spFall = { '设备名称': d.sp_name, '型号': d.sp_model, '规格型号': d.sp_model, '数量': d.quote_qty, '单位': d.quote_unit, '单价': d.quote_unit_price, '金额': d.quote_amount, '参数': d.sp_specs, '规格参数': d.sp_specs, '备注': d.remark };
    return `<tr ${rowStyle}>
      ${labelCt.map(h => `<td class="ct-col">${_highDiff(_tryRaw(ctRaw, h, ctFall), anom, 'ct')}</td>`).join('')}
      <td class="sep-col"></td>
      ${labelSp.map(h => `<td class="sp-col">${_highDiff(_tryRaw(spRaw, h, spFall), anom, 'sp')}</td>`).join('')}
      <td><span class="badge ${badgeCls}">${stLabel}</span></td>
      <td style="font-size:10px;max-width:280px;line-height:1.5;white-space:normal">${matchNoteHtml}</td>
      <td>${btn}</td>
    </tr>`;
  }).join('') || '<tr><td colspan="99" style="text-align:center;color:var(--text2);padding:20px">暂无比对结果，请先上传供应商报价</td></tr>';
  loadColumnAlign();
}

// ===== 列映射（列对齐） =====
let currentColumnMapping = null;
async function loadColumnAlign() {
  if (!currentCid) return;
  let r = {};
  try {
    const url = API + '/api/contract/' + currentCid + '/column-mapping' + (currentVer ? ('?version_id=' + currentVer) : '');
    r = await fetch(url).then(r => r.json());
  } catch (e) {}
  if (!r || !r.contract_headers || !r.contract_headers.length) {
    document.getElementById('columnAlignPanel').style.display = 'none';
    return;
  }
  if (!currentVer && r.version_id) currentVer = r.version_id;
  currentColumnMapping = r;
  document.getElementById('columnAlignPanel').style.display = '';
  const bar = document.getElementById('columnAlignBar');
  const spHeaders = r.supplier_headers || [];
  bar.innerHTML = r.contract_headers.map(ct => {
    const sp = r.mapping[ct] || '';
    const opts = ['<option value="">（无对应）</option>']
      .concat(spHeaders.map(h => `<option value="${_html(h)}" ${h === sp ? 'selected' : ''}>${_html(h)}</option>`)).join('');
    const mismatch = sp ? '' : ' ca-mismatch';
    return `<div class="colalign-item">
      <div class="ca-ct" title="${_html(ct)}">${_html(ct)}</div>
      <div class="ca-arrow">↕</div>
      <select class="ca-sp${mismatch}" data-ct="${_html(ct)}" onchange="onColumnAlignChange(this)">${opts}</select>
    </div>`;
  }).join('') + (r.reference_columns || []).map(h => `<div class="colalign-item colalign-ref">
      <div class="ca-ref-label">仅参考</div>
      <div class="ca-ref-name" title="${_html(h)}">${_html(h)}</div>
    </div>`).join('');
}
async function onColumnAlignChange(sel) {
  const ct = sel.dataset.ct;
  const sp = sel.value;
  if (!currentColumnMapping) return;
  currentColumnMapping.mapping[ct] = sp;
  sel.classList.remove('ca-mismatch');
  if (!sp) sel.classList.add('ca-mismatch');
  try {
    const r = await fetch(API + '/api/contract/' + currentCid + '/column-mapping', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ version_id: currentVer, mapping: currentColumnMapping.mapping })
    }).then(r => r.json());
    if (r && r.success) {
      toast('列对齐已更新，重新比对完成');
      loadResults();
      loadWsStats();
    } else {
      toast((r && r.error) || '调整失败', 'err');
      loadColumnAlign();
    }
  } catch (e) {
    toast('调整失败', 'err');
    loadColumnAlign();
  }
}
async function showDetail(id) {
  if (!currentCid) return;
  const p = new URLSearchParams(); if (currentVer) p.set('version_id', currentVer);
  const r = await fetch(API + '/api/contract/' + currentCid + '/compare/results?' + p).then(r => r.json());
  const d = r.results.find(x => x.id === id); if (!d) return;
  const sb = { '匹配成功': 'badge-s', '匹配异常': 'badge-w', '待采购': 'badge-e', '供应商增项': 'badge-p' }[d.match_status] || '';
  const confirmed = d.confirmed ? `<span class="badge badge-s" style="margin-left:8px">✓ 已确认</span>` : '';
  const anomaly = ((d.anomaly_detail || '').replace(/\n/g, '<br>'));
  document.getElementById('detailContent').innerHTML = `<h3>差异详情 ${confirmed}</h3>
    <div class="row"><div class="l">设备名称</div><div class="v"><b>${d.ct_name || d.sp_name || ''}</b> / ${d.ct_model || d.sp_model || ''}</div></div>
    <div class="row"><div class="l">状态</div><div class="v"><span class="badge ${sb}">${d.match_status}</span></div></div>
    <div class="row"><div class="l">数量</div><div class="v">合同 <b>${d.contract_qty || '-'}</b> &nbsp;→&nbsp; 报价 <b>${d.quote_qty || '-'}</b></div></div>
    <div class="row" style="flex-direction:column;align-items:stretch">
      <div class="l" style="margin-bottom:6px">📋 合同要求</div>
      <div style="background:#151530;padding:8px 12px;border-radius:4px;font-size:12px;line-height:1.6;max-height:150px;overflow:auto">${d.ct_specs || '（无）'}</div>
    </div>
    <div class="row" style="flex-direction:column;align-items:stretch">
      <div class="l" style="margin-bottom:6px">📦 供应商报价</div>
      <div style="background:#151530;padding:8px 12px;border-radius:4px;font-size:12px;line-height:1.6;max-height:150px;overflow:auto">${d.sp_specs || '（无）'}</div>
    </div>
    ${anomaly ? `<div class="row" style="flex-direction:column;align-items:stretch"><div class="l" style="margin-bottom:4px;color:var(--orange)">⚠️ 异常详情</div><div style="font-size:12px;line-height:1.8;padding:4px 0">${anomaly}</div></div>` : ''}
    <div style="display:flex;gap:8px;margin-top:12px">
      ${d.match_status === '匹配异常' && !d.confirmed ? `<button class="btn btn-s" style="background:#34d399" onclick="confirmAnomaly(${d.id},1)">✓ 确认无误</button>` : ''}
      ${d.confirmed ? `<button class="btn btn-o" onclick="confirmAnomaly(${d.id},0)">↩ 撤销确认</button>` : ''}
      <button class="btn btn-o" onclick="closeModal()">关闭</button>
    </div>`;
  document.getElementById('detailModal').classList.add('show');
}
async function confirmAnomaly(rid, val, btn) {
  if (btn) _spin(btn, true, '处理中...');
  try { await fetch(API + '/api/compare/' + rid + '/confirm?confirmed=' + val, { method: 'POST' }); } catch (e) {}
  if (btn) _spin(btn, false);
  closeModal(); loadResults(); loadVersions(); loadWsStats(); loadContracts();
}
function closeModal() { document.getElementById('detailModal').classList.remove('show'); }

// ===== 版本详情 =====
async function showVerDetail(vid) {
  if (!currentCid) return;
  const r = await fetch(API + '/api/contract/' + currentCid + '/supplier/items?version_id=' + vid).then(r => r.json());
  const headers = (r.headers && r.headers.length) ? r.headers : ['设备名称', '型号', '数量', '单位', '单价', '金额'];
  document.getElementById('detailContent').innerHTML = `<h3>📦 版本 v${vid} — 供应商报价明细</h3>
    <div class="twrap" style="max-height:500px;overflow:auto"><table><thead><tr>${headers.map(h => `<th>${_html(h)}</th>`).join('')}</tr></thead><tbody>
    ${r.items.map(i => {
      let raw = {}; try { raw = JSON.parse(i.raw_columns || '{}'); } catch (e) {}
      return `<tr>${headers.map(h => `<td>${_html(raw[h] !== undefined ? raw[h] : '')}</td>`).join('')}</tr>`;
    }).join('')}
    </tbody></table></div>
    <div style="margin-top:8px;color:var(--text2);font-size:11px">共 ${r.total} 条</div>
    <button class="btn btn-o" onclick="closeModal()" style="margin-top:10px">关闭</button>`;
  document.getElementById('detailModal').classList.add('show');
}

// ===== 导出 =====
function exportReport(btn) {
  if (!currentCid || !currentVer) { toast('请先上传供应商文件', 'err'); return; }
  if (btn) _spin(btn, true, '导出中...');
  window.open(API + '/api/contract/' + currentCid + '/export/report?version_id=' + currentVer);
  toast('导出中...');
  setTimeout(function () { if (btn) _spin(btn, false); }, 1500);
}

// ===== 视图2 · 上传资料工作区 =====
async function loadUpContracts() {
  const r = await fetch(API + '/api/contracts').then(r => r.json());
  const sel = document.getElementById('upContractSelect');
  sel.innerHTML = '<option value="">请选择合同</option>' + r.contracts.map(c =>
    `<option value="${c.id}">${(c.contract_name || '未命名合同')} · ${c.contract_no || '-'} (进度 ${c.progress || 0}%)</option>`
  ).join('');
  // 已存在当前合同 keep 选中；否则保持空（不自动触发，避免误拉版本）
  if (currentCid && sel.querySelector(`option[value="${currentCid}"]`)) {
    sel.value = currentCid;
    loadUpVersions();
  }
}
function onUpSelect() {
  const sel = document.getElementById('upContractSelect');
  const cid = parseInt(sel.value || '0', 10) || 0;
  if (cid) {
    currentCid = cid;
    const text = (sel.options[sel.selectedIndex] ? sel.options[sel.selectedIndex].text : '');
    currentCname = text.split(' · ')[0];
    const label = document.getElementById('currentContractLabel');
    if (label) label.textContent = '》' + currentCname;
  } else {
    currentCid = null; currentVer = null;
    const label = document.getElementById('currentContractLabel');
    if (label) label.textContent = '';
  }
  loadUpVersions();
}
function _renderUpEmpty() {
  const t = document.getElementById('upVerTable');
  if (t) t.innerHTML = '<tr><td colspan="10" style="text-align:center;color:var(--text2);padding:14px">请先选择目标合同</td></tr>';
}
async function loadUpVersions() {
  if (!currentCid) { _renderUpEmpty(); return; }
  const sf = document.getElementById('upVerSupplierFilter').value;
  const p = new URLSearchParams(); if (sf) p.set('supplier_name', sf);
  const r = await fetch(API + '/api/contract/' + currentCid + '/supplier/versions?' + p).then(r => r.json());
  const sel = document.getElementById('upVerSupplierFilter'); const curVal = sel.value;
  sel.innerHTML = '<option value="">全部供应商</option>' + r.suppliers.map(s => `<option value="${s.supplier_name}">${s.supplier_name} (${s.version_count}版本)</option>`).join('');
  sel.value = curVal;
  document.getElementById('upVerTable').innerHTML = r.versions.map(v => {
    const sname = v.supplier_name ? `<span class="badge badge-p">${v.supplier_name}</span>` : '<span style="color:var(--text2)">-</span>';
    const activeTag = v.is_active ? `<span class="badge badge-s" style="font-size:10px">🔵 生效中</span>` : '';
    const delBtn = v.is_active ? '' : `<button class="btn btn-o btn-s" onclick="upDelVer(${v.id})" style="color:#f44;border-color:#f44">🗑</button>`;
    return `<tr><td><span class="badge badge-c">v${v.id}</span>${activeTag}</td><td>${sname}</td><td>${(v.upload_time || '').substring(0, 16)}</td><td>${v.total_items}</td><td>${v.matched_count}</td><td>${v.anomaly_count}</td><td>${v.pending_count}</td><td>${v.extra_count}</td><td><span class="badge ${v.progress >= 100 ? 'badge-s' : 'badge-w'}">${v.progress}%</span></td><td><button class="btn btn-o btn-s" onclick="upVerDetail(${v.id})">详情</button>${delBtn}</td></tr>`;
  }).join('') || '<tr><td colspan="10" style="text-align:center;color:var(--text2);padding:14px">暂无版本</td></tr>';
  if (r.versions.length > 0 && !currentVer) currentVer = r.versions[0].id;
}
async function uploadUpContract(inp) {
  const cid = currentCid; const f = inp.files[0];
  if (!cid) { toast('请先选择目标合同', 'err'); inp.value = ''; return; }
  if (!f) { inp.value = ''; return; }
  toast('正在上传合同基准...'); inp.disabled = true;
  const fd = new FormData(); fd.append('file', f);
  try {
    const r = await fetch(API + '/api/contract/' + cid + '/upload', { method: 'POST', body: fd }).then(r => r.json());
    if (r.success) { toast(`已导入 ${r.count} 条`); loadUpVersions(); loadContracts(); }
    else toast(r.error, false);
  } catch (e) { toast('上传失败：' + e.message, false); }
  inp.disabled = false; inp.value = '';
}
async function uploadUpSupplier(inp) {
  const cid = currentCid; const f = inp.files[0];
  if (!cid) { toast('请先选择目标合同', 'err'); inp.value = ''; return; }
  if (!f) { inp.value = ''; return; }
  const snInput = document.getElementById('upSupplierName');
  if (!snInput.value.trim()) { snInput.value = f.name.replace(/\.[^.]+$/, ''); }
  const sn = snInput.value.trim();
  if (!sn) { toast('请先填写供应商名称', false); inp.value = ''; return; }
  toast('正在上传并比对...'); inp.disabled = true;
  const fd = new FormData(); fd.append('file', f);
  try {
    const r = await fetch(API + '/api/contract/' + cid + '/supplier/upload?supplier_name=' + encodeURIComponent(sn), { method: 'POST', body: fd }).then(r => r.json());
    if (r.success) { toast(`v${r.version_id} (${sn}) 比对完成！进度 ${r.progress}%`); currentVer = r.version_id; loadUpVersions(); loadContracts(); }
    else toast(r.error, false);
  } catch (e) { toast('上传失败：' + e.message, false); }
  inp.disabled = false; inp.value = '';
}
async function upDelVer(vid) {
  if (!currentCid) return;
  if (!confirm('确定删除版本 v' + vid + '？将同时删除该版本的比对结果和供应商报价数据。')) return;
  const r = await fetch(API + '/api/contract/' + currentCid + '/supplier/versions/' + vid, { method: 'DELETE' }).then(r => r.json());
  if (r.success) { toast('版本 v' + vid + ' 已删除'); loadUpVersions(); loadContracts(); }
  else toast(r.error || '删除失败', false);
}
function upVerDetail(vid) { showVerDetail(vid); }

// ===== 初始化 =====
document.addEventListener('DOMContentLoaded', function () {
  loadContracts();
});