/* 本体动作目录：按 category 折叠分组 + 按 指向实体 过滤 + 搜索 */
(function () {
  "use strict";
  var CAT_COLOR = {
    "财经入账": "#34d3ee", "交付履约": "#4f8cff", "结构变更": "#a78bfa", "预警闭环": "#fbbf24"
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
      state.data = (spec.actions || []);
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
    if (state.ent && !(item.targets || []).includes(state.ent)) return false;
    if (state.q) {
      var hay = [item.id, item.name, item.definition, (item.conditions || []).join(" "),
        (item.effects || ""), (item.invariants || []).join(" ")].join(" ").toLowerCase();
      if (hay.indexOf(state.q.toLowerCase()) === -1) return false;
    }
    return true;
  }

  function renderSide() {
    var cats = {}, ents = {};
    state.data.forEach(function (a) {
      cats[a.category || "未分类"] = (cats[a.category || "未分类"] || 0) + 1;
      (a.targets || []).forEach(function (e) { ents[e] = (ents[e] || 0) + 1; });
    });
    var html = "";
    html += '<div class="sgrp"><h4>按类型 <span class="n">' + state.data.length + "</span></h4><ul>";
    html += '<li class="' + (state.cat === null ? "active" : "") + '" data-cat=""><span class="dot" style="background:linear-gradient(135deg,#fb923c,#fbbf24)"></span>全部类型</li>';
    Object.keys(cats).sort().forEach(function (c) {
      html += '<li class="' + (state.cat === c ? "active" : "") + '" data-cat="' + esc(c) + '">' +
        '<span class="dot" style="background:' + catColor(c) + '"></span>' + esc(c) +
        '<span style="margin-left:auto;font-family:var(--mono);color:var(--text2)">' + cats[c] + "</span></li>";
    });
    html += "</ul></div>";
    html += '<div class="sgrp"><h4>按指向实体 <span class="n">' + Object.keys(ents).length + "</span></h4><ul>";
    html += '<li class="' + (state.ent === null ? "active" : "") + '" data-ent=""><span class="dot" style="background:#7d8db0"></span>全部实体</li>';
    Object.keys(ents).sort().forEach(function (e) {
      html += '<li class="' + (state.ent === e ? "active" : "") + '" data-ent="' + esc(e) + '">' +
        '<span class="dot" style="background:#fbbf24"></span>' + esc(e) +
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
    if (!list.length) { listEl.innerHTML = '<div class="empty">无匹配动作</div>'; return; }
    var groups = {};
    list.forEach(function (a) {
      var c = a.category || "未分类";
      (groups[c] = groups[c] || []).push(a);
    });
    var html = "";
    Object.keys(groups).sort().forEach(function (c) {
      html += '<div class="sec"><div class="sec-h"><span class="badge" style="background:' + catColor(c) + '">' + esc(c) +
        '</span><span class="cnt">' + groups[c].length + " 条</span></div>";
      groups[c].forEach(function (a) {
        var active = state.sel === a.id ? " active" : "";
        html += '<div class="card' + active + '" data-id="' + esc(a.id) + '" style="border-left-color:' + catColor(c) + '">' +
          '<div class="t"><span class="nm">' + esc(a.name || a.id) + '</span>' +
          '<span class="fid">' + esc(a.id) + "</span></div>" +
          '<div class="ds">' + esc(a.definition || "").slice(0, 80) + "</div></div>";
      });
      html += "</div>";
    });
    listEl.innerHTML = html;
    listEl.querySelectorAll(".card").forEach(function (card) {
      card.onclick = function () { state.sel = card.getAttribute("data-id"); renderList(); renderDetail(); };
    });
  }

  function renderDetail() {
    var a = state.data.find(function (x) { return x.id === state.sel; });
    var el = document.getElementById("detail");
    if (!a) { el.innerHTML = '<div class="empty">点击左侧动作查看详情</div>'; return; }
    var html = '<div class="detail">';
    html += "<h2>" + esc(a.name || a.id) + "</h2>";
    html += '<div style="margin:6px 0 4px"><span class="badge" style="background:' + catColor(a.category) +
      ';color:#04121f">' + esc(a.category || "未分类") + "</span> " +
      '<span class="chip">' + esc(a.idempotent ? "幂等" : "非幂等") + "</span>" +
      '<span class="chip">' + esc(a.id) + "</span></div>";
    if (a.definition) { html += '<div class="k">定义</div><p>' + esc(a.definition) + "</p>"; }
    if (a.conditions && a.conditions.length) {
      html += '<div class="k">条件 (conditions)</div><ul>';
      a.conditions.forEach(function (c) { html += "<li>" + esc(c) + "</li>"; });
      html += "</ul>";
    }
    if (a.effects) { html += '<div class="k">效果 (effects)</div><p>' + esc(a.effects) + "</p>"; }
    if (a.targets && a.targets.length) {
      html += '<div class="k">指向实体 (Action-targets-Entity)</div><div>';
      a.targets.forEach(function (t) { html += '<span class="chip" style="background:rgba(251,191,36,.15);color:#fcd34d;border-color:rgba(251,191,36,.4)">' + esc(t) + "</span>"; });
      html += "</div>";
    }
    if (a.invariants && a.invariants.length) {
      html += '<div class="k">不变量 (invariants)</div><ul>';
      a.invariants.forEach(function (i) { html += '<li style="color:var(--green)">' + esc(i) + "</li>"; });
      html += "</ul>";
    }
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
