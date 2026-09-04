/* 本体函数目录：按 category 折叠分组 + 按 产出实体 过滤 + 搜索 */
(function () {
  "use strict";
  var CAT_COLOR = {
    "聚合": "#34d399", "比率": "#22d3ee", "周期": "#4f8cff", "状态判定": "#a78bfa",
    "资金占用": "#fbbf24", "预警": "#f87171", "派生": "#60a5fa", "组合": "#c084fc"
  };
  var state = { data: [], q: "", cat: null, ent: null, sel: null };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function catColor(c) { return CAT_COLOR[c] || "#7d8db0"; }

  function load() {
    fetch("/api/ontos/spec").then(function (r) { return r.json(); }).then(function (spec) {
      state.data = (spec.functions || []);
      var rev = spec.meta && spec.meta.ontos_revision;
      document.getElementById("rev").textContent = "ontos@" + (rev || "?");
      document.getElementById("loading").style.display = "none";
      renderSide();
      renderList();
    }).catch(function (e) {
      document.getElementById("loading").textContent = "加载失败：" + e;
    });
  }

  function matchFilter(item) {
    if (state.cat && item.category !== state.cat) return false;
    if (state.ent && !(item.produces_for || []).includes(state.ent)) return false;
    if (state.q) {
      var hay = [item.id, item.name, item.description, (item.inputs || []).join(" "),
        (item.outputs || []).join(" ")].join(" ").toLowerCase();
      if (hay.indexOf(state.q.toLowerCase()) === -1) return false;
    }
    return true;
  }

  function renderSide() {
    var cats = {}, ents = {};
    state.data.forEach(function (f) {
      cats[f.category || "未分类"] = (cats[f.category || "未分类"] || 0) + 1;
      (f.produces_for || []).forEach(function (e) { ents[e] = (ents[e] || 0) + 1; });
    });
    var html = "";
    html += '<div class="sgrp"><h4>按类型 <span class="n">' + state.data.length + "</span></h4><ul>";
    html += '<li class="' + (state.cat === null ? "active" : "") + '" data-cat=""><span class="dot" style="background:linear-gradient(135deg,#4f8cff,#22d3ee)"></span>全部类型</li>';
    Object.keys(cats).sort().forEach(function (c) {
      html += '<li class="' + (state.cat === c ? "active" : "") + '" data-cat="' + esc(c) + '">' +
        '<span class="dot" style="background:' + catColor(c) + '"></span>' + esc(c) +
        '<span style="margin-left:auto;font-family:var(--mono);color:var(--text2)">' + cats[c] + "</span></li>";
    });
    html += "</ul></div>";
    html += '<div class="sgrp"><h4>按产出实体 <span class="n">' + Object.keys(ents).length + "</span></h4><ul>";
    html += '<li class="' + (state.ent === null ? "active" : "") + '" data-ent=""><span class="dot" style="background:#7d8db0"></span>全部实体</li>';
    Object.keys(ents).sort().forEach(function (e) {
      html += '<li class="' + (state.ent === e ? "active" : "") + '" data-ent="' + esc(e) + '">' +
        '<span class="dot" style="background:#60a5fa"></span>' + esc(e) +
        '<span style="margin-left:auto;font-family:var(--mono);color:var(--text2)">' + ents[e] + "</span></li>";
    });
    html += "</ul></div>";
    var side = document.getElementById("side");
    side.innerHTML = html;
    side.querySelectorAll("li[data-cat]").forEach(function (li) {
      li.onclick = function () { state.cat = li.getAttribute("data-cat") || null; renderSide(); renderList(); };
    });
    side.querySelectorAll("li[data-ent]").forEach(function (li) {
      li.onclick = function () { state.ent = li.getAttribute("data-ent") || null; renderSide(); renderList(); };
    });
  }

  function renderList() {
    var list = state.data.filter(matchFilter);
    document.getElementById("cnt").innerHTML = "共 <b>" + list.length + "</b> / " + state.data.length + " 条";
    var listEl = document.getElementById("list");
    if (!list.length) { listEl.innerHTML = '<div class="empty">无匹配函数</div>'; return; }
    var groups = {};
    list.forEach(function (f) {
      var c = f.category || "未分类";
      (groups[c] = groups[c] || []).push(f);
    });
    var html = "";
    Object.keys(groups).sort().forEach(function (c) {
      html += '<div class="sec"><div class="sec-h"><span class="badge" style="background:' + catColor(c) + '">' + esc(c) +
        '</span><span class="cnt">' + groups[c].length + " 条</span></div>";
      groups[c].forEach(function (f) {
        var active = state.sel === f.id ? " active" : "";
        html += '<div class="card' + active + '" data-id="' + esc(f.id) + '" style="border-left-color:' + catColor(c) + '">' +
          '<div class="t"><span class="nm">' + esc(f.name || f.id) + '</span>' +
          '<span class="fid">' + esc(f.id) + "</span></div>" +
          '<div class="ds">' + esc(f.description || "").slice(0, 80) + "</div></div>";
      });
      html += "</div>";
    });
    listEl.innerHTML = html;
    listEl.querySelectorAll(".card").forEach(function (card) {
      card.onclick = function () { state.sel = card.getAttribute("data-id"); renderList(); renderDetail(); };
    });
  }

  function renderDetail() {
    var f = state.data.find(function (x) { return x.id === state.sel; });
    var el = document.getElementById("detail");
    if (!f) { el.innerHTML = '<div class="empty">点击左侧函数查看详情</div>'; return; }
    var html = '<div class="detail">';
    html += "<h2>" + esc(f.name || f.id) + "</h2>";
    html += '<div style="margin:6px 0 4px"><span class="badge" style="background:' + catColor(f.category) +
      ';color:#04121f">' + esc(f.category || "未分类") + "</span> " +
      '<span class="chip">' + esc(f.domain || "") + "</span>" +
      '<span class="chip">v' + esc(f.version || "") + "</span>" +
      '<span class="chip">' + esc(f.id) + "</span></div>";
    if (f.description) { html += '<div class="k">描述</div><p>' + esc(f.description) + "</p>"; }
    if (f.inputs && f.inputs.length) {
      html += '<div class="k">输入 (inputs)</div><div>';
      f.inputs.forEach(function (i) { html += '<span class="chip">' + esc(i) + "</span>"; });
      html += "</div>";
    }
    if (f.outputs && f.outputs.length) {
      html += '<div class="k">输出 (outputs)</div><div>';
      f.outputs.forEach(function (o) { html += '<span class="chip">' + esc(o) + "</span>"; });
      html += "</div>";
    }
    if (f.produces_for && f.produces_for.length) {
      html += '<div class="k">产出属性归属实体 (produces_for)</div><div>';
      f.produces_for.forEach(function (e) { html += '<span class="chip" style="background:rgba(96,165,250,.15);color:#93c5fd;border-color:rgba(96,165,250,.4)">' + esc(e) + "</span>"; });
      html += "</div>";
    }
    if (f.invariant) { html += '<div class="k">不变量 (invariant)</div><p style="color:var(--green)">' + esc(f.invariant) + "</p>"; }
    if (f.meta && f.meta.policy) { html += '<div class="k">策略 (policy)</div><p><code>' + esc(f.meta.policy) + "</code></p>"; }
    html += "</div>";
    el.innerHTML = html;
  }

  document.getElementById("q").addEventListener("input", function (e) {
    state.q = e.target.value.trim(); renderList();
  });
  document.getElementById("reset").onclick = function () {
    state.q = ""; state.cat = null; state.ent = null; state.sel = null;
    document.getElementById("q").value = ""; renderSide(); renderList(); renderDetail();
  };
  load();
})();
