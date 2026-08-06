"""
GUI web : evaluation LOO, prediction hotel, comparaison sim_v1 / sim_v2 / ml.
"""

from __future__ import annotations

from flask import Flask, render_template_string

from src.api.app import create_api_app
from src.pipeline.paths import Paths
from src.web.styles import COMMON_CSS

NAV = """
<nav>
  <a class="link" href="/eval">Evaluation LOO</a>
  <a class="link" href="/compare">Comparaison</a>
  <a class="link" href="/predict">Prediction</a>
  <a class="link" href="/hotels">Hotels</a>
</nav>
"""

SHELL = """
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>__TITLE__</title>
  <style>__CSS__</style>
</head>
<body>
  <header>
    <h1><a class="brand" href="/" title="Accueil">Accor ROD</a> <span>release 1.0.0</span></h1>
    __NAV__
  </header>
  <main>__BODY__</main>
  <script>__SCRIPT__</script>
</body>
</html>
""".replace("__CSS__", COMMON_CSS).replace("__NAV__", NAV)


def _page(title: str, h1: str, body: str, script: str = "") -> str:
    return (
        SHELL.replace("__TITLE__", title)
        .replace("__H1__", h1)
        .replace("__BODY__", body)
        .replace("__SCRIPT__", script)
    )


HOME_BODY = """
<div class="grid">
  <a class="card" href="/eval" style="text-decoration:none;color:inherit">
    <div class="lbl">Evaluation</div>
    <div class="val" style="font-size:1rem">LOO hotels pilotes</div>
    <div class="sub">sim_v1 · sim_v2 · ml</div>
  </a>
  <a class="card" href="/compare" style="text-decoration:none;color:inherit">
    <div class="lbl">Comparaison</div>
    <div class="val" style="font-size:1rem">sim_v1 vs sim_v2 vs ml</div>
    <div class="sub">Metriques cote a cote</div>
  </a>
  <a class="card" href="/predict" style="text-decoration:none;color:inherit">
    <div class="lbl">Prediction</div>
    <div class="val" style="font-size:1rem">Hotel cible</div>
    <div class="sub">sim_v1 · sim_v2 · ml</div>
  </a>
  <a class="card" href="/hotels" style="text-decoration:none;color:inherit">
    <div class="lbl">Hotels</div>
    <div class="val" style="font-size:1rem">Parametres</div>
    <div class="sub">Pre-remplir la prediction</div>
  </a>
</div>
"""

EVAL_BODY = """
<div style="display:flex;gap:.5rem;flex-wrap:wrap;margin-bottom:1rem">
  <button class="btn primary" data-src="sim_v1" type="button">sim_v1</button>
  <button class="btn" data-src="sim_v2" type="button">sim_v2</button>
  <button class="btn" data-src="ml" type="button">ml</button>
</div>
<div id="main"><p class="muted">Chargement…</p></div>
"""

EVAL_SCRIPT = r"""
const fmt=(n,d=2)=>{if(n==null||n===''||Number.isNaN(Number(n)))return '—';return Number(n).toLocaleString('fr-FR',{maximumFractionDigits:d});};
const tag=s=>`<span class="tag ${(s||'').toString().toLowerCase().replace(/[^a-z0-9_]/g,'')}">${s??''}</span>`;
function table(cols,rows,nums=[]){
  const N=new Set(nums);
  let h='<div class="scroll"><table><thead><tr>'+cols.map(c=>`<th class="${N.has(c.k)?'num':''}">${c.l}</th>`).join('')+'</tr></thead><tbody>';
  for(const r of rows){
    h+='<tr>'+cols.map(c=>{
      let v=r[c.k];
      if(c.k==='solution'||c.k==='methode'||c.k==='target') v=v==null?'—':tag(v);
      else if(N.has(c.k)) v=fmt(v,c.d??2);
      else if(v==null) v='—';
      return `<td class="${N.has(c.k)?'num':''}">${v}</td>`;
    }).join('')+'</tr>';
  }
  return h+'</tbody></table></div>';
}
async function load(src){
  const main=document.getElementById('main');
  main.innerHTML='<p class="muted">Chargement…</p>';
  document.querySelectorAll('button[data-src]').forEach(b=>b.classList.toggle('primary', b.dataset.src===src));
  try{
    const res=await fetch('/api/eval/'+src);
    const data=await res.json();
    if(!data.ok) throw new Error(data.error||'erreur');
    let html='';
    if((data.metrics||[]).length){
      html+='<div class="grid">'+(data.metrics||[]).map(m=>{
        const title=m.target_label||m.target||m.methode||m.perimetre||m.scope||'';
        const mae=m.mae??m.montant_ventes_mae??m.mae_ca;
        return `<div class="card"><div class="lbl">${title}</div><div class="val">${fmt(mae)}</div>
          <div class="sub">MAE</div></div>`;
      }).join('')+'</div>';
    }
    html+='<h2>Predictions</h2>';
    const preds=data.predictions||[];
    const keys=preds[0]?Object.keys(preds[0]).slice(0,12):[];
    html+=table(keys.map(k=>({k,l:k})), preds, keys.filter(k=>/mae|err|reel|pred|ca_|marge_/i.test(k)));
    main.innerHTML=html;
  }catch(e){
    main.innerHTML=`<div class="errbox">${e.message}</div>`;
  }
}
document.querySelectorAll('button[data-src]').forEach(b=>b.onclick=()=>load(b.dataset.src));
load('sim_v1');
"""

