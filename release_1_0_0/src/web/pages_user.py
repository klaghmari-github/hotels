"""Page /user — parcours directeur multi-etapes (recherche → infos → leviers → sim)."""

USER_CSS = """
.user-wrap { max-width: 980px; margin: 0 auto; }
.steps { display:flex; gap:.4rem; flex-wrap:wrap; margin-bottom:1.1rem; justify-content:center; }
.steps .step {
  padding:.45rem .9rem; border-radius:999px; border:1px solid var(--line);
  font-size:.85rem; font-weight:600; color:var(--muted); background:#141c28;
  cursor:pointer; user-select:none;
}
.steps .step.on { background:var(--accent); border-color:var(--accent); color:#fff; }
.steps .step.done { border-color:var(--ok); color:var(--ok); }
.panel { display:none; }
.panel.on { display:block; }
.search-box { display:flex; gap:.5rem; margin-bottom:.75rem; }
.search-box input {
  flex:1; padding:.65rem .75rem; border-radius:10px; border:1px solid var(--line);
  background:#101820; color:var(--text); font-size:1rem;
}
.hotel-list { display:flex; flex-direction:column; gap:.4rem; max-height:420px; overflow:auto; }
.hotel-item {
  text-align:left; border:1px solid var(--line); background:var(--card); color:var(--text);
  border-radius:10px; padding:.7rem .85rem; cursor:pointer;
}
.hotel-item:hover { border-color:var(--accent); }
.hotel-item .name { font-weight:700; font-size:1rem; }
.hotel-item .meta { color:var(--muted); font-size:.88rem; margin-top:.15rem; }

/* KPI editables unifies */
.kpi-grid {
  display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:.7rem;
}
.kpi {
  background:#141c28; border:1px solid var(--line); border-radius:12px; padding:.75rem .85rem;
}
.kpi label {
  display:block; font-size:.72rem; text-transform:uppercase; letter-spacing:.04em;
  color:var(--muted); font-weight:700; margin:0 0 .35rem;
}
.kpi input {
  width:100%; border:0; background:transparent; color:var(--text);
  font-size:1.35rem; font-weight:700; padding:0; outline:none;
  font-variant-numeric: tabular-nums;
}
.kpi input:focus { color:var(--accent); }
.kpi .hint { font-size:.75rem; color:var(--muted); margin-top:.25rem; }
.kpi.def .hint { color:var(--warn); }

.section-title {
  font-size:.78rem; text-transform:uppercase; letter-spacing:.05em; color:var(--muted);
  font-weight:700; margin:1.1rem 0 .5rem;
}
.info-grid {
  display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:.55rem;
}
.info-item {
  background:#141c28; border:1px solid var(--line); border-radius:10px; padding:.55rem .7rem;
}
.info-item .k { font-size:.72rem; color:var(--muted); text-transform:uppercase; letter-spacing:.03em; }
.info-item .v { font-size:.95rem; font-weight:600; margin-top:.15rem; word-break:break-word; }
.identity-head {
  display:flex; gap:.85rem; align-items:flex-start; flex-wrap:wrap;
}
.identity-head img.brand-logo {
  height:48px; width:auto; max-width:120px; background:#fff; border-radius:8px; padding:6px 10px;
  object-fit:contain;
}
.bool-pills { display:flex; flex-wrap:wrap; gap:.35rem; }
.bool-pill {
  font-size:.78rem; padding:.35rem .7rem; border-radius:999px; border:1px solid var(--line);
  color:var(--muted); background:#141c28; cursor:pointer; user-select:none;
  transition: border-color .12s, background .12s, color .12s;
}
.bool-pill:hover { border-color:var(--accent); color:var(--text); }
.bool-pill.on { color:#86efac; border-color:rgba(61,214,140,.45); background:rgba(61,214,140,.1); }
.bool-pill.on:hover { border-color:#86efac; }
.muted-hint { font-size:.78rem; color:var(--muted); margin:.25rem 0 .55rem; }
.prox-edit {
  display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:.55rem;
}
.prox-card {
  background:#141c28; border:1px solid var(--line); border-radius:10px; padding:.6rem .75rem;
}
.prox-card .k { font-size:.72rem; color:var(--muted); text-transform:uppercase; letter-spacing:.03em; }
.prox-card .row {
  display:flex; align-items:center; justify-content:space-between; gap:.5rem; margin-top:.35rem;
}
.prox-card .v {
  font-size:1.15rem; font-weight:700; font-variant-numeric:tabular-nums; min-width:2.2rem; text-align:center;
}
.prox-step {
  display:inline-flex; gap:.25rem;
}
.prox-step button {
  width:28px; height:28px; border-radius:8px; border:1px solid var(--line);
  background:#101820; color:var(--text); font-weight:700; cursor:pointer; font-size:1rem; line-height:1;
}
.prox-step button:hover { border-color:var(--accent); color:var(--accent); }
.prox-card.bool-card .row { justify-content:flex-start; gap:.65rem; }

.nav-row { display:flex; gap:.5rem; flex-wrap:wrap; margin-top:1.1rem; justify-content:space-between; }
.nav-row .right { display:flex; gap:.5rem; flex-wrap:wrap; }

.engine-block {
  border:1px solid var(--line); border-radius:14px; background:var(--card);
  padding:1rem 1.05rem; margin-bottom:.85rem;
}
.engine-block h3 { margin:0 0 .55rem; font-size:1.05rem; display:flex; align-items:center; gap:.5rem; }
.reco-box {
  border:1px solid rgba(61,214,140,.35); background:rgba(61,214,140,.08);
  border-radius:12px; padding:.85rem 1rem; margin:.6rem 0 .8rem;
}
.reco-box h4 { margin:0 0 .3rem; font-size:.95rem; color:var(--ok); }
.payback { color:var(--warn); font-weight:700; }
.err-soft {
  margin:.4rem 0; padding:.55rem .7rem; border-radius:8px; font-size:.88rem;
  border:1px solid #5a2a35; background:#2a1520; color:#f5a0b0;
}
.subtabs { display:flex; gap:.4rem; flex-wrap:wrap; margin:0 0 .9rem; }
.subtabs .subtab {
  padding:.4rem .85rem; border-radius:999px; border:1px solid var(--line);
  background:#141c28; color:var(--muted); font-weight:600; font-size:.85rem; cursor:pointer;
}
.subtabs .subtab.on { background:var(--accent); border-color:var(--accent); color:#fff; }
.opt-panel { display:none; }
.opt-panel.on { display:block; }
.opt-progress { font-size:.9rem; color:var(--muted); margin:.5rem 0; }
.mix-chip {
  display:inline-block; font-size:.78rem; padding:.15rem .45rem; margin:.1rem;
  border-radius:6px; background:#1a2433; border:1px solid var(--line);
}
"""

