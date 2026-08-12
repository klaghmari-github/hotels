"""Page /user — parcours 6 etapes : hotel → infos → choix gammes → mix reco → choisir mix → estimation."""

USER_CSS = """
.user-wrap { max-width: 980px; margin: 0 auto; }
.steps { display:flex; gap:.3rem; flex-wrap:wrap; margin-bottom:1.1rem; justify-content:center; }
.steps .step {
  padding:.4rem .65rem; border-radius:999px; border:1px solid var(--line);
  font-size:.78rem; font-weight:600; color:var(--muted); background:#141c28;
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
.mix-row.mix-off { opacity:.45; }
.mix-row.mix-off .mix-label { text-decoration: line-through; }
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
.progress-wrap {
  margin:.75rem 0 1rem; padding:.85rem 1rem; border-radius:10px;
  background:var(--card-2, #f4f6f8); border:1px solid var(--border, #dde3ea);
}
.progress-wrap .progress-label {
  display:flex; justify-content:space-between; gap:.75rem;
  font-size:.88rem; margin-bottom:.45rem; color:var(--text, #1a1a1a);
}
.progress-wrap .progress-msg { color:var(--muted); font-size:.82rem; margin-top:.4rem; min-height:1.2em; }
.progress-track {
  height:12px; border-radius:999px; background:#d8dee6; overflow:hidden;
}
.progress-fill {
  height:100%; width:0%; border-radius:999px;
  background:linear-gradient(90deg, #1f6feb, #2ea043);
  transition:width .25s ease;
}
.progress-fill.indeterminate {
  width:35% !important;
  animation: progress-slide 1.1s ease-in-out infinite;
}
@keyframes progress-slide {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(320%); }
}
.mix-chip {
  display:inline-block; font-size:.78rem; padding:.15rem .45rem; margin:.1rem;
  border-radius:6px; background:#1a2433; border:1px solid var(--line);
}

/* ----- Mix summary (reco / estimation) ----- */
.mix-summary {
  border:1px solid var(--line);
  border-radius:14px;
  background:linear-gradient(165deg, #121a24 0%, #0e1520 100%);
  padding:1rem 1.1rem 1.05rem;
  margin:0 0 .9rem;
}
.mix-summary-head {
  display:flex; align-items:center; justify-content:space-between;
  gap:.75rem; margin:0 0 .85rem; flex-wrap:wrap;
}
.mix-summary-head h3 {
  margin:0; font-size:.78rem; text-transform:uppercase; letter-spacing:.06em;
  color:var(--muted); font-weight:700;
}
.mix-summary-total {
  font-size:.82rem; font-weight:600; color:var(--text);
  font-variant-numeric:tabular-nums;
}
.mix-summary-stack {
  display:flex; height:14px; border-radius:999px; overflow:hidden;
  background:#1a2433; border:1px solid var(--line); margin:0 0 .55rem;
}
.mix-summary-stack .seg {
  height:100%; min-width:0; transition:width .25s ease;
}
/* F&B = cyan/teal ; Non F&B = ambre/orange — contraste fort a l'oeil */
.mix-summary-stack .seg.fb { background:linear-gradient(90deg, #0e7490, #22d3ee); }
.mix-summary-stack .seg.nfb { background:linear-gradient(90deg, #c2410c, #fb923c); }
.mix-summary-stack .seg.zero { background:transparent; }
.mix-summary-legend {
  display:flex; flex-wrap:wrap; gap:.55rem 1rem; margin:0 0 1rem;
  font-size:.88rem;
}
.mix-summary-legend .leg {
  display:inline-flex; align-items:center; gap:.4rem;
  font-variant-numeric:tabular-nums;
}
.mix-summary-legend .dot {
  width:10px; height:10px; border-radius:3px; flex-shrink:0;
}
.mix-summary-legend .dot.fb { background:#22d3ee; }
.mix-summary-legend .dot.nfb { background:#fb923c; }
.mix-summary-legend .leg.off { opacity:.4; }
.mix-summary-legend .pct { font-weight:700; color:var(--text); }
.mix-summary-legend .lab { color:var(--muted); }

.mix-summary-grid {
  display:grid;
  grid-template-columns:1fr 1fr;
  gap:.85rem;
}
@media (max-width:720px){
  .mix-summary-grid { grid-template-columns:1fr; }
}
.mix-family {
  border:1px solid var(--line);
  border-radius:12px;
  background:#101820;
  padding:.7rem .8rem .75rem;
  min-height:100%;
}
.mix-family.off {
  opacity:.55;
}
.mix-family-head {
  display:flex; align-items:center; justify-content:space-between;
  gap:.5rem; margin:0 0 .55rem;
}
.mix-family-head .title {
  font-size:.8rem; font-weight:700; letter-spacing:.02em;
}
.mix-family.fb .mix-family-head .title { color:#67e8f9; }
.mix-family.nfb .mix-family-head .title { color:#fdba74; }
.mix-family-head .badge {
  font-size:.72rem; font-weight:700; padding:.15rem .45rem;
  border-radius:999px; font-variant-numeric:tabular-nums;
}
.mix-family.fb .badge {
  color:#67e8f9; background:rgba(6,182,212,.14); border:1px solid rgba(34,211,238,.4);
}
.mix-family.nfb .badge {
  color:#fdba74; background:rgba(249,115,22,.14); border:1px solid rgba(251,146,60,.4);
}
.mix-family .badge.zero {
  color:var(--muted); background:#141c28; border-color:var(--line);
}
.mix-bar-row {
  display:grid;
  grid-template-columns:minmax(0,1fr) 4.2rem;
  gap:.45rem .55rem;
  align-items:center;
  margin:.28rem 0;
}
.mix-bar-row.zero { opacity:.38; }
.mix-bar-meta {
  display:flex; flex-direction:column; gap:.12rem; min-width:0;
}
.mix-bar-name {
  font-size:.8rem; font-weight:600; color:var(--text);
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
}
.mix-bar-track {
  height:7px; border-radius:999px; background:#1a2433; overflow:hidden;
  border:1px solid rgba(255,255,255,.04);
}
.mix-bar-fill {
  height:100%; border-radius:999px; width:0%;
  transition:width .3s ease;
}
.mix-family.fb .mix-bar-fill {
  background:linear-gradient(90deg, #0891b2, #22d3ee);
}
.mix-family.nfb .mix-bar-fill {
  background:linear-gradient(90deg, #ea580c, #fb923c);
}
.mix-bar-pct {
  text-align:right; font-size:.82rem; font-weight:700;
  font-variant-numeric:tabular-nums; color:var(--text);
}
.mix-bar-row.zero .mix-bar-pct { color:var(--muted); font-weight:600; }
.mix-family-empty {
  font-size:.82rem; color:var(--muted); padding:.35rem 0 .15rem;
}
"""