COMPARE_BODY = """
<div id="main"><p class="muted">Chargement…</p></div>
"""

COMPARE_SCRIPT = r"""
const fmt=(n,d=2)=>{if(n==null||n===''||Number.isNaN(Number(n)))return '—';return Number(n).toLocaleString('fr-FR',{maximumFractionDigits:d});};
const tag=s=>`<span class="tag ${(s||'').toString().toLowerCase().replace(/[^a-z0-9_]/g,'')}">${s??''}</span>`;
const SOURCES=['sim_v1','sim_v2','ml'];

function isGlobalMetric(m){
  // ligne globale (pas de solution) — preferer pour les KPI
  return m.solution==null || m.solution==='' || m.perimetre==='ALL' || m.scope==='ALL';
}
function pickMaeCa(metrics){
  if(!metrics||!metrics.length) return null;
  const ordered=[...metrics].sort((a,b)=>Number(isGlobalMetric(b))-Number(isGlobalMetric(a)));
  for(const m of ordered){
    if(m.mae_ca!=null) return Number(m.mae_ca);
    if(m.montant_ventes_mae!=null) return Number(m.montant_ventes_mae);
    if(m.target==='montant_ventes_par_mois' && m.mae!=null) return Number(m.mae);
  }
  const mae=metrics.map(m=>m.mae).filter(v=>v!=null);
  if(mae.length) return mae.reduce((a,b)=>a+Number(b),0)/mae.length;
  return null;
}
function pickMaeMarge(metrics){
  if(!metrics||!metrics.length) return null;
  const ordered=[...metrics].sort((a,b)=>Number(isGlobalMetric(b))-Number(isGlobalMetric(a)));
  for(const m of ordered){
    if(m.mae_marge!=null) return Number(m.mae_marge);
    if(m.marge_mae!=null) return Number(m.marge_mae);
    if(m.target==='montant_marge_par_mois' && m.mae!=null) return Number(m.mae);
  }
  return null;
}
function pickMapeCa(metrics){
  if(!metrics||!metrics.length) return null;
  const ordered=[...metrics].sort((a,b)=>Number(isGlobalMetric(b))-Number(isGlobalMetric(a)));
  for(const m of ordered){
    if(m.mape_ca_pct!=null) return Number(m.mape_ca_pct);
    if(m.montant_ventes_mape!=null) return Number(m.montant_ventes_mape);
    if(m.target==='montant_ventes_par_mois' && m.mape!=null) return Number(m.mape);
  }
  return null;
}

function hotelCa(pred){
  // unify predicted / actual CA fields across sources
  return {
    hotel: pred.hotel_code,
    solution: pred.solution,
    methode: pred.methode||null,
    ca_pred: pred.ca_pred??pred.montant_ventes_par_mois_predit??pred.montant_ventes_par_mois_pred??null,
    ca_reel: pred.ca_reel??pred.montant_ventes_par_mois_reel??null,
    ca_err: pred.ca_err_abs??pred.montant_ventes_erreur_absolue??pred.montant_ventes_par_mois_erreur_absolue??null,
    marge_pred: pred.marge_pred??pred.montant_marge_par_mois_predite??pred.montant_marge_par_mois_predit??null,
    marge_reel: pred.marge_reel??pred.montant_marge_par_mois_reel??null,
  };
}

async function fetchEval(src){
  try{
    const res=await fetch('/api/eval/'+src);
    const data=await res.json();
    if(!data.ok) return {src, ok:false, error:data.error||'erreur'};
    return {src, ok:true, metrics:data.metrics||[], predictions:data.predictions||[]};
  }catch(e){
    return {src, ok:false, error:e.message};
  }
}

function bestSrc(rows, key){
  let best=null, bestVal=Infinity;
  for(const r of rows){
    const v=r[key];
    if(v==null||Number.isNaN(v)) continue;
    if(v<bestVal){ bestVal=v; best=r.src; }
  }
  return best;
}

async function render(){
  const main=document.getElementById('main');
  main.innerHTML='<p class="muted">Chargement…</p>';
  const results=await Promise.all(SOURCES.map(fetchEval));
  const ok=results.filter(r=>r.ok);
  const fail=results.filter(r=>!r.ok);

  // KPI cards
  const kpis=results.map(r=>{
    if(!r.ok) return {src:r.src, mae_ca:null, mae_marge:null, mape_ca:null, n:null, n_rows:null, err:r.error};
    const preds=r.predictions||[];
    const hotels=new Set(preds.map(p=>p.hotel_code).filter(Boolean));
    return {
      src:r.src,
      mae_ca: pickMaeCa(r.metrics),
      mae_marge: pickMaeMarge(r.metrics),
      mape_ca: pickMapeCa(r.metrics),
      n: hotels.size,           // hotels uniques (comparable)
      n_rows: preds.length,    // lignes brutes (sim_v2 = 2 methodes)
      err:null,
    };
  });
  const bestCa=bestSrc(kpis,'mae_ca');
  const bestMarge=bestSrc(kpis,'mae_marge');

  let html='';
  if(fail.length){
    html+=`<div class="errbox">Donnees manquantes : ${fail.map(r=>r.src).join(', ')}</div>`;
  }
  html+='<h2>Metriques globales (LOO)</h2><div class="grid">';
  for(const k of kpis){
    const winCa=k.src===bestCa?' · meilleur CA':'';
    const winM=k.src===bestMarge?' · meilleure marge':'';
    html+=`<div class="card">
      <div class="lbl">${tag(k.src)}</div>
      <div class="val">${fmt(k.mae_ca)}</div>
      <div class="sub">MAE CA${winCa}</div>
      <div class="sub" style="margin-top:.35rem">MAE marge : <strong>${fmt(k.mae_marge)}</strong>${winM}</div>
      <div class="sub">MAPE CA : ${fmt(k.mape_ca)} % · hotels=${k.n??'—'}${k.n_rows!=null && k.n_rows!==k.n?` · lignes=${k.n_rows}`:''}</div>
      ${k.err?`<div class="errbox" style="margin-top:.5rem;padding:.4rem .55rem;font-size:.78rem">${k.err}</div>`:''}
    </div>`;
  }
  html+='</div>';

  // Side-by-side metrics table
  html+='<h2>Tableau comparatif</h2><div class="scroll"><table><thead><tr>';
  html+='<th>Metrique</th>'+SOURCES.map(s=>`<th class="num">${s}</th>`).join('')+'</tr></thead><tbody>';
  const rows=[
    ['MAE CA', 'mae_ca'],
    ['MAE marge', 'mae_marge'],
    ['MAPE CA (%)', 'mape_ca'],
    ['Nb hotels', 'n'],
  ];
  for(const [label,key] of rows){
    html+=`<tr><td>${label}</td>`;
    for(const s of SOURCES){
      const k=kpis.find(x=>x.src===s);
      const v=k?k[key]:null;
      const isBest=(key==='mae_ca'&&s===bestCa)||(key==='mae_marge'&&s===bestMarge);
      html+=`<td class="num"${isBest?' style="color:var(--ok);font-weight:700"':''}>${fmt(v, key==='n'?0:2)}</td>`;
    }
    html+='</tr>';
  }
  html+='</tbody></table></div>';

  // Per-hotel comparison (CA pred / err)
  const byHotel={};
  for(const r of ok){
    for(const p of r.predictions){
      const u=hotelCa(p);
      if(!u.hotel) continue;
      // sim_v2 may have several methodes — keep best (lowest abs err) per hotel
      const key=u.hotel;
      if(!byHotel[key]) byHotel[key]={hotel:key, solution:u.solution};
      const slot=byHotel[key];
      const prev=slot[r.src];
      if(!prev || (u.ca_err!=null && (prev.ca_err==null || u.ca_err<prev.ca_err))){
        slot[r.src]=u;
        if(u.solution) slot.solution=u.solution;
      }
    }
  }
  const hotels=Object.values(byHotel).sort((a,b)=>String(a.hotel).localeCompare(String(b.hotel)));
  if(hotels.length){
    html+='<h2>Par hotel (CA predit / erreur abs.)</h2><div class="scroll"><table><thead><tr>';
    html+='<th>Hotel</th><th>Solution</th>';
    for(const s of SOURCES){
      html+=`<th class="num">${s} CA</th><th class="num">${s} err</th>`;
    }
    html+='</tr></thead><tbody>';
    for(const h of hotels){
      html+=`<tr><td>${h.hotel}</td><td>${h.solution?tag(h.solution):'—'}</td>`;
      // best err among sources for this hotel
      let bestE=Infinity, bestS=null;
      for(const s of SOURCES){
        const e=h[s]?.ca_err;
        if(e!=null && e<bestE){ bestE=e; bestS=s; }
      }
      for(const s of SOURCES){
        const u=h[s];
        const win=s===bestS;
        html+=`<td class="num">${fmt(u?.ca_pred)}</td>`;
        html+=`<td class="num"${win?' style="color:var(--ok);font-weight:700"':''}>${fmt(u?.ca_err)}</td>`;
      }
      html+='</tr>';
    }
    html+='</tbody></table></div>';
  }

  // Detail sim_v2 par solution (global = solution null)
  const v2=results.find(r=>r.src==='sim_v2'&&r.ok);
  if(v2){
    const bySol=(v2.metrics||[]).filter(m=>m.solution!=null && m.solution!=='');
    if(bySol.length){
      html+='<h2>sim_v2 par solution</h2><div class="scroll"><table><thead><tr>';
      html+='<th>Solution</th><th class="num">MAE CA</th><th class="num">MAE marge</th><th class="num">MAPE CA</th></tr></thead><tbody>';
      for(const m of bySol){
        html+=`<tr>
          <td>${tag(m.solution)}</td>
          <td class="num">${fmt(m.montant_ventes_mae)}</td>
          <td class="num">${fmt(m.marge_mae)}</td>
          <td class="num">${fmt(m.montant_ventes_mape)}</td>
        </tr>`;
      }
      html+='</tbody></table></div>';
    }
  }

  main.innerHTML=html;
}
render();
"""

