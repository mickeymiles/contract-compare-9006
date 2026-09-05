/* ABox 实例可视化页 · 纯前端渲染（无外部依赖） */
(function () {
  const root = document.getElementById('root');
  const revEl = document.getElementById('rev');

  const fmt = (v) => {
    if (v === null || v === undefined || v === '') return '—';
    if (typeof v === 'number') {
      if (!isFinite(v)) return '—';
      return v.toLocaleString('zh-CN', { maximumFractionDigits: 2 });
    }
    return String(v);
  };
  const pct = (v) => (v === null || v === undefined ? '—' : (v * 100).toFixed(1) + '%');

  function el(tag, cls, html) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html !== undefined) e.innerHTML = html;
    return e;
  }

  function showError(msg) {
    root.innerHTML = '';
    const d = el('div', 'err', msg);
    root.appendChild(d);
  }

  function renderDb(db) {
    const card = el('div', 'card');
    card.appendChild(el('h2', null, '① 库 / 表状态 <span class="tag">md_contract</span>'));
    const grid = el('div', 'stat-grid');
    const fileOk = db.file_exists;
    const tblOk = db.table_exists;
    const path = (db.path && db.path !== '(connection)') ? db.path : '(进程内连接)';
    grid.appendChild(stat('数据库文件', fileOk ? '存在' : '缺失', fileOk ? 'ok' : 'bad', path));
    grid.appendChild(stat('物理表 ' + db.table, tblOk ? '存在' : '缺失', tblOk ? 'ok' : 'bad'));
    grid.appendChild(stat('原始行数', fmt(db.raw_row_count), ''));
    grid.appendChild(stat('去重实例数', fmt(db.instance_count),
      db.instance_count > 0 ? 'ok' : 'warn', 'distinct 合同编号'));
    card.appendChild(grid);
    if (!tblOk) {
      const h = el('div', 'hint',
        '⚠️ 物理表 <code>' + db.table + '</code> 在当前库中不存在（多为本地空库未导入主数据）。' +
        '下列绑定映射与样本实例基于空表渲染；真实实例数据在服务器（已导入总合同表）可见。');
      card.appendChild(h);
    }
    return card;
  }

  function stat(k, v, cls, sub) {
    const s = el('div', 'stat');
    s.appendChild(el('div', 'k', k));
    const vv = el('div', 'v' + (cls ? ' ' + cls : ''), fmt(v));
    if (sub) vv.innerHTML += ' <small>' + sub + '</small>';
    s.appendChild(vv);
    return s;
  }

  function renderBindings(bindings) {
    const card = el('div', 'card');
    card.appendChild(el('h2', null,
      '② 绑定映射 · abox_adapter <span class="tag">本体属性 → 物理列</span>'));
    const wrap = el('div');
    wrap.style.overflowX = 'auto';
    const t = el('table');
    t.innerHTML = '<thead><tr><th>本体属性</th><th>物理列</th><th>存在</th>' +
      '<th>非空行</th><th>非空率</th></tr></thead>';
    const tb = el('tbody');
    bindings.forEach((b) => {
      const tr = el('tr');
      tr.appendChild(el('td', 'mono', b.property));
      tr.appendChild(el('td', 'mono', b.col || '—'));
      tr.appendChild(el('td', null,
        b.exists ? '<span class="badge yes">✓ 存在</span>' : '<span class="badge no">✗ 缺失</span>'));
      tr.appendChild(el('td', 'mono', fmt(b.non_null)));
      const rate = el('td');
      const r = el('div', 'rate');
      const bar = el('div', 'bar');
      const i = el('i');
      i.style.width = (Math.max(0, Math.min(1, b.non_null_rate || 0)) * 100) + '%';
      bar.appendChild(i);
      r.appendChild(bar);
      r.appendChild(el('span', 'pct', pct(b.non_null_rate)));
      rate.appendChild(r);
      tr.appendChild(rate);
      tb.appendChild(tr);
    });
    t.appendChild(tb);
    wrap.appendChild(t);
    card.appendChild(wrap);
    card.appendChild(el('div', 'muted',
      '绑定声明取自 ontos COST_FORMULA_POLICY.abox_adapter（单一真相），切源只改该声明块；' +
      '非空率 = 该列非空行数 / 原始行数。'));
    return card;
  }

  function renderNotAvailable(list) {
    if (!list || !list.length) return null;
    const card = el('div', 'card');
    card.appendChild(el('h2', null, '③ 未接入数据域 <span class="tag">⌛ not_available</span>'));
    const box = el('div', 'na-list');
    list.forEach((n) => {
      const na = el('div', 'na');
      na.appendChild(el('div', 't', '<span class="badge na">未接入</span> ' + n.domain));
      na.appendChild(el('div', 'd', n.reason));
      box.appendChild(na);
    });
    card.appendChild(box);
    card.appendChild(el('div', 'hint',
      '红线：这些域的数据源尚未接入，本体显式声明「未接入」而非编造假数据；接入后自动可用。'));
    return card;
  }

  function renderPortfolio(p) {
    const card = el('div', 'card');
    card.appendChild(el('h2', null,
      '④ 成本预警分布 <span class="tag">本体对全量 ABox 的判定</span>'));
    const sum = el('div', 'summary');
    const sm = p.summary || {};
    Object.keys(sm).forEach((k) => {
      const s = el('div', 's');
      s.appendChild(el('div', 'k', k));
      s.appendChild(el('div', 'v', sm[k]));
      sum.appendChild(s);
    });
    card.appendChild(sum);
    const sc = p.status_count || {};
    const dist = el('div', 'stat-grid');
    ['超支', '预警', '正常'].forEach((st) => {
      const n = sc[st] || 0;
      const s = el('div', 'stat');
      s.appendChild(el('div', 'k', st + '项目'));
      s.appendChild(el('div', 'v', '<span class="badge ' + st + '">' + n + '</span>'));
      dist.appendChild(s);
    });
    card.appendChild(dist);
    card.appendChild(el('div', 'muted',
      '判定口径：预算=累计实施成本预估，当前成本=累计实施成本实际，阈值走本体 F-project-cost-warning。'));
    return card;
  }

  function renderSample(sample) {
    const card = el('div', 'card');
    card.appendChild(el('h2', null,
      '⑤ 实体实例样本 <span class="tag">Project ← md_contract</span>'));
    if (!sample || !sample.length) {
      card.appendChild(el('div', 'hint', '当前库无实例（去重后 0 行）。'));
      return card;
    }
    const wrap = el('div');
    wrap.style.overflowX = 'auto';
    const t = el('table');
    t.innerHTML = '<thead><tr><th>合同编号</th><th>名称</th><th>部门</th><th>责任人</th>' +
      '<th>区域</th><th>状态</th><th>合同额</th><th>预算</th><th>当前成本</th>' +
      '<th>完成比</th><th>本体判定</th></tr></thead>';
    const tb = el('tbody');
    sample.forEach((r) => {
      const tr = el('tr');
      tr.appendChild(el('td', 'mono', r.contract_no));
      tr.appendChild(el('td', null, r.name || '—'));
      tr.appendChild(el('td', null, r.dept || '—'));
      tr.appendChild(el('td', null, r.owner || '—'));
      tr.appendChild(el('td', null, r.region || '—'));
      tr.appendChild(el('td', null, r.status || '—'));
      tr.appendChild(el('td', 'mono', fmt(r.amount)));
      tr.appendChild(el('td', 'mono', fmt(r.budget)));
      tr.appendChild(el('td', 'mono', fmt(r.current_cost)));
      tr.appendChild(el('td', 'mono', r.budget_ratio == null ? '—'
        : (r.budget_ratio * 100).toFixed(0) + '%'));
      tr.appendChild(el('td', null, '<span class="badge ' + (r.cost_status || 'na') + '">'
        + (r.cost_status || '—') + '</span>'));
      tb.appendChild(tr);
    });
    t.appendChild(tb);
    wrap.appendChild(t);
    card.appendChild(wrap);
    card.appendChild(el('div', 'muted', '仅展示前 ' + sample.length +
      ' 条样本（已去重）；完整全集见成本预警分布与 /api/ontos/abox 的 total。'));
    return card;
  }

  async function load() {
    try {
      const [aboxRes, specRes] = await Promise.all([
        fetch('/api/ontos/abox'),
        fetch('/api/ontos/spec').catch(() => null),
      ]);
      if (!aboxRes.ok) throw new Error('ABox 接口返回 ' + aboxRes.status);
      const abox = await aboxRes.json();
      if (specRes && specRes.ok) {
        const spec = await specRes.json();
        if (spec && spec.meta && spec.meta.ontos_revision) {
          revEl.textContent = 'ontos@' + spec.meta.ontos_revision;
        }
      }
      if (!abox || abox.success === false) {
        showError('ABox 加载失败：' + ((abox && abox.message) || '未知错误'));
        return;
      }
      root.innerHTML = '';
      root.appendChild(renderDb(abox.db || {}));
      root.appendChild(renderBindings(abox.bindings || []));
      const na = renderNotAvailable(abox.not_available);
      if (na) root.appendChild(na);
      root.appendChild(renderPortfolio(abox.cost_portfolio || {}));
      root.appendChild(renderSample(abox.sample));
    } catch (e) {
      showError('加载异常：' + e.message);
    }
  }

  load();
})();
