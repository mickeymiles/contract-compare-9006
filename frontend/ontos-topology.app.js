/* 本体浏览器 · UModel Explorer
 * 数据：/api/ontos/spec (TBox + 覆盖层) + /api/ontos/columns (物理字段)
 * 交互：实体 / 函数 / 动作 = 三级下钻（分类+数量 → 中间列表 → 右侧可编辑定义）
 *       拓扑 = 独立菜单，触发右侧全屏 G6 图谱（不再固定/复用）
 */
(function(){
  'use strict';
  const HEX = {
    cyan:'#4f8cff', cyan2:'#22d3ee', purple:'#a78bfa', green:'#34d399',
    orange:'#fbbf24', text:'#dbe4f5', text2:'#7d8db0',
    panel:'#131c2e', bg2:'#0e1726', border:'#24324d', red:'#f87171',
  };

  let SPEC=null, COLS=null, NODES=[], EDGES_=[], byId={};
  let graph=null, minimapInst=null;
  let entityIds=[];

  // 导航状态
  let activeGroup=null;     // 'entity' | 'function' | 'action' | 'topology'
  let activeCat=null;       // 当前选中的分类（drill）
  let selected=null;        // {kind, id} 当前详情项
  let mode='drill';         // 'drill' | 'topology'
  let chipState=null;       // Set，当前 chips 选中值
  let currentFields=null, currentItem=null;
  let searching=false;

  function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;')
    .replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
  function labelOf(id){const n=byId[id];return n?n.label:id;}

  /* ── 可编辑字段定义 ───────────────────────────── */
  const EDIT_FIELDS = {
    entity: [
      {key:'cn', label:'中文名', type:'text'},
      {key:'desc', label:'描述', type:'textarea'},
      {key:'attributes', label:'语义属性（JSON 数组）', type:'json',
        hint:'每项形如 {"name":"","type":"","source":"","desc":"","required":false,"unique":false}'},
    ],
    function: [
      {key:'name', label:'名称', type:'text'},
      {key:'category', label:'分类', type:'text'},
      {key:'description', label:'描述', type:'textarea'},
      {key:'inputs', label:'输入（每行一个）', type:'list'},
      {key:'outputs', label:'输出（每行一个）', type:'list'},
      {key:'produces_for', label:'产出归属实体', type:'chips', options:'entities'},
    ],
    action: [
      {key:'name', label:'名称', type:'text'},
      {key:'category', label:'分类', type:'text'},
      {key:'definition', label:'定义', type:'textarea'},
      {key:'conditions', label:'条件（每行一个）', type:'list'},
      {key:'effects', label:'效果（每行一个）', type:'list'},
      {key:'invariants', label:'不变量（每行一个）', type:'list'},
      {key:'idempotent', label:'幂等', type:'bool'},
      {key:'targets', label:'指向实体', type:'chips', options:'entities'},
    ],
  };

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
      renderCount();
      if(ld) ld.style.display='none';
      document.getElementById('rev').textContent='ontos @ '+((SPEC.meta&&SPEC.meta.ontos_revision)||'unknown');
      // 默认进入实体下钻
      openGroup('entity');
    });
  }

  function showError(title,msg,hint){
    const ld=document.getElementById('loading'); if(ld) ld.style.display='none';
    const d=document.createElement('div'); d.className='err';
    d.innerHTML='<div><b style="font-size:15px;color:var(--orange);">'+esc(title)+'</b><br><br>'+
      esc(msg||'')+(hint?'<br><br><span style="color:var(--text2);">提示：'+esc(hint)+'</span>':'')+'</div>';
    document.querySelector('.ucanvas').appendChild(d);
  }

  /* ── 构建图数据 ──────────────────────────────── */
  function build(){
    NODES=[]; EDGES_=[]; byId={};
    (SPEC.entities||[]).forEach(e=>{
      const n={id:e.id||e.name, en:e.name, label:e.cn||e.name,
        kind:e.kind||'top', desc:e.desc||'', attrs:e.attributes||[]};
      NODES.push(n); byId[n.id]=n;
    });
    const seen={};
    (SPEC.links||[]).forEach(l=>{
      const key=[l.subj,l.obj].sort().join('|');
      if(seen[key]) return; seen[key]=true;
      EDGES_.push({s:l.subj,t:l.obj,p:l.predicate,c:l.card,desc:l.desc||''});
    });
    EDGES_.forEach(e=>{
      [e.s,e.t].forEach(id=>{
        if(!byId[id]){
          const n={id,en:id,label:id,kind:'external',desc:'范围外占位：被关系引用但不在当前实体集内。',attrs:[]};
          NODES.push(n); byId[id]=n;
        }
      });
    });
    entityIds=NODES.filter(n=>n.kind!=='external').map(n=>n.id);
  }

  function renderCount(){
    document.getElementById('cnt-n').textContent=NODES.length;
    document.getElementById('cnt-l').textContent=EDGES_.length;
  }

  /* ── 分类 / 条目 ─────────────────────────────── */
  function groupByCat(arr){
    const by={};
    arr.forEach(x=>{const c=x.category||'未分类'; (by[c]=by[c]||[]).push(x);});
    return by;
  }
  // 某组的分类列表 [{cat,count}]
  function categoriesOf(group){
    if(group==='entity'){
      const order=[['top','顶层实体'],['child','子实体'],['external','外部占位']];
      return order.filter(([k])=>NODES.some(n=>n.kind===k))
        .map(([k,label])=>({cat:k,label,count:NODES.filter(n=>n.kind===k).length}));
    }
    if(group==='function'){
      const by=groupByCat(SPEC.functions||[]);
      return Object.keys(by).sort().map(c=>({cat:c,label:c,count:by[c].length}));
    }
    if(group==='action'){
      const by=groupByCat(SPEC.actions||[]);
      return Object.keys(by).sort().map(c=>({cat:c,label:c,count:by[c].length}));
    }
    return [];
  }
  // 某组某分类下的条目
  function itemsOf(group,cat){
    if(group==='entity') return NODES.filter(n=>n.kind===cat);
    if(group==='function') return (SPEC.functions||[]).filter(f=>(f.category||'未分类')===cat);
    if(group==='action') return (SPEC.actions||[]).filter(a=>(a.category||'未分类')===cat);
    return [];
  }
  function allItemsOf(group){
    if(group==='entity') return NODES;
    if(group==='function') return SPEC.functions||[];
    if(group==='action') return SPEC.actions||[];
    return [];
  }
  function itemId(it){ return it.id||it.name; }
  function findItem(kind,id){
    const arr= kind==='entity'?NODES:(kind==='function'?SPEC.functions||[]:SPEC.actions||[]);
    return arr.find(x=>(x.id||x.name)===id)||null;
  }

  /* ── 侧栏：四组互斥手风琴 ────────────────────── */
  function renderSide(){
    const side=document.getElementById('side');
    const groups=[
      {g:'entity', label:'实体', cls:'entity', n:(SPEC.entities||[]).length},
      {g:'function', label:'函数', cls:'function', n:(SPEC.functions||[]).length},
      {g:'action', label:'动作', cls:'action', n:(SPEC.actions||[]).length},
      {g:'topology', label:'拓扑', cls:'topo', n:NODES.length},
    ];
    let html='';
    groups.forEach(G=>{
      const open=activeGroup===G.g;
      html+='<div class="sgrp acc'+(open?' open':'')+'" data-grp="'+G.g+'">'+
        '<h4 class="acc-h'+(open?' open':'')+'">'+
          '<span class="ttl"><i class="grp-i '+G.cls+'"></i>'+G.label+'</span>'+
          (G.g==='topology'?'<span class="tg">⤢</span>':'<span class="tg">▶</span>')+
          '<span class="n">'+G.n+'</span>'+
        '</h4>';
      if(open){
        if(G.g==='topology'){
          html+='<div class="acc-b"><div class="topo-entry"><div class="big">完整关系图谱</div>'+
            '以 G6 力导向图展示全部实体与关系。<div class="go" id="topo-go">打开拓扑视图 →</div></div></div>';
        } else {
          const cats=categoriesOf(G.g);
          html+='<div class="acc-b">';
          cats.forEach(c=>{
            const act = (activeCat===c.cat)?' active':'';
            const dotcls = G.g==='entity'?'entity':G.g;
            html+='<div class="cat'+act+'" data-grp="'+G.g+'" data-cat="'+esc(c.cat)+'">'+
              '<span class="dot '+dotcls+'"></span>'+
              '<span class="lbl">'+esc(c.label)+'</span>'+
              '<span class="ct">'+c.count+'</span></div>';
          });
          html+='</div>';
        }
      }
      html+='</div>';
    });
    side.innerHTML=html;
    // 绑定
    side.querySelectorAll('.acc > .acc-h').forEach(h=>{
      h.addEventListener('click',()=>{
        const g=h.parentElement.dataset.grp;
        if(g==='topology'){ openTopology(); }
        else { openGroup(g); }
      });
    });
    side.querySelectorAll('.cat').forEach(c=>{
      c.addEventListener('click',()=>selectCategory(c.dataset.grp, c.dataset.cat));
    });
    const go=document.getElementById('topo-go');
    if(go) go.addEventListener('click',()=>openTopology());
  }

  function openGroup(g){
    if(activeGroup===g && mode==='drill'){
      // 再次点击当前组 → 收起
      activeGroup=null; activeCat=null; selected=null;
      renderSide(); clearRight(); return;
    }
    activeGroup=g; mode='drill'; selected=null; searching=false;
    const cats=categoriesOf(g);
    activeCat = cats.length?cats[0].cat:null;
    renderSide();
    setCanvas('drill');
    renderList();
    clearRight();
  }
  function openTopology(){
    activeGroup='topology'; mode='topology'; activeCat=null; selected=null; searching=false;
    renderSide();
    setCanvas('topology');
    renderTopologyInfo();
    ensureGraph();
  }

  // 选中某组下的某个分类：切换中间列表 + 清空右侧编辑区
  function selectCategory(group, cat){
    activeGroup=group; activeCat=cat; selected=null; mode='drill'; searching=false;
    renderSide();          // 高亮当前分类
    setCanvas('drill');
    renderList();          // 中间面板列出该分类全部条目
    clearRight();          // 右侧回到占位（待选中条目）
  }

  /* ── 中间面板：列表 ──────────────────────────── */
  function renderList(){
    const d=document.getElementById('detail');
    if(!activeGroup || activeGroup==='topology'){ d.innerHTML=''; return; }
    if(searching){ return; } // 搜索态由 renderSearch 接管
    const cats=categoriesOf(activeGroup);
    if(!cats.length){ d.innerHTML='<div class="list-empty">（无分类）</div>'; return; }
    if(!activeCat){ activeCat=cats[0].cat; renderSide(); }
    const items=itemsOf(activeGroup, activeCat);
    const catLabel=(cats.find(c=>c.cat===activeCat)||{}).label||activeCat;
    let html='<div class="list-h">'+esc(catLabel)+'<span class="ct">'+items.length+'</span></div>';
    if(!items.length){ html+='<div class="list-empty">该分类下暂无条目</div>'; }
    items.forEach(it=>{
      const id=itemId(it);
      const sel=(selected&&selected.kind===activeGroup&&selected.id===id)?' active':'';
      const cls=activeGroup==='entity'?'ent':activeGroup==='function'?'fn':'act';
      const name=it.cn||it.name||it.id||'(未命名)';
      const ds=it.desc||it.description||it.definition||'';
      let meta='';
      if(activeGroup==='function'){ meta='('+(it.inputs||[]).join(', ')+' → '+(it.outputs||[]).join(', ')+')'; }
      if(activeGroup==='action'){ meta='条件 '+(it.conditions||[]).length+' · 效果 '+(it.effects||[]).length; }
      html+='<div class="list-item '+cls+sel+'" data-kind="'+activeGroup+'" data-id="'+esc(id)+'">'+
        '<span class="nm">'+esc(name)+'</span><span class="id">'+esc(id)+'</span>'+
        (ds?'<div class="ds">'+esc(ds)+'</div>':'')+
        (meta?'<div class="meta">'+esc(meta)+'</div>':'')+
        '</div>';
    });
    d.innerHTML=html;
    d.querySelectorAll('.list-item').forEach(el=>{
      el.addEventListener('click',()=>selectItem(el.dataset.kind, el.dataset.id));
    });
  }

  function renderSearch(q){
    const d=document.getElementById('detail');
    if(!activeGroup || activeGroup==='topology'){ return; }
    const all=allItemsOf(activeGroup);
    const ql=q.toLowerCase();
    const res=all.filter(it=>{
      const id=itemId(it);
      const name=(it.cn||it.name||'').toLowerCase();
      const desc=(it.desc||it.description||it.definition||'').toLowerCase();
      const cat=(it.category||'').toLowerCase();
      return id.toLowerCase().indexOf(ql)>=0 || name.indexOf(ql)>=0 ||
             desc.indexOf(ql)>=0 || cat.indexOf(ql)>=0;
    });
    let html='<div class="list-h">搜索 “'+esc(q)+'”<span class="ct">'+res.length+'</span></div>';
    if(!res.length){ html+='<div class="list-empty">无匹配</div>'; }
    res.forEach(it=>{
      const id=itemId(it);
      const cls=activeGroup==='entity'?'ent':activeGroup==='function'?'fn':'act';
      const name=it.cn||it.name||it.id||'(未命名)';
      const ds=it.desc||it.description||it.definition||'';
      html+='<div class="list-item '+cls+'" data-kind="'+activeGroup+'" data-id="'+esc(id)+'">'+
        '<span class="nm">'+esc(name)+'</span><span class="id">'+esc(id)+'</span>'+
        (ds?'<div class="ds">'+esc(ds)+'</div>':'')+'</div>';
    });
    d.innerHTML=html;
    d.querySelectorAll('.list-item').forEach(el=>{
      el.addEventListener('click',()=>selectItem(el.dataset.kind, el.dataset.id));
    });
  }

  /* ── 右侧：可编辑详情 ────────────────────────── */
  function selectItem(kind,id){
    const it=findItem(kind,id);
    if(!it) return;
    selected={kind,id};
    mode='drill';
    activeGroup=kind;
    // 让中间列表对齐到该条目所属分类，便于高亮与回看
    activeCat = kind==='entity' ? (it.kind||'top') : (it.category||'未分类');
    renderSide(); renderList();
    setCanvas('drill');
    renderEdit(kind, it);
  }

  function clearRight(){
    const ed=document.getElementById('detail-edit');
    ed.classList.remove('show');
    ed.innerHTML='<div style="position:absolute;inset:0;display:flex;align-items:center;'+
      'justify-content:center;text-align:center;color:var(--text2);font-size:13px;padding:40px;line-height:1.8">'+
      '请从<b style="color:var(--cyan2);margin:0 4px">左侧分类</b>中选择条目，<br>此处显示其<b style="color:var(--cyan2);margin:0 4px">可编辑定义</b>。<br>'+
      '<span style="font-size:11px;color:var(--text2)">修改后点击「保存修改」即可写入覆盖层（不回写 ontos 源码）。</span></div>';
    ed.classList.add('show');
  }

  function renderEdit(kind,item){
    currentItem={kind,id:itemId(item)};
    currentFields=EDIT_FIELDS[kind];
    const ed=document.getElementById('detail-edit');
    const kindLabel= kind==='entity'?'实体':kind==='function'?'函数':'动作';
    let html='<div class="ed-head"><div class="tags">'+
      '<span class="pn-tag '+kind+'">'+kindLabel+'</span>'+
      (item.category?'<span class="pn-tag cat">'+esc(item.category)+'</span>':'')+
      '</div><h2>'+esc(item.cn||item.name||item.id)+'</h2>'+
      (item.id&&item.id!==(item.cn||item.name)?'<div class="en">'+esc(item.id)+'</div>':'')+
      ((item.description||item.definition||item.desc)?'<div style="color:var(--text2);font-size:12px;margin-top:6px;line-height:1.6">'+esc(item.description||item.definition||item.desc)+'</div>':'')+
      '</div>';
    html+='<div id="ed-form">';
    currentFields.forEach(f=>{ html+=fieldHTML(f, item[f.key]); });
    html+='</div>';
    html+=readonlyContext(kind,item);
    html+='<div class="ed-actions"><button class="btn-save" id="ed-save">保存修改</button>'+
      '<button class="btn-reset" id="ed-reset">重置</button>'+
      '<span class="ed-status" id="ed-status"></span></div>';
    ed.innerHTML=html;
    ed.classList.add('show');
    bindEdit(kind,item,currentFields);
  }

  function fieldHTML(f,val){
    const v=val==null?'':val;
    if(f.type==='text'){
      return '<div class="ed-sec"><label>'+esc(f.label)+'</label>'+
        '<input class="ed-input" data-field="'+f.key+'" data-type="text" value="'+esc(v)+'"></div>';
    }
    if(f.type==='textarea'){
      return '<div class="ed-sec"><label>'+esc(f.label)+'</label>'+
        '<textarea class="ed-textarea" data-field="'+f.key+'" data-type="textarea">'+esc(v)+'</textarea></div>';
    }
    if(f.type==='list'){
      const txt=Array.isArray(v)?v.join('\n'):String(v);
      return '<div class="ed-sec"><label>'+esc(f.label)+'</label>'+
        '<textarea class="ed-textarea" data-field="'+f.key+'" data-type="list">'+esc(txt)+'</textarea></div>';
    }
    if(f.type==='json'){
      let txt='';
      try{ txt=JSON.stringify(v,null,2); }catch(e){ txt=String(v); }
      return '<div class="ed-sec"><label>'+esc(f.label)+'</label>'+
        '<textarea class="ed-textarea" data-field="'+f.key+'" data-type="json" style="min-height:160px">'+esc(txt)+'</textarea>'+
        (f.hint?'<div class="ed-hint">'+esc(f.hint)+'</div>':'')+'</div>';
    }
    if(f.type==='bool'){
      const chk=v===true||v==='true'?' checked':'';
      return '<div class="ed-sec"><label>'+esc(f.label)+'</label>'+
        '<label class="ed-check"><input type="checkbox" data-field="'+f.key+'" data-type="bool"'+chk+'> 是</label></div>';
    }
    if(f.type==='chips'){
      const opts=(f.options==='entities')?entityIds:[];
      const set=new Set(Array.isArray(v)?v:[]);
      const chips=opts.map(o=>'<span class="ed-chip'+(set.has(o)?' on':'')+'" data-val="'+esc(o)+'">'+esc(o)+'</span>').join('');
      return '<div class="ed-sec"><label>'+esc(f.label)+'</label>'+
        '<div class="ed-chips" data-field="'+f.key+'">'+chips+'</div>'+
        '<div class="ed-hint">点击切换选中；可多选</div></div>';
    }
    return '';
  }

  function bindEdit(kind,item,fields){
    // chips 委托
    document.querySelectorAll('#ed-form .ed-chips').forEach(box=>{
      const key=box.dataset.field;
      chipState=new Set(Array.isArray(item[key])?item[key]:[]);
      box.addEventListener('click',e=>{
        const chip=e.target.closest('.ed-chip'); if(!chip) return;
        const val=chip.dataset.val;
        if(chipState.has(val)){ chipState.delete(val); chip.classList.remove('on'); }
        else { chipState.add(val); chip.classList.add('on'); }
      });
    });
    const save=document.getElementById('ed-save');
    if(save) save.addEventListener('click',saveCurrent);
    const reset=document.getElementById('ed-reset');
    if(reset) reset.addEventListener('click',()=>renderEdit(kind,item));
  }

  function gatherFields(fields){
    const out={};
    fields.forEach(f=>{
      if(f.type==='chips'){ out[f.key]=Array.from(chipState); }
      else if(f.type==='bool'){
        const el=document.querySelector('[data-field="'+f.key+'"]'); out[f.key]=!!(el&&el.checked);
      }
      else if(f.type==='list'){
        const el=document.querySelector('[data-field="'+f.key+'"]');
        out[f.key]=(el?el.value:'').split('\n').map(s=>s.trim()).filter(Boolean);
      }
      else if(f.type==='json'){
        const el=document.querySelector('[data-field="'+f.key+'"]');
        const raw=el?el.value:'';
        try{ out[f.key]=JSON.parse(raw); }
        catch(e){ throw new Error('「'+f.label+'」JSON 格式错误'); }
      }
      else {
        const el=document.querySelector('[data-field="'+f.key+'"]'); out[f.key]=el?el.value:'';
      }
    });
    return out;
  }

  function saveCurrent(){
    const status=document.getElementById('ed-status');
    let fields;
    try{ fields=gatherFields(currentFields); }
    catch(e){ if(status){status.textContent=e.message;status.className='ed-status err';} return; }
    const btn=document.getElementById('ed-save'); if(btn) btn.disabled=true;
    if(status){status.textContent='保存中…';status.className='ed-status';}
    fetch('/api/ontos/definition/'+currentItem.kind+'/'+encodeURIComponent(currentItem.id),{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({fields})
    }).then(r=>r.json().then(j=>({ok:r.ok,j}))).then(({ok,j})=>{
      if(btn) btn.disabled=false;
      if(ok&&j.success){
        if(status){status.textContent='已保存 ✓';status.className='ed-status ok';}
        toast('已保存：'+currentItem.kind+' / '+currentItem.id);
        reloadSpecAndRefresh();
      } else {
        if(status){status.textContent=(j&&j.message)||'保存失败';status.className='ed-status err';}
      }
    }).catch(e=>{
      if(btn) btn.disabled=false;
      if(status){status.textContent=String(e);status.className='ed-status err';}
    });
  }

  function reloadSpecAndRefresh(){
    fetch('/api/ontos/spec').then(r=>r.json()).then(j=>{
      if(j&&j.success){ SPEC=j; build(); renderCount(); renderSide(); renderList();
        if(selected){ const it=findItem(selected.kind,selected.id); if(it) renderEdit(selected.kind,it); } }
    }).catch(()=>{});
  }

  function readonlyContext(kind,item){
    if(kind!=='entity') return '';
    const n=byId[item.id||item.name]; if(!n) return '';
    let html='';
    // 关系
    const out=EDGES_.filter(e=>e.s===n.id);
    const inn=EDGES_.filter(e=>e.t===n.id&&e.s!==n.id);
    html+='<div class="ed-readonly"><h4>关系 <span style="color:var(--text2);font-family:var(--mono)">'+(out.length+inn.length)+'</span></h4><div class="rel-list">';
    out.forEach(e=>{ html+='<div class="r"><span class="arrow">→</span><span class="p">'+esc(e.p)+'</span><span class="lab">'+esc(labelOf(e.t))+'</span></div>'; });
    inn.forEach(e=>{ html+='<div class="r"><span class="arrow">←</span><span class="p">'+esc(e.p)+'</span><span class="lab">'+esc(labelOf(e.s))+'</span></div>'; });
    if(!out.length&&!inn.length) html+='<div style="color:var(--text2);font-size:11px">（无关系）</div>';
    html+='</div></div>';
    // 相关函数
    const relFn=(SPEC.functions||[]).filter(f=>(f.produces_for||[]).indexOf(n.id)>=0);
    html+='<div class="ed-readonly"><h4>产出归属本实体的函数 <span style="color:var(--text2);font-family:var(--mono)">'+relFn.length+'</span></h4>';
    relFn.forEach(f=>{ const io='('+(f.inputs||[]).join(', ')+' → '+(f.outputs||[]).join(', ')+')';
      html+='<div class="fn-item"><span class="nm">'+esc(f.name)+'</span><span style="color:var(--text2);font-family:var(--mono);font-size:10px;margin-left:6px">'+esc(f.id)+'</span><div class="desc">'+esc(f.description||'')+'</div><div style="color:var(--green);font-size:10px;font-family:var(--mono)">'+esc(io)+'</div></div>'; });
    if(!relFn.length) html+='<div style="color:var(--text2);font-size:11px">（无）</div>';
    html+='</div>';
    // 相关动作
    const relAct=(SPEC.actions||[]).filter(a=>(a.targets||[]).indexOf(n.id)>=0);
    html+='<div class="ed-readonly"><h4>指向本实体的动作 <span style="color:var(--text2);font-family:var(--mono)">'+relAct.length+'</span></h4>';
    relAct.forEach(a=>{ html+='<div class="act-item"><span class="nm">'+esc(a.name||a.id)+'</span><div class="desc">'+esc(a.definition||'')+'</div></div>'; });
    if(!relAct.length) html+='<div style="color:var(--text2);font-size:11px">（无）</div>';
    html+='</div>';
    // 物理字段
    html+=renderPhysical(n);
    return html;
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
    let html='<div class="ed-readonly"><h4>物理字段映射</h4>'+
      '<div style="font-size:11px;color:var(--text2);margin-bottom:6px;line-height:1.6;">'+
      '来源 <b style="color:var(--cyan2);">'+esc(dsName)+'</b> · '+ds.rows+' 行 / '+ds.column_count+' 列'+
      ' · <span style="color:var(--green);">绿</span>=已被引用</div>';
    (ds.groups||[]).forEach(g=>{
      html+='<div style="font-size:11px;color:var(--text2);margin:6px 0 3px;font-weight:600">'+esc(g.name)+' <span style="color:var(--cyan);font-family:var(--mono)">'+g.columns.length+'</span></div>';
      (g.columns||[]).forEach(c=>{
        const f=ds.field_map&&ds.field_map[c];
        const isBound=!!(f&&bound.has(f));
        if(isBound) hit++;
        html+='<span class="col-chip'+(isBound?' bound':'')+'"'+(f?' title="'+esc(c)+' → '+esc(f)+'"':'')+'>'+esc(c)+'</span>';
      });
    });
    html+='<div class="ed-hint" style="margin-top:8px">语义属性 <b style="color:var(--orange)">'+n.attrs.length+'</b> · 物理列 <b style="color:var(--orange)">'+ds.column_count+'</b> · 已映射 <b style="color:var(--green)">'+hit+'</b></div></div>';
    return html;
  }

  /* ── 画布模式切换（拓扑 vs 下钻） ─────────────── */
  function setCanvas(m){
    const g6=document.getElementById('g6');
    const g6t=document.getElementById('g6-table');
    const gt=document.getElementById('g-tools');
    const ed=document.getElementById('detail-edit');
    const seg=document.getElementById('view-seg');
    if(m==='topology'){
      g6.style.display='block'; g6t.style.display='none'; gt.style.display='flex';
      if(seg) seg.classList.remove('hide');
      ed.classList.remove('show'); ed.innerHTML='';
    } else {
      g6.style.display='none'; g6t.style.display='none'; gt.style.display='none';
      if(seg) seg.classList.add('hide');
    }
  }

  function renderTopologyInfo(){
    const d=document.getElementById('detail');
    d.innerHTML='<div class="ed-readonly"><h4>拓扑视图</h4>'+
      '<div style="font-size:12px;color:var(--text2);line-height:1.8">'+
      '当前本体共 <b style="color:var(--cyan2)">'+NODES.length+'</b> 个节点（含外部占位）、'+
      '<b style="color:var(--cyan2)">'+EDGES_.length+'</b> 条关系。<br>'+
    '图谱以力导向布局展示实体间关系；<b style="color:var(--cyan2)">点击任意节点</b>会高亮其上下游并列出关系，点空白处重置。<br>'+
    '右上角可在 <b>Graph / Table</b> 间切换。</div></div>';
  }

  /* ── G6 图谱 ─────────────────────────────────── */
  function ensureGraph(){
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
          style:{fill:HEX.panel,stroke:HEX.orange,lineWidth:1.5,radius:6,
            shadowColor:'rgba(251,191,36,.35)',shadowBlur:8},
          labelCfg:{style:{fill:HEX.text,fontSize:12,fontWeight:600,cursor:'pointer'}}},
        defaultEdge:{type:'line',
          style:{stroke:HEX.orange,lineWidth:1.1,opacity:.55,
            endArrow:{fill:HEX.orange,path:G6.Arrow.triangle(6,8,2)},cursor:'pointer'},
          labelCfg:{autoRotate:true,
            style:{fill:HEX.text2,fontSize:9,fontWeight:500,
              background:{fill:HEX.bg2,padding:[2,4,2,4],radius:3}}}},
        nodeStateStyles:{
          active:{lineWidth:2.4, stroke:'#ffe9a8', shadowColor:'rgba(251,191,36,.55)', shadowBlur:14, opacity:1},
          inactive:{opacity:0.12}
        },
        edgeStateStyles:{
          active:{opacity:0.95, stroke:'#ffe9a8', lineWidth:1.8},
          inactive:{opacity:0.06, stroke:HEX.text2}
        },
      });
      graph.node(node=>{
        const k=node.kind;
        const stroke=k==='child'?HEX.purple:(k==='external'?HEX.text2:HEX.orange);
        const lineDash=k==='external'?[4,3]:undefined;
        const shadow=k==='child'?'rgba(167,139,250,.3)':k==='external'?'transparent':'rgba(79,140,255,.3)';
        return {style:{stroke,lineWidth:1.5,lineDash,shadowColor:shadow,shadowBlur:8},
          labelCfg:{style:{fill:HEX.text,fontSize:12,fontWeight:600}}};
      });
      graph.data({nodes,edges});
      graph.render();
      try{ minimapInst=new G6.Minimap({size:[180,120]}); graph.addPlugin(minimapInst); }catch(e){}
      graph.on('node:click',e=>{
        const id=e.item.getModel().id;
        focusNode(id);   // 点节点 = 显示上下游关系，不跳转
      });
      graph.on('canvas:click',()=>{
        if(graph){
          graph.getNodes().forEach(node=>{ graph.setItemState(node,'active',false); graph.setItemState(node,'inactive',false); });
          graph.getEdges().forEach(edge=>{ graph.setItemState(edge,'active',false); graph.setItemState(edge,'inactive',false); });
        }
        renderTopologyInfo();   // 重置中间面板
      });
    } catch(err){
      console.error('G6 init failed', err);
      showError('G6 图谱初始化失败', String(err&&err.message||err));
    }
  }

  /* 点节点：高亮上下游 + 中间面板列出关系（不跳转） */
  function focusNode(id){
    const n=byId[id]; if(!n) return;
    const downstream=EDGES_.filter(e=>e.s===id);              // 从此出发
    const upstream=EDGES_.filter(e=>e.t===id && e.s!==id);     // 指向此处
    if(graph){
      graph.getNodes().forEach(node=>{
        const nid=node.getModel().id;
        const related = downstream.some(e=>e.t===nid) || upstream.some(e=>e.s===nid);
        const on=(nid===id)||related;
        graph.setItemState(node,'active',on);
        graph.setItemState(node,'inactive',!on);
      });
      graph.getEdges().forEach(edge=>{
        const m=edge.getModel();
        const on=(m.source===id)||(m.target===id);
        graph.setItemState(edge,'active',on);
        graph.setItemState(edge,'inactive',!on);
      });
      try{ graph.focusItem(id,true); }catch(e){}
    }
    renderNodeRelations(n, upstream, downstream);
  }

  function relRow(pred, label, id){
    return '<div class="rel-row" data-id="'+esc(id)+'"><span class="p">'+esc(pred)+'</span>'+
      '<span class="lab">'+esc(label)+'</span><span class="id">'+esc(id)+'</span></div>';
  }

  function renderNodeRelations(n, upstream, downstream){
    const d=document.getElementById('detail');
    let html='<div class="list-h">'+esc(n.label)+'</div>';
    html+='<div style="font-family:var(--mono);font-size:11px;color:var(--text2);margin:0 4px 12px">'+
      esc(n.id)+' · '+esc(n.kind)+'</div>';
    html+='<div class="ed-readonly"><h4>下游 · 从此出发（'+downstream.length+'）</h4>';
    if(downstream.length) downstream.forEach(e=>{ html+=relRow(e.p, labelOf(e.t), e.t); });
    else html+='<div style="color:var(--text2);font-size:11px">（无）</div>';
    html+='</div>';
    html+='<div class="ed-readonly"><h4>上游 · 指向此处（'+upstream.length+'）</h4>';
    if(upstream.length) upstream.forEach(e=>{ html+=relRow(e.p, labelOf(e.s), e.s); });
    else html+='<div style="color:var(--text2);font-size:11px">（无）</div>';
    html+='</div>';
    html+='<div class="rel-jump" id="rel-jump">查看该实体定义 →</div>';
    d.innerHTML=html;
    d.querySelectorAll('.rel-row').forEach(row=>{
      row.addEventListener('click',()=>focusNode(row.dataset.id));  // 关系可继续钻取
    });
    const j=document.getElementById('rel-jump');
    if(j) j.addEventListener('click',()=>{ openGroup('entity'); selectItem('entity', n.id); });
  }

  function renderTable(){
    const tb=document.getElementById('tbl-body'); if(!tb) return; tb.innerHTML='';
    EDGES_.forEach(e=>{
      tb.innerHTML+='<tr>'+
        '<td style="color:var(--cyan2);font-family:var(--mono);font-weight:600;">'+esc(e.p)+'</td>'+
        '<td><b>'+esc(labelOf(e.s))+'</b> <span style="color:var(--text2);font-family:var(--mono);font-size:10px;">'+esc(e.s)+'</span>'+
        ' <span style="color:var(--cyan);">→</span> '+
        '<b>'+esc(labelOf(e.t))+'</b> <span style="color:var(--text2);font-family:var(--mono);font-size:10px;">'+esc(e.t)+'</span></td>'+
        '<td style="color:var(--purple);font-family:var(--mono);">'+esc(e.c)+'</td>'+
        '<td style="color:var(--text2);">'+esc(e.desc||'')+'</td></tr>';
    });
  }

  /* ── 提示气泡 ─────────────────────────────────── */
  let toastTimer;
  function toast(msg, isErr){
    const t=document.getElementById('toast'); if(!t) return;
    t.textContent=msg; t.className='toast show'+(isErr?' err':'');
    clearTimeout(toastTimer);
    toastTimer=setTimeout(()=>{ t.className='toast'+(isErr?' err':''); }, 2600);
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
        if(v==='table') renderTable();
        const mm=document.querySelector('.g6-minimap-container, .g-minimap');
        if(mm) mm.style.display=v==='graph'?'block':'none';
        if(v==='graph'&&graph) setTimeout(()=>graph.fitView(40),100);
      });
    });
    document.querySelectorAll('#g-tools button').forEach(btn=>{
      btn.addEventListener('click',()=>{
        if(!graph) return; const act=btn.dataset.act;
        if(act==='zoom-in') graph.zoom(graph.getZoom()*1.2);
        else if(act==='zoom-out') graph.zoom(graph.getZoom()/1.2);
        else if(act==='fit') graph.fitView(40);
        else if(act==='reset'){ ensureGraph(); }
      });
    });
    document.getElementById('q').addEventListener('input',e=>{
      const q=e.target.value.trim();
      if(!activeGroup || activeGroup==='topology') return;
      if(!q){ searching=false; renderList(); return; }
      searching=true; renderSearch(q);
    });
    document.getElementById('reset').addEventListener('click',()=>{
      document.getElementById('q').value=''; searching=false;
      if(mode==='topology'){ ensureGraph(); } else { renderList(); }
    });
    document.getElementById('reload').addEventListener('click',()=>location.reload());
    let rzTimer;
    window.addEventListener('resize',()=>{
      clearTimeout(rzTimer);
      rzTimer=setTimeout(()=>{
        if(mode==='topology' && graph){
          const rect=document.getElementById('g6').parentElement.getBoundingClientRect();
          graph.changeSize(rect.width,rect.height); graph.fitView(40);
        }
      },150);
    });
    load();
  }

  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',init);
  else init();
})();