PREDICT_BODY = """
<div class="layout">
  <form class="card" id="form" onsubmit="return false;">
    <h2 style="margin-top:0">Parametres hotel</h2>
    <label>Hotel pilote</label>
    <select id="hotel_select"><option value="">— manuel —</option></select>
    <div class="row">
      <div><label>Chambres</label><input name="hotel_nb_chambres" type="number" step="1" value="100"/></div>
      <div><label>TO annuel (0-1)</label><input name="hotel_to_annuel" type="number" step="0.01" value="0.70"/></div>
    </div>
    <div class="row">
      <div><label>Guests / chambre</label><input name="hotel_guests_per_chambre" type="number" step="0.1" value="1.7"/></div>
      <div><label>Metres lineaires</label><input name="metres_lineaires" type="number" step="0.1" value="6"/></div>
    </div>
    <label>Solution</label>
    <select name="solution">
      <option value="simply">simply</option>
      <option value="liberty">liberty</option>
      <option value="connected">connected</option>
    </select>
    <label>hotel_code (sim_v1)</label>
    <input name="hotel_code" type="text" placeholder="ex. H2075"/>

    <div id="mix_type" class="mix-block"></div>
    <div id="mix_gamme" class="mix-block"></div>
  </form>
  <div class="predict-right">
    <div class="predict-actions card">
      <div class="btn-row" style="margin-top:0">
        <button class="btn primary" id="btnV2" type="button">sim_v2</button>
        <button class="btn" id="btnML" type="button">ml</button>
        <button class="btn" id="btnV1" type="button">sim_v1</button>
        <button class="btn" id="btnAll" type="button">Comparer les 3</button>
      </div>
    </div>
    <div id="hotel_info" class="card muted">Selectionner un hotel pour pre-remplir les champs.</div>
    <div id="out"></div>
  </div>
</div>
"""

