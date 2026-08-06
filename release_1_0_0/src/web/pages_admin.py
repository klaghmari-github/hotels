"""Page /admin — studio leger (datasets ALL/PILOTE + evaluation)."""

ADMIN_CSS = """
.admin-shell { display:grid; grid-template-columns: 280px 1fr; min-height: calc(100vh - 64px); }
@media (max-width: 900px){ .admin-shell { grid-template-columns: 1fr; } }
.admin-side {
  border-right:1px solid var(--line); background:#121a24; padding:1rem .85rem 2rem;
  overflow:auto;
}
.admin-side .group-title {
  font-size:.72rem; text-transform:uppercase; letter-spacing:.06em; color:var(--muted);
  margin:1rem 0 .4rem; font-weight:700;
}
.admin-side .nav-item {
  display:flex; gap:.55rem; align-items:flex-start; width:100%; text-align:left;
  border:1px solid transparent; background:transparent; color:var(--text);
  border-radius:10px; padding:.55rem .6rem; cursor:pointer; margin-bottom:.25rem;
}
.admin-side .nav-item:hover { border-color:var(--line); background:#1a2433; }
.admin-side .nav-item.active { border-color:var(--accent); background:rgba(61,139,253,.12); }
.admin-side .nav-label { font-weight:700; font-size:.9rem; display:block; }
.admin-side .nav-desc { font-size:.78rem; color:var(--muted); display:block; margin-top:.1rem; }
.admin-main { padding:1.1rem 1.25rem 2.5rem; overflow:auto; }
.admin-toolbar { display:flex; flex-wrap:wrap; gap:.6rem; align-items:center; margin-bottom:.8rem; }
.admin-toolbar input[type=search] {
  flex:1; min-width:180px; padding:.5rem .65rem; border-radius:8px;
  border:1px solid var(--line); background:#101820; color:var(--text); font-size:.95rem;
}
.logo-cell img { max-height:28px; max-width:80px; object-fit:contain; vertical-align:middle; }
.brand-strip { display:flex; flex-wrap:wrap; gap:.5rem; margin:.5rem 0 1rem; }
.brand-strip img { height:32px; width:auto; background:#fff; border-radius:6px; padding:4px 8px; }
"""

ADMIN_BODY = """
<div class="admin-shell">
  <aside class="admin-side">
    <div style="display:flex;align-items:center;gap:.6rem;margin-bottom:.5rem">
      <img src="/static/img/accor-logo.svg" alt="Accor" style="height:28px"/>
      <strong style="font-size:.95rem">Admin studio</strong>
    </div>
    <div class="group-title">ALL</div>
    <div id="nav-all"></div>
    <div class="group-title">PILOTE</div>
    <div id="nav-pilote"></div>
    <div class="group-title">Evaluation</div>
    <button type="button" class="nav-item" data-panel="eval" id="nav-eval">
      <span><span class="nav-label">LOO · comparaison</span>
      <span class="nav-desc">sim_v1 · sim_v2 · ml</span></span>
    </button>
    <button type="button" class="nav-item" data-panel="predict" id="nav-predict">
      <span><span class="nav-label">Prediction test</span>
      <span class="nav-desc">Parametres + mix</span></span>
    </button>
  </aside>
  <section class="admin-main">
    <div id="view-table">
      <div class="admin-toolbar">
        <h2 id="ds-title" style="margin:0;flex:1">Dataset</h2>
        <input type="search" id="ds-q" placeholder="Filtrer…"/>
        <button class="btn" type="button" id="ds-prev">Prev</button>
        <span id="ds-page" class="muted"></span>
        <button class="btn" type="button" id="ds-next">Next</button>
      </div>
      <div id="brand-logos" class="brand-strip"></div>
      <div id="ds-meta" class="muted" style="margin-bottom:.5rem"></div>
      <div id="ds-table" class="scroll"><p class="muted">Chargement…</p></div>
    </div>
    <div id="view-eval" style="display:none">
      <div style="display:flex;gap:.5rem;flex-wrap:wrap;margin-bottom:1rem">
        <button class="btn primary" data-src="sim_v1" type="button">sim_v1</button>
        <button class="btn" data-src="sim_v2" type="button">sim_v2</button>
        <button class="btn" data-src="ml" type="button">ml</button>
        <a class="btn" href="/admin#compare">Comparaison</a>
      </div>
      <div id="eval-main"><p class="muted">Choisir une source.</p></div>
      <div id="compare-main" style="margin-top:1.5rem"></div>
    </div>
    <div id="view-predict" style="display:none">
      <p class="muted">Outil admin — prediction detaillee (mix, moteurs).</p>
      <p><a class="btn primary" href="/predict">Ouvrir prediction avancee</a>
         <a class="btn" href="/user" style="margin-left:.4rem">Interface user</a></p>
    </div>
  </section>
</div>
"""

