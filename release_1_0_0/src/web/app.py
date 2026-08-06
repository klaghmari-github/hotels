"""
GUI web : evaluation LOO, prediction hotel, exploration datasets.
"""

from __future__ import annotations

from flask import Flask, render_template_string

from release_1_0_0.src.api.app import create_api_app
from release_1_0_0.src.pipeline.paths import Paths
from release_1_0_0.src.web.styles import COMMON_CSS

NAV = """
<nav>
  <a class="link" href="/">Accueil</a>
  <a class="link" href="/eval">Evaluation LOO</a>
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
    <h1>__H1__ <span>release 1.0.0</span></h1>
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
<p class="muted">Simulateurs ROD v1 / v2 et modele CatBoost — evaluation leave-one-out et prediction hotel.</p>
<div class="grid">
  <a class="card" href="/eval" style="text-decoration:none;color:inherit">
    <div class="lbl">Evaluation</div>
    <div class="val" style="font-size:1rem">LOO hotels pilotes</div>
    <div class="sub">sim_v1 · sim_v2 · CatBoost</div>
  </a>
  <a class="card" href="/predict" style="text-decoration:none;color:inherit">
    <div class="lbl">Prediction</div>
    <div class="val" style="font-size:1rem">Hotel cible</div>
    <div class="sub">Restitution et ML</div>
  </a>
  <a class="card" href="/hotels" style="text-decoration:none;color:inherit">
    <div class="lbl">Hotels</div>
    <div class="val" style="font-size:1rem">Parametres</div>
    <div class="sub">Charger un pilote pour predire</div>
  </a>
</div>
"""

EVAL_BODY = """
<div style="display:flex;gap:.5rem;flex-wrap:wrap;margin-bottom:1rem">
  <button class="btn primary" data-src="sim_v1" type="button">sim_v1</button>
  <button class="btn" data-src="sim_v2" type="button">sim_v2</button>
  <button class="btn" data-src="ml" type="button">CatBoost</button>
  <span id="status" class="muted"></span>
</div>
<div id="main"><p class="muted">Choisir une source d evaluation.</p></div>
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
  document.getElementById('status').textContent='Chargement…';
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
    document.getElementById('main').innerHTML=html;
    document.getElementById('status').textContent=data.source||'';
  }catch(e){
    document.getElementById('main').innerHTML=`<div class="errbox">${e.message}</div>`;
    document.getElementById('status').textContent='Erreur';
  }
}
document.querySelectorAll('button[data-src]').forEach(b=>b.onclick=()=>load(b.dataset.src));
load('sim_v1');
"""

PREDICT_BODY = """
<div class="layout">
  <form class="card" id="form" onsubmit="return false;">
    <h2 style="margin-top:0">Parametres hotel</h2>
    <label>Hotel pilote (optionnel)</label>
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
    <label>hotel_code (sim_v1 LOO)</label>
    <input name="hotel_code" type="text" placeholder="ex. H2075"/>
    <label>Mix type (JSON)</label>
    <textarea name="type_mix" rows="2">{"F&B": 0.7, "NON F&B": 0.3}</textarea>
    <label>Mix gamme (JSON)</label>
    <textarea name="gamme_mix" rows="3">{"sans alcool": 0.35, "food salee": 0.25, "food sucree": 0.15, "accessoires": 0.15, "sos": 0.10}</textarea>
    <div style="margin-top:1rem;display:flex;gap:.5rem;flex-wrap:wrap">
      <button class="btn primary" id="btnV2" type="button">sim_v2</button>
      <button class="btn" id="btnML" type="button">CatBoost</button>
      <button class="btn" id="btnV1" type="button">sim_v1</button>
    </div>
  </form>
  <div>
    <div id="hotel_info" class="card muted">Selectionner un hotel pour pre-remplir les champs (modifiables pour simulation).</div>
    <div id="out" style="margin-top:1rem"></div>
  </div>
</div>
"""