USER_BODY = """
<div class="user-wrap">
  <div class="steps">
    <span class="step on" data-step="1">1 · Hotel</span>
    <span class="step" data-step="2">2 · Infos generales</span>
    <span class="step" data-step="3">3 · Leviers</span>
    <span class="step" data-step="4">4 · Estimation</span>
    <span class="step" data-step="5">5 · Optimisation</span>
  </div>

  <!-- 1 Recherche -->
  <section class="panel on" id="panel-1">
    <div class="card">
      <h2 style="margin-top:0">Choisir un hotel</h2>
      <p class="muted">Code, nom, marque ou ville — ex. <em>paris adagio H8</em></p>
      <div class="search-box">
        <input type="search" id="q" placeholder="paris adagio H8…" autocomplete="off"/>
        <button class="btn primary" type="button" id="btn-search">Rechercher</button>
      </div>
      <div id="results" class="hotel-list"><p class="muted">Saisir une recherche.</p></div>
    </div>
  </section>

  <!-- 2 Infos generales -->
  <section class="panel" id="panel-2">
    <div class="card" id="identity-card"></div>
    <div class="card" style="margin-top:.85rem">
      <div class="section-title">Exploitation</div>
      <div class="kpi-grid" id="kpi-general"></div>
      <div class="section-title">Services</div>
      <p class="muted-hint">Cliquez pour activer / desactiver (modifs en memoire uniquement — la base n'est jamais ecrite).</p>
      <div id="services-box" class="bool-pills"></div>
      <div class="section-title">Proximite (500 m)</div>
      <p class="muted-hint">Ajustez les comptes commerces et la presence d'une plage a 500 m (RAM uniquement).</p>
      <div id="prox-box" class="prox-edit"></div>
      <div class="nav-row">
        <button class="btn" type="button" data-go="1">Retour</button>
        <div class="right">
          <button class="btn primary" type="button" data-go="3">Continuer vers les leviers</button>
        </div>
      </div>
    </div>
  </section>

  <!-- 3 Leviers -->
  <section class="panel" id="panel-3">
    <div class="card">
      <h2 style="margin-top:0">Leviers d'estimation</h2>
      <p class="muted">Exploitation reprise de l'etape precedente (non modifiable ici). Ajustez uniquement le mix type / gammes.</p>
      <div class="section-title">Exploitation (fixe)</div>
      <div class="kpi-grid" id="kpi-levers"></div>
      <div class="section-title">Mix</div>
      <div id="mix_type" class="mix-block"></div>
      <div class="mix-family-grid">
        <div id="mix_gamme_fb" class="mix-block mix-block-fb"></div>
        <div id="mix_gamme_nfb" class="mix-block mix-block-nfb"></div>
      </div>
      <p class="muted mix-hint">UI : chaque famille de gammes somme a 100&nbsp;% (facile a ajuster). <strong>sim_v2 / ML</strong> attendent des parts de gammes sur le <em>total natures</em> (comme en base). A l'envoi : part_globale(gamme) = part_type(F&amp;B ou Non) × part_dans_la_famille — le mix type pondere donc le total transmis.</p>
      <div class="nav-row">
        <button class="btn" type="button" data-go="2">Retour</button>
        <div class="right">
          <button class="btn" type="button" data-go="5">Aller a l'optimisation</button>
          <button class="btn primary" type="button" id="btn-run">Lancer l'estimation</button>
        </div>
      </div>
    </div>
  </section>

  <!-- 4 Estimation -->
  <section class="panel" id="panel-4">
    <div id="sim-out"><p class="muted">En attente…</p></div>
    <div class="nav-row">
      <button class="btn" type="button" data-go="3">Modifier les leviers</button>
      <div class="right">
        <button class="btn" type="button" data-go="5">Optimisation</button>
        <button class="btn primary" type="button" id="btn-rerun">Relancer</button>
      </div>
    </div>
  </section>

  <!-- 5 Optimisation -->
  <section class="panel" id="panel-5">
    <div class="card">
      <h2 style="margin-top:0">Optimisation du mix</h2>
      <div class="subtabs">
        <button type="button" class="subtab on" data-opt-tab="params">Parametres</button>
        <button type="button" class="subtab" data-opt-tab="estim">Estimations</button>
      </div>

      <div class="opt-panel on" id="opt-params">
        <p class="muted">Point de depart = mix des leviers (etape 3). Pour chaque element d'un groupe (type, gammes F&amp;B, gammes Non F&amp;B), on teste 0&nbsp;%…100&nbsp;% par pas de 10&nbsp;% ; l'ecart est redistribue equitabelement sur les autres elements du groupe. Chaque config est evaluee par <strong>sim_v1</strong>, <strong>sim_v2</strong> et <strong>ml</strong> (3 solutions). On retient le plus grand CA estime.</p>
        <div class="section-title">Mix de reference (leviers)</div>
        <div id="opt-baseline-preview" class="muted">Ouvrir les leviers puis revenir ici.</div>
        <div class="nav-row">
          <button class="btn" type="button" data-go="3">Retour leviers</button>
          <div class="right">
            <button class="btn primary" type="button" id="btn-optimize">Lancer l'optimisation</button>
          </div>
        </div>
        <div id="opt-status" class="opt-progress"></div>
      </div>

      <div class="opt-panel" id="opt-estim">
        <div id="opt-out"><p class="muted">Lancez l'optimisation dans l'onglet Parametres.</p></div>
      </div>
    </div>
    <div class="nav-row">
      <button class="btn" type="button" data-go="4">Retour estimation</button>
    </div>
  </section>
</div>
"""