PREDICT_SCRIPT = r"""
const fmt=(n,d=2)=>{if(n==null||n===''||Number.isNaN(Number(n)))return '—';return Number(n).toLocaleString('fr-FR',{maximumFractionDigits:d});};
const tag=s=>`<span class="tag ${(s||'').toString().toLowerCase()}">${s??''}</span>`;
const pctLabel=v=>`${Math.round(v*1000)/10} %`.replace('.0 %',' %');
const EPS=1e-9;

/** Panneau mix : sliders 0-100%, switch bleu = libre, somme = 1. */
class MixPanel {
  constructor(rootId, title, entries){
    this.root=document.getElementById(rootId);
    this.title=title;
    this.items=entries.map(e=>({
      key:e.key,
      value:Math.max(0, Number(e.value)||0),
      locked:false,
      autoLocked:false,
    }));
    this._normalizeAll();
    this.render();
  }
  lockedSum(exceptKey=null){
    return this.items
      .filter(i=>i.locked && i.key!==exceptKey)
      .reduce((s,i)=>s+i.value,0);
  }
  freeItems(exceptKey=null){
    return this.items.filter(i=>!i.locked && i.key!==exceptKey);
  }
  /** Bornes logiques pour un slider libre (en %). Affichage range toujours 0-100. */
  freeMaxPct(key){
    const locked=this.lockedSum(key);
    return Math.max(0, (1-locked)*100);
  }
  setValue(key, pct, {soft=true}={}){
    const it=this.items.find(i=>i.key===key);
    if(!it || it.locked) return;
    const locked=this.lockedSum();
    const max=Math.max(0, 1-locked);
    let v=Math.min(max, Math.max(0, Number(pct)/100));
    // evite les artefacts flottants
    v=Math.round(v*1000)/1000;
    const others=this.freeItems(key);
    if(others.length===0){
      it.value=max;
      this._fixFloat();
      soft?this._paint():this.render();
      return;
    }
    it.value=v;
    const remaining=Math.max(0, 1-locked-v);
    const each=remaining/others.length;
    others.forEach(o=>{ o.value=each; });
    this._fixFloat();
    soft?this._paint():this.render();
  }
  /**
   * free=true  → switch bleu allumé, slider maniable
   * free=false → figé, valeur conservee, slider desactive
   */
  setFree(key, free){
    const it=this.items.find(i=>i.key===key);
    if(!it) return;
    if(it.autoLocked && free){
      // liberer le reste auto : liberer tous les auto-locks
      this.items.forEach(i=>{ if(i.autoLocked){ i.locked=false; i.autoLocked=false; }});
      this.render();
      return;
    }
    if(free){
      // liberer ce groupe (valeur inchangee)
      it.locked=false;
      it.autoLocked=false;
      this.items.forEach(i=>{ if(i.autoLocked){ i.locked=false; i.autoLocked=false; }});
    } else {
      // figer a la valeur actuelle (ne pas reinitialiser)
      const keep=it.value;
      it.locked=true;
      it.autoLocked=false;
      it.value=keep;
      this._autoLockResidual();
    }
    this.render();
  }
  _autoLockResidual(){
    this.items.forEach(i=>{
      if(i.autoLocked){ i.locked=false; i.autoLocked=false; }
    });
    const free=this.items.filter(i=>!i.locked);
    if(free.length===1){
      const only=free[0];
      // conserve la valeur residuelle exacte, sans la remettre a 0
      only.value=Math.max(0, 1-this.lockedSum(only.key));
      only.locked=true;
      only.autoLocked=true;
    }
  }
  _normalizeAll(){
    const s=this.items.reduce((a,i)=>a+i.value,0);
    if(s<=EPS){
      const each=1/this.items.length;
      this.items.forEach(i=>{ i.value=each; });
    } else {
      this.items.forEach(i=>{ i.value=i.value/s; });
    }
  }
  _fixFloat(){
    const s=this.items.reduce((a,i)=>a+i.value,0);
    const delta=1-s;
    if(Math.abs(delta)<1e-12) return;
    const free=this.items.filter(i=>!i.locked);
    const target=free.length?free[free.length-1]:this.items[this.items.length-1];
    target.value=Math.max(0, target.value+delta);
  }
  toObject(){
    const o={};
    this.items.forEach(i=>{ o[i.key]=Math.round(i.value*1e6)/1e6; });
    return o;
  }
  _paint(){
    const sum=this.items.reduce((a,i)=>a+i.value,0);
    const sumEl=this.root.querySelector('.mix-sum');
    if(sumEl){
      sumEl.textContent=`Σ ${pctLabel(sum)}`;
      sumEl.classList.toggle('warn', Math.abs(sum-1)>=1e-6);
    }
    for(const it of this.items){
      const row=this.root.querySelector(`.mix-row[data-key="${CSS.escape(it.key)}"]`);
      if(!row) continue;
      const pct=Math.round(it.value*1000)/10;
      const pctEl=row.querySelector('.mix-pct');
      if(pctEl) pctEl.textContent=pctLabel(it.value);
      const range=row.querySelector('input[type=range]');
      if(range){
        // toujours 0-100 pour garder la position visuelle correcte
        range.min=0;
        range.max=100;
        range.value=String(pct);
        range.style.setProperty('--pct', `${pct}%`);
        range.disabled=!!it.locked;
      }
      row.classList.toggle('locked', !!it.locked);
      row.classList.toggle('residual', !!it.autoLocked);
      const sw=row.querySelector('input[data-lock]');
      if(sw){
        // bleu = libre
        sw.checked=!it.locked;
        sw.disabled=!!it.autoLocked;
      }
    }
  }
  render(){
    const sum=this.items.reduce((a,i)=>a+i.value,0);
    const sumOk=Math.abs(sum-1)<1e-6;
    let html=`<div class="mix-head">
      <p class="mix-title">${this.title}</p>
      <span class="mix-sum${sumOk?'':' warn'}">Σ ${pctLabel(sum)}</span>
    </div>`;
    for(const it of this.items){
      const pct=Math.round(it.value*1000)/10;
      const free=!it.locked;
      const residual=it.autoLocked?' residual':'';
      const lockedCls=it.locked?' locked':'';
      const lockTitle=it.autoLocked
        ? 'Reste automatique (fige) — allumez un autre groupe pour ajuster'
        : (free ? 'Libre — cliquer pour figer' : 'Figé — cliquer pour liberer');
      html+=`<div class="mix-row${lockedCls}${residual}" data-key="${this._escAttr(it.key)}">
        <div class="mix-label" title="${this._escAttr(it.key)}">${this._escHtml(it.key)}</div>
        <div class="mix-pct">${pctLabel(it.value)}</div>
        <label class="sw" title="${lockTitle}">
          <input type="checkbox" data-lock="${this._escAttr(it.key)}" ${free?'checked':''} ${it.autoLocked?'disabled':''}/>
          <span class="slider"></span>
        </label>
        <div class="mix-slider-wrap">
          <input type="range" min="0" max="100" step="0.1" value="${pct}"
            data-key="${this._escAttr(it.key)}" ${it.locked?'disabled':''}
            style="--pct:${pct}%"/>
        </div>
      </div>`;
    }
    this.root.innerHTML=html;
    this.root.querySelectorAll('input[type=range]').forEach(el=>{
      el.addEventListener('input', e=>{
        const key=e.target.getAttribute('data-key');
        let pct=Number(e.target.value);
        // clamp au max disponible (part des groupes figes)
        const max=this.freeMaxPct(key);
        if(pct>max){ pct=max; e.target.value=String(max); }
        this.setValue(key, pct, {soft:true});
      });
      el.addEventListener('change', e=>{
        const key=e.target.getAttribute('data-key');
        let pct=Number(e.target.value);
        const max=this.freeMaxPct(key);
        if(pct>max) pct=max;
        this.setValue(key, pct, {soft:false});
      });
    });
    this.root.querySelectorAll('input[data-lock]').forEach(el=>{
      el.addEventListener('change', e=>{
        const key=e.target.getAttribute('data-lock');
        // checked (bleu) = libre
        this.setFree(key, !!e.target.checked);
      });
    });
  }
  _escAttr(s){
    return String(s).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;');
  }
  _escHtml(s){
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }
}

const typeMix=new MixPanel('mix_type', 'Mix type', [
  {key:'F&B', value:0.7},
  {key:'NON F&B', value:0.3},
]);
const gammeMix=new MixPanel('mix_gamme', 'Mix gamme', [
  {key:'sans alcool', value:0.35},
  {key:'food salee', value:0.25},
  {key:'food sucree', value:0.15},
  {key:'accessoires', value:0.15},
  {key:'sos', value:0.10},
]);

function bodyFromForm(){
  const fd=new FormData(document.getElementById('form'));
  return {
    hotel_nb_chambres: Number(fd.get('hotel_nb_chambres')),
    hotel_to_annuel: Number(fd.get('hotel_to_annuel')),
    hotel_guests_per_chambre: Number(fd.get('hotel_guests_per_chambre')),
    metres_lineaires: Number(fd.get('metres_lineaires')),
    solution: fd.get('solution'),
    hotel_code: (fd.get('hotel_code')||'').trim(),
    type_mix: typeMix.toObject(),
    gamme_mix: gammeMix.toObject(),
  };
}
function extractCa(data){
  if(data.predictions && data.predictions.length){
    const rows=data.predictions;
    const r=rows[0];
    return {
      ca: r.montant_ventes_par_mois_predit,
      marge: r.montant_marge_par_mois_predite,
      marge_coef: r.montant_marge_selon_coef_par_mois_predite,
      detail: rows,
    };
  }
  if(data.prediction){
    const p=data.prediction;
    return {
      ca: p.montant_ventes_par_mois,
      marge: p.montant_marge_par_mois,
      marge_coef: p.montant_marge_selon_coef_par_mois,
      detail:null,
    };
  }
  if(data.montant_ventes_par_mois!=null){
    return {
      ca: data.montant_ventes_par_mois,
      marge: data.montant_marge_par_mois,
      marge_coef: null,
      detail:null,
    };
  }
  return null;
}
function renderOne(data, {title=null, showLabel=false, label=''}={}){
  if(!data.ok) return `<div class="errbox">${showLabel&&label?label+' : ':''}${data.error||'echec'}</div>`;
  const head=title?`<h2>${title}</h2>`:(showLabel&&label?`<h2>${tag(label)}</h2>`:'');
  if(data.predictions){
    let h=head+`<div class="scroll"><table><thead><tr><th>Solution</th><th class="num">CA</th><th class="num">Marge marche</th><th class="num">Marge coef</th></tr></thead><tbody>`;
    for(const r of data.predictions){
      h+=`<tr><td>${tag(r.solution)}</td>
        <td class="num">${fmt(r.montant_ventes_par_mois_predit)}</td>
        <td class="num">${fmt(r.montant_marge_par_mois_predite)}</td>
        <td class="num">${fmt(r.montant_marge_selon_coef_par_mois_predite)}</td></tr>`;
    }
    return h+'</tbody></table></div>';
  }
  if(data.prediction){
    const p=data.prediction;
    return head+`<div class="grid">
        <div class="card"><div class="lbl">CA mensuel</div><div class="val">${fmt(p.montant_ventes_par_mois)}</div></div>
        <div class="card"><div class="lbl">Marge marche</div><div class="val">${fmt(p.montant_marge_par_mois)}</div></div>
        <div class="card"><div class="lbl">Marge coef</div><div class="val">${fmt(p.montant_marge_selon_coef_par_mois)}</div></div>
      </div>`;
  }
  if(data.montant_ventes_par_mois!=null){
    const sol=data.solution?` ${tag(data.solution)}`:'';
    return (title?`<h2>${title}${sol}</h2>`:(showLabel&&label?`<h2>${tag(label)}${sol}</h2>`:(sol?`<h2>${sol}</h2>`:'')))+
      `<div class="grid">
        <div class="card"><div class="lbl">CA predit</div><div class="val">${fmt(data.montant_ventes_par_mois)}</div></div>
        <div class="card"><div class="lbl">Marge predite</div><div class="val">${fmt(data.montant_marge_par_mois)}</div></div>
      </div>`;
  }
  return `<div class="errbox">Reponse inattendue</div>`;
}
async function call(url){
  const out=document.getElementById('out');
  out.innerHTML='<p class="muted">Calcul…</p>';
  try{
    const res=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(bodyFromForm())});
    const data=await res.json();
    if(!data.ok) throw new Error(data.error||'echec');
    out.innerHTML=renderOne(data);
  }catch(e){ out.innerHTML=`<div class="errbox">${e.message}</div>`; }
}
async function callAll(){
  const out=document.getElementById('out');
  out.innerHTML='<p class="muted">Calcul…</p>';
  const body=bodyFromForm();
  const jobs=[
    {src:'sim_v1', url:'/api/predict/sim_v1'},
    {src:'sim_v2', url:'/api/predict/sim_v2'},
    {src:'ml', url:'/api/predict/ml'},
  ];
  const results=await Promise.all(jobs.map(async j=>{
    try{
      const res=await fetch(j.url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const data=await res.json();
      return {src:j.src, data};
    }catch(e){
      return {src:j.src, data:{ok:false, error:e.message}};
    }
  }));
  let html='<div class="grid">';
  for(const r of results){
    const x=r.data.ok?extractCa(r.data):null;
    html+=`<div class="card">
      <div class="lbl">${tag(r.src)}</div>
      <div class="val">${x?fmt(x.ca):'—'}</div>
      <div class="sub">CA mensuel</div>
      <div class="sub" style="margin-top:.35rem">Marge : <strong>${x?fmt(x.marge):'—'}</strong></div>
      ${!r.data.ok?`<div class="errbox" style="margin-top:.5rem;padding:.4rem .55rem;font-size:.85rem">${r.data.error||'echec'}</div>`:''}
    </div>`;
  }
  html+='</div>';
  const v2=results.find(r=>r.src==='sim_v2');
  if(v2 && v2.data.ok && v2.data.predictions && v2.data.predictions.length>1){
    html+=renderOne(v2.data, {title:'Detail par solution'});
  }
  out.innerHTML=html;
}
function markBtn(id){
  ['btnV1','btnV2','btnML','btnAll'].forEach(x=>{
    const el=document.getElementById(x);
    if(el) el.classList.toggle('primary', x===id);
  });
}
document.getElementById('btnV2').onclick=()=>{ markBtn('btnV2'); call('/api/predict/sim_v2'); };
document.getElementById('btnML').onclick=()=>{ markBtn('btnML'); call('/api/predict/ml'); };
document.getElementById('btnV1').onclick=()=>{ markBtn('btnV1'); call('/api/predict/sim_v1'); };
document.getElementById('btnAll').onclick=()=>{ markBtn('btnAll'); callAll(); };

fetch('/api/hotels').then(r=>r.json()).then(data=>{
  if(!data.ok) return;
  const sel=document.getElementById('hotel_select');
  for(const h of (data.hotels||[])){
    const o=document.createElement('option');
    o.value=h.hotel_code;
    o.textContent=`${h.hotel_code} · ${h.solution||''}`;
    o.dataset.payload=JSON.stringify(h);
    sel.appendChild(o);
  }
  const applyHotel=(h)=>{
    const form=document.getElementById('form');
    form.hotel_code.value=h.hotel_code||'';
    if(h.hotel_nb_chambres) form.hotel_nb_chambres.value=h.hotel_nb_chambres;
    if(h.hotel_to_annuel) form.hotel_to_annuel.value=h.hotel_to_annuel;
    if(h.hotel_guests_per_chambre) form.hotel_guests_per_chambre.value=h.hotel_guests_per_chambre;
    if(h.solution) form.solution.value=String(h.solution).toLowerCase();
    document.getElementById('hotel_info').innerHTML=
      `<strong>${h.hotel_code}</strong> ${tag(h.solution)}
       <div class="sub">chambres ${fmt(h.hotel_nb_chambres,0)} · TO ${fmt(h.hotel_to_annuel,2)} · guests ${fmt(h.hotel_guests_per_chambre,2)}</div>`;
  };
  sel.onchange=()=>{
    const opt=sel.selectedOptions[0];
    if(!opt||!opt.dataset.payload) return;
    applyHotel(JSON.parse(opt.dataset.payload));
  };
  const q=new URLSearchParams(location.search).get('hotel');
  if(q){
    const opt=[...sel.options].find(o=>o.value===q);
    if(opt){ sel.value=q; if(opt.dataset.payload) applyHotel(JSON.parse(opt.dataset.payload)); }
  }
}).catch(()=>{});
"""