PREDICT_SCRIPT = r"""
const fmt=(n,d=2)=>{if(n==null||n===''||Number.isNaN(Number(n)))return '—';return Number(n).toLocaleString('fr-FR',{maximumFractionDigits:d});};
const tag=s=>`<span class="tag ${(s||'').toString().toLowerCase()}">${s??''}</span>`;
function bodyFromForm(){
  const fd=new FormData(document.getElementById('form'));
  return {
    hotel_nb_chambres: Number(fd.get('hotel_nb_chambres')),
    hotel_to_annuel: Number(fd.get('hotel_to_annuel')),
    hotel_guests_per_chambre: Number(fd.get('hotel_guests_per_chambre')),
    metres_lineaires: Number(fd.get('metres_lineaires')),
    solution: fd.get('solution'),
    hotel_code: (fd.get('hotel_code')||'').trim(),
    type_mix: JSON.parse(fd.get('type_mix')||'{}'),
    gamme_mix: JSON.parse(fd.get('gamme_mix')||'{}'),
  };
}
async function call(url){
  const out=document.getElementById('out');
  out.innerHTML='<p class="muted">Calcul…</p>';
  try{
    const res=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(bodyFromForm())});
    const data=await res.json();
    if(!data.ok) throw new Error(data.error||'echec');
    if(data.predictions){
      let h='<h2>Restitution sim_v2</h2><div class="scroll"><table><thead><tr><th>Solution</th><th>Methode</th><th>CA</th><th>Marge marche</th><th>Marge coef</th></tr></thead><tbody>';
      for(const r of data.predictions){
        h+=`<tr><td>${tag(r.solution)}</td><td>${tag(r.methode)}</td>
          <td class="num">${fmt(r.montant_ventes_par_mois_predit)}</td>
          <td class="num">${fmt(r.montant_marge_par_mois_predite)}</td>
          <td class="num">${fmt(r.montant_marge_selon_coef_par_mois_predite)}</td></tr>`;
      }
      out.innerHTML=h+'</tbody></table></div>';
    } else if(data.prediction){
      const p=data.prediction;
      out.innerHTML=`<h2>Prediction ${tag(data.model||'ml')}</h2>
        <div class="grid">
          <div class="card"><div class="lbl">CA mensuel</div><div class="val">${fmt(p.montant_ventes_par_mois)}</div></div>
          <div class="card"><div class="lbl">Marge marche</div><div class="val">${fmt(p.montant_marge_par_mois)}</div></div>
          <div class="card"><div class="lbl">Marge coef</div><div class="val">${fmt(p.montant_marge_selon_coef_par_mois)}</div></div>
        </div>`;
    } else if(data.montant_ventes_par_mois!=null){
      out.innerHTML=`<h2>Prediction sim_v1 ${tag(data.solution)}</h2>
        <div class="grid">
          <div class="card"><div class="lbl">CA predit</div><div class="val">${fmt(data.montant_ventes_par_mois)}</div></div>
          <div class="card"><div class="lbl">Marge predite</div><div class="val">${fmt(data.montant_marge_par_mois)}</div></div>
        </div>`;
    }
  }catch(e){ out.innerHTML=`<div class="errbox">${e.message}</div>`; }
}
document.getElementById('btnV2').onclick=()=>call('/api/predict/sim_v2');
document.getElementById('btnML').onclick=()=>call('/api/predict/ml');
document.getElementById('btnV1').onclick=()=>call('/api/predict/sim_v1');

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
  sel.onchange=()=>{
    const opt=sel.selectedOptions[0];
    if(!opt||!opt.dataset.payload) return;
    const h=JSON.parse(opt.dataset.payload);
    const form=document.getElementById('form');
    form.hotel_code.value=h.hotel_code||'';
    if(h.hotel_nb_chambres) form.hotel_nb_chambres.value=h.hotel_nb_chambres;
    if(h.hotel_to_annuel) form.hotel_to_annuel.value=h.hotel_to_annuel;
    if(h.hotel_guests_per_chambre) form.hotel_guests_per_chambre.value=h.hotel_guests_per_chambre;
    if(h.solution) form.solution.value=String(h.solution).toLowerCase();
    document.getElementById('hotel_info').innerHTML=
      `<strong>${h.hotel_code}</strong> ${tag(h.solution)}
       <div class="sub">chambres ${fmt(h.hotel_nb_chambres,0)} · TO ${fmt(h.hotel_to_annuel,2)} · guests ${fmt(h.hotel_guests_per_chambre,2)}</div>
       <p class="muted" style="margin:.4rem 0 0">Champs modifiables pour simuler (certains non consommes par tous les modeles).</p>`;
  };
}).catch(()=>{});
"""

HOTELS_BODY = """
<p class="muted">Hotels pilotes charges depuis la base (t_sales / v_hotel_params). Cliquer pour ouvrir la prediction pre-remplie.</p>
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
