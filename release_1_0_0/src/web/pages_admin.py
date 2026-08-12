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
.logo-cell { text-align:center; vertical-align:middle !important; }
.logo-cell img {
  height:36px; width:auto; max-width:100px; object-fit:contain; vertical-align:middle;
  background:#fff; border-radius:6px; padding:4px 8px;
}
.admin-table-wrap { overflow:auto; max-width:100%; border:1px solid var(--line); border-radius:10px; }
.admin-table-wrap table { margin:0; border:0; border-radius:0; font-size:.86rem; }
.admin-table-wrap th {
  position:sticky; top:0; z-index:2; white-space:nowrap;
  background:#152030; box-shadow:0 1px 0 var(--line);
}
.admin-table-wrap th.sticky-col, .admin-table-wrap td.sticky-col {
  position:sticky; left:0; z-index:1; background:var(--card);
  box-shadow:1px 0 0 var(--line); max-width:220px;
}
.admin-table-wrap th.sticky-col { z-index:3; background:#152030; }
.admin-table-wrap td { white-space:nowrap; max-width:280px; overflow:hidden; text-overflow:ellipsis; }
.admin-table-wrap td.wrap { white-space:normal; max-width:320px; }
.nullish { color:var(--muted); opacity:.55; }
.col-toggle { display:flex; flex-wrap:wrap; gap:.35rem; margin:.4rem 0 .7rem; }
.col-toggle label {
  font-size:.75rem; color:var(--muted); border:1px solid var(--line);
  border-radius:999px; padding:.15rem .5rem; cursor:pointer; user-select:none;
}
.col-toggle label.on { color:var(--text); border-color:var(--accent); background:rgba(61,139,253,.12); }
/* Eval LOO : reel / predit / erreur */
.eval-legend { display:flex; flex-wrap:wrap; gap:.75rem; margin:.4rem 0 .8rem; font-size:.82rem; }
.eval-legend span { display:inline-flex; align-items:center; gap:.35rem; }
.eval-legend i {
  display:inline-block; width:10px; height:10px; border-radius:3px;
}
.col-reel, th.col-reel { color:#7dd3fc !important; }
.col-pred, th.col-pred { color:#c4b5fd !important; }
.col-err, th.col-err { color:#f5a524 !important; }
td.col-reel { background:rgba(125,211,252,.06); }
td.col-pred { background:rgba(196,181,253,.06); }
td.col-err { background:rgba(245,165,36,.07); font-weight:600; }
.eval-table th { font-size:.72rem; letter-spacing:.02em; }
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
  </aside>
  <section class="admin-main">
    <div id="view-table">
      <div class="admin-toolbar">
        <h2 id="ds-title" style="margin:0;flex:1">Dataset</h2>
        <input type="search" id="ds-q" placeholder="Filtrer…"/>
        <button class="btn" type="button" id="ds-prev">Prev</button>
        <span id="ds-page" class="muted" style="min-width:7rem;text-align:center;font-weight:600"></span>
        <button class="btn" type="button" id="ds-next">Next</button>
      </div>
      <div id="ds-meta" class="muted" style="margin-bottom:.5rem"></div>
      <div id="ds-table" class="scroll"><p class="muted">Chargement…</p></div>
    </div>
    <div id="view-eval" style="display:none">
      <div style="display:flex;gap:.5rem;flex-wrap:wrap;margin-bottom:1rem">
        <button class="btn primary" data-src="compare" type="button">comparaison</button>
        <button class="btn" data-src="sim_v1" type="button">sim_v1</button>
        <button class="btn" data-src="sim_v2" type="button">sim_v2</button>
        <button class="btn" data-src="ml" type="button">ml</button>
      </div>
      <div id="eval-main"></div>
    </div>
  </section>
</div>
"""

ADMIN_SCRIPT = r"""
const fmt=(n,d=2)=>{if(n==null||n===''||Number.isNaN(Number(n)))return '—';return Number(n).toLocaleString('fr-FR',{maximumFractionDigits:d});};
const tag=s=>`<span class="tag ${(s||'').toString().toLowerCase().replace(/[^a-z0-9_]/g,'')}">${s??''}</span>`;
const state={datasets:[], current:null, page:1, pageSize:50, totalPages:1, q:''};

function showView(name){
  document.getElementById('view-table').style.display=name==='table'?'':'none';
  document.getElementById('view-eval').style.display=name==='eval'?'':'none';
  document.querySelectorAll('.admin-side .nav-item').forEach(b=>{
    const panel=b.dataset.panel;
    const id=b.dataset.id;
    if(panel) b.classList.toggle('active', panel===name);
    else if(id) b.classList.toggle('active', name==='table' && id===state.current);
  });
}

function logoUrl(path){
  // logo_path Excel (relatif data/marques) → API avec Content-Type correct
  // (beaucoup de .png Accor sont en realite du SVG)
  if(path==null || path==='') return null;
  let p=String(path).trim().replace(/\\/g,'/');
  if(!p || /^(nan|none|null)$/i.test(p)) return null;
  if(/^https?:\/\//i.test(p)) return p;
  if(p.startsWith('/api/marques/logos/')) return p;
  // strip prefixes redondants
  p=p.replace(/^\/+/, '');
  p=p.replace(/^(?:\.\/)?(?:data\/)?(?:static\/)?marques\//i, '');
  // encoder chaque segment (espaces, accents) sans casser les /
  const encoded=p.split('/').filter(Boolean).map(encodeURIComponent).join('/');
  return '/api/marques/logos/'+encoded;
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

function esc(s){
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function isEmptyVal(v){
  return v==null || v==='' || (typeof v==='number' && Number.isNaN(v));
}
/** Colonnes prioritaires en tete — logo juste apres la marque. */
function orderColumns(cols, rows){
  const priority=[
    'Marque','logo_path','hotel_code','HOTEL_CODE','hotel_name','HOTEL_NAME',
    'hotel_brand','hotel_city','hotel_country','SOLUTION','solution',
    'scenario_id','scenario_removed_natures','row_kind','n_natures_retirees',
    'DATE','NATURE_PRODUIT','CATEGORIE','PRIX_TTC','MARGE','QUANTITE',
    'montant_ventes_par_mois','montant_marge_selon_coef_par_mois',
    'nombre_natures','type_f_b_part_natures','type_non_f_b_part_natures',
  ];
  const set=new Set(cols);
  const first=priority.filter(c=>set.has(c));
  const rest=cols.filter(c=>!first.includes(c));
  return [...first, ...rest];
}
function headerLabel(c){
  if(c==='logo_path' || c==='logo') return 'Logo';
  return c;
}
function cellHtml(c, v, sticky=false){
  const classes=[];
  if(sticky) classes.push('sticky-col');
  if(c==='logo_path' || c==='logo'){
    if(isEmptyVal(v)) return `<td class="${['nullish',...classes].join(' ')}">—</td>`;
    const src=logoUrl(v);
    classes.push('logo-cell');
    // image seule (chemin en title pour debug) — prefix API applique via logoUrl
    if(!src) return `<td class="${['nullish',...classes].join(' ')}" title="${esc(v)}">—</td>`;
    return `<td class="${classes.join(' ')}" title="${esc(v)}"><img src="${esc(src)}" alt="logo" loading="lazy" onerror="this.replaceWith(document.createTextNode('—'))"/></td>`;
  }
  if(isEmptyVal(v)) return `<td class="${['nullish',...classes].join(' ')}">—</td>`;
  if(typeof v==='number'){ classes.push('num'); return `<td class="${classes.join(' ')}">${fmt(v)}</td>`; }
  if(typeof v==='boolean') return `<td class="${classes.join(' ')}">${v?'oui':'non'}</td>`;
  const s=String(v);
  if(s.length>48) classes.push('wrap');
  return `<td class="${classes.join(' ')}" title="${esc(s)}">${esc(s)}</td>`;
}

async function loadPage(){
  if(!state.current) return;
  const main=document.getElementById('ds-table');
  main.innerHTML='<p class="muted">Chargement…</p>';
  const url=new URL('/api/admin/datasets/'+state.current, location.origin);
  url.searchParams.set('page', state.page);
  url.searchParams.set('page_size', state.pageSize);
  if(state.q) url.searchParams.set('q', state.q);
  const ctrl=new AbortController();
  const timer=setTimeout(()=>ctrl.abort(), 90000);
  try{
    const res=await fetch(url, {signal: ctrl.signal});
    clearTimeout(timer);
    if(!res.ok){
      let msg=`HTTP ${res.status}`;
      try{ const j=await res.json(); if(j.error) msg=j.error; }catch(_){}
      throw new Error(msg);
    }
    const data=await res.json();
    if(!data.ok) throw new Error(data.error||'erreur');
    const ds=data.dataset;
    const rows=data.rows||[];
    const allCols=data.columns||(rows[0]?Object.keys(rows[0]):[]);
    const cols=orderColumns(allCols, rows);

    const total=Number(data.total||0);
    const pageSize=Number(data.page_size||state.pageSize||50);
    const page=Number(data.page||state.page||1);
    const totalPages=Math.max(1, Math.ceil(total/pageSize)||1);
    state.page=page;
    state.totalPages=totalPages;

    document.getElementById('ds-title').textContent=ds.label;
    document.getElementById('ds-meta').textContent=
      `${total.toLocaleString('fr-FR')} lignes`
      +(data.total!==data.total_all?` (filtre / ${(data.total_all||0).toLocaleString('fr-FR')})`:'')
      +` · page ${page} / ${totalPages}`
      +` · ${cols.length} colonnes`;
    document.getElementById('ds-page').textContent=`${page} / ${totalPages}`;
    // desactiver prev/next aux bornes
    const prev=document.getElementById('ds-prev');
    const next=document.getElementById('ds-next');
    if(prev) prev.disabled = page<=1;
    if(next) next.disabled = page>=totalPages;

    if(!rows.length){
      main.innerHTML='<p class="muted">Aucune ligne.</p>';
      return;
    }

    let h='<div class="admin-table-wrap"><table><thead><tr>';    cols.forEach((c,i)=>{ h+=`<th class="${i<2?'sticky-col':''}">${esc(headerLabel(c))}</th>`; });
    h+='</tr></thead><tbody>';
    for(const r of rows){
      h+='<tr>';
      cols.forEach((c,i)=>{ h+=cellHtml(c, r[c], i<2); });
      h+='</tr>';
    }
    h+='</tbody></table></div>';
    main.innerHTML=h;
    document.querySelectorAll('.admin-side .nav-item[data-id]').forEach(b=>b.classList.toggle('active', b.dataset.id===state.current));
  }catch(e){
    clearTimeout(timer);
    const msg = e && e.name==='AbortError'
      ? 'Delai depasse (serveur trop lent ou DuckDB lock). Reessayez ou relancez le serveur.'
      : (e.message==='Failed to fetch'
        ? 'Connexion impossible (serveur arrete, redemarrage, ou reseau). Verifiez http://127.0.0.1:5080 et reessayez.'
        : e.message);
    main.innerHTML=`<div class="errbox">${esc(msg)}</div>
      <p class="muted" style="margin-top:.5rem"><button class="btn" type="button" id="ds-retry">Reessayer</button></p>`;
    const rb=document.getElementById('ds-retry');
    if(rb) rb.onclick=()=>loadPage();
  }
}

// ---- eval (admin) — CA / marge ventes / cout / ROI / amort (mensuel) ----
// ROI = marge ventes (PV − PA) − couts solution
// Ordre d affichage solutions : Connected → Liberty → Simply
const SOLUTION_DISPLAY_ORDER=['connected','liberty','simply'];
function sortBySolution(rows, solKey='solution', hotelKey='hotel_code'){
  const order=SOLUTION_DISPLAY_ORDER;
  return [...(rows||[])].sort((a,b)=>{
    const sa=String((a&&a[solKey])||'').toLowerCase();
    const sb=String((b&&b[solKey])||'').toLowerCase();
    const ia=order.indexOf(sa); const ib=order.indexOf(sb);
    const ka=ia<0?999:ia; const kb=ib<0?999:ib;
    if(ka!==kb) return ka-kb;
    const ha=String((a&&a[hotelKey])||'');
    const hb=String((b&&b[hotelKey])||'');
    return ha.localeCompare(hb);
  });
}
const EVAL_COLS=[
  {k:'hotel_code', l:'Hotel', kind:''},
  {k:'solution', l:'Solution', kind:''},
  {k:'metres_lineaires', l:'m_lin', kind:''},
  {k:'ca_reel', l:'CA reel', kind:'reel'},
  {k:'ca_pred', l:'CA estime', kind:'pred'},
  {k:'ca_err_abs', l:'|err| CA', kind:'err'},
  {k:'marge_reel', l:'Marge ventes reel', kind:'reel'},
  {k:'marge_pred', l:'Marge ventes estimee', kind:'pred'},
  {k:'marge_err_abs', l:'|err| Marge ventes', kind:'err'},
  {k:'cout_monthly', l:'Cout', kind:''},
  {k:'capex', l:'Capex', kind:''},
  {k:'marge_nette_reel', l:'ROI reel', kind:'reel'},
  {k:'marge_nette_pred', l:'ROI estime', kind:'pred'},
  {k:'payback_months_reel', l:'Amort. reel (mois)', kind:'reel'},
  {k:'payback_months_pred', l:'Amort. estime (mois)', kind:'pred'},
];

function pickMetric(metrics, key){
  if(!metrics||!metrics.length) return null;
  const ordered=[...metrics].sort((a,b)=>{
    const ag=String(a.scope||'').toUpperCase()==='ALL'?0:1;
    const bg=String(b.scope||'').toUpperCase()==='ALL'?0:1;
    return ag-bg;
  });
  for(const m of ordered){
    if(m[key]!=null && !Number.isNaN(Number(m[key]))) return Number(m[key]);
  }
  return null;
}

function normalizeEvalRow(r){
  if(!r) return null;
  if(r.ca_reel!=null || r.ca_pred!=null || (r.hotel_code && 'ca_err_abs' in r)){
    return {
      hotel_code: r.hotel_code,
      solution: r.solution,
      metres_lineaires: r.metres_lineaires,
      ca_reel: r.ca_reel, ca_pred: r.ca_pred, ca_err_abs: r.ca_err_abs,
      marge_reel: r.marge_reel, marge_pred: r.marge_pred, marge_err_abs: r.marge_err_abs,
      cout_monthly: r.cout_monthly, capex: r.capex,
      marge_nette_reel: r.marge_nette_reel, marge_nette_pred: r.marge_nette_pred,
      payback_months_reel: r.payback_months_reel, payback_months_pred: r.payback_months_pred,
    };
  }
  const ca_r=r.montant_ventes_par_mois_reel??r.ca_reel??null;
  const ca_p=r.montant_ventes_par_mois_predit??r.ca_pred??null;
  const ca_e=r.montant_ventes_erreur_absolue??r.ca_err_abs
    ??(ca_r!=null&&ca_p!=null?Math.abs(ca_p-ca_r):null);
  const m_r=r.montant_marge_selon_coef_par_mois_reel??r.marge_reel??r.montant_marge_par_mois_reel??null;
  const m_p=r.montant_marge_selon_coef_par_mois_predite??r.montant_marge_selon_coef_par_mois_predit
    ??r.marge_pred??r.montant_marge_par_mois_predite??r.montant_marge_par_mois_predit??null;
  const m_e=r.montant_marge_selon_coef_erreur_absolue??r.montant_marge_selon_coef_par_mois_erreur_absolue
    ??r.marge_err_abs??(m_r!=null&&m_p!=null?Math.abs(m_p-m_r):null);
  return {
    hotel_code: r.hotel_code??r.HOTEL_CODE,
    solution: r.solution??r.SOLUTION,
    metres_lineaires: r.metres_lineaires??r.m_lin??null,
    ca_reel: ca_r, ca_pred: ca_p, ca_err_abs: ca_e,
    marge_reel: m_r, marge_pred: m_p, marge_err_abs: m_e,
    cout_monthly: r.cout_monthly??null, capex: r.capex??null,
    marge_nette_reel: r.marge_nette_reel??null, marge_nette_pred: r.marge_nette_pred??null,
    payback_months_reel: r.payback_months_reel??null, payback_months_pred: r.payback_months_pred??null,
  };
}

function fmtPb(v){
  if(v==null||v===''||Number.isNaN(Number(v))) return '—';
  return fmt(v,1);
}

function renderEvalTable(preds){
  const rows=sortBySolution((preds||[]).map(normalizeEvalRow).filter(Boolean));
  let h=`<div class="eval-legend">
    <span><i style="background:#7dd3fc"></i> Reel</span>
    <span><i style="background:#c4b5fd"></i> Estime</span>
    <span><i style="background:#f5a524"></i> Erreur</span>
    <span class="muted" style="margin-left:.5rem">€ / mois · amort. en mois</span>
  </div>`;
  h+='<div class="admin-table-wrap"><table class="eval-table"><thead><tr>';
  for(const c of EVAL_COLS) h+=`<th class="${c.kind?('col-'+c.kind):''}">${c.l}</th>`;
  h+='</tr></thead><tbody>';
  for(const r of rows){
    h+='<tr>';
    for(const c of EVAL_COLS){
      const v=r[c.k];
      if(c.k==='solution'){ h+=`<td>${v!=null?tag(v):'—'}</td>`; continue; }
      if(c.k==='hotel_code'){ h+=`<td class="sticky-col"><strong>${v??'—'}</strong></td>`; continue; }
      if(c.k.startsWith('payback_')){
        h+=`<td class="num ${c.kind?('col-'+c.kind):''}">${fmtPb(v)}</td>`;
        continue;
      }
      h+=`<td class="num ${c.kind?('col-'+c.kind):''}">${v==null||v===''?'—':fmt(v)}</td>`;
    }
    h+='</tr>';
  }
  h+='</tbody></table></div>';
  return h;
}

/**
 * Meilleur moteur = plus faible |err| (pas le plus grand CA predit).
 * Un CA surestime peut etre « grand » mais mauvais en evaluation.
 */
function bestEngineByMinErr(row, engines, errPrefix){
  let best=null, bestE=Infinity;
  for(const eng of engines){
    const raw=row[errPrefix+eng];
    if(raw==null||raw==='') continue;
    const e=Number(raw);
    if(Number.isNaN(e)) continue;
    if(e<bestE){ bestE=e; best=eng; }
  }
  return best;
}

function renderCompareTable(rows){
  const engines=['sim_v1','sim_v2','ml'];
  // Connected → Liberty → Simply, puis hotel_code
  const ordered=sortBySolution(rows||[]);
  let h=`<div class="eval-legend">
    <span><i style="background:#7dd3fc"></i> Reel</span>
    <span><i style="background:#c4b5fd"></i> Estime</span>
    <span><i style="background:#f5a524"></i> |err|</span>
    <span class="muted" style="margin-left:.5rem">€ / mois · amort. en mois</span>
  </div>`;
  h+=`<p class="muted" style="margin:.35rem 0 .65rem;font-size:.85rem">
    <strong>Critere d evaluation</strong> : moteur avec la plus faible
    <strong>|erreur| CA</strong> vs reel (pas le CA predit le plus eleve).
  </p>`;
  h+='<div class="admin-table-wrap"><table class="eval-table"><thead><tr>';
  h+='<th>Hotel</th><th>Solution</th><th class="num">m_lin</th>';
  h+='<th class="col-reel">CA reel</th>';
  for(const eng of engines){
    h+=`<th class="col-pred">CA ${eng}</th><th class="col-err">|err| CA</th>`;
  }
  h+='<th title="Moteur avec la plus faible |err| CA vs reel">Meilleur |err| CA</th>';
  h+='<th class="col-reel">Marge ventes reel</th>';
  for(const eng of engines){
    h+=`<th class="col-pred">Marge ventes ${eng}</th>`;
  }
  h+='<th class="num">Cout</th><th class="num">Capex</th>';
  h+='<th class="col-reel">ROI reel</th>';
  h+='<th class="col-reel">Amort. reel</th>';
  for(const eng of engines){
    h+=`<th class="col-pred">ROI ${eng}</th><th class="col-pred">Amort. ${eng}</th>`;
  }
  h+='</tr></thead><tbody>';
  for(const r of ordered){
    // force critere = min |err| CA (ignore un best_ca_engine eventuellement ambigu)
    const bestCa=bestEngineByMinErr(r, engines, 'ca_err_') || r.best_ca_engine;
    h+='<tr>';
    h+=`<td class="sticky-col"><strong>${r.hotel_code??'—'}</strong></td>`;
    h+=`<td>${r.solution!=null?tag(r.solution):'—'}</td>`;
    h+=`<td class="num">${fmt(r.metres_lineaires,1)}</td>`;
    h+=`<td class="num col-reel">${fmt(r.ca_reel)}</td>`;
    for(const eng of engines){
      const best=bestCa===eng;
      // mise en avant sur l erreur, pas sur le CA predit (qui peut etre surestime)
      h+=`<td class="num col-pred">${fmt(r['ca_pred_'+eng])}</td>`;
      h+=`<td class="num col-err"${best?' style="font-weight:800;color:var(--ok)"':''}>${fmt(r['ca_err_'+eng])}</td>`;
    }
    h+=`<td>${bestCa?tag(bestCa):'—'}</td>`;
    h+=`<td class="num col-reel">${fmt(r.marge_reel)}</td>`;
    for(const eng of engines){
      h+=`<td class="num col-pred">${fmt(r['marge_pred_'+eng])}</td>`;
    }
    h+=`<td class="num">${fmt(r.cout_monthly)}</td>`;
    h+=`<td class="num">${fmt(r.capex)}</td>`;
    h+=`<td class="num col-reel">${fmt(r.marge_nette_reel)}</td>`;
    h+=`<td class="num col-reel">${fmtPb(r.payback_months_reel)}</td>`;
    for(const eng of engines){
      h+=`<td class="num col-pred">${fmt(r['marge_nette_pred_'+eng])}</td>`;
      h+=`<td class="num col-pred">${fmtPb(r['payback_months_pred_'+eng])}</td>`;
    }
    h+='</tr>';
  }
  h+='</tbody></table></div>';
  return h;
}

/** MAE par solution. */
function renderBySolution(bySolution, engines){
  const engList=engines||['sim_v1','sim_v2','ml'];
  // Connected → Liberty → Simply (affichage premium d abord)
  const order=['connected','liberty','simply'];
  const sols=Object.keys(bySolution||{});
  if(!sols.length) return '';
  const ordered=[
    ...order.filter(s=>bySolution[s]),
    ...sols.filter(s=>!order.includes(s)).sort(),
  ];
  let h='<h2 style="margin-top:1.1rem">Par solution</h2>';
  h+=`<p class="muted" style="margin:0 0 .65rem;font-size:.85rem">
    Meilleur moteur = <strong>MAE minimale</strong> (erreur moyenne absolue),
    pas le CA predit le plus grand.
  </p>`;
  h+='<div class="grid" style="margin-bottom:.85rem">';
  for(const sol of ordered){
    const block=bySolution[sol]||{};
    // recompute min MAE CA si engines present
    let best=block.best_ca_engine;
    let bestM=block.best_marge_engine;
    const est0=block.engines||{};
    let minCa=Infinity, minMg=Infinity;
    for(const eng of engList){
      const m=est0[eng]||{};
      if(m.mae_ca!=null && Number(m.mae_ca)<minCa){ minCa=Number(m.mae_ca); best=eng; }
      if(m.mae_marge!=null && Number(m.mae_marge)<minMg){ minMg=Number(m.mae_marge); bestM=eng; }
    }
    const hotels=(block.hotels||[]).join(', ')||'—';
    h+=`<div class="card" style="border-color:${best?'rgba(61,214,140,.35)':'var(--line)'}">
      <div class="lbl">${tag(sol)} · n=${block.n_hotels??'—'}</div>
      <div class="val" style="font-size:1.05rem;margin:.25rem 0">min |err| CA : ${best?tag(best):'—'}</div>
      <div class="sub">min |err| marge : ${bestM?tag(bestM):'—'} · ${hotels}</div>
    </div>`;
  }
  h+='</div>';
  // tableau detail MAE par solution × moteur
  h+='<div class="admin-table-wrap"><table class="eval-table"><thead><tr>';
  h+='<th>Solution</th><th class="num">n</th>';
  for(const eng of engList){
    h+=`<th class="num col-err">MAE CA ${eng}</th>`;
  }
  h+='<th title="Moteur avec la plus faible MAE CA">Meilleur |err| CA</th>';
  for(const eng of engList){
    h+=`<th class="num col-err">MAE marge ventes ${eng}</th>`;
  }
  h+='<th title="Moteur avec la plus faible MAE marge">Meilleur |err| marge</th>';
  h+='</tr></thead><tbody>';
  for(const sol of ordered){
    const block=bySolution[sol]||{};
    const est=block.engines||{};
    let bestCa=block.best_ca_engine;
    let bestMg=block.best_marge_engine;
    let minCa=Infinity, minMg=Infinity;
    for(const eng of engList){
      const m=est[eng]||{};
      if(m.mae_ca!=null && Number(m.mae_ca)<minCa){ minCa=Number(m.mae_ca); bestCa=eng; }
      if(m.mae_marge!=null && Number(m.mae_marge)<minMg){ minMg=Number(m.mae_marge); bestMg=eng; }
    }
    h+='<tr>';
    h+=`<td>${tag(sol)}</td>`;
    h+=`<td class="num">${block.n_hotels??'—'}</td>`;
    for(const eng of engList){
      const m=est[eng]||{};
      const isBest=bestCa===eng;
      h+=`<td class="num col-err"${isBest?' style="font-weight:800;color:var(--ok)"':''}>${fmt(m.mae_ca)}</td>`;
    }
    h+=`<td>${bestCa?tag(bestCa):'—'}</td>`;
    for(const eng of engList){
      const m=est[eng]||{};
      const isBest=bestMg===eng;
      h+=`<td class="num col-err"${isBest?' style="font-weight:800;color:var(--ok)"':''}>${fmt(m.mae_marge)}</td>`;
    }
    h+=`<td>${bestMg?tag(bestMg):'—'}</td>`;
    h+='</tr>';
  }
  h+='</tbody></table></div>';
  return h;
}

/** MAE d'un moteur calculee sur ses predictions, par solution. */
function metricsBySolutionFromPreds(preds){
  const rows=(preds||[]).map(normalizeEvalRow).filter(Boolean);
  const by={};
  for(const r of rows){
    const sol=String(r.solution||'').trim().toLowerCase();
    if(!sol) continue;
    if(!by[sol]) by[sol]={ca:[], marge:[], hotels:new Set()};
    if(r.hotel_code) by[sol].hotels.add(r.hotel_code);
    if(r.ca_err_abs!=null && !Number.isNaN(Number(r.ca_err_abs))) by[sol].ca.push(Number(r.ca_err_abs));
    if(r.marge_err_abs!=null && !Number.isNaN(Number(r.marge_err_abs))) by[sol].marge.push(Number(r.marge_err_abs));
  }
  const out={};
  for(const [sol,v] of Object.entries(by)){
    const avg=a=>a.length?a.reduce((x,y)=>x+y,0)/a.length:null;
    out[sol]={
      solution:sol,
      n_hotels:v.hotels.size,
      mae_ca:avg(v.ca),
      mae_marge:avg(v.marge),
      hotels:[...v.hotels],
    };
  }
  return out;
}

function renderEngineBySolution(src, bySol){
  // Connected → Liberty → Simply
  const order=['connected','liberty','simply'];
  const sols=[...order.filter(s=>bySol[s]), ...Object.keys(bySol).filter(s=>!order.includes(s)).sort()];
  if(!sols.length) return '';
  let h='<h2 style="margin-top:1.1rem">MAE par solution</h2>';
  h+='<div class="grid" style="margin-bottom:.75rem">';
  for(const sol of sols){
    const m=bySol[sol];
    h+=`<div class="card"><div class="lbl">${tag(sol)} · ${tag(src)}</div>
      <div class="val" style="font-size:1.15rem">${fmt(m.mae_ca)}</div>
      <div class="sub">n=${m.n_hotels} · MAE marge ventes ${fmt(m.mae_marge)}</div></div>`;
  }
  h+='</div>';
  return h;
}

async function loadEval(src){
  const main=document.getElementById('eval-main');
  main.innerHTML='<p class="muted">Chargement…</p>';
  document.querySelectorAll('#view-eval button[data-src]').forEach(b=>b.classList.toggle('primary', b.dataset.src===src));
  try{
    if(src==='compare'){
      const res=await fetch('/api/eval/compare');
      const data=await res.json();
      if(!data.ok) throw new Error(data.error||'erreur');
      const gm=data.global_metrics||{};
      const engines=data.engines||['sim_v1','sim_v2','ml'];
      let html='<div class="grid">';
      for(const eng of engines){
        const m=gm[eng]||{};
        html+=`<div class="card"><div class="lbl">${tag(eng)} · MAE CA</div><div class="val">${fmt(m.mae_ca)}</div><div class="sub">n=${m.n_hotels??'—'}</div></div>`;
      }
      html+='</div>';
      if((data.missing||[]).length){
        html+=`<div class="err-soft" style="margin-top:.75rem">Manquant : ${(data.missing||[]).join(', ')}</div>`;
      }
      // bloc principal : par solution
      html+=renderBySolution(data.by_solution||{}, engines);
      html+='<h2 style="margin-top:1.25rem">Detail par hotel</h2>';
      html+=renderCompareTable(data.rows||[]);
      main.innerHTML=html;
      return;
    }
    const res=await fetch('/api/eval/'+src);
    const data=await res.json();
    if(!data.ok) throw new Error(data.error||'erreur');
    const maeCa=pickMetric(data.metrics,'mae_ca');
    const maeM=pickMetric(data.metrics,'mae_marge');
    const n=new Set((data.predictions||[]).map(p=>p.hotel_code).filter(Boolean)).size;
    let html=`<div class="grid">
      <div class="card"><div class="lbl">${tag(src)} · MAE CA</div><div class="val">${fmt(maeCa)}</div><div class="sub">n=${n}</div></div>
      <div class="card"><div class="lbl">${tag(src)} · MAE marge ventes</div><div class="val">${fmt(maeM)}</div><div class="sub">PV − PA</div></div>
    </div>`;
    const bySol=metricsBySolutionFromPreds(data.predictions||[]);
    html+=renderEngineBySolution(src, bySol);
    html+='<h2 style="margin-top:1rem">Detail par hotel</h2>';
    html+=renderEvalTable(data.predictions||[]);
    main.innerHTML=html;
  }catch(e){ main.innerHTML=`<div class="errbox">${e.message}</div>`; }
}

document.getElementById('nav-eval').onclick=()=>{ showView('eval'); loadEval('compare'); };
document.getElementById('ds-prev').onclick=()=>{
  if(state.page>1){ state.page--; loadPage(); }
};
document.getElementById('ds-next').onclick=()=>{
  const max=state.totalPages||Infinity;
  if(state.page<max){ state.page++; loadPage(); }
};
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
