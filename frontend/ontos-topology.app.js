/* 本体拓扑 · 业务域 v4 —— UModel 风格实体关系图
 *
 * 数据全部来自后端 API（无内嵌快照）：
 *   GET /api/ontos/spec     → TBox 定义（ontos.domain_business.to_spec() 实时执行）
 *   GET /api/ontos/columns  → 物理字段（总合同表 / 项目里程碑表 最新版本列清单）
 *
 * 交互：点击节点看属性、拖拽调整、搜索高亮、重置布局、重新加载。
 */
(function () {
  'use strict';

  var LABEL = {
    Project: '项目', Contract: '合同', Milestone: '里程碑',
    Receipt: '回款', Payment: '付款', Warning: '预警',
    Order: '订单', WorkOrder: '工单', Task: '任务', Person: '人员',
    Opportunity: '商机', PreSales: '售前', OutputValue: '产值',
    Invoice: '发票', Deposit: '保证金',
  };

  var SPEC = null, COLS = null;
  var ENTITIES = [], EDGES = [], byId = {};
  var currentDim = null;
  var wrap, svg, SVGNS = 'http://www.w3.org/2000/svg';
  var W = 0, H = 0;

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  function kindText(k) {
    return k === 'top' ? '顶层实体' : k === 'child' ? '子实体' : '范围外占位';
  }

  /* ───────────── 数据加载 ───────────── */

  function load() {
    var loading = document.getElementById('loading');
    if (loading) { loading.style.display = 'flex'; loading.textContent = '正在从 ontos 加载本体定义…'; }
    Promise.all([
      fetch('/api/ontos/spec').then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); }),
      fetch('/api/ontos/columns').then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); }),
    ]).then(function (res) {
      var specRes = res[0], colRes = res[1];
      if (!specRes.ok || specRes.j.success === false) {
        showError('本体定义加载失败', specRes.j && specRes.j.message
          ? specRes.j.message : ('HTTP ' + specRes.ok), specRes.j && specRes.j.hint);
        return;
      }
      SPEC = specRes.j;
      COLS = (colRes.ok && colRes.j.success) ? colRes.j : null;
      build();
      renderOverview();
      layout(); renderNodes(); renderEdges(null);
      if (loading) loading.style.display = 'none';
      var rev = (SPEC.meta && SPEC.meta.ontos_revision) || 'unknown';
      document.getElementById('rev').textContent = 'ontos @ ' + rev;
    }).catch(function (err) {
      showError('无法连接后端接口', String(err));
    });
  }

  function showError(title, msg, hint) {
    var loading = document.getElementById('loading');
    if (loading) loading.style.display = 'none';
    var wrapEl = document.getElementById('wrap');
    var old = wrapEl.querySelector('.err'); if (old) old.remove();
    var d = document.createElement('div');
    d.className = 'err';
    d.innerHTML = '<div><b style="font-size:15px;">' + esc(title) + '</b><br><br>' +
      esc(msg || '') + (hint ? '<br><br><span style="color:#64748b;">提示：' + esc(hint) + '</span>' : '') + '</div>';
    wrapEl.appendChild(d);
  }

  /* ───────────── 由 spec 构造图 ───────────── */

  function build() {
    ENTITIES = []; byId = {};
    (SPEC.entities || []).forEach(function (e) {
      var n = {
        id: e.name, en: e.name, label: e.cn || LABEL[e.name] || e.name,
        kind: e.kind || 'top', desc: e.desc || '', attrs: e.attributes || [],
      };
      ENTITIES.push(n); byId[n.id] = n;
    });

    // 逆关系去重：同一对实体只画一条边（如 realizesReceivable 与它的逆 sourceMilestone）
    var seen = {}, drawn = [];
    (SPEC.links || []).forEach(function (l) {
      var key = [l.subj, l.obj].sort().join('|');
      if (seen[key]) return;
      seen[key] = true;
      drawn.push({ s: l.subj, t: l.obj, p: l.predicate, c: l.card, desc: l.desc || '' });
    });

    // 补「范围外占位」节点（被关系引用但不在 v4 实体集内，如 Supplier）
    drawn.forEach(function (e) {
      [e.s, e.t].forEach(function (id) {
        if (!byId[id]) {
          var n = { id: id, en: id, label: LABEL[id] || id, kind: 'external',
                    desc: '范围外占位：v4 场景未纳入该实体，仅被关系引用。', attrs: [] };
          ENTITIES.push(n); byId[id] = n;
        }
        var n2 = byId[id];
        if (n2 && n2.kind !== 'external') return;
      });
    });

    EDGES = drawn;
  }

  /* ───────────── 力导向布局 ───────────── */

  function size() {
    W = wrap.clientWidth; H = wrap.clientHeight;
    svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
  }

  function layout() {
    size();
    var N = ENTITIES.length, cx = W / 2, cy = H / 2, R = Math.min(W, H) * 0.30;
    ENTITIES.forEach(function (n, i) {
      n.x = cx + Math.cos(i / N * 2 * Math.PI) * R;
      n.y = cy + Math.sin(i / N * 2 * Math.PI) * R;
      n.vx = 0; n.vy = 0;
    });
    var rep = 11000, spring = 0.035, target = 200, iters = 460;
    for (var it = 0; it < iters; it++) {
      for (var i = 0; i < N; i++) for (var j = i + 1; j < N; j++) {
        var a = ENTITIES[i], b = ENTITIES[j];
        var dx = a.x - b.x, dy = a.y - b.y, d2 = dx * dx + dy * dy + 0.01;
        var d = Math.sqrt(d2), f = rep / d2;
        var fx = dx / d * f, fy = dy / d * f;
        a.vx += fx; a.vy += fy; b.vx -= fx; b.vy -= fy;
      }
      EDGES.forEach(function (e) {
        var a = byId[e.s], b = byId[e.t];
        if (a === b) return;
        var dx = b.x - a.x, dy = b.y - a.y, d = Math.sqrt(dx * dx + dy * dy) + 0.01;
        var f = spring * (d - target);
        var fx = dx / d * f, fy = dy / d * f;
        a.vx += fx; a.vy += fy; b.vx -= fx; b.vy -= fy;
      });
      ENTITIES.forEach(function (n) {
        n.vx += (cx - n.x) * 0.006; n.vy += (cy - n.y) * 0.006;
        n.vx *= 0.85; n.vy *= 0.85; n.x += n.vx; n.y += n.vy;
        n.x = Math.max(70, Math.min(W - 70, n.x));
        n.y = Math.max(50, Math.min(H - 50, n.y));
      });
    }
  }

  /* ───────────── 渲染 ───────────── */

  function physCount(id) {
    if (!COLS) return null;
    var name = COLS.entity_dataset[id];
    var ds = name && COLS.datasets[name];
    return ds ? { name: name, count: ds.column_count } : null;
  }

  function renderNodes() {
    Array.prototype.slice.call(wrap.querySelectorAll('.node')).forEach(function (el) { el.remove(); });
    ENTITIES.forEach(function (n) {
      var el = document.createElement('div');
      el.className = 'node ' + n.kind; el.dataset.id = n.id;
      var pc = physCount(n.id);
      var cnt = n.kind === 'external' ? ''
        : '<div class="cnt">属性 ' + n.attrs.length + (pc ? ' · ' + pc.name + ' ' + pc.count + '列' : '') + '</div>';
      el.innerHTML = '<div class="kind">' + kindText(n.kind) + '</div>' +
        '<div class="nm">' + esc(n.label) + '</div>' +
        '<div class="ent">' + esc(n.en) + '</div>' + cnt;
      el.style.left = n.x + 'px'; el.style.top = n.y + 'px';
      el.addEventListener('click', function (ev) { ev.stopPropagation(); select(n.id); });
      el.addEventListener('pointerdown', function (ev) { startDrag(ev, n, el); });
      wrap.appendChild(el); n._el = el;
    });
  }

  function edgeLabel(x, y, text, dim) {
    var g = document.createElementNS(SVGNS, 'g');
    var txt = document.createElementNS(SVGNS, 'text');
    txt.setAttribute('x', x); txt.setAttribute('y', y);
    txt.setAttribute('text-anchor', 'middle'); txt.setAttribute('font-size', '10');
    txt.setAttribute('fill', '#475569'); txt.textContent = text;
    var bg = document.createElementNS(SVGNS, 'rect');
    var w = text.length * 6.6 + 16;
    bg.setAttribute('x', x - w / 2); bg.setAttribute('y', y - 12);
    bg.setAttribute('width', w); bg.setAttribute('height', 15);
    bg.setAttribute('rx', 3); bg.setAttribute('fill', '#fff'); bg.setAttribute('opacity', '0.92');
    g.appendChild(bg); g.appendChild(txt);
    if (dim) g.classList.add('dim');
    return g;
  }

  function renderEdges(dimSet) {
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    EDGES.forEach(function (e) {
      var a = byId[e.s], b = byId[e.t];
      var dim = dimSet && !(dimSet.has(e.s) && dimSet.has(e.t));
      if (e.s === e.t) {
        // 自关系（小里程碑 decomposedFrom 父大里程碑）：节点上方自环
        var x = a.x, y = a.y;
        var path = document.createElementNS(SVGNS, 'path');
        path.setAttribute('d', 'M ' + (x - 30) + ' ' + (y - 22) +
          ' C ' + (x - 46) + ' ' + (y - 78) + ', ' + (x + 46) + ' ' + (y - 78) + ', ' + (x + 30) + ' ' + (y - 22));
        path.setAttribute('fill', 'none');
        path.setAttribute('stroke', 'var(--line)');
        path.setAttribute('stroke-width', '1.6');
        path.setAttribute('class', 'edge'); if (dim) path.classList.add('dim');
        svg.appendChild(path);
        svg.appendChild(edgeLabel(x, y - 80, e.p + ' · ' + e.c, dim));
        return;
      }
      var line = document.createElementNS(SVGNS, 'line');
      line.setAttribute('x1', a.x); line.setAttribute('y1', a.y);
      line.setAttribute('x2', b.x); line.setAttribute('y2', b.y);
      line.setAttribute('stroke', 'var(--line)');
      line.setAttribute('stroke-width', '1.8');
      line.setAttribute('class', 'edge'); if (dim) line.classList.add('dim');
      svg.appendChild(line);
      svg.appendChild(edgeLabel((a.x + b.x) / 2, (a.y + b.y) / 2 - 2, e.p + ' · ' + e.c, dim));
    });
  }

  function startDrag(ev, n, el) {
    ev.preventDefault();
    function move(ev2) {
      var r = wrap.getBoundingClientRect();
      n.x = ev2.clientX - r.left; n.y = ev2.clientY - r.top;
      el.style.left = n.x + 'px'; el.style.top = n.y + 'px';
      renderEdges(currentDim);
    }
    function up() {
      document.removeEventListener('pointermove', move);
      document.removeEventListener('pointerup', up);
    }
    document.addEventListener('pointermove', move);
    document.addEventListener('pointerup', up);
  }

  function select(id) {
    ENTITIES.forEach(function (n) { n._el.classList.toggle('sel', n.id === id); });
    var nb = new Set([id]);
    EDGES.forEach(function (e) {
      if (e.s === id) nb.add(e.t);
      if (e.t === id) nb.add(e.s);
    });
    currentDim = nb; renderEdges(nb);
    renderDetail(byId[id]);
  }

  /* ───────────── 属性面板 ───────────── */

  function boundFields(entity) {
    var s = new Set();
    (entity.attrs || []).forEach(function (a) {
      if (!a.source) return;
      var last = String(a.source).split('.').pop();
      if (last) s.add(last);
    });
    return s;
  }

  function renderPhysical(entity) {
    if (!COLS) return '';
    var dsName = COLS.entity_dataset[entity.id];
    if (!dsName) return '';
    var ds = COLS.datasets[dsName];
    if (!ds) return '';
    var bound = boundFields(entity);
    var hit = 0;
    var html = '<div class="sec-t">物理字段 · ' + esc(dsName) + '<span class="ln"></span></div>';
    html += '<div style="font-size:11px;color:#64748b;line-height:1.6;margin-bottom:4px;">' +
      '来源 <b>' + esc(ds.file) + '</b>：' + ds.rows + ' 行 / <b>' + ds.column_count + '</b> 列（' +
      esc(ds.uploaded_at) + ' 上传）。' +
      '<span style="color:#065f46;font-weight:600;">绿色</span> = 已被本体属性引用。</div>';
    ds.groups.forEach(function (g) {
      html += '<div class="grp"><span>' + esc(g.name) + '</span><span class="n">' + g.columns.length + '</span></div>';
      html += '<div class="cols-wrap">' + g.columns.map(function (c) {
        var f = ds.field_map[c];
        var isBound = !!(f && bound.has(f));
        if (isBound) hit++;
        return '<span class="col-chip' + (isBound ? ' bound' : '') + '"' +
          (f ? ' title="' + esc(c) + ' → ' + esc(f) + '"' : '') + '>' + esc(c) + '</span>';
      }).join('') + '</div>';
    });
    html += '<div class="note">本体语义属性（上表）是 <b>TBox 契约层</b>；此处为 <b>ABox 物理列</b>。' +
      '当前实体声明 ' + entity.attrs.length + ' 个语义属性，物理表 ' + ds.column_count +
      ' 列，其中 <b>' + hit + '</b> 列已被本体引用——差距即后续要补的属性。</div>';
    return html;
  }

  function renderDetail(n) {
    var d = document.getElementById('detail');
    var ktag = n.kind === 'top'
      ? '<span class="tag" style="background:var(--top-bg);color:var(--top-tx);">顶层实体</span>'
      : n.kind === 'child'
        ? '<span class="tag" style="background:var(--child-bg);color:var(--child-tx);">子实体</span>'
        : '<span class="tag" style="background:var(--ext-bg);color:var(--ext-tx);">范围外占位</span>';
    var html = '<h2>' + esc(n.label) + ' <span style="color:#94a3b8;font-size:12px;font-weight:400;">' +
      esc(n.en) + '</span></h2>' + ktag +
      '<div class="desc">' + esc(n.desc) + '</div>';

    // 关系
    var out = EDGES.filter(function (e) { return e.s === n.id; });
    var inn = EDGES.filter(function (e) { return e.t === n.id && e.s !== n.id; });
    html += '<div class="sec-t">关系<span class="ln"></span></div><div class="rel-list">' +
      (out.length ? out.map(function (e) {
        return '<div class="r"><span class="arrow">→</span><b>' + esc(e.p) + '</b> ' +
          esc(LABEL[e.t] || e.t) + ' <span style="color:#94a3b8;">(' + esc(e.c) + ')</span></div>';
      }).join('') : '<span style="color:#94a3b8;">（无出向关系）</span>') +
      (inn.length ? inn.map(function (e) {
        return '<div class="r"><span class="arrow">←</span><b>' + esc(e.p) + '</b> ' +
          esc(LABEL[e.s] || e.s) + ' <span style="color:#94a3b8;">(' + esc(e.c) + ')</span></div>';
      }).join('') : '') + '</div>';

    // 语义属性
    html += '<div class="sec-t">语义属性（TBox）<span class="ln"></span></div>';
    if (n.attrs.length) {
      html += '<table class="fields"><tr><th>属性</th><th>类型 / 来源 / 说明</th></tr>' +
        n.attrs.map(function (a) {
          return '<tr><td>' + esc(a.name) + (a.required ? ' <span class="req">*</span>' : '') +
            (a.unique ? ' <span style="color:#0891b2;font-size:10px;">U</span>' : '') + '</td><td>' +
            '<span class="ty">' + esc(a.type) + '</span>' +
            (a.source ? '<span class="src">' + esc(a.source) + '</span>' : '') +
            (a.desc ? esc(a.desc) : '') + '</td></tr>';
        }).join('') + '</table>';
    } else {
      html += '<div style="font-size:12px;color:#94a3b8;">范围外占位，暂无属性定义。</div>';
    }

    // 相关 Function
    var rel = (SPEC.functions || []).filter(function (f) {
      var s = (f.inputs || []).concat(f.outputs || []).join(' ') + ' ' + (f.description || '');
      var key = n.id.toLowerCase();
      return s.toLowerCase().indexOf(key) >= 0 ||
        (f.inputs || []).some(function (i) { return String(i).toLowerCase().indexOf(key) >= 0; });
    });
    if (rel.length) {
      html += '<div class="sec-t">相关场景函数<span class="ln"></span></div><div class="fn-list">' +
        rel.map(function (f) {
          return '<div><b>' + esc(f.name) + '</b> <span style="color:#94a3b8;">' + esc(f.id) + '</span><br>' +
            '<span style="color:#64748b;">' + esc(f.description) + '</span></div>';
        }).join('') + '</div>';
    }

    html += renderPhysical(n);
    d.innerHTML = html;
    d.scrollTop = 0;
  }

  function renderOverview() {
    var ne = (SPEC.entities || []).length;
    var nl = EDGES.length;
    var nf = (SPEC.functions || []).length;
    var na = (SPEC.actions || []).length;
    var phys = '';
    if (COLS) {
      Object.keys(COLS.datasets).forEach(function (k) {
        var ds = COLS.datasets[k];
        phys += '<div style="font-size:11px;color:#64748b;">' + esc(k) + '：<b style="color:#334155;">' +
          ds.column_count + '</b> 列（' + ds.rows + ' 行）</div>';
      });
    }
    var html = '<div class="stat">' +
      '<div class="s"><div class="v">' + ne + '</div><div class="l">实体</div></div>' +
      '<div class="s"><div class="v">' + nl + '</div><div class="l">关系</div></div>' +
      '<div class="s"><div class="v">' + nf + '</div><div class="l">函数</div></div>' +
      '<div class="s"><div class="v">' + na + '</div><div class="l">动作</div></div>' +
      '</div>' + phys;

    html += '<div class="sec-t">场景函数（' + nf + '）<span class="ln"></span></div><div class="fn-list">' +
      (SPEC.functions || []).map(function (f) {
        return '<div><b>' + esc(f.name) + '</b> <span style="color:#94a3b8;">' + esc(f.id) + '</span><br>' +
          '<span style="color:#64748b;">' + esc(f.description) + '</span></div>';
      }).join('') + '</div>';

    html += '<div class="sec-t">动作（' + na + '）<span class="ln"></span></div><div class="fn-list">' +
      (SPEC.actions || []).map(function (a) {
        return '<div><b>' + esc(a.id) + '</b><br><span style="color:#64748b;">' +
          esc(a.definition || '') + '</span></div>';
      }).join('') + '</div>';

    if ((SPEC.invariants || []).length) {
      html += '<div class="sec-t">不变量<span class="ln"></span></div><div class="fn-list">' +
        SPEC.invariants.map(function (v) {
          var id = v.id || v.name || '', desc = v.desc || v.description || '';
          return '<div><b>' + esc(id) + '</b> <span style="color:#64748b;">' + esc(desc) + '</span></div>';
        }).join('') + '</div>';
    }

    html += '<div class="note">点击左侧任意实体：查看语义属性、关系，以及它在物理表里实际有哪些列、' +
      '其中多少已被本体声明。当前范围只覆盖 <b>回款周期 / 资金占用 / 毛利率 / 成本预警 / ROI</b> 五个场景。</div>';
    document.getElementById('detail').innerHTML = html;
  }

  /* ───────────── 事件 ───────────── */

  function init() {
    wrap = document.getElementById('wrap');
    svg = document.getElementById('edges');

    document.getElementById('q').addEventListener('input', function (e) {
      var q = e.target.value.trim().toLowerCase();
      if (!q) {
        currentDim = null;
        ENTITIES.forEach(function (n) { n._el.classList.remove('dim'); });
        renderEdges(null);
        return;
      }
      var hit = new Set();
      ENTITIES.forEach(function (n) {
        var m = n.label.toLowerCase().indexOf(q) >= 0 || n.en.toLowerCase().indexOf(q) >= 0 ||
          (n.attrs || []).some(function (a) {
            return String(a.name).toLowerCase().indexOf(q) >= 0 ||
              String(a.desc || '').toLowerCase().indexOf(q) >= 0;
          });
        n._el.classList.toggle('dim', !m);
        if (m) hit.add(n.id);
      });
      EDGES.forEach(function (ed) {
        if (ed.p.toLowerCase().indexOf(q) >= 0) { hit.add(ed.s); hit.add(ed.t); }
      });
      ENTITIES.forEach(function (n) { n._el.classList.toggle('dim', !hit.has(n.id)); });
      currentDim = hit; renderEdges(hit);
    });

    document.getElementById('reset').addEventListener('click', function () {
      currentDim = null; layout(); renderNodes(); renderEdges(null);
    });
    document.getElementById('reload').addEventListener('click', function () {
      location.reload();
    });
    window.addEventListener('resize', function () {
      layout(); renderNodes(); renderEdges(currentDim);
    });

    load();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
