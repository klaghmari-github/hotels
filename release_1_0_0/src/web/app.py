"""
GUI web : accueil, /user, /admin (+ outils avances).
"""

from __future__ import annotations

from flask import Flask, render_template_string

from src.api.app import create_api_app
from src.pipeline.paths import Paths
from src.web.pages_admin import ADMIN_BODY, ADMIN_CSS, ADMIN_SCRIPT
from src.web.pages_user import USER_BODY, USER_CSS, USER_SCRIPT
from src.web.styles import COMMON_CSS

NAV_HOME = """
<nav>
  <a class="link" href="/user">User</a>
  <a class="link" href="/admin">Admin</a>
</nav>
"""

NAV_USER = """
<nav>
  <a class="link" href="/user">Parcours</a>
  <a class="link" href="/admin">Admin</a>
</nav>
"""

NAV_ADMIN = """
<nav>
  <a class="link" href="/user">User</a>
  <a class="link" href="/admin">Studio</a>
</nav>
"""


def _shell(extra_css: str = "", nav: str = NAV_HOME) -> str:
    css = COMMON_CSS + extra_css
    return f"""
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>__TITLE__</title>
  <style>{css}</style>
</head>
<body>
  <header>
    <h1><a class="brand" href="/" title="Accueil">Accor ROD</a> <span>release 1.0.0</span></h1>
    {nav}
  </header>
  <main>__BODY__</main>
  <script>__SCRIPT__</script>
</body>
</html>
"""


def _page(
    title: str,
    body: str,
    script: str = "",
    *,
    extra_css: str = "",
    nav: str = NAV_HOME,
) -> str:
    return (
        _shell(extra_css=extra_css, nav=nav)
        .replace("__TITLE__", title)
        .replace("__BODY__", body)
        .replace("__SCRIPT__", script)
    )