USER_SCRIPT = r"""
const fmt=(n,d=2)=>{if(n==null||n===''||Number.isNaN(Number(n)))return '—';return Number(n).toLocaleString('fr-FR',{maximumFractionDigits:d});};
const tag=s=>`<span class="tag ${(s||'').toString().toLowerCase()}">${s??''}</span>`;
const pctLabel=v=>`${Math.round(v*1000)/10} %`.replace('.0 %',' %');
const EPS=1e-9;

/** Etat en memoire (modifiable avant estimation / optimisation). */
const memory={
  hotel:null, identity:null, exploitation:null, services:null, proximity:null,
  levers:null, defaults_used:{}, typeMix:null, gammeMixFb:null, gammeMixNfb:null,
  optimize:null,
};

/** Classification gammes (alignee ventes TYPE / GAMME). */
const GAMMES_FB = ['alcool','sans alcool','food salee','food sucree','formule'];
const GAMMES_NFB = ['accessoires','cosmetique','jeux enfants','pap','sos','souvenirs'];
const DEFAULT_GAMME_FB = { 'sans alcool':0.40, 'food salee':0.28, 'food sucree':0.18, 'alcool':0.10, 'formule':0.04 };
const DEFAULT_GAMME_NFB = { 'accessoires':0.35, 'sos':0.30, 'cosmetique':0.12, 'pap':0.10, 'jeux enfants':0.08, 'souvenirs':0.05 };

function _normKey(k){ return String(k||'').toLowerCase().replace(/_/g,' ').replace(/\s+/g,' ').trim(); }
function _isGammeFb(key){
  const k=_normKey(key);
  if(GAMMES_FB.includes(k)) return true;
  if(GAMMES_NFB.includes(k)) return false;
  // fallback heuristique
  if(/alcool|food|formule|fresh|dry|boisson/.test(k)) return true;
  return false;
}
/**
 * Split un gamme_mix PLAT (parts du total natures, format sim_v2)
 * en deux familles UI (chaque famille renormalisee a 1).
 */
function splitGammeMix(flat){
  const fb={}, nfb={};
  for(const [k,v] of Object.entries(flat||{})){
    const key=_normKey(k); const val=Math.max(0, Number(v)||0);
    if(_isGammeFb(key)) fb[key]=(fb[key]||0)+val; else nfb[key]=(nfb[key]||0)+val;
  }
  const norm=obj=>{
    const s=Object.values(obj).reduce((a,b)=>a+b,0);
    if(s<=EPS) return null;
    const o={}; for(const [k,v] of Object.entries(obj)) o[k]=v/s; return o;
  };
  return { fb: norm(fb)||{...DEFAULT_GAMME_FB}, nfb: norm(nfb)||{...DEFAULT_GAMME_NFB} };
}
/**
 * UI hierarchique → format sim_v2 / restitution :
 * part_totale(gamme) = weight(type) × part_dans_famille(gamme).
 * Les parts gamme en base sont deja des % du total natures
 * (metric / nombre_natures_global), pas des % du type.
 * type_mix et gamme_mix envoyes doivent chacun sommer a ~1.
 */
function combineGammeMix(typeMixObj, fbObj, nfbObj){
  const tm=typeMixObj||{};
  let wFb=0, wNfb=0;
  for(const [k,v] of Object.entries(tm)){
    const key=_normKey(k).replace('&','');
    if(key.includes('non')) wNfb+=Number(v)||0;
    else if(key.includes('f') && key.includes('b')) wFb+=Number(v)||0;
    else if(key==='f_b'||key==='fb') wFb+=Number(v)||0;
  }
  const tw=wFb+wNfb;
  if(tw>EPS){ wFb/=tw; wNfb/=tw; } else { wFb=0.7; wNfb=0.3; }
  const out={};
  for(const [k,v] of Object.entries(fbObj||{})){
    const key=_normKey(k);
    out[key]=(out[key]||0)+wFb*(Number(v)||0);
  }
  for(const [k,v] of Object.entries(nfbObj||{})){
    const key=_normKey(k);
    out[key]=(out[key]||0)+wNfb*(Number(v)||0);
  }
  const s=Object.values(out).reduce((a,b)=>a+b,0);
  if(s>EPS){ for(const k of Object.keys(out)) out[k]=Math.round((out[k]/s)*1e6)/1e6; }
  return out;
}
/** Alias explicite pour l'envoi simulateur. */
function toGlobalGammeMix(typeMixObj, fbObj, nfbObj){
  return combineGammeMix(typeMixObj, fbObj, nfbObj);
}

// ---------- MixPanel (switch bleu = libre) ----------
class MixPanel {
  constructor(rootId, title, entries){
    this.root=document.getElementById(rootId);
    this.title=title;
    this.items=entries.map(e=>({key:e.key,value:Math.max(0,Number(e.value)||0),locked:false,autoLocked:false}));
    this._normalizeAll(); this.render();
  }
  lockedSum(exceptKey=null){ return this.items.filter(i=>i.locked&&i.key!==exceptKey).reduce((s,i)=>s+i.value,0); }
  freeItems(exceptKey=null){ return this.items.filter(i=>!i.locked&&i.key!==exceptKey); }
  freeMaxPct(key){ return Math.max(0,(1-this.lockedSum(key))*100); }
  setValue(key,pct,{soft=true}={}){
    const it=this.items.find(i=>i.key===key); if(!it||it.locked) return;
    const locked=this.lockedSum(); const max=Math.max(0,1-locked);
    let v=Math.min(max,Math.max(0,Number(pct)/100)); v=Math.round(v*1000)/1000;
    const others=this.freeItems(key);
    if(!others.length){ it.value=max; this._fixFloat(); soft?this._paint():this.render(); return; }
    it.value=v; const rem=Math.max(0,1-locked-v); const each=rem/others.length;
    others.forEach(o=>o.value=each); this._fixFloat(); soft?this._paint():this.render();
  }
  setFree(key,free){
    const it=this.items.find(i=>i.key===key); if(!it) return;
    if(it.autoLocked&&free){ this.items.forEach(i=>{if(i.autoLocked){i.locked=false;i.autoLocked=false;}}); this.render(); return; }
    if(free){ it.locked=false; it.autoLocked=false; this.items.forEach(i=>{if(i.autoLocked){i.locked=false;i.autoLocked=false;}}); }
    else { const keep=it.value; it.locked=true; it.autoLocked=false; it.value=keep; this._autoLockResidual(); }
    this.render();
  }
  _autoLockResidual(){
    this.items.forEach(i=>{if(i.autoLocked){i.locked=false;i.autoLocked=false;}});
    const free=this.items.filter(i=>!i.locked);
    if(free.length===1){ const only=free[0]; only.value=Math.max(0,1-this.lockedSum(only.key)); only.locked=true; only.autoLocked=true; }
  }
  _normalizeAll(){ const s=this.items.reduce((a,i)=>a+i.value,0); if(s<=EPS){const e=1/this.items.length; this.items.forEach(i=>i.value=e);} else this.items.forEach(i=>i.value=i.value/s); }
  _fixFloat(){ const s=this.items.reduce((a,i)=>a+i.value,0); const d=1-s; if(Math.abs(d)<1e-12)return; const free=this.items.filter(i=>!i.locked); const t=free.length?free[free.length-1]:this.items[this.items.length-1]; t.value=Math.max(0,t.value+d); }
  toObject(){ const o={}; this.items.forEach(i=>o[i.key]=Math.round(i.value*1e6)/1e6); return o; }
  _paint(){
    const sum=this.items.reduce((a,i)=>a+i.value,0);
    const sumEl=this.root.querySelector('.mix-sum'); if(sumEl){ sumEl.textContent=`Σ ${pctLabel(sum)}`; sumEl.classList.toggle('warn',Math.abs(sum-1)>=1e-6); }
    for(const it of this.items){
      const row=this.root.querySelector(`.mix-row[data-key="${CSS.escape(it.key)}"]`); if(!row) continue;
      const pct=Math.round(it.value*1000)/10;
      const pctEl=row.querySelector('.mix-pct'); if(pctEl) pctEl.textContent=pctLabel(it.value);
      const range=row.querySelector('input[type=range]');
      if(range){ range.min=0; range.max=100; range.value=String(pct); range.style.setProperty('--pct',`${pct}%`); range.disabled=!!it.locked; }
      row.classList.toggle('locked',!!it.locked); row.classList.toggle('residual',!!it.autoLocked);
      const sw=row.querySelector('input[data-lock]'); if(sw){ sw.checked=!it.locked; sw.disabled=!!it.autoLocked; }
    }
  }
  render(){
    const sum=this.items.reduce((a,i)=>a+i.value,0);
    let html=`<div class="mix-head"><p class="mix-title">${this.title}</p><span class="mix-sum">Σ ${pctLabel(sum)}</span></div>`;
    for(const it of this.items){
      const pct=Math.round(it.value*1000)/10; const free=!it.locked;
      html+=`<div class="mix-row${it.locked?' locked':''}${it.autoLocked?' residual':''}" data-key="${it.key.replace(/"/g,'&quot;')}">
        <div class="mix-label">${it.key}</div><div class="mix-pct">${pctLabel(it.value)}</div>
        <label class="sw"><input type="checkbox" data-lock="${it.key.replace(/"/g,'&quot;')}" ${free?'checked':''} ${it.autoLocked?'disabled':''}/><span class="slider"></span></label>
        <div class="mix-slider-wrap"><input type="range" min="0" max="100" step="0.1" value="${pct}" data-key="${it.key.replace(/"/g,'&quot;')}" ${it.locked?'disabled':''} style="--pct:${pct}%"/></div>
      </div>`;
    }
    this.root.innerHTML=html;
    this.root.querySelectorAll('input[type=range]').forEach(el=>{
      el.addEventListener('input',e=>{ let pct=Number(e.target.value); const max=this.freeMaxPct(e.target.getAttribute('data-key')); if(pct>max){pct=max;e.target.value=String(max);} this.setValue(e.target.getAttribute('data-key'),pct,{soft:true}); });
      el.addEventListener('change',e=>{ let pct=Number(e.target.value); const max=this.freeMaxPct(e.target.getAttribute('data-key')); if(pct>max)pct=max; this.setValue(e.target.getAttribute('data-key'),pct,{soft:false}); });
    });
    this.root.querySelectorAll('input[data-lock]').forEach(el=>{
      el.addEventListener('change',e=>this.setFree(e.target.getAttribute('data-lock'), !!e.target.checked));
    });
  }
}

function setStep(n){
  document.querySelectorAll('.steps .step').forEach(s=>{
    const k=Number(s.dataset.step);
    s.classList.toggle('on', k===n);
    s.classList.toggle('done', k<n);
  });
  document.querySelectorAll('.panel').forEach((p,i)=>p.classList.toggle('on', i===n-1));
  window.scrollTo({top:0, behavior:'smooth'});
}
document.querySelectorAll('.steps .step').forEach(s=>{
  s.onclick=()=>{
    const n=Number(s.dataset.step);
    if(n===1 || (n>1 && memory.hotel)) {
      setStep(n);
      if(n===5) previewOptBaseline();
    }
  };
});
document.querySelectorAll('[data-go]').forEach(b=>b.onclick=()=>{
  const n=Number(b.dataset.go);
  setStep(n);
  if(n===5) previewOptBaseline();
});

function logoUrl(path){
  if(!path) return null;
  let p=String(path).trim().replace(/\\/g,'/').replace(/^\/+/,'');
  if(!p||/^(nan|none|null)$/i.test(p)) return null;
  p=p.replace(/^(?:\.\/)?(?:data\/)?(?:static\/)?marques\//i,'');
  return '/api/marques/logos/'+p.split('/').filter(Boolean).map(encodeURIComponent).join('/');
}

function kpiInput(id, label, value, {step=1, min=null, max=null, hint='', isDefault=false, fmtPct=false}={}){
  const v = value==null||value==='' ? '' : (fmtPct ? Math.round(Number(value)*1000)/10 : value);
  return `<div class="kpi${isDefault?' def':''}">
    <label for="${id}">${label}</label>
    <input id="${id}" type="number" step="${step}" ${min!=null?`min="${min}"`:''} ${max!=null?`max="${max}"`:''} value="${v}"/>
    <div class="hint">${hint}${isDefault?' · defaut (absent en base)':''}</div>
  </div>`;
}

/** KPI lecture seule (choix utilisateur conserve depuis Exploitation). */
function kpiFixed(label, value, {fmtPct=false, digits=2, hint='Issu de l etape Infos generales'}={}){
  let shown='—';
  if(value!=null && value!==''){
    const n=Number(value);
    if(fmtPct){
      const pct = n<=1.5 ? n*100 : n;
      shown = fmt(pct, 1)+' %';
    }else{
      shown = fmt(n, digits);
    }
  }
  return `<div class="kpi" style="opacity:.95">
    <label>${label}</label>
    <div class="val" style="font-size:1.35rem;font-weight:700;font-variant-numeric:tabular-nums">${shown}</div>
    <div class="hint">${hint}</div>
  </div>`;
}

function readNum(id, fallback){
  const el=document.getElementById(id);
  if(!el||el.value==='') return fallback;
  const n=Number(el.value);
  return Number.isNaN(n)?fallback:n;
}

// ---------- Step 1 search ----------
async function search(){
  const q=document.getElementById('q').value.trim();
  const box=document.getElementById('results');
  if(!q){ box.innerHTML='<p class="muted">Saisir une recherche.</p>'; return; }
  box.innerHTML='<p class="muted">Recherche…</p>';
  try{
    const res=await fetch('/api/user/hotels/search?q='+encodeURIComponent(q)+'&limit=40');
    const data=await res.json();
    if(!data.ok) throw new Error(data.error||'erreur');
    const hotels=data.hotels||[];
    if(!hotels.length){ box.innerHTML='<p class="muted">Aucun hotel.</p>'; return; }
    box.innerHTML='';
    for(const h of hotels){
      const b=document.createElement('button'); b.type='button'; b.className='hotel-item';
      b.innerHTML=`<div class="name">${h.hotel_code||''} · ${h.hotel_name||''}</div>
        <div class="meta">${h.hotel_brand||''} · ${h.hotel_city||''} · ${h.hotel_country||''}</div>`;
      b.onclick=()=>selectHotel(h.hotel_code);
      box.appendChild(b);
    }
  }catch(e){ box.innerHTML=`<div class="errbox">${e.message}</div>`; }
}

// ---------- Step 2 load ----------
async function selectHotel(code){
  try{
    const res=await fetch('/api/user/hotels/'+encodeURIComponent(code));
    const data=await res.json();
    if(!data.ok) throw new Error(data.error||'erreur');
    memory.hotel=data.hotel;
    memory.identity=data.identity||{};
    memory.exploitation=data.exploitation||{};
    memory.services=data.services||{};
    memory.proximity=data.proximity_summary||{};
    memory.levers=data.levers||{};
    memory.defaults_used=data.defaults_used||{};
    renderIdentity();
    renderGeneralKpis();
    renderServices();
    renderProximity();
    renderLevers();
    setStep(2);
  }catch(e){ alert(e.message); }
}

function renderIdentity(){
  const id=memory.identity||{};
  const src=logoUrl(id.logo_path);
  document.getElementById('identity-card').innerHTML=`
    <div class="identity-head">
      ${src?`<img class="brand-logo" src="${src}" alt="" onerror="this.remove()"/>`:''}
      <div style="flex:1;min-width:200px">
        <h2 style="margin:0 0 .35rem">${id.hotel_code||''} · ${id.hotel_name||''}</h2>
        <div class="sub">${tag(id.hotel_brand)} · ${id.hotel_city||''} · ${id.hotel_country||''}</div>
        <div class="muted" style="margin-top:.35rem;font-size:.9rem">
          ${[id.hotel_adresse_postale_1, id.hotel_code_postal, id.hotel_city].filter(Boolean).join(' · ')}
        </div>
      </div>
    </div>`;
}

function renderGeneralKpis(){
  const e=memory.exploitation||{};
  const d=memory.defaults_used||{};
  // TO affiche en %
  document.getElementById('kpi-general').innerHTML=
    kpiInput('g_chambres','Chambres', e.hotel_nb_chambres, {step:1,min:1,max:2000, isDefault:!!d.hotel_nb_chambres})
    + kpiInput('g_to','TO annuel (%)', e.hotel_to_annuel, {step:0.1,min:1,max:100, fmtPct:true, isDefault:!!d.hotel_to_annuel})
    + kpiInput('g_guests','Guests / chambre', e.hotel_guests_per_chambre, {step:0.1,min:0.5,max:5, isDefault:!!d.hotel_guests_per_chambre})
    + kpiInput('g_mlin','Metres lineaires', memory.levers?.metres_lineaires??6, {step:0.1,min:0.5,max:50, isDefault:!!d.metres_lineaires});
}

const SERVICE_LABELS={
  hotel_f_b_restaurant:'Restaurant', hotel_f_b_bar:'Bar', hotel_f_b_minibar:'Minibar',
  hotel_f_b_room_service:'Room service', hotel_non_f_b_piscine:'Piscine',
  hotel_non_f_b_salle_de_sport:'Sport', hotel_non_f_b_salles_de_reunion:'Reunions',
  hotel_non_f_b_spa:'Spa', hotel_has_parking:'Parking', hotel_has_wifi:'Wifi',
  hotel_has_clim:'Clim', hotel_has_petit_dejeuner:'Petit-dej',
};

function _isOn(v){
  return v===true || v===1 || v==='1' || (typeof v==='number' && v>0);
}

function toggleService(key){
  if(!memory.services) memory.services={};
  const on=_isOn(memory.services[key]);
  memory.services[key]= on ? 0 : 1;
  renderServices();
}

function renderServices(){
  const s=memory.services||{};
  // ensure keys exist for toggling even if absents en base
  for(const k of Object.keys(SERVICE_LABELS)){
    if(s[k]==null) s[k]=0;
  }
  memory.services=s;
  const box=document.getElementById('services-box');
  let html='';
  for(const [k,lab] of Object.entries(SERVICE_LABELS)){
    const on=_isOn(s[k]);
    html+=`<button type="button" class="bool-pill${on?' on':''}" data-svc="${k}" title="Activer / desactiver (memoire)">
      ${lab}${on?' · on':' · off'}
    </button>`;
  }
  box.innerHTML=html;
  box.querySelectorAll('[data-svc]').forEach(btn=>{
    btn.onclick=()=>toggleService(btn.getAttribute('data-svc'));
  });
}

const PROX_COUNTERS={
  commerce_supermarket_500m:'Supermarches 500m',
  commerce_bakery_500m:'Boulangeries 500m',
  commerce_fast_food_500m:'Fast-food 500m',
};

function bumpProx(key, delta){
  if(!memory.proximity) memory.proximity={};
  const cur=Number(memory.proximity[key]);
  const base=Number.isFinite(cur)?cur:0;
  memory.proximity[key]=Math.max(0, Math.round(base+delta));
  renderProximity();
}

function togglePlage500(){
  if(!memory.proximity) memory.proximity={};
  const on=_isOn(memory.proximity.plage_500m);
  if(on){
    // desactive : pas d'affichage distance
    memory.proximity.plage_500m=0;
  }else{
    memory.proximity.plage_500m=1;
    // distance par defaut ou reprise des donnees (clamp 0–0.5 km si presente a 500 m)
    let d=Number(memory.proximity.plage_distance_km);
    if(!Number.isFinite(d) || d<0) d=0.3;
    if(d>0.5) d=0.3; // hors rayon → defaut proche
    memory.proximity.plage_distance_km=Math.round(d*100)/100;
  }
  renderProximity();
}

function setPlageDistance(val){
  if(!memory.proximity) memory.proximity={};
  let d=Number(val);
  if(!Number.isFinite(d) || d<0) d=0;
  // plage « a 500 m » : distance editable dans [0, 0.5]
  if(d>0.5) d=0.5;
  memory.proximity.plage_distance_km=Math.round(d*100)/100;
  memory.proximity.plage_500m=1;
  const el=document.getElementById('plage-dist-input');
  if(el) el.value=String(memory.proximity.plage_distance_km);
}

function renderProximity(){
  if(!memory.proximity) memory.proximity={};
  const p=memory.proximity;
  // defaults si absents (hotel hors zone / pas de table)
  for(const k of Object.keys(PROX_COUNTERS)){
    if(p[k]==null || p[k]==='') p[k]=0;
    else p[k]=Math.max(0, Number(p[k])||0);
  }
  if(p.plage_500m==null || p.plage_500m==='') p.plage_500m=0;
  else p.plage_500m=_isOn(p.plage_500m)?1:0;

  const box=document.getElementById('prox-box');
  let html='';
  for(const [k,lab] of Object.entries(PROX_COUNTERS)){
    const v=p[k];
    html+=`<div class="prox-card">
      <div class="k">${lab}</div>
      <div class="row">
        <div class="prox-step">
          <button type="button" data-prox-dec="${k}" aria-label="moins">−</button>
          <button type="button" data-prox-inc="${k}" aria-label="plus">+</button>
        </div>
        <div class="v">${fmt(v,0)}</div>
      </div>
    </div>`;
  }
  const plageOn=_isOn(p.plage_500m);
  // distance : uniquement si plage presente (donnee ou defaut 0.3)
  let distHtml='';
  if(plageOn){
    let d=Number(p.plage_distance_km);
    if(!Number.isFinite(d) || d<0) d=0.3;
    if(d>0.5) d=0.3;
    p.plage_distance_km=Math.round(d*100)/100;
    distHtml=`<label class="plage-dist" style="display:flex;align-items:center;gap:.35rem;font-size:.85rem;color:var(--muted)">
      dist.
      <input id="plage-dist-input" type="number" min="0" max="0.5" step="0.01"
        value="${p.plage_distance_km}"
        style="width:4.2rem;padding:.25rem .35rem;border-radius:8px;border:1px solid var(--line);background:#101820;color:var(--text);font-weight:600"/>
      km
    </label>`;
  }
  html+=`<div class="prox-card bool-card">
    <div class="k">Plage a 500 m</div>
    <div class="row" style="flex-wrap:wrap">
      <button type="button" class="bool-pill${plageOn?' on':''}" id="btn-plage-500">
        ${plageOn?'Oui · presente':'Non · absente'}
      </button>
      ${distHtml}
    </div>
  </div>`;
  box.innerHTML=html;
  box.querySelectorAll('[data-prox-inc]').forEach(b=>b.onclick=()=>bumpProx(b.getAttribute('data-prox-inc'), +1));
  box.querySelectorAll('[data-prox-dec]').forEach(b=>b.onclick=()=>bumpProx(b.getAttribute('data-prox-dec'), -1));
  const bp=document.getElementById('btn-plage-500');
  if(bp) bp.onclick=()=>togglePlage500();
  const di=document.getElementById('plage-dist-input');
  if(di){
    di.addEventListener('change',e=>setPlageDistance(e.target.value));
    di.addEventListener('input',e=>setPlageDistance(e.target.value));
  }
}

// ---------- Step 3 leviers ----------
function syncGeneralToLevers(){
  // recopie les KPI generaux vers leviers si l'utilisateur les a modifies
  const ch=readNum('g_chambres', memory.levers?.hotel_nb_chambres??100);
  const toPct=readNum('g_to', (memory.levers?.hotel_to_annuel??0.7)*100);
  const guests=readNum('g_guests', memory.levers?.hotel_guests_per_chambre??1.7);
  const mlin=readNum('g_mlin', memory.levers?.metres_lineaires??6);
  memory.levers={
    ...(memory.levers||{}),
    hotel_nb_chambres: ch,
    hotel_to_annuel: toPct>1.5? toPct/100 : toPct,
    hotel_guests_per_chambre: guests,
    metres_lineaires: mlin,
  };
}

function renderLevers(){
  // fige les valeurs d'exploitation choisies a l'etape 2 (plus d'edition ici)
  syncGeneralToLevers();
  const L=memory.levers||{};
  const toDisp = (L.hotel_to_annuel!=null && L.hotel_to_annuel<=1.5)
    ? L.hotel_to_annuel
    : (Number(L.hotel_to_annuel)||0.7)/100;
  document.getElementById('kpi-levers').innerHTML=
    kpiFixed('Chambres', L.hotel_nb_chambres, {digits:0})
    + kpiFixed('TO annuel', toDisp, {fmtPct:true})
    + kpiFixed('Guests / chambre', L.hotel_guests_per_chambre, {digits:1})
    + kpiFixed('Metres lineaires', L.metres_lineaires, {digits:1});

  const tm=L.type_mix||{ 'F&B':0.7, 'NON F&B':0.3 };
  // prefer structured defaults if API provides them, else split flat gamme_mix
  let fb=L.gamme_mix_fb, nfb=L.gamme_mix_nfb;
  if(!fb || !nfb){
    const split=splitGammeMix(L.gamme_mix||{...DEFAULT_GAMME_FB, ...DEFAULT_GAMME_NFB});
    fb=fb||split.fb; nfb=nfb||split.nfb;
  }
  memory.typeMix=new MixPanel('mix_type','Mix type (F&B vs Non F&B)', Object.entries(tm).map(([k,v])=>({key:k,value:v})));
  memory.gammeMixFb=new MixPanel('mix_gamme_fb','Gammes F&B', Object.entries(fb).map(([k,v])=>({key:k,value:v})));
  memory.gammeMixNfb=new MixPanel('mix_gamme_nfb','Gammes Non F&B', Object.entries(nfb).map(([k,v])=>({key:k,value:v})));
}

// when going to step 3, refresh levers from step 2
document.querySelectorAll('[data-go="3"]').forEach(b=>{
  b.addEventListener('click', ()=>{ renderLevers(); });
});

function payloadFromMemory(){
  // exploitation = choix etape 2 (memoire), pas re-edites en leviers
  syncGeneralToLevers();
  const L=memory.levers||{};
  const ch=Number(L.hotel_nb_chambres ?? readNum('g_chambres', 100));
  let to=Number(L.hotel_to_annuel ?? 0.7);
  if(to>1.5) to=to/100;
  const guests=Number(L.hotel_guests_per_chambre ?? readNum('g_guests', 1.7));
  const mlin=Number(L.metres_lineaires ?? readNum('g_mlin', 6));
  // services / prox : etat RAM (jamais ecrit en base)
  const services={};
  for(const [k,v] of Object.entries(memory.services||{})){
    services[k]=_isOn(v)?1:0;
  }
  const proximity={...(memory.proximity||{})};
  for(const k of Object.keys(PROX_COUNTERS)){
    proximity[k]=Math.max(0, Number(proximity[k])||0);
  }
  proximity.plage_500m=_isOn(proximity.plage_500m)?1:0;
  if(proximity.plage_500m){
    let d=Number(proximity.plage_distance_km);
    if(!Number.isFinite(d) || d<0) d=0.3;
    if(d>0.5) d=0.5;
    proximity.plage_distance_km=Math.round(d*100)/100;
  }else{
    // absente : ne pas envoyer de distance utile
    delete proximity.plage_distance_km;
  }
  return {
    hotel_code: memory.hotel?.hotel_code,
    hotel_nb_chambres: ch,
    hotel_to_annuel: to,
    hotel_guests_per_chambre: guests,
    metres_lineaires: mlin,
    type_mix: memory.typeMix?memory.typeMix.toObject():{},
    // plat format sim_v2 : % du total natures = type × part famille
    gamme_mix: toGlobalGammeMix(
      memory.typeMix?memory.typeMix.toObject():{},
      memory.gammeMixFb?memory.gammeMixFb.toObject():DEFAULT_GAMME_FB,
      memory.gammeMixNfb?memory.gammeMixNfb.toObject():DEFAULT_GAMME_NFB,
    ),
    // UI hierarchique conserve (optimisation / reaffichage)
    gamme_mix_fb: memory.gammeMixFb?memory.gammeMixFb.toObject():{},
    gamme_mix_nfb: memory.gammeMixNfb?memory.gammeMixNfb.toObject():{},
    services,
    proximity,
    solutions: ['simply','liberty','connected'],
  };
}

// ---------- Step 4 estimation (affichage ANNUEL = mensuel moteur × 12) ----------
/** CA / marge / cout annuels (API fournit *_annual, sinon ×12 depuis mensuel). */
function annualOf(r){
  if(!r) return {ca:null, marge:null, cout:null, nette:null};
  const ca = r.ca_annual!=null ? Number(r.ca_annual)
    : (r.ca_monthly!=null ? Number(r.ca_monthly)*12 : null);
  const marge = r.marge_annual!=null ? Number(r.marge_annual)
    : (r.marge_monthly!=null ? Number(r.marge_monthly)*12 : null);
  const cout = r.cout_annual!=null ? Number(r.cout_annual)
    : (r.costs && r.costs.annual_cost!=null ? Number(r.costs.annual_cost)
      : (r.costs && r.costs.monthly_cost!=null ? Number(r.costs.monthly_cost)*12 : null));
  const nette = r.marge_nette_annual!=null ? Number(r.marge_nette_annual)
    : (r.marge_nette_annuelle!=null ? Number(r.marge_nette_annuelle)
      : (r.marge_nette_monthly!=null ? Number(r.marge_nette_monthly)*12 : null));
  return {ca, marge, cout, nette};
}

function engineBlock(eng, block){
  const label = ({ml:'IA (super-modele ml)'})[eng] || eng;
  const rows=block.results||[];
  const reco=block.recommendation||{};
  let html=`<div class="engine-block"><h3>${tag(label)}</h3>`;
  if(reco.recommended){
    const best=reco.best||{};
    const a=annualOf(best);
    html+=`<div class="reco-box">
      <h4>Recommandation : ${tag(reco.recommended)}</h4>
      <p style="margin:0 0 .35rem">${reco.reason||''}</p>
      <div class="muted">CA estime ${fmt(a.ca)} €/an · Marge nette ${fmt(a.nette)} €/an
      · Amort. ${best.payback_months!=null?`<span class="payback">${fmt(best.payback_months,1)} mois (${fmt(best.payback_years,1)} ans)</span>`:'n/a'}</div>
      ${(reco.warnings||[]).map(w=>`<div class="muted" style="margin-top:.3rem">${w}</div>`).join('')}
    </div>`;
  } else {
    html+=`<p class="muted">${reco.reason||'Pas de resultat'}</p>`;
  }
  if(rows.length){
    html+=`<div class="admin-table-wrap" style="border:0"><table><thead><tr>
      <th>Solution</th><th class="num">CA estime / an</th><th class="num">Marge / an</th>
      <th class="num">Cout / an</th><th class="num">Marge nette / an</th>
      <th class="num">Amort. (mois)</th>
    </tr></thead><tbody>`;
    for(const r of rows){
      const a=annualOf(r);
      html+=`<tr>
        <td>${tag(r.solution)}</td>
        <td class="num col-pred">${fmt(a.ca)}</td>
        <td class="num col-pred">${fmt(a.marge)}</td>
        <td class="num">${fmt(a.cout)}</td>
        <td class="num"><strong>${fmt(a.nette)}</strong></td>
        <td class="num payback">${r.payback_months!=null?fmt(r.payback_months,1):'—'}</td>
      </tr>`;
    }
    html+='</tbody></table></div>';
  }
  html+='</div>';
  return html;
}

async function runSim(){
  setStep(4);
  const out=document.getElementById('sim-out');
  out.innerHTML='<p class="muted">Estimation sim_v1 · sim_v2 · IA…</p>';
  try{
    const res=await fetch('/api/user/simulate',{
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify(payloadFromMemory())
    });
    const data=await res.json();
    if(!data.ok) throw new Error(data.error||'erreur');
    const by=data.by_engine||{};
    let html='<p class="muted">Trois moteurs : sim_v1 · sim_v2 · <strong>ml</strong> (super-modele). Montants en <strong>€ / an</strong> (sorties mensuelles des modeles ×&nbsp;12). Regles de couts / reco identiques.</p>';
    for(const eng of ['sim_v1','sim_v2','ml']){
      html+=engineBlock(eng, by[eng]||{results:[], recommendation:{}});
    }
    if((data.errors||[]).length){
      html+='<h2>Alertes</h2>';
      for(const e of data.errors){
        html+=`<div class="err-soft">${e.engine||''} ${e.solution||''}: ${e.error||''}</div>`;
      }
    }
    out.innerHTML=html;
  }catch(e){ out.innerHTML=`<div class="errbox">${e.message}</div>`; }
}

// ---------- Step 5 optimisation ----------
function chipsMix(obj){
  if(!obj) return '—';
  return Object.entries(obj).map(([k,v])=>`<span class="mix-chip">${k}: ${pctLabel(Number(v)||0)}</span>`).join('');
}

function previewOptBaseline(){
  const el=document.getElementById('opt-baseline-preview');
  if(!el) return;
  if(!memory.typeMix){ renderLevers(); }
  const p=payloadFromMemory();
  el.innerHTML=`
    <div style="margin:.35rem 0"><strong>Type</strong><br/>${chipsMix(p.type_mix)}</div>
    <div style="margin:.35rem 0"><strong>Gammes F&B</strong><br/>${chipsMix(p.gamme_mix_fb)}</div>
    <div style="margin:.35rem 0"><strong>Gammes Non F&B</strong><br/>${chipsMix(p.gamme_mix_nfb)}</div>
    <div class="muted" style="margin-top:.4rem">Hotel ${p.hotel_code||'—'} · ${fmt(p.hotel_nb_chambres,0)} ch. · TO ${pctLabel(p.hotel_to_annuel)} · ${fmt(p.metres_lineaires,1)} ml</div>`;
}

function showOptTab(name){
  document.querySelectorAll('[data-opt-tab]').forEach(b=>b.classList.toggle('on', b.dataset.optTab===name));
  document.getElementById('opt-params').classList.toggle('on', name==='params');
  document.getElementById('opt-estim').classList.toggle('on', name==='estim');
}

function renderOptResults(data){
  const out=document.getElementById('opt-out');
  const best=data.best;
  if(!best){
    out.innerHTML=`<div class="errbox">Aucune estimation obtenue.${(data.errors||[]).map(e=>`<div>${e.error||''}</div>`).join('')}</div>`;
    return;
  }
  let html=`<p class="muted">${data.n_scenarios||0} scenarios · ${data.n_trials||0} estimations (pas ${pctLabel(data.step||0.1)})</p>`;
  const bestA=annualOf(best.result||best);
  html+=`<div class="reco-box">
    <h4>Meilleur CA estime (annuel)</h4>
    <p style="margin:0 0 .4rem"><strong>${fmt(bestA.ca!=null?bestA.ca:(best.ca_monthly!=null?best.ca_monthly*12:null))}</strong> €/an · ${tag(best.engine)} · ${tag(best.solution)}</p>
    <div class="muted">Variation : groupe <em>${best.group||'baseline'}</em>${best.varied_key!=null?` · <em>${best.varied_key}</em> → ${pctLabel(best.varied_target)} (base ${pctLabel(best.base_value||0)})`:''}</div>
  </div>`;

  html+='<div class="section-title">Mix optimal</div>';
  html+=`<div style="margin:.35rem 0"><strong>Type</strong><br/>${chipsMix(best.type_mix)}</div>`;
  html+=`<div style="margin:.35rem 0"><strong>Gammes F&B</strong><br/>${chipsMix(best.gamme_mix_fb)}</div>`;
  html+=`<div style="margin:.35rem 0"><strong>Gammes Non F&B</strong><br/>${chipsMix(best.gamme_mix_nfb)}</div>`;

  const reco=data.best_recommendation||{};
  if(reco.recommended){
    const b=reco.best||{};
    const ba=annualOf(b);
    html+=`<div class="reco-box" style="margin-top:1rem">
      <h4>Recommandation solution (meilleur mix)</h4>
      <p style="margin:0 0 .35rem">${tag(reco.recommended)} — ${reco.reason||''}</p>
      <div class="muted">CA ${fmt(ba.ca)} €/an · Marge nette ${fmt(ba.nette)} €/an
      ${b.payback_months!=null?` · Amort. <span class="payback">${fmt(b.payback_months,1)} mois</span>`:''}</div>
      ${(reco.warnings||[]).map(w=>`<div class="muted" style="margin-top:.3rem">${w}</div>`).join('')}
    </div>`;
  }

  html+='<div class="section-title">Detail par moteur (mix optimal)</div>';
  const by=data.best_by_engine||{};
  for(const eng of ['sim_v1','sim_v2','ml']){
    html+=engineBlock(eng, by[eng]||{results:[], recommendation:{}});
  }

  const top=data.top||[];
  if(top.length){
    html+='<div class="section-title">Top CA annuel (toutes configs)</div>';
    html+='<div class="admin-table-wrap" style="border:0"><table><thead><tr>';
    html+='<th>Groupe</th><th>Cle</th><th class="num">Cible</th><th>Moteur</th><th>Solution</th><th class="num">CA / an</th><th class="num">Marge nette / an</th>';
    html+='</tr></thead><tbody>';
    for(const t of top){
      const caA=t.ca_annual!=null?t.ca_annual:(t.ca_monthly!=null?t.ca_monthly*12:null);
      const nA=t.marge_nette_annual!=null?t.marge_nette_annual
        :(t.marge_nette_annuelle!=null?t.marge_nette_annuelle
          :(t.marge_nette_monthly!=null?t.marge_nette_monthly*12:null));
      html+=`<tr>
        <td>${t.group??'—'}</td>
        <td>${t.varied_key??'baseline'}</td>
        <td class="num">${t.varied_target!=null?pctLabel(t.varied_target):'—'}</td>
        <td>${tag(t.engine)}</td>
        <td>${tag(t.solution)}</td>
        <td class="num col-pred">${fmt(caA)}</td>
        <td class="num">${fmt(nA)}</td>
      </tr>`;
    }
    html+='</tbody></table></div>';
  }
  if((data.errors||[]).length){
    html+='<h2>Alertes</h2>';
    for(const e of data.errors.slice(0,20)){
      html+=`<div class="err-soft">${e.scenario||''}: ${e.error||''}</div>`;
    }
  }
  out.innerHTML=html;
}

async function runOptimize(){
  if(!memory.hotel){ alert('Choisissez un hotel d abord.'); return; }
  if(!memory.typeMix) renderLevers();
  previewOptBaseline();
  const status=document.getElementById('opt-status');
  status.textContent='Optimisation en cours (balayage 10 % sur type + gammes) — cela peut prendre 1 a 3 minutes…';
  const btn=document.getElementById('btn-optimize');
  if(btn) btn.disabled=true;
  try{
    const res=await fetch('/api/user/optimize',{
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify(payloadFromMemory())
    });
    const data=await res.json();
    if(!data.ok) throw new Error(data.error||'erreur optimisation');
    memory.optimize=data;
    status.textContent=`Termine : ${data.n_scenarios} scenarios, ${data.n_trials} estimations.`;
    renderOptResults(data);
    showOptTab('estim');
  }catch(e){
    status.textContent='';
    document.getElementById('opt-out').innerHTML=`<div class="errbox">${e.message}</div>`;
    showOptTab('estim');
  }finally{
    if(btn) btn.disabled=false;
  }
}

document.querySelectorAll('[data-opt-tab]').forEach(b=>{
  b.onclick=()=>showOptTab(b.dataset.optTab);
});
document.getElementById('btn-search').onclick=search;
document.getElementById('q').addEventListener('keydown',e=>{ if(e.key==='Enter') search(); });
document.getElementById('btn-run').onclick=runSim;
document.getElementById('btn-rerun').onclick=runSim;
document.getElementById('btn-optimize').onclick=runOptimize;
"""