USER_BODY = """
<div class="user-wrap">
  <div class="steps">
    <span class="step on" data-step="1">1 · Hotel</span>
    <span class="step" data-step="2">2 · Infos generales</span>
    <span class="step" data-step="3">3 · Choix gammes</span>
    <span class="step" data-step="4">4 · Mix reco</span>
    <span class="step" data-step="5">5 · Choisir mix</span>
    <span class="step" data-step="6">6 · Estimation</span>
  </div>

  <!-- 1 Recherche -->
  <section class="panel on" id="panel-1">
    <div class="card">
      <h2 style="margin-top:0">Choisir un hotel</h2>
      <div class="search-box">
        <input type="search" id="q" placeholder="Code, nom, marque ou ville…" autocomplete="off"/>
        <button class="btn primary" type="button" id="btn-search">Rechercher</button>
      </div>
      <div id="results" class="hotel-list"></div>
    </div>
  </section>

  <!-- 2 Infos generales -->
  <section class="panel" id="panel-2">
    <div class="card" id="identity-card"></div>
    <div class="card" style="margin-top:.85rem">
      <div class="section-title">Exploitation</div>
      <div class="kpi-grid" id="kpi-general"></div>
      <div class="section-title">Services</div>
      <div id="services-box" class="bool-pills"></div>
      <div class="section-title">Proximite (500 m)</div>
      <div id="prox-box" class="prox-edit"></div>
      <div class="nav-row">
        <button class="btn" type="button" data-go="1">Retour</button>
        <div class="right">
          <button class="btn primary" type="button" data-go="3">Continuer</button>
        </div>
      </div>
    </div>
  </section>

  <!-- 3 Choix gammes -->
  <section class="panel" id="panel-3">
    <div class="card">
      <h2 style="margin-top:0">Choix des gammes</h2>
      <div class="section-title">Metres lineaires &amp; perimetre</div>
      <div class="kpi-grid" id="kpi-scope"></div>
      <p class="muted" style="margin:.25rem 0 .85rem;font-size:.88rem">
        Les metres lineaires F&amp;B se reglent ici (exposition physique), avant le choix des gammes.
      </p>
      <div class="section-title">Types et gammes</div>
      <div id="mix_type_scope" class="mix-block"></div>
      <div class="mix-family-grid">
        <div id="mix_gamme_fb_scope" class="mix-block mix-block-fb"></div>
        <div id="mix_gamme_nfb_scope" class="mix-block mix-block-nfb"></div>
      </div>
      <div class="nav-row">
        <button class="btn" type="button" data-go="2">Retour</button>
        <div class="right">
          <button class="btn primary" type="button" id="btn-mix-reco">Calculer le mix recommande</button>
        </div>
      </div>
    </div>
  </section>

  <!-- 4 Mix recommande -->
  <section class="panel" id="panel-4">
    <div id="mix-reco-out"></div>
    <div class="nav-row">
      <button class="btn" type="button" data-go="3">Retour</button>
      <div class="right">
        <button class="btn primary" type="button" id="btn-go-choose-mix" style="display:none">Choisir mon mix</button>
      </div>
    </div>
  </section>

  <!-- 5 Choisir mix -->
  <section class="panel" id="panel-5">
    <div class="card">
      <h2 style="margin-top:0">Choisir mon mix</h2>
      <div class="section-title">Exploitation</div>
      <div class="kpi-grid" id="kpi-edit"></div>
      <div class="section-title">Mix</div>
      <div id="mix_type_edit" class="mix-block"></div>
      <div class="mix-family-grid">
        <div id="mix_gamme_fb_edit" class="mix-block mix-block-fb"></div>
        <div id="mix_gamme_nfb_edit" class="mix-block mix-block-nfb"></div>
      </div>
      <div class="nav-row">
        <button class="btn" type="button" data-go="4">Retour</button>
        <div class="right">
          <button class="btn" type="button" id="btn-reload-mix">Recharger le mix recommande</button>
          <button class="btn primary" type="button" id="btn-estimate">Estimation</button>
        </div>
      </div>
    </div>
  </section>

  <!-- 6 Estimation -->
  <section class="panel" id="panel-6">
    <div id="estimate-out"></div>
    <div class="nav-row">
      <button class="btn" type="button" data-go="5">Retour</button>
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
  levers:null, defaults_used:{},
  /** Etape 3 : perimetre ON/OFF (scope) */
  scopeTypeMix:null, scopeGammeFb:null, scopeGammeNfb:null,
  /** Etape 5 : proportions editables (catalogue complet) */
  editTypeMix:null, editGammeFb:null, editGammeNfb:null,
  optimize:null,
  estimate:null,
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
 * Renormalise un mix pour que la somme soit exactement 1.
 * Residu place sur la plus grande part (evite les alertes sim_v2
 * dues aux arrondis float / multiplications type×gamme).
 */
function normalizeMixExact(obj, defaults){
  const o={};
  for(const [k,v] of Object.entries(obj||{})){
    const key=String(k||'').trim();
    if(!key) continue;
    const val=Math.max(0, Number(v)||0);
    o[key]=(o[key]||0)+val;
  }
  let s=Object.values(o).reduce((a,b)=>a+b,0);
  if(s<=EPS){
    const d=defaults||{};
    for(const [k,v] of Object.entries(d)){
      const key=String(k||'').trim();
      if(!key) continue;
      o[key]=Math.max(0, Number(v)||0);
    }
    s=Object.values(o).reduce((a,b)=>a+b,0);
    if(s<=EPS){
      const keys=Object.keys(o);
      if(!keys.length){
        // dernier recours
        return {...(defaults||{'F&B':0.7,'NON F&B':0.3})};
      }
      const e=1/keys.length;
      keys.forEach(k=>{ o[k]=e; });
      return o;
    }
  }
  for(const k of Object.keys(o)) o[k]=o[k]/s;
  // corrige le residu float sur la plus grande cle
  let maxK=null, maxV=-1, sum=0;
  for(const [k,v] of Object.entries(o)){
    sum+=v;
    if(v>maxV){ maxV=v; maxK=k; }
  }
  if(maxK!=null){
    o[maxK]=Math.max(0, o[maxK]+(1-sum));
  }
  return o;
}

/**
 * UI hierarchique → format sim_v2 / restitution :
 * part_totale(gamme) = weight(type) × part_dans_famille(gamme).
 * type_mix et gamme_mix envoyes doivent chacun sommer a exactement 1.
 */
function combineGammeMix(typeMixObj, fbObj, nfbObj){
  const tm=normalizeMixExact(typeMixObj||{}, {'F&B':0.7,'NON F&B':0.3});
  let wFb=0, wNfb=0;
  for(const [k,v] of Object.entries(tm)){
    const key=_normKey(k).replace('&','');
    if(key.includes('non')) wNfb+=Number(v)||0;
    else if(key.includes('f') && key.includes('b')) wFb+=Number(v)||0;
    else if(key==='f_b'||key==='fb') wFb+=Number(v)||0;
  }
  const tw=wFb+wNfb;
  if(tw>EPS){ wFb/=tw; wNfb/=tw; } else { wFb=0.7; wNfb=0.3; }

  // familles actives uniquement (type a 0 % => pas de contribution gamme)
  const fb = wFb>EPS ? normalizeMixExact(fbObj||{}, DEFAULT_GAMME_FB) : null;
  const nfb = wNfb>EPS ? normalizeMixExact(nfbObj||{}, DEFAULT_GAMME_NFB) : null;

  const out={};
  if(fb){
    for(const [k,v] of Object.entries(fb)){
      const key=_normKey(k);
      out[key]=(out[key]||0)+wFb*(Number(v)||0);
    }
  }
  if(nfb){
    for(const [k,v] of Object.entries(nfb)){
      const key=_normKey(k);
      out[key]=(out[key]||0)+wNfb*(Number(v)||0);
    }
  }
  return normalizeMixExact(out, {...DEFAULT_GAMME_FB, ...DEFAULT_GAMME_NFB});
}
/** Alias explicite pour l'envoi simulateur. */
function toGlobalGammeMix(typeMixObj, fbObj, nfbObj){
  return combineGammeMix(typeMixObj, fbObj, nfbObj);
}

// ---------- MixPanel ----------
// mode 'select' : ON/OFF uniquement (perimetre avant reco)
// mode 'edit'   : proportions + redistribution proportionnelle (apres reco)
class MixPanel {
  constructor(rootId, title, entries, mode, opts){
    this.root=document.getElementById(rootId);
    this.title=title;
    this.mode=mode||'select';
    this.onChange=(opts&&opts.onChange)||null;
    this.allowZeroSum=!!(opts&&opts.allowZeroSum);
    this.cascadeLocked=false; // true si force a 0 par le type parent
    this.items=entries.map(e=>{
      const v=Math.max(0,Number(e.value)||0);
      // enabled: actif dans le perimetre (select) ; locked: fixe en edit
      const enabled = e.enabled!=null ? !!e.enabled : (v>EPS || this.mode==='select');
      return {key:e.key, value:v, enabled, locked:!!e.locked, autoLocked:false};
    });
    if(this.mode==='select') this._equalizeEnabled();
    else this._normalizeAll();
    this.render();
  }
  _notify(){ if(typeof this.onChange==='function') this.onChange(this); }
  setMode(mode){
    this.mode=mode;
    if(mode==='select') this._equalizeEnabled();
    this.render();
  }
  lockedSum(exceptKey=null){ return this.items.filter(i=>i.locked&&i.key!==exceptKey).reduce((s,i)=>s+i.value,0); }
  freeItems(exceptKey=null){ return this.items.filter(i=>!i.locked&&i.enabled!==false&&i.key!==exceptKey); }
  freeMaxPct(key){ return Math.max(0,(1-this.lockedSum(key))*100); }
  /** Parts egales entre items enabled (mode select). */
  _equalizeEnabled(){
    const on=this.items.filter(i=>i.enabled);
    const off=this.items.filter(i=>!i.enabled);
    off.forEach(i=>{ i.value=0; });
    if(!on.length){
      // si cascade par type parent : rester tout a 0 / off
      if(this.cascadeLocked) return;
      this.items.forEach(i=>{ i.enabled=true; }); return this._equalizeEnabled();
    }
    const e=1/on.length;
    on.forEach(i=>{ i.value=e; });
  }
  setValue(key,pct,{soft=true}={}){
    if(this.mode==='select') return; // pas d'edition de parts en select
    if(this.cascadeLocked) return;
    /**
     * Fixe la part de `key` a pct (%).
     * Ecart repercute sur les autres LIBRES enabled, proportionnellement.
     */
    const it=this.items.find(i=>i.key===key); if(!it||it.locked||it.enabled===false) return;
    const locked=this.lockedSum(); const max=Math.max(0,1-locked);
    let v=Math.min(max,Math.max(0,Number(pct)/100)); v=Math.round(v*1000)/1000;
    const others=this.freeItems(key);
    if(!others.length){ it.value=max; this._fixFloat(); soft?this._paint():this.render(); this._notify(); return; }
    const rem=Math.max(0,1-locked-v);
    const othersSum=others.reduce((s,o)=>s+Math.max(0,o.value),0);
    if(othersSum<=EPS){
      const each=rem/others.length;
      others.forEach(o=>{ o.value=each; });
    }else{
      others.forEach(o=>{
        const w=Math.max(0,o.value)/othersSum;
        o.value=rem*w;
      });
    }
    it.value=v;
    this._fixFloat(); soft?this._paint():this.render();
    this._notify();
  }
  setEnabled(key, on){
    if(this.cascadeLocked && on) return; // type parent a 0 %
    const it=this.items.find(i=>i.key===key); if(!it) return;
    it.enabled=!!on;
    if(!it.enabled) it.value=0;
    this._equalizeEnabled();
    this.render();
    this._notify();
  }
  setFree(key,free){
    if(this.mode==='select'){ this.setEnabled(key, free); return; }
    if(this.cascadeLocked) return;
    const it=this.items.find(i=>i.key===key); if(!it) return;
    if(it.autoLocked&&free){ this.items.forEach(i=>{if(i.autoLocked){i.locked=false;i.autoLocked=false;}}); this.render(); this._notify(); return; }
    if(free){ it.locked=false; it.autoLocked=false; this.items.forEach(i=>{if(i.autoLocked){i.locked=false;i.autoLocked=false;}}); }
    else { const keep=it.value; it.locked=true; it.autoLocked=false; it.value=keep; this._autoLockResidual(); }
    this.render();
    this._notify();
  }
  _autoLockResidual(){
    this.items.forEach(i=>{if(i.autoLocked){i.locked=false;i.autoLocked=false;}});
    const free=this.items.filter(i=>!i.locked && i.enabled!==false);
    if(free.length===1){ const only=free[0]; only.value=Math.max(0,1-this.lockedSum(only.key)); only.locked=true; only.autoLocked=true; }
  }
  _normalizeAll(){
    if(this.cascadeLocked){
      this.items.forEach(i=>{ i.value=0; i.enabled=false; i.locked=true; i.autoLocked=false; });
      return;
    }
    const active=this.items.filter(i=>i.enabled!==false);
    const s=active.reduce((a,i)=>a+i.value,0);
    if(s<=EPS){
      // ne pas re-egaliser si le type parent impose 0 % (allowZeroSum)
      if(this.allowZeroSum){ this.items.forEach(i=>{ i.value=0; }); return; }
      const e=1/Math.max(active.length,1); active.forEach(i=>i.value=e);
    }
    else active.forEach(i=>{ i.value=i.value/s; });
    this.items.filter(i=>i.enabled===false).forEach(i=>{ i.value=0; });
  }
  _fixFloat(){ const s=this.items.reduce((a,i)=>a+i.value,0); const d=1-s; if(Math.abs(d)<1e-12)return; const free=this.items.filter(i=>!i.locked&&i.enabled!==false); const t=free.length?free[free.length-1]:this.items[this.items.length-1]; t.value=Math.max(0,t.value+d); }
  /** Force toutes les lignes a 0 (type parent a 0 %). */
  forceAllZero(){
    this.cascadeLocked=true;
    this.allowZeroSum=true;
    this.items.forEach(i=>{
      i.value=0;
      i.enabled=false;
      i.locked=true;
      i.autoLocked=false;
    });
    this.render();
  }
  /** Leve le verrou cascade uniquement s'il etait actif ; restaure des parts si tout a 0. */
  releaseCascade(defaults){
    if(!this.cascadeLocked) return false;
    this.cascadeLocked=false;
    this.allowZeroSum=false;
    this.items.forEach(i=>{
      i.enabled=true;
      i.locked=false;
      i.autoLocked=false;
    });
    const s=this.items.reduce((a,i)=>a+i.value,0);
    if(s<=EPS){
      const src=defaults||{};
      this.items.forEach(i=>{
        i.value=Math.max(0, Number(src[i.key])||0);
      });
      this._normalizeAll();
    }
    this.render();
    return true;
  }
  toObject(){
    // renvoie parts normalisees (0 si desactive en select)
    if(this.mode==='select' && !this.cascadeLocked) this._equalizeEnabled();
    const o={}; this.items.forEach(i=>o[i.key]=Math.round(i.value*1e6)/1e6); return o;
  }
  /** Cles actives (perimetre) pour filtres API. */
  activeKeys(){ return this.items.filter(i=>i.enabled!==false && i.value>EPS).map(i=>i.key); }
  /** Part d'un type F&B ou NON F&B (0 si off / 0 %). */
  typeWeight(which){
    // which: 'fb' | 'nfb'
    for(const it of this.items){
      const k=_normKey(it.key).replace('&','');
      const isNfb=k.includes('non');
      const isFb=!isNfb && ((k.includes('f')&&k.includes('b')) || k==='fb' || k==='f b');
      if(which==='nfb' && isNfb){
        if(this.mode==='select') return it.enabled ? Math.max(it.value, EPS) : 0; // enabled => actif
        return Math.max(0, it.value||0);
      }
      if(which==='fb' && isFb){
        if(this.mode==='select') return it.enabled ? Math.max(it.value, EPS) : 0;
        return Math.max(0, it.value||0);
      }
    }
    return 0;
  }
  _paint(){
    const sum=this.items.reduce((a,i)=>a+i.value,0);
    const sumEl=this.root.querySelector('.mix-sum');
    if(sumEl){
      sumEl.textContent=`Σ ${pctLabel(sum)}`;
      const warn=!(this.allowZeroSum && sum<=EPS) && Math.abs(sum-1)>=1e-6;
      sumEl.classList.toggle('warn', warn);
    }
    for(const it of this.items){
      const row=this.root.querySelector(`.mix-row[data-key="${CSS.escape(it.key)}"]`); if(!row) continue;
      const pct=Math.round(it.value*1000)/10;
      const pctEl=row.querySelector('.mix-pct'); if(pctEl) pctEl.textContent=this.mode==='select'?(it.enabled?'actif':'off'):pctLabel(it.value);
      const range=row.querySelector('input[type=range]');
      if(range){ range.min=0; range.max=100; range.value=String(pct); range.style.setProperty('--pct',`${pct}%`); range.disabled=this.mode==='select'||!!it.locked||it.enabled===false||this.cascadeLocked; }
      row.classList.toggle('locked',!!it.locked); row.classList.toggle('residual',!!it.autoLocked);
      row.classList.toggle('mix-off', it.enabled===false || this.cascadeLocked);
      const sw=row.querySelector('input[data-lock]'); if(sw){ sw.checked=this.mode==='select'?!!it.enabled:!it.locked; sw.disabled=!!it.autoLocked||this.cascadeLocked; }
    }
  }
  render(){
    const sum=this.items.reduce((a,i)=>a+i.value,0);
    let html=`<div class="mix-head"><p class="mix-title">${this.title}</p><span class="mix-sum">${this.mode==='select'?'':`Σ ${pctLabel(sum)}`}</span></div>`;
    for(const it of this.items){
      const pct=Math.round(it.value*1000)/10;
      const on=this.mode==='select'?!!it.enabled:!it.locked;
      const rowOff=it.enabled===false||this.cascadeLocked;
      html+=`<div class="mix-row${it.locked?' locked':''}${it.autoLocked?' residual':''}${rowOff?' mix-off':''}" data-key="${it.key.replace(/"/g,'&quot;')}">
        <div class="mix-label">${it.key}</div>
        <div class="mix-pct">${this.mode==='select'?(it.enabled?'actif':'off'):pctLabel(it.value)}</div>
        <label class="sw">
          <input type="checkbox" data-lock="${it.key.replace(/"/g,'&quot;')}" ${on?'checked':''} ${it.autoLocked||this.cascadeLocked?'disabled':''}/>
          <span class="slider"></span>
        </label>
        ${this.mode==='edit'?`<div class="mix-slider-wrap"><input type="range" min="0" max="100" step="0.1" value="${pct}" data-key="${it.key.replace(/"/g,'&quot;')}" ${it.locked||it.enabled===false||this.cascadeLocked?'disabled':''} style="--pct:${pct}%"/></div>`:''}
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

/**
 * Si type F&B = 0 % (ou off) → toutes les gammes F&B a 0.
 * Idem Non F&B → gammes Non F&B.
 */
function syncTypeGammeCascade(typePanel, fbPanel, nfbPanel){
  if(!typePanel) return;
  const wFb=typePanel.typeWeight('fb');
  const wNfb=typePanel.typeWeight('nfb');
  if(fbPanel){
    if(wFb<=EPS) fbPanel.forceAllZero();
    else fbPanel.releaseCascade(DEFAULT_GAMME_FB);
  }
  if(nfbPanel){
    if(wNfb<=EPS) nfbPanel.forceAllZero();
    else nfbPanel.releaseCascade(DEFAULT_GAMME_NFB);
  }
}

function wireTypeGammeCascade(typePanel, fbPanel, nfbPanel){
  if(!typePanel) return;
  typePanel.onChange=()=>syncTypeGammeCascade(typePanel, fbPanel, nfbPanel);
  syncTypeGammeCascade(typePanel, fbPanel, nfbPanel);
}

function setStep(n){
  document.querySelectorAll('.steps .step').forEach(s=>{
    const k=Number(s.dataset.step);
    if(!k) return;
    s.classList.toggle('on', k===n);
    s.classList.toggle('done', k<n);
  });
  document.querySelectorAll('.panel').forEach((p,i)=>p.classList.toggle('on', i===n-1));
  window.scrollTo({top:0, behavior:'smooth'});
}
function canGoStep(n){
  if(n===1) return true;
  if(!memory.hotel) return false;
  if(n<=3) return true;
  if(n===4) return true; // calcul ou relecture
  if(n===5) return !!(memory.optimize && (memory.optimize.apply_mix || memory.optimize.best));
  if(n===6) return !!(memory.editTypeMix || (memory.optimize && (memory.optimize.apply_mix || memory.optimize.best)));
  return false;
}
document.querySelectorAll('.steps .step[data-step]').forEach(s=>{
  s.onclick=()=>{
    const n=Number(s.dataset.step);
    if(n>=1 && n<=6 && canGoStep(n)){
      if(n===3) renderScopeMix();
      if(n===5){ if(!memory.editTypeMix) applyRecommendedMixFull(); renderEditMix(); }
      setStep(n);
    }
  };
});
document.querySelectorAll('[data-go]').forEach(b=>b.onclick=()=>{
  const n=Number(b.dataset.go);
  if(n>=1 && n<=6){
    if(n===3) renderScopeMix();
    if(n===5){ if(!memory.editTypeMix) applyRecommendedMixFull(); renderEditMix(); }
    setStep(n);
  }
});

function logoUrl(path){
  if(!path) return null;
  let p=String(path).trim().replace(/\\/g,'/').replace(/^\/+/,'');
  if(!p||/^(nan|none|null)$/i.test(p)) return null;
  p=p.replace(/^(?:\.\/)?(?:data\/)?(?:static\/)?marques\//i,'');
  return '/api/marques/logos/'+p.split('/').filter(Boolean).map(encodeURIComponent).join('/');
}

function kpiInput(id, label, value, {step=1, min=null, max=null, isDefault=false, fmtPct=false}={}){
  const v = value==null||value==='' ? '' : (fmtPct ? Math.round(Number(value)*1000)/10 : value);
  return `<div class="kpi${isDefault?' def':''}">
    <label for="${id}">${label}</label>
    <input id="${id}" type="number" step="${step}" ${min!=null?`min="${min}"`:''} ${max!=null?`max="${max}"`:''} value="${v}"/>
  </div>`;
}

/** KPI lecture seule. */
function kpiFixed(label, value, {fmtPct=false, digits=2}={}){
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
  </div>`;
}

function readNum(id, fallback){
  const el=document.getElementById(id);
  if(!el||el.value==='') return fallback;
  const n=Number(el.value);
  return Number.isNaN(n)?fallback:n;
}

// ---------- Step 1 search ----------
let _searchSeq=0;
let _searchTimer=null;

async function search(opts){
  const immediate=!!(opts&&opts.immediate);
  const qEl=document.getElementById('q');
  const box=document.getElementById('results');
  if(!qEl||!box) return;
  const q=qEl.value.trim();
  if(!q){
    box.innerHTML='';
    return;
  }
  // debounce sauf si Enter / Espace / bouton
  if(!immediate){
    if(_searchTimer) clearTimeout(_searchTimer);
    _searchTimer=setTimeout(()=>search({immediate:true}), 280);
    return;
  }
  if(_searchTimer){ clearTimeout(_searchTimer); _searchTimer=null; }

  const seq=++_searchSeq;
  box.innerHTML='<p class="muted">Recherche…</p>';
  try{
    const res=await fetch('/api/user/hotels/search?q='+encodeURIComponent(q)+'&limit=40');
    const data=await res.json();
    if(seq!==_searchSeq) return; // reponse obsolete
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
  }catch(e){
    if(seq!==_searchSeq) return;
    box.innerHTML=`<div class="errbox">${e.message}</div>`;
  }
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
    memory.optimize=null;
    memory.estimate=null;
    memory.editTypeMix=null; memory.editGammeFb=null; memory.editGammeNfb=null;
    memory.scopeTypeMix=null; memory.scopeGammeFb=null; memory.scopeGammeNfb=null;
    renderIdentity();
    renderGeneralKpis();
    renderServices();
    renderProximity();
    renderScopeMix();
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
  // TO affiche en % — metres lineaires sont a l etape 3 (choix gammes)
  document.getElementById('kpi-general').innerHTML=
    kpiInput('g_chambres','Chambres', e.hotel_nb_chambres, {step:1,min:1,max:2000, isDefault:!!d.hotel_nb_chambres})
    + kpiInput('g_to','TO annuel (%)', e.hotel_to_annuel, {step:0.1,min:1,max:100, fmtPct:true, isDefault:!!d.hotel_to_annuel})
    + kpiInput('g_guests','Guests / chambre', e.hotel_guests_per_chambre, {step:0.1,min:0.5,max:5, isDefault:!!d.hotel_guests_per_chambre});
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
    html+=`<button type="button" class="bool-pill${on?' on':''}" data-svc="${k}">${lab}</button>`;
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
        ${plageOn?'Oui':'Non'}
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

// ---------- Catalogues complets types / gammes ----------
const ALL_TYPES = ['F&B', 'NON F&B'];

function _lookupMixVal(obj, key){
  if(!obj) return 0;
  if(obj[key]!=null) return Math.max(0, Number(obj[key])||0);
  const nk=_normKey(key);
  for(const [k,v] of Object.entries(obj)){
    if(_normKey(k)===nk) return Math.max(0, Number(v)||0);
  }
  // aliases type
  if(nk==='f&b' || nk==='fb' || nk==='f b'){
    for(const [k,v] of Object.entries(obj)){
      const kk=_normKey(k).replace('&','');
      if(kk.includes('non')) continue;
      if(kk.includes('f') && kk.includes('b')) return Math.max(0, Number(v)||0);
    }
  }
  if(nk.includes('non')){
    for(const [k,v] of Object.entries(obj)){
      if(_normKey(k).includes('non')) return Math.max(0, Number(v)||0);
    }
  }
  return 0;
}

/** Catalogue complet : toutes les cles, valeur depuis src (0 si absent). */
function fullCatalogEntries(keys, srcObj, {enabledAll=true, prevEnabled=null}={}){
  return keys.map(k=>{
    const v=_lookupMixVal(srcObj, k);
    let en=enabledAll;
    if(prevEnabled && prevEnabled[k]!=null) en=!!prevEnabled[k];
    else if(!enabledAll) en=v>EPS;
    return {key:k, value:v, enabled:en};
  });
}

function prevEnabledMap(panel){
  const m={};
  if(panel&&panel.items) panel.items.forEach(i=>{ m[i.key]=i.enabled; });
  return m;
}

function renderFixedKpis(hostId){
  const el=document.getElementById(hostId);
  if(!el) return;
  syncGeneralToLevers();
  const L=memory.levers||{};
  const toDisp = (L.hotel_to_annuel!=null && L.hotel_to_annuel<=1.5)
    ? L.hotel_to_annuel
    : (Number(L.hotel_to_annuel)||0.7)/100;
  el.innerHTML=
    kpiFixed('Chambres', L.hotel_nb_chambres, {digits:0})
    + kpiFixed('TO annuel', toDisp, {fmtPct:true})
    + kpiFixed('Guests / chambre', L.hotel_guests_per_chambre, {digits:1})
    + kpiFixed('Metres lineaires', L.metres_lineaires, {digits:1});
}

// ---------- Step 3 : choix gammes (ON/OFF, catalogue complet) ----------
function syncGeneralToLevers(){
  // recopie les KPI generaux (+ m_lin etape 3 si present) vers leviers
  const ch=readNum('g_chambres', memory.levers?.hotel_nb_chambres??200);
  const toPct=readNum('g_to', (memory.levers?.hotel_to_annuel??0.7)*100);
  const guests=readNum('g_guests', memory.levers?.hotel_guests_per_chambre??1.7);
  // g_mlin n existe qu a l etape 3 (choix gammes)
  const mlinEl=document.getElementById('g_mlin');
  const mlin=mlinEl
    ? readNum('g_mlin', memory.levers?.metres_lineaires??6)
    : (memory.levers?.metres_lineaires??6);
  memory.levers={
    ...(memory.levers||{}),
    hotel_nb_chambres: ch,
    hotel_to_annuel: toPct>1.5? toPct/100 : toPct,
    hotel_guests_per_chambre: guests,
    metres_lineaires: mlin,
  };
}

/** KPI etape 3 : chambres/TO/guests en lecture, m_lin editable. */
function renderScopeKpis(){
  syncGeneralToLevers();
  const el=document.getElementById('kpi-scope');
  if(!el) return;
  const L=memory.levers||{};
  const d=memory.defaults_used||{};
  const toDisp = (L.hotel_to_annuel!=null && L.hotel_to_annuel<=1.5)
    ? L.hotel_to_annuel
    : (Number(L.hotel_to_annuel)||0.7)/100;
  el.innerHTML=
    kpiFixed('Chambres', L.hotel_nb_chambres, {digits:0})
    + kpiFixed('TO annuel', toDisp, {fmtPct:true})
    + kpiFixed('Guests / chambre', L.hotel_guests_per_chambre, {digits:1})
    + kpiInput(
        'g_mlin',
        'Metres lineaires',
        L.metres_lineaires??6,
        {step:0.1,min:0.5,max:50, isDefault:!!d.metres_lineaires}
      );
  const mlinEl=document.getElementById('g_mlin');
  if(mlinEl){
    const save=()=>{
      const v=readNum('g_mlin', memory.levers?.metres_lineaires??6);
      memory.levers={...(memory.levers||{}), metres_lineaires:v};
    };
    mlinEl.addEventListener('change', save);
    mlinEl.addEventListener('input', save);
  }
}

function renderScopeMix(){
  renderScopeKpis();
  const L=memory.levers||{};
  const tm=L.type_mix||{ 'F&B':0.7, 'NON F&B':0.3 };
  let fb=L.gamme_mix_fb, nfb=L.gamme_mix_nfb;
  if(!fb || !nfb){
    const split=splitGammeMix(L.gamme_mix||{...DEFAULT_GAMME_FB, ...DEFAULT_GAMME_NFB});
    fb=fb||split.fb; nfb=nfb||split.nfb;
  }
  // catalogue complet toujours ; conserver ON/OFF precedent si present
  const peT=prevEnabledMap(memory.scopeTypeMix);
  const peF=prevEnabledMap(memory.scopeGammeFb);
  const peN=prevEnabledMap(memory.scopeGammeNfb);
  // premiere visite : tout actif (valeur >0 ou defaut)
  const first=!memory.scopeTypeMix;
  memory.scopeTypeMix=new MixPanel('mix_type_scope','Types (F&B vs Non F&B)',
    fullCatalogEntries(ALL_TYPES, tm, {enabledAll:true, prevEnabled:first?null:peT}), 'select');
  memory.scopeGammeFb=new MixPanel('mix_gamme_fb_scope','Gammes F&B',
    fullCatalogEntries(GAMMES_FB, fb, {enabledAll:true, prevEnabled:first?null:peF}), 'select');
  memory.scopeGammeNfb=new MixPanel('mix_gamme_nfb_scope','Gammes Non F&B',
    fullCatalogEntries(GAMMES_NFB, nfb, {enabledAll:true, prevEnabled:first?null:peN}), 'select');
  wireTypeGammeCascade(memory.scopeTypeMix, memory.scopeGammeFb, memory.scopeGammeNfb);
}

// ---------- Step 5 : choisir mix (catalogue complet, % editables, 0 % hors reco) ----------
function recommendedMixSource(data){
  const src=data||memory.optimize;
  if(!src) return null;
  return src.apply_mix||(src.best?{
    type_mix:src.best.type_mix,
    gamme_mix_fb:src.best.gamme_mix_fb,
    gamme_mix_nfb:src.best.gamme_mix_nfb,
    gamme_mix:src.best.gamme_mix,
  }:null);
}

function applyRecommendedMixFull(data){
  /** Precharge le mix reco sur le catalogue COMPLET (0 % hors selection moteur). */
  const am=recommendedMixSource(data);
  const L=memory.levers||{};
  let tm=am?.type_mix || L.type_mix || { 'F&B':0.7, 'NON F&B':0.3 };
  let fb=am?.gamme_mix_fb, nfb=am?.gamme_mix_nfb;
  if(!fb || !nfb){
    const split=splitGammeMix(am?.gamme_mix || L.gamme_mix || {...DEFAULT_GAMME_FB, ...DEFAULT_GAMME_NFB});
    fb=fb||split.fb; nfb=nfb||split.nfb;
  }
  // construire objets complets avec 0 pour absents
  const tmFull={}; for(const k of ALL_TYPES) tmFull[k]=_lookupMixVal(tm, k);
  const fbFull={}; for(const k of GAMMES_FB) fbFull[k]=_lookupMixVal(fb, k);
  const nfbFull={}; for(const k of GAMMES_NFB) nfbFull[k]=_lookupMixVal(nfb, k);
  // renormaliser si somme nulle (fallback defauts)
  const renorm=(obj, def)=>{
    const s=Object.values(obj).reduce((a,b)=>a+b,0);
    if(s>EPS){ for(const k of Object.keys(obj)) obj[k]=obj[k]/s; }
    else{ for(const k of Object.keys(def)) obj[k]=def[k]||0; }
    return obj;
  };
  renorm(tmFull, {'F&B':0.7,'NON F&B':0.3});
  // cascade : type a 0 % => gammes famille a 0 %
  if(_lookupMixVal(tmFull,'F&B')<=EPS){
    for(const k of GAMMES_FB) fbFull[k]=0;
  }else{
    renorm(fbFull, DEFAULT_GAMME_FB);
  }
  if(_lookupMixVal(tmFull,'NON F&B')<=EPS){
    for(const k of GAMMES_NFB) nfbFull[k]=0;
  }else{
    renorm(nfbFull, DEFAULT_GAMME_NFB);
  }
  if(!memory.levers) memory.levers={};
  memory.levers.type_mix=tmFull;
  memory.levers.gamme_mix_fb=fbFull;
  memory.levers.gamme_mix_nfb=nfbFull;
  memory.levers.gamme_mix=toGlobalGammeMix(tmFull, fbFull, nfbFull);
  renderEditMix();
  updateReloadMixButton();
  return true;
}

function renderEditMix(){
  renderFixedKpis('kpi-edit');
  const L=memory.levers||{};
  const tm=L.type_mix||{ 'F&B':0.7, 'NON F&B':0.3 };
  let fb=L.gamme_mix_fb, nfb=L.gamme_mix_nfb;
  if(!fb || !nfb){
    const split=splitGammeMix(L.gamme_mix||{...DEFAULT_GAMME_FB, ...DEFAULT_GAMME_NFB});
    fb=fb||split.fb; nfb=nfb||split.nfb;
  }
  // cascade donnees : zero les familles dont le type est a 0
  const fbOff=_lookupMixVal(tm,'F&B')<=EPS;
  const nfbOff=_lookupMixVal(tm,'NON F&B')<=EPS;
  if(fbOff){ fb={}; for(const k of GAMMES_FB) fb[k]=0; }
  if(nfbOff){ nfb={}; for(const k of GAMMES_NFB) nfb[k]=0; }
  // TOUS les types/gammes, enabled=true meme a 0 % (editables)
  memory.editTypeMix=new MixPanel('mix_type_edit','Types (F&B vs Non F&B)',
    fullCatalogEntries(ALL_TYPES, tm, {enabledAll:true}), 'edit');
  memory.editGammeFb=new MixPanel('mix_gamme_fb_edit','Gammes F&B',
    fullCatalogEntries(GAMMES_FB, fb, {enabledAll:true}), 'edit', {allowZeroSum:fbOff});
  memory.editGammeNfb=new MixPanel('mix_gamme_nfb_edit','Gammes Non F&B',
    fullCatalogEntries(GAMMES_NFB, nfb, {enabledAll:true}), 'edit', {allowZeroSum:nfbOff});
  wireTypeGammeCascade(memory.editTypeMix, memory.editGammeFb, memory.editGammeNfb);
  updateReloadMixButton();
}

/**
 * Payload simulateur / optim.
 * which: 'scope' (etape 3 → mix reco) | 'edit' (etape 5 → estimation)
 */
function payloadFromMemory(which){
  which=which||'edit';
  syncGeneralToLevers();
  const L=memory.levers||{};
  const ch=Number(L.hotel_nb_chambres ?? readNum('g_chambres', 200));
  let to=Number(L.hotel_to_annuel ?? 0.7);
  if(to>1.5) to=to/100;
  const guests=Number(L.hotel_guests_per_chambre ?? readNum('g_guests', 1.7));
  const mlin=Number(L.metres_lineaires ?? readNum('g_mlin', 6));
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
    delete proximity.plage_distance_km;
  }
  let typeP, fbP, nfbP;
  if(which==='scope'){
    if(!memory.scopeTypeMix) renderScopeMix();
    typeP=memory.scopeTypeMix?memory.scopeTypeMix.toObject():{};
    fbP=memory.scopeGammeFb?memory.scopeGammeFb.toObject():DEFAULT_GAMME_FB;
    nfbP=memory.scopeGammeNfb?memory.scopeGammeNfb.toObject():DEFAULT_GAMME_NFB;
  }else{
    if(!memory.editTypeMix) applyRecommendedMixFull();
    typeP=memory.editTypeMix?memory.editTypeMix.toObject():{};
    fbP=memory.editGammeFb?memory.editGammeFb.toObject():DEFAULT_GAMME_FB;
    nfbP=memory.editGammeNfb?memory.editGammeNfb.toObject():DEFAULT_GAMME_NFB;
  }
  // type toujours somme 1
  typeP=normalizeMixExact(typeP, {'F&B':0.7,'NON F&B':0.3});
  const wFb=_lookupMixVal(typeP,'F&B');
  const wNfb=_lookupMixVal(typeP,'NON F&B');
  // cascade + renorm familles actives (type a 0 % => gammes a 0, pas envoye comme mix plat nul)
  if(wFb<=EPS){
    fbP={}; for(const k of GAMMES_FB) fbP[k]=0;
  }else{
    fbP=normalizeMixExact(fbP, DEFAULT_GAMME_FB);
  }
  if(wNfb<=EPS){
    nfbP={}; for(const k of GAMMES_NFB) nfbP[k]=0;
  }else{
    nfbP=normalizeMixExact(nfbP, DEFAULT_GAMME_NFB);
  }
  // mix plat sim_v2 : toujours somme exacte 1
  const gammeP=toGlobalGammeMix(typeP, fbP, nfbP);
  return {
    hotel_code: memory.hotel?.hotel_code,
    hotel_nb_chambres: ch,
    hotel_to_annuel: to,
    hotel_guests_per_chambre: guests,
    metres_lineaires: mlin,
    type_mix: typeP,
    gamme_mix: gammeP,
    gamme_mix_fb: fbP,
    gamme_mix_nfb: nfbP,
    services,
    proximity,
    // Affichage / estimation : Connected → Liberty → Simply
    solutions: ['connected','liberty','simply'],
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
  // ROI = marge ventes (PV − PA) − couts solution
  const roi = r.roi_annual!=null ? Number(r.roi_annual)
    : (r.marge_nette_annual!=null ? Number(r.marge_nette_annual)
      : (r.marge_nette_annuelle!=null ? Number(r.marge_nette_annuelle)
        : (r.roi_monthly!=null ? Number(r.roi_monthly)*12
          : (r.marge_nette_monthly!=null ? Number(r.marge_nette_monthly)*12 : null))));
  return {ca, marge, cout, roi, nette: roi};
}

/** Ordre d affichage solutions : Connected → Liberty → Simply (plus chic d abord). */
const SOLUTION_DISPLAY_ORDER=['connected','liberty','simply'];
function sortRowsBySolution(rows){
  const order=SOLUTION_DISPLAY_ORDER;
  return [...(rows||[])].sort((a,b)=>{
    const sa=String(a&&a.solution||'').toLowerCase();
    const sb=String(b&&b.solution||'').toLowerCase();
    const ia=order.indexOf(sa); const ib=order.indexOf(sb);
    const ka=ia<0?999:ia; const kb=ib<0?999:ib;
    if(ka!==kb) return ka-kb;
    return sa.localeCompare(sb);
  });
}

function engineBlock(eng, block){
  const label = ({ml:'ML', sim_v1:'sim_v1', sim_v2:'sim_v2'})[eng] || eng;
  const rows=sortRowsBySolution(block.results||[]);
  const reco=block.recommendation||{};
  let html=`<div class="engine-block"><h3>${tag(label)}</h3>`;
  if(reco.recommended){
    const best=reco.best||{};
    const a=annualOf(best);
    html+=`<div class="reco-box">
      <h4>Recommandation : ${tag(reco.recommended)}</h4>
      <div class="muted">CA ${fmt(a.ca)} €/an · ROI ${fmt(a.roi)} €/an
      · Amort. ${best.payback_months!=null?`<span class="payback">${fmt(best.payback_months,1)} mois (${fmt(best.payback_years,1)} ans)</span>`:'n/a'}</div>
    </div>`;
  } else {
    html+=`<p class="muted">Pas de resultat</p>`;
  }
  if(rows.length){
    html+=`<div class="admin-table-wrap" style="border:0"><table><thead><tr>
      <th>Solution</th><th class="num">CA estime / an</th><th class="num">Marge ventes / an</th>
      <th class="num">Cout / an</th><th class="num">ROI / an</th>
      <th class="num">Amort. (mois)</th>
    </tr></thead><tbody>`;
    for(const r of rows){
      const a=annualOf(r);
      html+=`<tr>
        <td>${tag(r.solution)}</td>
        <td class="num col-pred">${fmt(a.ca)}</td>
        <td class="num col-pred">${fmt(a.marge)}</td>
        <td class="num">${fmt(a.cout)}</td>
        <td class="num"><strong>${fmt(a.roi)}</strong></td>
        <td class="num payback">${r.payback_months!=null?fmt(r.payback_months,1):'—'}</td>
      </tr>`;
    }
    html+='</tbody></table></div>';
  }
  html+='</div>';
  return html;
}

/** Nettoie le message de progression (pas de detail moteur). */
function progressMessage(raw){
  let m=String(raw||'').trim();
  if(!m) return 'Calcul…';
  // masquer references techniques sim_v1 / sim_v2 / ml
  m=m.replace(/\s*\(?\s*sim_v1\s*[·/,]\s*sim_v2\s*[·/,]\s*ml\s*\)?/gi,'');
  m=m.replace(/\bsim_v[12]\b/gi,'').replace(/\bml\b/gi,'');
  m=m.replace(/\s{2,}/g,' ').replace(/\s+([,.;:…])/g,'$1').trim();
  if(!m || /^[\-–—·,/]+$/.test(m)) return 'Calcul…';
  return m;
}

/** Affiche une barre de progression reelle dans un conteneur. */
function renderProgressBar(host, {pct=0, message='', indeterminate=false}={}){
  if(!host) return;
  let wrap=host.querySelector('.progress-wrap');
  if(!wrap){
    host.innerHTML=`<div class="progress-wrap" data-testid="progress-wrap">
      <div class="progress-label"><span class="progress-title">Calcul</span><span class="progress-pct">0 %</span></div>
      <div class="progress-track"><div class="progress-fill" data-testid="progress-fill"></div></div>
      <div class="progress-msg" data-testid="progress-msg"></div>
    </div>`;
    wrap=host.querySelector('.progress-wrap');
  }
  const fill=wrap.querySelector('.progress-fill');
  const pctEl=wrap.querySelector('.progress-pct');
  const msgEl=wrap.querySelector('.progress-msg');
  const p=Math.max(0, Math.min(100, Number(pct)||0));
  if(indeterminate){
    fill.classList.add('indeterminate');
    fill.style.width='35%';
    if(pctEl) pctEl.textContent='…';
  }else{
    fill.classList.remove('indeterminate');
    fill.style.width=`${p}%`;
    if(pctEl) pctEl.textContent=`${Math.round(p*10)/10} %`;
  }
  if(msgEl) msgEl.textContent=progressMessage(message);
}

/**
 * Lance un job long (optimize) et poll jusqu'a done/error.
 * Retourne le result du job.
 */
async function runJobWithProgress(startUrl, payload, progressHost, {pollMs=400}={}){
  renderProgressBar(progressHost, {pct:0, message:'Calcul…', indeterminate:true});
  const startRes=await fetch(startUrl,{
    method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify(payload)
  });
  const start=await startRes.json();
  if(!start.ok && !start.job_id) throw new Error(start.error||'echec demarrage job');
  const jobId=start.job_id;
  renderProgressBar(progressHost, {
    pct:start.pct||0,
    message:start.message||'Calcul…',
    indeterminate:!(start.total>1),
  });

  const deadline=Date.now()+15*60*1000; // 15 min max
  while(Date.now()<deadline){
    await new Promise(r=>setTimeout(r, pollMs));
    const stRes=await fetch(`/api/user/jobs/${encodeURIComponent(jobId)}`);
    const st=await stRes.json();
    if(!st.ok && st.status!=='running' && st.status!=='pending' && st.status!=='done'){
      throw new Error(st.error||'job en erreur');
    }
    renderProgressBar(progressHost, {
      pct:st.pct||0,
      message:st.message||'Calcul…',
      indeterminate:st.status==='pending'||(st.total<=1 && st.status==='running'),
    });
    if(st.status==='done'){
      renderProgressBar(progressHost, {pct:100, message:'Termine'});
      if(!st.result) throw new Error('Job termine sans resultat');
      return st.result;
    }
    if(st.status==='error'){
      throw new Error(st.error||'erreur job');
    }
  }
  throw new Error('Delai depasse (job trop long)');
}

function chipsMix(obj){
  if(!obj) return '—';
  return Object.entries(obj).map(([k,v])=>`<span class="mix-chip">${k}: ${pctLabel(Number(v)||0)}</span>`).join('');
}

function chipsMixFull(keys, obj){
  const o={};
  for(const k of keys) o[k]=_lookupMixVal(obj, k);
  return chipsMix(o);
}

/**
 * Affichage ergonomique du mix (type + gammes) pour reco / estimation.
 * Respecte la cascade : type a 0 % => gammes famille a 0 % visuellement.
 */
function renderMixSummary(typeMix, fbMix, nfbMix, {title='Mix'}={}){
  const wFb=Math.max(0, _lookupMixVal(typeMix, 'F&B'));
  const wNfb=Math.max(0, _lookupMixVal(typeMix, 'NON F&B'));
  const tw=wFb+wNfb;
  const pFb=tw>EPS ? wFb/tw : 0;
  const pNfb=tw>EPS ? wNfb/tw : 0;
  const fbOn=pFb>EPS;
  const nfbOn=pNfb>EPS;

  const rows=(keys, src, familyOn)=>{
    const list=keys.map(k=>{
      let v=familyOn ? _lookupMixVal(src, k) : 0;
      return {key:k, value:Math.max(0, Number(v)||0)};
    });
    // renormalise pour la barre (parts dans la famille) si famille active
    if(familyOn){
      const s=list.reduce((a,r)=>a+r.value,0);
      if(s>EPS) list.forEach(r=>{ r.share=r.value/s; });
      else list.forEach(r=>{ r.share=0; });
    }else{
      list.forEach(r=>{ r.share=0; });
    }
    // tri : non nuls d'abord (desc), puis zeros
    list.sort((a,b)=>{
      if(a.share<=EPS && b.share>EPS) return 1;
      if(b.share<=EPS && a.share>EPS) return -1;
      return b.share-a.share;
    });
    return list;
  };

  const fbRows=rows(GAMMES_FB, fbMix, fbOn);
  const nfbRows=rows(GAMMES_NFB, nfbMix, nfbOn);

  const familyBlock=(kind, label, typePct, items, on)=>{
    const badge=on
      ? `<span class="badge">${pctLabel(typePct)}</span>`
      : `<span class="badge zero">0 %</span>`;
    let body='';
    if(!on){
      body=`<div class="mix-family-empty">Inactif</div>`;
    }else{
      for(const r of items){
        const zero=r.share<=EPS;
        const pct=Math.round(r.share*1000)/10;
        body+=`<div class="mix-bar-row${zero?' zero':''}">
          <div class="mix-bar-meta">
            <div class="mix-bar-name">${r.key}</div>
            <div class="mix-bar-track"><div class="mix-bar-fill" style="width:${pct}%"></div></div>
          </div>
          <div class="mix-bar-pct">${pctLabel(r.share)}</div>
        </div>`;
      }
    }
    return `<div class="mix-family ${kind}${on?'':' off'}">
      <div class="mix-family-head"><span class="title">${label}</span>${badge}</div>
      ${body}
    </div>`;
  };

  const segFb=Math.round(pFb*1000)/10;
  const segNfb=Math.round(pNfb*1000)/10;

  return `<div class="mix-summary">
    <div class="mix-summary-head">
      <h3>${title}</h3>
      <span class="mix-summary-total">F&amp;B ${pctLabel(pFb)} · Non F&amp;B ${pctLabel(pNfb)}</span>
    </div>
    <div class="mix-summary-stack" aria-hidden="true">
      <div class="seg fb${pFb<=EPS?' zero':''}" style="width:${segFb}%"></div>
      <div class="seg nfb${pNfb<=EPS?' zero':''}" style="width:${segNfb}%"></div>
    </div>
    <div class="mix-summary-legend">
      <span class="leg${fbOn?'':' off'}"><span class="dot fb"></span><span class="lab">F&amp;B</span> <span class="pct">${pctLabel(pFb)}</span></span>
      <span class="leg${nfbOn?'':' off'}"><span class="dot nfb"></span><span class="lab">Non F&amp;B</span> <span class="pct">${pctLabel(pNfb)}</span></span>
    </div>
    <div class="mix-summary-grid">
      ${familyBlock('fb','Gammes F&B', pFb, fbRows, fbOn)}
      ${familyBlock('nfb','Gammes Non F&B', pNfb, nfbRows, nfbOn)}
    </div>
  </div>`;
}

// ---------- Step 4 : mix recommande (job product_rank) ----------
async function runMixReco(){
  setStep(4);
  const out=document.getElementById('mix-reco-out');
  const goBtn=document.getElementById('btn-go-choose-mix');
  if(goBtn) goBtn.style.display='none';
  out.innerHTML='';
  try{
    const payload=payloadFromMemory('scope');
    payload.method='product_rank';
    const data=await runJobWithProgress('/api/user/jobs/optimize', payload, out);
    if(!data.ok) throw new Error(data.error||'erreur');
    memory.optimize=data;
    // pre-prepare le mix edit (catalogue complet + 0 %) sans afficher encore
    applyRecommendedMixFull(data);

    let html='';
    if(data.best){
      const best=data.best;
      const bestA=annualOf(best.result||best);
      html+=`<div class="reco-box"><h4>Mix &amp; CA recommandes</h4>
        <p style="margin:0 0 .65rem"><strong>${fmt(bestA.ca!=null?bestA.ca:(best.ca_monthly!=null?best.ca_monthly*12:null))}</strong> €/an · ${tag(best.solution)}</p>
        ${renderMixSummary(best.type_mix, best.gamme_mix_fb, best.gamme_mix_nfb, {title:'Mix recommande'})}
      </div>`;
    }
    const by=data.best_by_engine||{};
    for(const eng of ['sim_v1','sim_v2','ml']){
      html+=engineBlock(eng, by[eng]||{results:[], recommendation:{}});
    }
    if((data.errors||[]).length){
      html+='<h2>Alertes</h2>';
      for(const e of data.errors){
        html+=`<div class="err-soft">${e.scenario||e.engine||''}: ${e.error||''}</div>`;
      }
    }
    out.innerHTML=html;
    if(goBtn) goBtn.style.display='inline-flex';
  }catch(e){ out.innerHTML=`<div class="errbox">${e.message}</div>`; }
}

function goChooseMix(){
  if(!memory.optimize || !(memory.optimize.apply_mix || memory.optimize.best)){
    alert('Calculez d abord le mix recommande.');
    return;
  }
  applyRecommendedMixFull(memory.optimize);
  setStep(5);
}

function updateReloadMixButton(){
  const btn=document.getElementById('btn-reload-mix');
  if(!btn) return;
  const has=!!(memory.optimize && (memory.optimize.apply_mix || memory.optimize.best));
  btn.style.display=has?'inline-flex':'none';
}

function reloadRecommendedMix(){
  if(!memory.optimize){
    alert('Aucun mix recommande disponible.');
    return;
  }
  if(!applyRecommendedMixFull(memory.optimize)){
    alert('Mix recommande indisponible.');
    return;
  }
  setStep(5);
}

// ---------- Step 6 : estimation pure (simulate only) ----------
async function runEstimate(){
  setStep(6);
  const out=document.getElementById('estimate-out');
  out.innerHTML='';
  // barre de progression (requete sync : avancement visuel pendant l'attente)
  let fakePct=8;
  renderProgressBar(out, {pct:fakePct, message:'Calcul…', indeterminate:false});
  const tick=setInterval(()=>{
    fakePct=Math.min(90, fakePct+(90-fakePct)*0.12+1.5);
    renderProgressBar(out, {pct:fakePct, message:'Calcul…', indeterminate:false});
  }, 220);
  // eviter double-clic pendant le calcul
  const btnEst=document.getElementById('btn-estimate');
  if(btnEst) btnEst.disabled=true;
  try{
    const payload=payloadFromMemory('edit');
    // sync levers from edit panels for redisplay
    if(memory.editTypeMix){
      memory.levers=memory.levers||{};
      memory.levers.type_mix=memory.editTypeMix.toObject();
      memory.levers.gamme_mix_fb=memory.editGammeFb?memory.editGammeFb.toObject():{};
      memory.levers.gamme_mix_nfb=memory.editGammeNfb?memory.editGammeNfb.toObject():{};
      memory.levers.gamme_mix=payload.gamme_mix;
    }
    const res=await fetch('/api/user/simulate',{
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify(payload)
    });
    const data=await res.json();
    if(!data.ok) throw new Error(data.error||'erreur estimation');
    memory.estimate=data;

    clearInterval(tick);
    renderProgressBar(out, {pct:100, message:'Termine'});
    // brief flash a 100 % puis resultats
    await new Promise(r=>setTimeout(r, 180));

    let html=renderMixSummary(
      payload.type_mix, payload.gamme_mix_fb, payload.gamme_mix_nfb,
      {title:'Mix evalue'}
    );

    const by=data.by_engine||{};
    let globalReco=null;
    for(const eng of ['ml','sim_v2','sim_v1']){
      const r=(by[eng]||{}).recommendation;
      if(r && r.recommended){ globalReco={eng, ...r}; break; }
    }
    if(globalReco){
      const best=globalReco.best||{};
      const a=annualOf(best);
      html+=`<div class="reco-box"><h4>Solution recommandee : ${tag(globalReco.recommended)}</h4>
        <div class="muted">CA ${fmt(a.ca)} €/an · ROI ${fmt(a.roi)} €/an
        ${best.payback_months!=null?` · Amort. <span class="payback">${fmt(best.payback_months,1)} mois (${fmt(best.payback_years,1)} ans)</span>`:''}</div>
      </div>`;
    }

    for(const eng of ['sim_v1','sim_v2','ml']){
      html+=engineBlock(eng, by[eng]||{results:[], recommendation:{}});
    }
    if((data.errors||[]).length){
      html+='<h2>Alertes</h2>';
      for(const e of data.errors){
        html+=`<div class="err-soft">${e.scenario||e.engine||''}: ${e.error||''}</div>`;
      }
    }
    out.innerHTML=html;
  }catch(e){
    clearInterval(tick);
    out.innerHTML=`<div class="errbox">${e.message}</div>`;
  }finally{
    if(btnEst) btnEst.disabled=false;
  }
}

document.getElementById('btn-search').onclick=()=>search({immediate:true});
const qInput=document.getElementById('q');
if(qInput){
  // Enter ou Espace → proposer les choix tout de suite
  qInput.addEventListener('keydown',e=>{
    if(e.key==='Enter'){
      e.preventDefault();
      search({immediate:true});
    }
  });
  qInput.addEventListener('keyup',e=>{
    if(e.key===' '||e.key==='Spacebar'||e.code==='Space'){
      search({immediate:true});
    }
  });
  // Saisie continue : debounce (des 2 caracteres utiles)
  qInput.addEventListener('input',()=>{
    const v=qInput.value.trim();
    if(v.length>=2) search({immediate:false});
    else if(!v){
      const box=document.getElementById('results');
      if(box) box.innerHTML='';
    }
  });
}
const btnMixReco=document.getElementById('btn-mix-reco');
if(btnMixReco) btnMixReco.onclick=runMixReco;
const btnGoChoose=document.getElementById('btn-go-choose-mix');
if(btnGoChoose) btnGoChoose.onclick=goChooseMix;
const btnReload=document.getElementById('btn-reload-mix');
if(btnReload) btnReload.onclick=reloadRecommendedMix;
const btnEstimate=document.getElementById('btn-estimate');
if(btnEstimate) btnEstimate.onclick=runEstimate;
updateReloadMixButton();
"""