HOME_BODY = """
<div style="max-width:820px;margin:0 auto">
  <div style="display:flex;align-items:center;gap:1rem;margin-bottom:1.25rem">
    <img src="/static/img/accor-logo.svg" alt="Accor" style="height:40px"/>
    <div>
      <h2 style="margin:0">Accor ROD</h2>
      <p class="muted" style="margin:.2rem 0 0">Choisir une interface</p>
    </div>
  </div>
  <div class="grid">
    <a class="card" href="/user" style="text-decoration:none;color:inherit">
      <div class="lbl">User</div>
      <div class="val" style="font-size:1.05rem">Interface directeur</div>
      <div class="sub">Recherche hotel · parametres · simulation · recommandation</div>
    </a>
    <a class="card" href="/admin" style="text-decoration:none;color:inherit">
      <div class="lbl">Admin</div>
      <div class="val" style="font-size:1.05rem">Studio donnees</div>
      <div class="sub">ALL · PILOTE · evaluation LOO</div>
    </a>
  </div>
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
const EVAL_COLS=[
  {k:'hotel_code',l:'Hotel'},{k:'solution',l:'Solution'},
  {k:'ca_reel',l:'CA reel / mois',kind:'reel'},{k:'ca_pred',l:'CA estime / mois',kind:'pred'},{k:'ca_err_abs',l:'|err| CA / mois',kind:'err'},
  {k:'marge_reel',l:'Marge reel / mois',kind:'reel'},{k:'marge_pred',l:'Marge estimee / mois',kind:'pred'},{k:'marge_err_abs',l:'|err| Marge / mois',kind:'err'},
];
function pickM(metrics,key){
  if(!metrics||!metrics.length) return null;
  const o=[...metrics].sort((a,b)=>(String(a.scope||'').toUpperCase()==='ALL'?0:1)-(String(b.scope||'').toUpperCase()==='ALL'?0:1));
  for(const m of o){ if(m[key]!=null) return Number(m[key]); }
  return null;
}
async function load(src){
  const main=document.getElementById('main');
  main.innerHTML='<p class="muted">Chargement…</p>';
  document.querySelectorAll('button[data-src]').forEach(b=>b.classList.toggle('primary', b.dataset.src===src));
  try{
    const res=await fetch('/api/eval/'+src);
    const data=await res.json();
    if(!data.ok) throw new Error(data.error||'erreur');
    const n=new Set((data.predictions||[]).map(p=>p.hotel_code).filter(Boolean)).size;
    let html=`<div class="grid">
      <div class="card"><div class="lbl">${tag(src)} · MAE CA</div><div class="val">${fmt(pickM(data.metrics,'mae_ca'))}</div><div class="sub">n=${n}</div></div>
      <div class="card"><div class="lbl">${tag(src)} · MAE marge</div><div class="val">${fmt(pickM(data.metrics,'mae_marge'))}</div><div class="sub">selon coef</div></div>
    </div>`;
    html+='<p class="muted" style="margin:.75rem 0 .4rem">Bleu reel · Violet estime · Orange erreur · <strong>mensuel (€ / mois)</strong></p>';
    html+='<div class="scroll"><table><thead><tr>';
    html+=EVAL_COLS.map(c=>`<th class="${c.kind?('col-'+c.kind):''}">${c.l}</th>`).join('');
    html+='</tr></thead><tbody>';
    for(const r of (data.predictions||[])){
      html+='<tr>'+EVAL_COLS.map(c=>{
        if(c.k==='solution') return `<td>${tag(r[c.k])}</td>`;
        if(c.k==='hotel_code') return `<td><strong>${r[c.k]??'—'}</strong></td>`;
        return `<td class="num ${c.kind?('col-'+c.kind):''}">${r[c.k]==null?'—':fmt(r[c.k])}</td>`;
      }).join('')+'</tr>';
    }
    html+='</tbody></table></div>';
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
function pick(metrics,key){
  if(!metrics||!metrics.length) return null;
  const ordered=[...metrics].sort((a,b)=>(String(a.scope||'').toUpperCase()==='ALL'?0:1)-(String(b.scope||'').toUpperCase()==='ALL'?0:1));
  for(const m of ordered){ if(m[key]!=null) return Number(m[key]); }
  return null;
}
async function render(){
  const main=document.getElementById('main');
  main.innerHTML='<p class="muted">Chargement…</p>';
  const results=await Promise.all(SOURCES.map(async src=>{
    try{
      const res=await fetch('/api/eval/'+src); const data=await res.json();
      if(!data.ok) return {src, ok:false, error:data.error};
      return {src, ok:true, metrics:data.metrics||[], predictions:data.predictions||[]};
    }catch(e){ return {src, ok:false, error:e.message}; }
  }));
  const kpis=results.map(r=>{
    if(!r.ok) return {src:r.src, mae_ca:null, mae_marge:null, n:null, err:r.error};
    return {
      src:r.src,
      mae_ca: pick(r.metrics,'mae_ca'),
      mae_marge: pick(r.metrics,'mae_marge'),
      n: new Set((r.predictions||[]).map(p=>p.hotel_code).filter(Boolean)).size,
      err:null,
    };
  });
  const best=(key)=>{ let b=null,v=Infinity; for(const k of kpis){ if(k[key]!=null&&k[key]<v){v=k[key];b=k.src;} } return b; };
  const bestCa=best('mae_ca'), bestM=best('mae_marge');
  let html='<p class="muted">Comparaison sur <strong>MAE CA</strong> et <strong>MAE marge selon coef</strong> uniquement.</p><div class="grid">';
  for(const k of kpis){
    html+=`<div class="card"><div class="lbl">${tag(k.src)}</div>
      <div class="val">${fmt(k.mae_ca)}</div><div class="sub">MAE CA${k.src===bestCa?' · meilleur':''}</div>
      <div class="sub">MAE marge coef : <strong style="${k.src===bestM?'color:var(--ok)':''}">${fmt(k.mae_marge)}</strong></div>
      <div class="sub">hotels=${k.n??'—'}</div></div>`;
  }
  html+='</div><h2>Tableau</h2><div class="scroll"><table><thead><tr><th>Metrique</th>';
  html+=SOURCES.map(s=>`<th class="num">${s}</th>`).join('')+'</tr></thead><tbody>';
  for(const [lab,key] of [['MAE CA','mae_ca'],['MAE marge coef','mae_marge'],['Nb hotels','n']]){
    html+=`<tr><td>${lab}</td>`;
    for(const s of SOURCES){
      const k=kpis.find(x=>x.src===s); const v=k?k[key]:null;
      const win=(key==='mae_ca'&&s===bestCa)||(key==='mae_marge'&&s===bestM);
      html+=`<td class="num"${win?' style="color:var(--ok);font-weight:700"':''}>${fmt(v,key==='n'?0:2)}</td>`;
    }
    html+='</tr>';
  }
  html+='</tbody></table></div>';
  // par hotel — err marge coef
  const byH={};
  for(const r of results.filter(x=>x.ok)){
    for(const p of r.predictions||[]){
      if(!p.hotel_code) continue;
      if(!byH[p.hotel_code]) byH[p.hotel_code]={hotel:p.hotel_code, solution:p.solution};
      byH[p.hotel_code][r.src]=p;
    }
  }
  const hotels=Object.values(byH).sort((a,b)=>String(a.hotel).localeCompare(String(b.hotel)));
  if(hotels.length){
    html+='<h2>Par hotel (|err| marge coef)</h2><div class="scroll"><table><thead><tr><th>Hotel</th><th>Solution</th>';
    for(const s of SOURCES) html+=`<th class="num col-err">${s}</th>`;
    html+='</tr></thead><tbody>';
    for(const h of hotels){
      html+=`<tr><td><strong>${h.hotel}</strong></td><td>${tag(h.solution)}</td>`;
      let bestE=Infinity,bestS=null;
      for(const s of SOURCES){ const e=h[s]?.marge_err_abs; if(e!=null&&e<bestE){bestE=e;bestS=s;} }
      for(const s of SOURCES){
        const e=h[s]?.marge_err_abs;
        html+=`<td class="num col-err"${s===bestS?' style="font-weight:700;color:var(--ok)"':''}>${fmt(e)}</td>`;
      }
      html+='</tr>';
    }
    html+='</tbody></table></div>';
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
        <div class="card"><div class="lbl">CA estime</div><div class="val">${fmt(data.montant_ventes_par_mois)}</div></div>
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
            _page("Accor ROD", HOME_BODY, nav=NAV_HOME)
        )

    @app.get("/user")
    def user_page():
        return render_template_string(
            _page(
                "ROD User",
                USER_BODY,
                USER_SCRIPT,
                extra_css=USER_CSS,
                nav=NAV_USER,
            )
        )

    @app.get("/admin")
    def admin_page():
        return render_template_string(
            _page(
                "ROD Admin",
                ADMIN_BODY,
                ADMIN_SCRIPT,
                extra_css=ADMIN_CSS,
                nav=NAV_ADMIN,
            )
        )

    # Outils avances (admin)
    @app.get("/eval")
    def eval_page():
        return render_template_string(
            _page("Evaluation LOO", EVAL_BODY, EVAL_SCRIPT, nav=NAV_ADMIN)
        )

    @app.get("/compare")
    def compare_page():
        return render_template_string(
            _page("Comparaison", COMPARE_BODY, COMPARE_SCRIPT, nav=NAV_ADMIN)
        )

    @app.get("/predict")
    def predict_page():
        return render_template_string(
            _page("Prediction", PREDICT_BODY, PREDICT_SCRIPT, nav=NAV_ADMIN)
        )

    @app.get("/hotels")
    def hotels_page():
        return render_template_string(
            _page("Hotels", HOTELS_BODY, HOTELS_SCRIPT, nav=NAV_ADMIN)
        )

    return app