HOTELS_BODY = """
<div id="list"><p class="muted">Chargement…</p></div>
"""

HOTELS_SCRIPT = r"""
const fmt=(n,d=2)=>{if(n==null||n===''||Number.isNaN(Number(n)))return '—';return Number(n).toLocaleString('fr-FR',{maximumFractionDigits:d});};
const tag=s=>`<span class="tag ${(s||'').toString().toLowerCase()}">${s??''}</span>`;
fetch('/api/hotels').then(r=>r.json()).then(data=>{
  if(!data.ok){ document.getElementById('list').innerHTML=`<div class="errbox">${data.error||'Erreur'}</div>`; return; }
  let h='<div class="scroll"><table><thead><tr><th>Hotel</th><th>Solution</th><th>Chambres</th><th>TO</th><th>Guests</th><th></th></tr></thead><tbody>';
  for(const r of (data.hotels||[])){
    h+=`<tr>
      <td>${r.hotel_code||'—'}</td>
      <td>${tag(r.solution)}</td>
      <td class="num">${fmt(r.hotel_nb_chambres??r.nb_chambres,0)}</td>
      <td class="num">${fmt(r.hotel_to_annuel??r.taux_occupation,2)}</td>
      <td class="num">${fmt(r.hotel_guests_per_chambre??r.guests_per_chambre,2)}</td>
      <td><a class="link" href="/predict?hotel=${encodeURIComponent(r.hotel_code||'')}">Predire</a></td>
    </tr>`;
  }
  document.getElementById('list').innerHTML=h+'</tbody></table></div>';
}).catch(e=>{ document.getElementById('list').innerHTML=`<div class="errbox">${e.message}</div>`; });
"""


def create_web_app(paths: Paths | None = None) -> Flask:
    """App unique : routes web + API montees ensemble."""
    paths = (paths or Paths()).ensure()
    app = create_api_app(paths)

    @app.get("/")
    def home():
        return render_template_string(
            _page("Accor ROD", "Accor ROD", HOME_BODY)
        )

    @app.get("/eval")
    def eval_page():
        return render_template_string(
            _page("Evaluation LOO", "Evaluation LOO", EVAL_BODY, EVAL_SCRIPT)
        )

    @app.get("/compare")
    def compare_page():
        return render_template_string(
            _page(
                "Comparaison",
                "Comparaison",
                COMPARE_BODY,
                COMPARE_SCRIPT,
            )
        )

    @app.get("/predict")
    def predict_page():
        return render_template_string(
            _page("Prediction", "Prediction", PREDICT_BODY, PREDICT_SCRIPT)
        )

    @app.get("/hotels")
    def hotels_page():
        return render_template_string(
            _page("Hotels", "Hotels pilotes", HOTELS_BODY, HOTELS_SCRIPT)
        )

    return app
