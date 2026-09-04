/* 本体拓扑 · UModel Explorer
 * 数据：/api/ontos/spec (TBox) + /api/ontos/columns (物理字段)
 * 图谱：antv G6 v4.8.24（阿里官方 CDN）
 */
(function(){
  'use strict';
  const HEX = {
    cyan:'#4f8cff', cyan2:'#22d3ee', purple:'#a78bfa', green:'#34d399',
    orange:'#fbbf24', text:'#dbe4f5', text2:'#7d8db0',
    panel:'#131c2e', bg2:'#0e1726', border:'#24324d', red:'#f87171',
  };

  let SPEC=null, COLS=null, NODES=[], EDGES_=[], byId={};
  let selectedId=null, graph=null, minimapInst=null;
  let openGroup='entity';    // 手风琴：当前展开的组（entity|function|action|null）
  let viewMode='graph';      // 右侧：graph | empty（函数/动作收起图谱）

  function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;')
    .replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
  function labelOf(id){const n=byId[id];return n?n.label:id;}

  /* ── 加载 ───────────────────────────────────── */
  function load(){
    const ld=document.getElementById('loading');
    if(ld){ld.style.display='flex';ld.textContent='正在从 ontos 加载本体定义…';}
    Promise.all([
      fetch('/api/ontos/spec').then(r=>r.json().then(j=>({ok:r.ok,j}))).catch(e=>({ok:false,j:{message:String(e)}})),
      fetch('/api/ontos/columns').then(r=>r.json().then(j=>({ok:r.ok,j}))).catch(e=>({ok:false,j:null})),
    ]).then(([s,c])=>{
      if(!s.ok||!s.j||s.j.success===false){
        showError('本体定义加载失败',(s.j&&s.j.message)||'HTTP 错误',(s.j&&s.j.hint)||null);
        return;
      }
      SPEC=s.j; COLS=(c.ok&&c.j&&c.j.success)?c.j:null;
      build();
      renderSide(); renderPanel(); renderCount();
      if(ld) ld.style.display='none';
      document.getElementById('rev').textContent='ontos @ '+((SPEC.meta&&SPEC.meta.ontos_revision)||'unknown');
      setViewMode('graph');     // 默认显示图谱
      initGraph(); renderTable();
    });
  }

  function showError(title,msg,hint){
    const ld=document.getElementById('loading'); if(ld) ld.style.display='none';
    const d=document.createElement('div'); d.className='err';
    d.innerHTML='<div><b style="font-size:15px;color:var(--orange);">'+esc(title)+'</b><br><br>'+
      esc(msg||'')+(hint?'<br><br><span style="color:var(--text2);">提示：'+esc(hint)+'</span>':'')+'</div>';
    document.querySelector('.ucanvas').appendChild(d);
  }

  /* ── 构建图 ──────────────────────────────────── */
  function build(){
    NODES=[]; EDGES_=[]; byId={};
    (SPEC.entities||[]).forEach(e=>{
      const n={id:e.name,en:e.name,label:e.cn||e.name,
        kind:e.kind||'top',desc:e.desc||'',attrs:e.attributes||[]};
      NODES.push(n); byId[n.id]=n;
    });
    // 关系去重（避免逆关系重复显示同一对）
    const seen={};
    (SPEC.links||[]).forEach(l=>{
      const key=[l.subj,l.obj].sort().join('|');
      if(seen[key]) return;
      seen[key]=true;
      EDGES_.push({s:l.subj,t:l.obj,p:l.predicate,c:l.card,desc:l.desc||''});
    });
    // 补外部占位节点
    EDGES_.forEach(e=>{
      [e.s,e.t].forEach(id=>{
        if(!byId[id]){
          const n={id,en:id,label:id,kind:'external',desc:'范围外占位：被关系引用但不在当前实体集内。',attrs:[]};
          NODES.push(n); byId[id]=n;
        }
      });
    });
  }

  function renderCount(){
    document.getElementById('cnt-n').textContent=NODES.length;
    document.getElementById('cnt-l').textContent=EDGES_.length;
  }

  /* ── 侧栏：三组互斥手风琴（实体/函数/动作） ──────────── */
  function renderSide(){
    const side=document.getElementById('side');
    const top=NODES.filter(n=>n.kind==='top');
    const child=NODES.filter(n=>n.kind==='child');
    const ext=NODES.filter(n=>n.kind==='external');
    const fn=(SPEC.functions||[]), ac=(SPEC.actions||[]);
    const openE=openGroup==='entity';
    const openF=openGroup==='function';
    const openA=openGroup==='action';

    let html='';

    /* ─ 实体组 ─ */
    html+='<div class="sgrp acc'+(openE?' open':'')+'" data-grp="entity">'+
      '<h4 class="acc-h'+(openE?' open':'')+'">'+
        '<span class="ttl"><i class="grp-i entity"></i>实体</span>'+
        '<span class="tg">▶</span>'+
        '<span class="n">'+NODES.length+'</span>'+
      '</h4>';
    if(openE){
      html+='<div class="acc-b">'+
        '<ul>'+
          '<li data-filter-kind="top"><span class="dot top"></span>顶层实体<span class="ct">'+top.length+'</span></li>'+
          '<li data-filter-kind="child"><span class="dot child"></span>子实体<span class="ct">'+child.length+'</span></li>'+
          (ext.length?'<li data-filter-kind="external"><span class="dot ext"></span>外部占位<span class="ct">'+ext.length+'</span></li>':'')+
        '</ul>'+
        '<ul id="ent-list">';
      NODES.forEach(n=>{
        html+='<li data-id="'+esc(n.id)+'" data-kind="'+n.kind+'">'+
          '<span class="dot '+n.kind+'"></span>'+
          '<span class="lbl">'+esc(n.label)+'</span>'+
          '<span class="en">'+esc(n.en)+'</span></li>';
      });
      html+='</ul></div>';
    }
    html+='</div>';

    /* ─ 函数组 ─ */
    html+='<div class="sgrp acc'+(openF?' open':'')+'" data-grp="function">'+
      '<h4 class="acc-h'+(openF?' open':'')+'">'+
        '<span class="ttl"><i class="grp-i function"></i>函数目录</span>'+
        '<span class="tg">▶</span>'+
        '<span class="n">'+fn.length+'</span>'+
      '</h4>';
    if(openF){
      html+='<div class="acc-b">';
      const fby=groupByCat(fn);
      Object.keys(fby).sort().forEach(cat=>{
        html+='<div class="sub-grp" data-kind="function"><h5>'+esc(cat)+'<span class="n">'+fby[cat].length+'</span></h5><ul>';
        fby[cat].forEach(f=>{
          html+='<li data-kind="function" data-id="'+esc(f.id)+'"><span class="dot fn"></span>'+
            '<span class="lbl">'+esc(f.name||f.id)+'</span>'+
            '<span class="en">'+esc(f.id)+'</span></li>';
        });
        html+='</ul></div>';
      });
      html+='</div>';
    }
    html+='</div>';

    /* ─ 动作组 ─ */
    html+='<div class="sgrp acc'+(openA?' open':'')+'" data-grp="action">'+
      '<h4 class="acc-h'+(openA?' open':'')+'">'+
        '<span class="ttl"><i class="grp-i action"></i>动作目录</span>'+
        '<span class="tg">▶</span>'+
        '<span class="n">'+ac.length+'</span>'+
      '</h4>';
    if(openA){
      html+='<div class="acc-b">';
      const aby=groupByCat(ac);
      Object.keys(aby).sort().forEach(cat=>{
        html+='<div class="sub-grp" data-kind="action"><h5>'+esc(cat)+'<span class="n">'+aby[cat].length+'</span></h5><ul>';
        aby[cat].forEach(a=>{
          html+='<li data-kind="action" data-id="'+esc(a.id)+'"><span class="dot act"></span>'+
            '<span class="lbl">'+esc(a.name||a.id)+'</span>'+
            '<span class="en">'+esc(a.id)+'</span></li>';
        });
        html+='</ul></div>';
      });
      html+='</div>';
    }
    html+='</div>';

    side.innerHTML=html;
    bindSideEvents();
  }

  function groupByCat(arr){
    const by={};
    arr.forEach(x=>{const c=x.category||'未分类'; (by[c]=by[c]||[]).push(x);});
    return by;
  }
  function bindSideEvents(){
    const side=document.getElementById('side');
    // 手风琴标题：互斥展开（再次点击当前组可全部收起）
    side.querySelectorAll('.acc > .acc-h').forEach(h=>{
      h.addEventListener('click',()=>{
        const grp=h.parentElement.dataset.grp;
        openGroup = (openGroup===grp) ? null : grp;
        renderSide();
      });
    });
    // 实体条目
    side.querySelectorAll('#ent-list li').forEach(li=>{
      li.addEventListener('click',()=>select(li.dataset.id));
    });
    side.querySelectorAll('li[data-filter-kind]').forEach(li=>{
      li.addEventListener('click',()=>{
        const k=li.dataset.filterKind;
        document.querySelectorAll('#ent-list li').forEach(it=>{
          it.style.display=(k&&it.dataset.kind!==k)?'none':'';
        });
      });
    });
    // 函数/动作条目
    side.querySelectorAll('li[data-kind="function"], li[data-kind="action"]').forEach(li=>{
      li.addEventListener('click',()=>selectItem(li.dataset.kind, li.dataset.id));
    });
    // 空状态返回按钮
    const back=document.getElementById('empty-back');
    if(back) back.addEventListener('click',()=>backToEntity());
  }
  function backToEntity(){
    // 返回实体拓扑：展开实体组、选中第一个顶层实体、清选状态切图谱
    openGroup='entity';
    renderSide();
    const first=document.querySelector('#ent-list li[data-kind="top"]') ||
                 document.querySelector('#ent-list li');
    if(first) select(first.dataset.id);
    else { clearSelection(); setViewMode('graph'); }
  }
  function clearSideActive(){
    document.querySelectorAll('#side li').forEach(li=>li.classList.remove('active'));
  }

  /* ── 中间面板 · 默认概览 ──────────────────────── */
  function renderPanel(){
    const d=document.getElementById('detail');
    const ne=NODES.length, nl=EDGES_.length;
    const nf=(SPEC.functions||[]).length, na=(SPEC.actions||[]).length;
    const nv=(SPEC.invariants||[]).length;

    let html='<div class="ov-cards">'+
      '<div class="ov-card"><div class="lbl">实体</div><div class="val">'+ne+'</div></div>'+
      '<div class="ov-card"><div class="lbl">关系</div><div class="val g">'+nl+'</div></div>'+
      '<div class="ov-card"><div class="lbl">函数</div><div class="val p">'+nf+'</div></div>'+
      '<div class="ov-card"><div class="lbl">动作</div><div class="val o">'+na+'</div></div>'+
      '</div>';

    html+='<div class="ov-section"><h4>函数 <span class="n">'+nf+'</span></h4>';
    (SPEC.functions||[]).forEach(f=>{
      const io='('+(f.inputs||[]).join(', ')+' → '+(f.outputs||[]).join(', ')+')';
      html+='<div class="it" data-jump="'+esc(f.id)+'" style="cursor:pointer"><b style="color:var(--cyan2);">'+esc(f.name)+'</b>'+
        '<span class="id">'+esc(f.id)+'</span>'+
        '<div class="desc">'+esc(f.description||'')+'</div>'+
        '<div class="meta">'+esc(io)+'</div></div>';
    });
    html+='</div>';

    html+='<div class="ov-section"><h4>动作 <span class="n">'+na+'</span></h4>';
    (SPEC.actions||[]).forEach(a=>{
      html+='<div class="it" data-jump="'+esc(a.id)+'" style="cursor:pointer"><b style="color:var(--purple);">'+esc(a.name||a.id)+'</b>'+
        '<span class="id">'+esc(a.id)+'</span>'+
        '<div class="desc">'+esc(a.definition||'')+'</div></div>';
    });
    html+='</div>';

    if((SPEC.invariants||[]).length){
      html+='<div class="ov-section"><h4>不变量 <span class="n">'+nv+'</span></h4>';
      (SPEC.invariants||[]).forEach(v=>{
        const id=v.id||v.name||'', desc=v.desc||v.description||'';
        html+='<div class="it"><b style="color:var(--orange);">'+esc(id)+'</b>'+
          '<div class="desc">'+esc(desc)+'</div></div>';
      });
      html+='</div>';
    }

    if(COLS){
      html+='<div class="ov-section"><h4>物理字段源</h4>';
      Object.keys(COLS.datasets).forEach(k=>{
        const ds=COLS.datasets[k];
        html+='<div class="it"><b style="color:var(--cyan2);">'+esc(k)+'</b>'+
          '<div class="desc">'+esc(ds.file||'')+' · '+ds.column_count+' 列 / '+ds.rows+' 行 · '+esc(ds.uploaded_at||'')+'</div></div>';
      });
      html+='</div>';
    }

    html+='<div class="unote">点击左侧<b>实体 / 函数目录 / 动作目录</b>，查看其<b>语义属性 / 关系 / 产出归属 / 指向关系</b>，以及物理字段映射。' +
      '<br><span style="color:var(--text2);">函数→产出实体、动作→指向实体的关联均由 ontos TBox <b>结构化字段</b>（produces_for / targets）权威给出，非启发式匹配。</span></div>';
    d.innerHTML=html; bindDetailJumps(d);
  }

  /* ── 中间面板 · 实体详情 ──────────────────────── */
  function renderDetail(n){
    const d=document.getElementById('detail');
    const ktag='<span class="pn-tag '+n.kind+'">'+(n.kind==='top'?'顶层实体':n.kind==='child'?'子实体':'外部占位')+'</span>';
    let html='<div class="pn-head">'+ktag+'<h2>'+esc(n.label)+'</h2>' +
      '<div class="en">'+esc(n.en)+'</div>' +
      '<div class="desc">'+esc(n.desc||'(无说明)')+'</div></div>';

    // 关系
    const out=EDGES_.filter(e=>e.s===n.id);
    const inn=EDGES_.filter(e=>e.t===n.id&&e.s!==n.id);
    html+='<div class="pn-sec"><h4>关系 <span class="ln"></span><span class="ct">'+(out.length+inn.length)+'</span></h4><div class="rel-list">';
    out.forEach(e=>{
      html+='<div class="r"><span class="arrow">→</span><span class="p">'+esc(e.p)+'</span>'+
        '<span class="lab">'+esc(labelOf(e.t))+' <span class="en">'+esc(e.t)+'</span></span>'+
        '<span class="card">'+esc(e.c)+'</span></div>';
    });
    inn.forEach(e=>{
      html+='<div class="r"><span class="arrow">←</span><span class="p">'+esc(e.p)+'</span>'+
        '<span class="lab">'+esc(labelOf(e.s))+' <span class="en">'+esc(e.s)+'</span></span>'+
        '<span class="card">'+esc(e.c)+'</span></div>';
    });
    if(!out.length&&!inn.length) html+='<div class="u-empty">（无关系）</div>';
    html+='</div></div>';

    // 语义属性
    html+='<div class="pn-sec"><h4>语义属性 <span class="ln"></span><span class="ct">'+n.attrs.length+'</span></h4>';
    if(n.attrs.length){
      html+='<table class="fields-tbl"><thead><tr><th style="width:32%;">属性</th><th>类型 / 源 / 说明</th></tr></thead><tbody>';
      n.attrs.forEach(a=>{
        html+='<tr><td>'+esc(a.name)+(a.required?' <span class="req">*</span>':'')+
          (a.unique?' <span style="color:var(--cyan2);font-size:9px;background:rgba(34,211,238,.15);padding:1px 4px;border-radius:3px;margin-left:3px;">U</span>':'')+'</td><td>'+
          '<span class="ty">'+esc(a.type)+'</span>' +
          (a.source?'<span class="src">'+esc(a.source)+'</span>':'')+
          (a.desc?'<div style="color:var(--text2);font-size:11px;margin-top:3px;line-height:1.5;">'+esc(a.desc)+'</div>':'')+
          '</td></tr>';
      });
      html+='</tbody></table>';
    } else {
      html+='<div class="u-empty">（无属性定义）</div>';
    }
    html+='</div>';

    // 相关函数（结构化：produces_for 指向本实体）
    const relFn=(SPEC.functions||[]).filter(f=>(f.produces_for||[]).indexOf(n.id)>=0);
    html+='<div class="pn-sec"><h4>产出属性归属本实体的函数 <span class="ln"></span><span class="ct">'+relFn.length+'</span><span class="hz">结构化</span></h4>';
    if(relFn.length){
      relFn.forEach(f=>{
        const io='('+(f.inputs||[]).join(', ')+' → '+(f.outputs||[]).join(', ')+')';
        html+='<div class="fn-item" data-jump="'+esc(f.id)+'"><span class="nm">'+esc(f.name)+'</span><span class="id">'+esc(f.id)+'</span>' +
          '<div class="desc">'+esc(f.description||'')+'</div>' +
          '<div class="io">'+esc(io)+'</div></div>';
      });
    } else {
      html+='<div class="u-empty">（暂无函数以本实体为产出归属）</div>';
    }
    html+='</div>';

    // 相关动作（结构化：targets 指向本实体）
    const relAct=(SPEC.actions||[]).filter(a=>(a.targets||[]).indexOf(n.id)>=0);
    html+='<div class="pn-sec"><h4>指向本实体的动作 <span class="ln"></span><span class="ct">'+relAct.length+'</span><span class="hz act">结构化</span></h4>';
    if(relAct.length){
      relAct.forEach(a=>{
        html+='<div class="act-item" data-jump="'+esc(a.id)+'"><span class="nm">'+esc(a.name||a.id)+'</span><span class="id">'+esc(a.id)+'</span>' +
          '<div class="desc">'+esc(a.definition||'')+'</div></div>';
      });
    } else {
      html+='<div class="u-empty">（暂无动作指向本实体）</div>';
    }
    html+='</div>';

    // 物理字段
    html+=renderPhysical(n);

    d.innerHTML=html; d.scrollTop=0;
    bindDetailJumps(d);
  }

  /* ── 右侧视图模式：graph（拓扑） | empty（函数/动作占位） ── */
  function setViewMode(mode, ctx){
    viewMode=mode;
    const g6=document.getElementById('g6');
    const g6t=document.getElementById('g6-table');
    const mm=document.querySelector('.g6-minimap-container');
    const ep=document.getElementById('empty-pane');
    const gt=document.getElementById('g-tools');
    if(mode==='graph'){
      if(g6) g6.style.display='';
      if(g6t) g6t.style.display='';
      if(mm) mm.style.display='';
      if(gt) gt.style.display='';
      if(ep) ep.classList.add('hide');
      // 重新触发 fitView（G6 容器从隐藏切回显示后尺寸需要刷新）
      setTimeout(()=>{
        if(graph){
          const r=document.getElementById('g6').parentElement.getBoundingClientRect();
          graph.changeSize(Math.max(r.width,400), Math.max(r.height,400));
          graph.fitView(20);
        }
      }, 30);
    } else {
      if(g6) g6.style.display='none';
      if(g6t) g6t.style.display='none';
      if(mm) mm.style.display='none';
      if(gt) gt.style.display='none';
      if(ep) ep.classList.remove('hide');
      // 写入占位文案
      const kind=(ctx&&ctx.kind)==='action'?'action':'function';
      const name=(ctx&&ctx.name)||'—';
      const tagEl=document.getElementById('empty-tag');
      const nameEl=document.getElementById('empty-name');
      const kindEl=document.getElementById('empty-kind');
      if(tagEl){tagEl.textContent=kind==='action'?'动作':'函数'; tagEl.className='tag '+(kind==='action'?'act':'fn');}
      if(nameEl) nameEl.textContent=name;
      if(kindEl) kindEl.textContent=kind==='action'?'动作目录':'函数目录';
    }
  }

  /* ── 函数/动作详情（侧栏分组点击） ──────────────── */
  function selectItem(kind,id){
    selectedId=null;
    clearSideActive();
    const li=document.querySelector('#side li[data-kind="'+kind+'"][data-id="'+id+'"]');
    if(li) li.classList.add('active');
    if(kind==='function'){
      const f=(SPEC.functions||[]).find(x=>x.id===id);
      if(f){
        renderItemDetail('function',f);
        setViewMode('empty',{kind:'function',name:f.name||f.id});
        // 图谱仍保留可联动（高亮 produces_for 实体），但整体由 empty 占位主导
        if(graph) highlightNodes(f.produces_for||[]);
      }
    } else {
      const a=(SPEC.actions||[]).find(x=>x.id===id);
      if(a){
        renderItemDetail('action',a);
        setViewMode('empty',{kind:'action',name:a.name||a.id});
        if(graph) highlightNodes(a.targets||[]);
      }
    }
  }

  function renderItemDetail(kind,item){
    const d=document.getElementById('detail');
    const isFn=kind==='function';
    const tagBg=isFn?'rgba(52,211,153,.14)':'rgba(251,191,36,.14)';
    const tagBd=isFn?'#34d399':'#fbbf24';
    const tagTx=isFn?'#34d399':'#fbbf24';
    const name=item.name||item.id;
    const cat=item.category||'未分类';
    let html='<div class="pn-head">'+
      '<span class="pn-tag" style="background:'+tagBg+';color:'+tagTx+';border:1px solid '+tagBd+'">'+(isFn?'函数':'动作')+'</span>'+
      '<span class="pn-tag" style="background:rgba(125,141,176,.12);color:var(--text2);border:1px solid var(--border)">'+esc(cat)+'</span>'+
      '<h2>'+esc(name)+'</h2>'+
      '<div class="en">'+esc(item.id)+'</div>'+
      (item.description||item.definition?'<div class="desc">'+esc(item.description||item.definition||'')+'</div>':'')+
      '</div>';

    if(isFn){
      const io='('+(item.inputs||[]).join(', ')+' → '+(item.outputs||[]).join(', ')+')';
      html+='<div class="pn-sec"><h4>输入输出 <span class="ln"></span></h4><div class="meta-line">'+esc(io)+'</div></div>';
      const pf=item.produces_for||[];
      html+='<div class="pn-sec"><h4>产出属性归属实体 <span class="ln"></span><span class="ct">'+pf.length+'</span><span class="hz">结构化</span></h4>';
      html+= pf.length
        ? '<div class="rel-entities">'+pf.map(e=>'<span class="ent-chip" data-jump="'+esc(e)+'">'+esc(e)+'</span>').join('')+'</div>'
        : '<div class="u-empty">（无归属实体）</div>';
      html+='</div>';
    } else {
      const con=(item.conditions||[]).join('；');
      const inv=Array.isArray(item.invariants)?item.invariants.join('；'):(item.invariants||'');
      html+='<div class="pn-sec"><h4>条件 <span class="ln"></span></h4><div class="desc-block">'+esc(con||'(无)')+'</div></div>';
      html+='<div class="pn-sec"><h4>效果 <span class="ln"></span></h4><div class="desc-block">'+esc(item.effects||'(无)')+'</div></div>';
      if(inv) html+='<div class="pn-sec"><h4>不变量 <span class="ln"></span></h4><div class="desc-block">'+esc(inv)+'</div></div>';
      html+='<div class="pn-sec"><h4>幂等 <span class="ln"></span></h4><div class="desc-block">'+esc(item.idempotent===false?'否':'是')+'</div></div>';
      const tg=item.targets||[];
      html+='<div class="pn-sec"><h4>指向实体 (targets) <span class="ln"></span><span class="ct">'+tg.length+'</span><span class="hz act">结构化</span></h4>';
      html+= tg.length
        ? '<div class="rel-entities">'+tg.map(e=>'<span class="ent-chip" data-jump="'+esc(e)+'">'+esc(e)+'</span>').join('')+'</div>'
        : '<div class="u-empty">（无指向实体）</div>';
      html+='</div>';
    }

    d.innerHTML=html; d.scrollTop=0;
    bindDetailJumps(d);
  }

  function bindDetailJumps(d){
    d.querySelectorAll('[data-jump]').forEach(el=>{
      el.addEventListener('click',()=>{
        const id=el.dataset.jump;
        if(el.classList.contains('ent-chip')){ if(byId[id]) select(id); }
        else { const k=el.classList.contains('fn-item')?'function':'action'; selectItem(k,id); }
      });
    });
  }

  /* ── 图谱：高亮一组实体（函数/动作相关实体） ── */
  function highlightNodes(ids){
    if(!graph) return;
    const set=new Set((ids||[]).filter(x=>byId[x]));
    if(!set.size){
      graph.getNodes().forEach(n=>{
        const m=n.getModel(), k=m.kind;
        const stroke=k==='child'?HEX.purple:(k==='external'?HEX.text2:HEX.cyan);
        n.update({style:{stroke,lineWidth:1.5,opacity:1,shadowColor:'rgba(79,140,255,.3)',shadowBlur:8}});
      });
      graph.getEdges().forEach(e=>e.update({style:{opacity:.55}}));
      return;
    }
    graph.getNodes().forEach(n=>{
      const m=n.getModel();
      const hit=set.has(m.id);
      const k=m.kind;
      const stroke=k==='child'?HEX.purple:(k==='external'?HEX.text2:HEX.cyan);
      n.update({style:{
        stroke:hit?HEX.orange:stroke, lineWidth:hit?2.5:1.5,
        opacity:hit?1:.25,
        shadowColor:hit?'rgba(251,191,36,.6)':'rgba(79,140,255,.3)',
        shadowBlur:hit?14:8,
      }});
    });
    graph.getEdges().forEach(e=>{
      const m=e.getModel();
      const hit=set.has(m.source)&&set.has(m.target);
      e.update({style:{opacity:hit?.85:.1}});
    });
  }

  function renderPhysical(n){
    if(!COLS) return '';
    const dsName=COLS.entity_dataset&&COLS.entity_dataset[n.id];
    if(!dsName) return '';
    const ds=COLS.datasets&&COLS.datasets[dsName];
    if(!ds) return '';
    const bound=new Set();
    (n.attrs||[]).forEach(a=>{if(a.source){const last=String(a.source).split('.').pop();if(last)bound.add(last);}});
    let hit=0;
    let html='<div class="pn-sec"><h4>物理字段映射 <span class="ln"></span></h4>' +
      '<div style="font-size:11px;color:var(--text2);margin-bottom:6px;line-height:1.6;">' +
      '来源 <b style="color:var(--cyan2);">'+esc(dsName)+'</b> · '+ds.rows+' 行 / '+ds.column_count+' 列' +
      ' · <span style="color:var(--green);">绿色</span>=已被本体属性引用</div>';
    (ds.groups||[]).forEach(g=>{
      html+='<div class="ugrp"><span>'+esc(g.name)+'</span><span class="n">'+g.columns.length+'</span></div>';
      (g.columns||[]).forEach(c=>{
        const f=ds.field_map&&ds.field_map[c];
        const isBound=!!(f&&bound.has(f));
        if(isBound) hit++;
        html+='<span class="col-chip'+(isBound?' bound':'')+'"'+
          (f?' title="'+esc(c)+' → '+esc(f)+'"':'')+'>'+esc(c)+'</span>';
      });
    });
    html+='<div class="unote">语义属性 <b style="color:var(--orange);">'+n.attrs.length+'</b> · 物理列 <b style="color:var(--orange);">'+ds.column_count+'</b> · 已映射 <b style="color:var(--green);">'+hit+'</b></div>';
    return html+'</div>';
  }

  /* ── G6 图谱 ─────────────────────────────────── */
  function initGraph(){
    const canvas=document.getElementById('g6');
    const rect=canvas.parentElement.getBoundingClientRect();
    const W=Math.max(rect.width,400), H=Math.max(rect.height,400);

    const nodes=NODES.map(n=>({id:n.id,label:n.label,en:n.en,kind:n.kind,attrs:n.attrs.length}));
    const edges=EDGES_.map((e,i)=>({id:'e'+i,source:e.s,target:e.t,label:e.p+' · '+e.c}));

    if(graph){try{graph.destroy();}catch(e){} graph=null;}
    if(minimapInst){try{minimapInst.destroy();}catch(e){} minimapInst=null;}

    try {
      graph=new G6.Graph({
        container:'g6', width:W, height:H, fitView:true, animate:true,
        modes:{default:['drag-canvas','zoom-canvas','drag-node']},
        layout:{type:'force',preventOverlap:true,nodeStrength:-50,
          edgeStrength:0.05,linkDistance:200,alpha:0.3,animate:true},
        defaultNode:{type:'rect',size:[150,44],
          style:{fill:HEX.panel,stroke:HEX.cyan,lineWidth:1.5,radius:6,
            shadowColor:'rgba(79,140,255,.3)',shadowBlur:8},
          labelCfg:{style:{fill:HEX.text,fontSize:12,fontWeight:600,cursor:'pointer'}}},
        defaultEdge:{type:'line',
          style:{stroke:HEX.cyan,lineWidth:1.1,opacity:.55,
            endArrow:{fill:HEX.cyan,path:G6.Arrow.triangle(6,8,2)},
            cursor:'pointer'},
          labelCfg:{autoRotate:true,
            style:{fill:HEX.text2,fontSize:9,fontWeight:500,
              background:{fill:HEX.bg2,padding:[2,4,2,4],radius:3}}}},
      });

      graph.node(node=>{
        const k=node.kind;
        const stroke=k==='child'?HEX.purple:(k==='external'?HEX.text2:HEX.cyan);
        const lineDash=k==='external'?[4,3]:undefined;
        const shadow=k==='child'?'rgba(167,139,250,.3)':k==='external'?'transparent':'rgba(79,140,255,.3)';
        return {
          style:{stroke,lineWidth:1.5,lineDash,shadowColor:shadow,shadowBlur:8},
          labelCfg:{style:{fill:HEX.text,fontSize:12,fontWeight:600}},
        };
      });

      graph.data({nodes,edges});
      graph.render();

      // 小地图
      try{
        minimapInst=new G6.Minimap({size:[180,120]});
        graph.addPlugin(minimapInst);
      }catch(e){/* 忽略小地图错误 */}

      graph.on('node:click',e=>select(e.item.getModel().id));
      graph.on('canvas:click',()=>{if(selectedId) clearSelection();});
      graph.on('node:mouseenter',e=>{const el=e.item.getKeyShape(); if(el) el.attr('shadowBlur',14);});
      graph.on('node:mouseleave',e=>{const el=e.item.getKeyShape(); if(el) el.attr('shadowBlur',8);});

      if(selectedId) highlightNode(selectedId);
    } catch(err){
      console.error('G6 init failed', err);
      showError('G6 图谱初始化失败', String(err&&err.message||err));
    }
  }

  function select(id){
    const n=byId[id]; if(!n) return;
    selectedId=id;
    clearSideActive();
    const li=document.querySelector('#ent-list li[data-id="'+id+'"]');
    if(li) li.classList.add('active');
    setViewMode('graph');      // 选实体 → 切回拓扑视图
    renderDetail(n);
    highlightNode(id);
  }
  function clearSelection(){
    selectedId=null;
    clearSideActive();
    renderPanel();
    setViewMode('graph');      // 清选 → 切回拓扑概览
    if(graph){
      graph.getNodes().forEach(n=>{
        const m=n.getModel();
        const k=m.kind;
        const stroke=k==='child'?HEX.purple:(k==='external'?HEX.text2:HEX.cyan);
        const lineDash=k==='external'?[4,3]:null;
        n.update({style:{stroke,lineWidth:1.5,lineDash,opacity:1}});
      });
      graph.getEdges().forEach(e=>e.update({style:{opacity:.55}}));
    }
  }
  function highlightNode(id){
    if(!graph) return;
    const nb=new Set([id]);
    EDGES_.forEach(e=>{if(e.s===id) nb.add(e.t); if(e.t===id) nb.add(e.s);});
    graph.getNodes().forEach(n=>{
      const m=n.getModel();
      const hit=nb.has(m.id);
      const k=m.kind;
      const stroke=k==='child'?HEX.purple:(k==='external'?HEX.text2:HEX.cyan);
      n.update({style:{
        stroke:hit?HEX.orange:stroke,
        lineWidth:hit?2.5:1.5,
        opacity:hit?1:.3,
        shadowColor:hit?'rgba(251,191,36,.6)':'rgba(79,140,255,.3)',
        shadowBlur:hit?14:8,
      }});
    });
    graph.getEdges().forEach(e=>{
      const m=e.getModel();
      const hit=m.source===id||m.target===id;
      e.update({style:{opacity:hit?.85:.12}});
    });
  }

  /* ── Table 视图 ───────────────────────────────── */
  function renderTable(){
    const tb=document.getElementById('tbl-body');
    if(!tb) return;
    tb.innerHTML='';
    EDGES_.forEach(e=>{
      tb.innerHTML+='<tr>'+
        '<td style="color:var(--cyan2);font-family:var(--mono);font-weight:600;">'+esc(e.p)+'</td>'+
        '<td><b>'+esc(labelOf(e.s))+'</b> <span style="color:var(--text2);font-family:var(--mono);font-size:10px;">'+esc(e.s)+'</span>' +
        ' <span style="color:var(--cyan);">→</span> ' +
        '<b>'+esc(labelOf(e.t))+'</b> <span style="color:var(--text2);font-family:var(--mono);font-size:10px;">'+esc(e.t)+'</span></td>'+
        '<td style="color:var(--purple);font-family:var(--mono);">'+esc(e.c)+'</td>'+
        '<td style="color:var(--text2);">'+esc(e.desc||'')+'</td></tr>';
    });
  }

  /* ── 事件 ────────────────────────────────────── */
  function init(){
    document.querySelectorAll('#view-seg button').forEach(btn=>{
      btn.addEventListener('click',()=>{
        document.querySelectorAll('#view-seg button').forEach(b=>b.classList.remove('active'));
        btn.classList.add('active');
        const v=btn.dataset.view;
        document.getElementById('g6').style.display=v==='graph'?'block':'none';
        document.getElementById('g6-table').style.display=v==='graph'?'none':'block';
        document.getElementById('g-tools').style.display=v==='graph'?'flex':'none';
        const mm=document.querySelector('.g6-minimap-container, .g-minimap');
        if(mm) mm.style.display=v==='graph'?'block':'none';
        if(v==='graph'&&graph) setTimeout(()=>graph.fitView(40),100);
      });
    });
    document.querySelectorAll('#g-tools button').forEach(btn=>{
      btn.addEventListener('click',()=>{
        if(!graph) return;
        const act=btn.dataset.act;
        if(act==='zoom-in') graph.zoom(graph.getZoom()*1.2);
        else if(act==='zoom-out') graph.zoom(graph.getZoom()/1.2);
        else if(act==='fit') graph.fitView(40);
        else if(act==='reset'){clearSelection();initGraph();}
      });
    });
    document.getElementById('q').addEventListener('input',e=>{
      const q=e.target.value.trim().toLowerCase();
      const allLi=document.querySelectorAll('#side li');
      if(!q){
        allLi.forEach(li=>li.style.display='');
        if(graph){
          graph.getNodes().forEach(n=>n.update({style:{opacity:1}}));
          graph.getEdges().forEach(e=>e.update({style:{opacity:.55}}));
        }
        return;
      }
      const hit=new Set();
      let needOpen=null;
      allLi.forEach(li=>{
        if(li.classList.contains('sub-h')){ li.style.display=''; return; }
        const kind=li.dataset.kind, id=li.dataset.id;
        let m=false;
        if(kind==='function'){
          const f=(SPEC.functions||[]).find(x=>x.id===id);
          m = f ? ((f.name||f.id).toLowerCase().indexOf(q)>=0 || id.toLowerCase().indexOf(q)>=0 ||
                   (f.category||'').toLowerCase().indexOf(q)>=0 || (f.description||'').toLowerCase().indexOf(q)>=0) : false;
          if(m) needOpen='function';
        } else if(kind==='action'){
          const a=(SPEC.actions||[]).find(x=>x.id===id);
          m = a ? ((a.name||a.id).toLowerCase().indexOf(q)>=0 || id.toLowerCase().indexOf(q)>=0 ||
                   (a.category||'').toLowerCase().indexOf(q)>=0 || (a.definition||'').toLowerCase().indexOf(q)>=0) : false;
          if(m) needOpen='action';
        } else {
          const n=byId[id];
          m = n ? (n.label.toLowerCase().indexOf(q)>=0 || n.en.toLowerCase().indexOf(q)>=0 ||
                   (n.attrs||[]).some(a=>String(a.name).toLowerCase().indexOf(q)>=0 || String(a.desc||'').toLowerCase().indexOf(q)>=0)) : false;
          if(m) needOpen='entity';
        }
        li.style.display=m?'':'none';
        if(m && kind!=='function' && kind!=='action') hit.add(id);
      });
      EDGES_.forEach(e=>{
        if(e.p.toLowerCase().indexOf(q)>=0){hit.add(e.s); hit.add(e.t);}
      });
      // 命中后自动展开对应手风琴组（互斥）
      if(needOpen && openGroup!==needOpen){
        openGroup=needOpen;
        renderSide();
        document.querySelectorAll('#side li').forEach(li=>{
          if(li.classList.contains('sub-h')){ li.style.display=''; return; }
          const kind=li.dataset.kind, id=li.dataset.id;
          let m=false;
          if(kind==='function'){
            const f=(SPEC.functions||[]).find(x=>x.id===id);
            m = f ? ((f.name||f.id).toLowerCase().indexOf(q)>=0 || id.toLowerCase().indexOf(q)>=0) : false;
          } else if(kind==='action'){
            const a=(SPEC.actions||[]).find(x=>x.id===id);
            m = a ? ((a.name||a.id).toLowerCase().indexOf(q)>=0 || id.toLowerCase().indexOf(q)>=0) : false;
          } else {
            const n=byId[id];
            m = n ? (n.label.toLowerCase().indexOf(q)>=0 || n.en.toLowerCase().indexOf(q)>=0) : false;
          }
          li.style.display=m?'':'none';
        });
      }
      if(graph){
        graph.getNodes().forEach(n=>{
          const m=n.getModel();
          n.update({style:{opacity:hit.has(m.id)?1:.15}});
        });
        graph.getEdges().forEach(e=>{
          const m=e.getModel();
          const ok=hit.has(m.source)&&hit.has(m.target);
          e.update({style:{opacity:ok?.85:.1}});
        });
      }
    });
    document.getElementById('reset').addEventListener('click',()=>{
      document.getElementById('q').value='';
      clearSelection(); initGraph();
    });
    document.getElementById('reload').addEventListener('click',()=>location.reload());

    let rzTimer;
    window.addEventListener('resize',()=>{
      clearTimeout(rzTimer);
      rzTimer=setTimeout(()=>{
        if(graph){
          const rect=document.getElementById('g6').parentElement.getBoundingClientRect();
          graph.changeSize(rect.width,rect.height);
          graph.fitView(40);
        }
      },150);
    });

    load();
  }

  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',init);
  else init();
})();