ADMIN_SCRIPT = r"""
const fmt=(n,d=2)=>{if(n==null||n===''||Number.isNaN(Number(n)))return '—';return Number(n).toLocaleString('fr-FR',{maximumFractionDigits:d});};
const tag=s=>`<span class="tag ${(s||'').toString().toLowerCase().replace(/[^a-z0-9_]/g,'')}">${s??''}</span>`;
const state={datasets:[], current:null, page:1, pageSize:50, q:''};

function showView(name){
  document.getElementById('view-table').style.display=name==='table'?'':'none';
  document.getElementById('view-eval').style.display=name==='eval'?'':'none';
  document.getElementById('view-predict').style.display=name==='predict'?'':'none';
  document.querySelectorAll('.admin-side .nav-item').forEach(b=>{
    const panel=b.dataset.panel;
    const id=b.dataset.id;
    if(panel) b.classList.toggle('active', panel===name);
    else if(id) b.classList.toggle('active', name==='table' && id===state.current);
  });
}

function logoUrl(path){
  if(!path) return null;
  let p=String(path).replace(/\\/g,'/').replace(/^\/+/, '');
  // brand table paths : economy/ibis.png ou marques/economy/ibis.png
  if(p.startsWith('static/')) return '/'+p;
  if(p.startsWith('marques/')) return '/static/'+p;
  if(p.includes('marques/')) return '/static/marques/'+p.split('marques/').pop();
  return '/static/marques/'+p;
}

function renderNav(){
  const all=document.getElementById('nav-all');
  const pil=document.getElementById('nav-pilote');
  all.innerHTML=''; pil.innerHTML='';
  for(const ds of state.datasets){
    const btn=document.createElement('button');
    btn.type='button'; btn.className='nav-item'; btn.dataset.id=ds.id;
    btn.innerHTML=`<span><span class="nav-label">${ds.label}</span><span class="nav-desc">${ds.description||''}</span></span>`;
    btn.onclick=()=>selectDataset(ds.id);
    (ds.group==='PILOTE'?pil:all).appendChild(btn);
  }
}

async function selectDataset(id){
  state.current=id; state.page=1; state.q='';
  document.getElementById('ds-q').value='';
  showView('table');
  await loadPage();
}

async function loadPage(){
  if(!state.current) return;
  const main=document.getElementById('ds-table');
  main.innerHTML='<p class="muted">Chargement…</p>';
  const url=new URL('/api/admin/datasets/'+state.current, location.origin);
  url.searchParams.set('page', state.page);
  url.searchParams.set('page_size', state.pageSize);
  if(state.q) url.searchParams.set('q', state.q);
  try{
    const res=await fetch(url); const data=await res.json();
    if(!data.ok) throw new Error(data.error||'erreur');
    const ds=data.dataset;
    document.getElementById('ds-title').textContent=ds.label;
    document.getElementById('ds-meta').textContent=
      `${data.total.toLocaleString('fr-FR')} lignes`+(data.total!==data.total_all?` (filtre / ${data.total_all.toLocaleString('fr-FR')})`:'')
      +` · page ${data.page}`;
    document.getElementById('ds-page').textContent=`${data.page}`;
    // logos strip for brand dataset
    const strip=document.getElementById('brand-logos');
    strip.innerHTML='';
    if(ds.id==='hotel_brand_data' && data.rows){
      for(const r of data.rows.slice(0,24)){
        const src=logoUrl(r.logo_path);
        if(!src) continue;
        const img=document.createElement('img');
        img.src=src; img.alt=r.Marque||''; img.title=r.Marque||'';
        img.onerror=()=>img.remove();
        strip.appendChild(img);
      }
    }
    const cols=data.columns||[];
    let h='<table><thead><tr>'+cols.map(c=>`<th>${c}</th>`).join('')+'</tr></thead><tbody>';
    for(const r of (data.rows||[])){
      h+='<tr>'+cols.map(c=>{
        let v=r[c];
        if(c==='logo_path' && v){
          const src=logoUrl(v);
          return `<td class="logo-cell">${src?`<img src="${src}" alt=""/>`:''} <span class="muted">${v}</span></td>`;
        }
        if(v==null) v='—';
        return `<td>${typeof v==='number'?fmt(v):String(v)}</td>`;
      }).join('')+'</tr>';
    }
    h+='</tbody></table>';
    main.innerHTML=h||'<p class="muted">Vide</p>';
    document.querySelectorAll('.admin-side .nav-item[data-id]').forEach(b=>b.classList.toggle('active', b.dataset.id===state.current));
  }catch(e){
    main.innerHTML=`<div class="errbox">${e.message}</div>`;
  }
}

// ---- eval (admin) ----
async function loadEval(src){
  const main=document.getElementById('eval-main');
  main.innerHTML='<p class="muted">Chargement…</p>';
  document.querySelectorAll('#view-eval button[data-src]').forEach(b=>b.classList.toggle('primary', b.dataset.src===src));
  try{
    const res=await fetch('/api/eval/'+src); const data=await res.json();
    if(!data.ok) throw new Error(data.error||'erreur');
    let html='';
    if((data.metrics||[]).length){
      html+='<div class="grid">'+(data.metrics||[]).map(m=>{
        const title=m.target_label||m.target||m.methode||m.perimetre||m.solution||'';
        const mae=m.mae??m.montant_ventes_mae??m.mae_ca;
        return `<div class="card"><div class="lbl">${title}</div><div class="val">${fmt(mae)}</div><div class="sub">MAE</div></div>`;
      }).join('')+'</div>';
    }
    html+='<h2>Predictions</h2>';
    const preds=data.predictions||[];
    const keys=preds[0]?Object.keys(preds[0]).slice(0,12):[];
    html+='<div class="scroll"><table><thead><tr>'+keys.map(k=>`<th>${k}</th>`).join('')+'</tr></thead><tbody>';
    for(const r of preds){
      html+='<tr>'+keys.map(k=>`<td class="${/mae|err|reel|pred|ca_|marge_/i.test(k)?'num':''}">${r[k]==null?'—':(/mae|err|reel|pred|ca_|marge_/i.test(k)?fmt(r[k]):r[k])}</td>`).join('')+'</tr>';
    }
    html+='</tbody></table></div>';
    main.innerHTML=html;
  }catch(e){ main.innerHTML=`<div class="errbox">${e.message}</div>`; }
}

async function loadCompare(){
  const box=document.getElementById('compare-main');
  box.innerHTML='<p class="muted">Comparaison…</p>';
  const SOURCES=['sim_v1','sim_v2','ml'];
  const results=await Promise.all(SOURCES.map(async src=>{
    try{
      const res=await fetch('/api/eval/'+src); const data=await res.json();
      return {src, ok:!!data.ok, metrics:data.metrics||[], predictions:data.predictions||[], error:data.error};
    }catch(e){ return {src, ok:false, error:e.message}; }
  }));
  function pickMae(metrics){
    if(!metrics||!metrics.length) return null;
    const ordered=[...metrics].sort((a,b)=>Number(a.solution==null||a.solution==='')-Number(b.solution==null||b.solution===''));
    for(const m of ordered){
      if(m.mae_ca!=null) return Number(m.mae_ca);
      if(m.montant_ventes_mae!=null) return Number(m.montant_ventes_mae);
      if(m.target==='montant_ventes_par_mois' && m.mae!=null) return Number(m.mae);
    }
    return null;
  }
  let html='<h2>Comparaison LOO</h2><div class="grid">';
  for(const r of results){
    const hotels=new Set((r.predictions||[]).map(p=>p.hotel_code).filter(Boolean));
    html+=`<div class="card"><div class="lbl">${tag(r.src)}</div>
      <div class="val">${r.ok?fmt(pickMae(r.metrics)):'—'}</div>
      <div class="sub">MAE CA · hotels=${hotels.size}</div>
      ${r.error?`<div class="errbox" style="margin-top:.4rem;padding:.4rem">${r.error}</div>`:''}
    </div>`;
  }
  html+='</div>';
  box.innerHTML=html;
}

document.getElementById('nav-eval').onclick=()=>{ showView('eval'); loadEval('sim_v1'); loadCompare(); };
document.getElementById('nav-predict').onclick=()=>showView('predict');
document.getElementById('ds-prev').onclick=()=>{ if(state.page>1){ state.page--; loadPage(); } };
document.getElementById('ds-next').onclick=()=>{ state.page++; loadPage(); };
document.getElementById('ds-q').addEventListener('keydown', e=>{
  if(e.key==='Enter'){ state.q=e.target.value.trim(); state.page=1; loadPage(); }
});
document.querySelectorAll('#view-eval button[data-src]').forEach(b=>b.onclick=()=>loadEval(b.dataset.src));

fetch('/api/admin/datasets').then(r=>r.json()).then(data=>{
  if(!data.ok) return;
  state.datasets=data.datasets||[];
  renderNav();
  if(state.datasets.length) selectDataset(state.datasets[0].id);
}).catch(e=>{
  document.getElementById('ds-table').innerHTML=`<div class="errbox">${e.message}</div>`;
});
"""
