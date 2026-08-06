"""Page /user — parcours directeur (recherche hotel → params → simulation)."""

USER_CSS = """
.user-wrap { max-width: 980px; margin: 0 auto; }
.steps { display:flex; gap:.4rem; flex-wrap:wrap; margin-bottom:1rem; }
.steps .step {
  padding:.4rem .75rem; border-radius:999px; border:1px solid var(--line);
  font-size:.85rem; font-weight:600; color:var(--muted); background:#141c28;
}
.steps .step.on { background:var(--accent); border-color:var(--accent); color:#fff; }
.steps .step.done { border-color:var(--ok); color:var(--ok); }
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
.hotel-item:hover, .hotel-item.active { border-color:var(--accent); }
.hotel-item .name { font-weight:700; font-size:1rem; }
.hotel-item .meta { color:var(--muted); font-size:.88rem; margin-top:.15rem; }
.panel { display:none; }
.panel.on { display:block; }
.reco-box {
  border:1px solid rgba(61,214,140,.35); background:rgba(61,214,140,.08);
  border-radius:12px; padding:1rem 1.1rem; margin-bottom:1rem;
}
.reco-box h3 { margin:0 0 .35rem; font-size:1.05rem; color:var(--ok); }
"""

USER_BODY = """
<div class="user-wrap">
  <div class="steps">
    <span class="step on" data-step="1">1 · Hotel</span>
    <span class="step" data-step="2">2 · Parametres</span>
    <span class="step" data-step="3">3 · Simulation</span>
  </div>

  <section class="panel on" id="panel-1">
    <div class="card">
      <h2 style="margin-top:0">Choisir un hotel</h2>
      <p class="muted">Recherche par code, nom, marque ou ville — ex. <em>paris mercure H02</em></p>
      <div class="search-box">
        <input type="search" id="q" placeholder="paris mercure H02…" autocomplete="off"/>
        <button class="btn primary" type="button" id="btn-search">Rechercher</button>
      </div>
      <div id="results" class="hotel-list"><p class="muted">Saisir une recherche.</p></div>
    </div>
  </section>

  <section class="panel" id="panel-2">
    <div class="card" id="hotel-card"></div>
    <div class="card" style="margin-top:.85rem">
      <h2 style="margin-top:0">Parametres simulation</h2>
      <div class="row">
        <div><label>Chambres</label><input id="p_chambres" type="number" step="1"/></div>
        <div><label>TO annuel (0-1)</label><input id="p_to" type="number" step="0.01"/></div>
      </div>
      <div class="row">
        <div><label>Guests / chambre</label><input id="p_guests" type="number" step="0.1"/></div>
        <div><label>Metres lineaires</label><input id="p_mlin" type="number" step="0.1"/></div>
      </div>
      <div id="mix_type" class="mix-block"></div>
      <div id="mix_gamme" class="mix-block"></div>
      <div class="btn-row">
        <button class="btn" type="button" id="btn-back-1">Retour</button>
        <button class="btn primary" type="button" id="btn-to-sim">Lancer la simulation</button>
      </div>
    </div>
  </section>

  <section class="panel" id="panel-3">
    <div id="sim-out"><p class="muted">En attente…</p></div>
    <div class="btn-row">
      <button class="btn" type="button" id="btn-back-2">Modifier parametres</button>
      <button class="btn primary" type="button" id="btn-rerun">Relancer</button>
    </div>
  </section>
</div>
"""

# MixPanel class duplicated lightly + user flow (kept self-contained in script)
USER_SCRIPT = r"""
const fmt=(n,d=2)=>{if(n==null||n===''||Number.isNaN(Number(n)))return '—';return Number(n).toLocaleString('fr-FR',{maximumFractionDigits:d});};
const tag=s=>`<span class="tag ${(s||'').toString().toLowerCase()}">${s??''}</span>`;
const pctLabel=v=>`${Math.round(v*1000)/10} %`.replace('.0 %',' %');
const EPS=1e-9;

/** Etat hotel en memoire (modifs locales avant prediction). */
const memory={ hotel:null, typeMix:null, gammeMix:null };

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

let typeMix=null, gammeMix=null;

function setStep(n){
  document.querySelectorAll('.steps .step').forEach(s=>{
    const k=Number(s.dataset.step);
    s.classList.toggle('on', k===n);
    s.classList.toggle('done', k<n);
  });
  document.querySelectorAll('.panel').forEach((p,i)=>p.classList.toggle('on', i===n-1));
}

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
        <div class="meta">${h.hotel_brand||''} · ${h.hotel_city||''} · ${h.hotel_country||''} · ${fmt(h.hotel_nb_chambres,0)} ch</div>`;
      b.onclick=()=>selectHotel(h.hotel_code);
      box.appendChild(b);
    }
  }catch(e){ box.innerHTML=`<div class="errbox">${e.message}</div>`; }
}

async function selectHotel(code){
  try{
    const res=await fetch('/api/user/hotels/'+encodeURIComponent(code));
    const data=await res.json();
    if(!data.ok) throw new Error(data.error||'erreur');
    memory.hotel=data.hotel;
    // fill params
    const h=memory.hotel;
    document.getElementById('hotel-card').innerHTML=
      `<h2 style="margin-top:0">${h.hotel_code} · ${h.hotel_name||''}</h2>
       <div class="sub">${tag(h.hotel_brand)} · ${h.hotel_city||''} · ${h.hotel_country||''}</div>
       <div class="grid" style="margin-top:.7rem">
         <div class="card"><div class="lbl">Chambres</div><div class="val">${fmt(h.hotel_nb_chambres,0)}</div></div>
         <div class="card"><div class="lbl">TO</div><div class="val">${fmt(h.hotel_to_annuel,2)}</div></div>
         <div class="card"><div class="lbl">m lin.</div><div class="val">${fmt(h.hotel_metres_lineaires_dedies_corner??6,1)}</div></div>
       </div>`;
    document.getElementById('p_chambres').value=h.hotel_nb_chambres??100;
    document.getElementById('p_to').value=h.hotel_to_annuel??0.7;
    document.getElementById('p_guests').value=h.hotel_guests_per_chambre??1.7;
    document.getElementById('p_mlin').value=h.hotel_metres_lineaires_dedies_corner??6;
    typeMix=new MixPanel('mix_type','Mix type',[{key:'F&B',value:0.7},{key:'NON F&B',value:0.3}]);
    gammeMix=new MixPanel('mix_gamme','Mix gamme',[
      {key:'sans alcool',value:0.35},{key:'food salee',value:0.25},{key:'food sucree',value:0.15},
      {key:'accessoires',value:0.15},{key:'sos',value:0.10}
    ]);
    setStep(2);
  }catch(e){ alert(e.message); }
}

function payloadFromMemory(){
  const h=memory.hotel||{};
  return {
    hotel_code: h.hotel_code,
    hotel_nb_chambres: Number(document.getElementById('p_chambres').value),
    hotel_to_annuel: Number(document.getElementById('p_to').value),
    hotel_guests_per_chambre: Number(document.getElementById('p_guests').value),
    metres_lineaires: Number(document.getElementById('p_mlin').value),
    type_mix: typeMix?typeMix.toObject():{},
    gamme_mix: gammeMix?gammeMix.toObject():{},
    solutions: ['simply','liberty','connected'],
  };
}

async function runSim(){
  setStep(3);
  const out=document.getElementById('sim-out');
  out.innerHTML='<p class="muted">Simulation sim_v1 · sim_v2 · ml…</p>';
  try{
    const res=await fetch('/api/user/simulate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payloadFromMemory())});
    const data=await res.json();
    if(!data.ok) throw new Error(data.error||'erreur');
    const reco=data.recommendation||{};
    let html='';
    if(reco.recommended){
      html+=`<div class="reco-box"><h3>Recommandation : ${tag(reco.recommended)} ${reco.recommended_engine?tag(reco.recommended_engine):''}</h3>
        <p style="margin:0">${reco.reason||''}</p>
        ${(reco.warnings||[]).map(w=>`<div class="muted" style="margin-top:.35rem">${w}</div>`).join('')}
      </div>`;
    }
    // group by engine
    const byEng={};
    for(const r of (data.results||[])){
      (byEng[r.engine]=byEng[r.engine]||[]).push(r);
    }
    for(const eng of ['sim_v2','ml','sim_v1']){
      const rows=byEng[eng]; if(!rows||!rows.length) continue;
      html+=`<h2>${tag(eng)}</h2><div class="scroll"><table><thead><tr>
        <th>Solution</th><th class="num">CA / mois</th><th class="num">Marge / mois</th>
        <th class="num">Cout / mois</th><th class="num">Marge nette / mois</th><th class="num">Marge nette / an</th>
      </tr></thead><tbody>`;
      for(const r of rows){
        html+=`<tr>
          <td>${tag(r.solution)}</td>
          <td class="num">${fmt(r.ca_monthly)}</td>
          <td class="num">${fmt(r.marge_monthly)}</td>
          <td class="num">${fmt(r.costs&&r.costs.monthly_cost)}</td>
          <td class="num">${fmt(r.marge_nette_monthly)}</td>
          <td class="num"><strong>${fmt(r.marge_nette_annuelle)}</strong></td>
        </tr>`;
      }
      html+='</tbody></table></div>';
    }
    if((data.errors||[]).length){
      html+='<h2>Alertes</h2>';
      for(const e of data.errors){
        html+=`<div class="errbox">${e.engine||''} ${e.solution||''}: ${e.error||''}</div>`;
      }
    }
    out.innerHTML=html||'<p class="muted">Aucun resultat</p>';
  }catch(e){ out.innerHTML=`<div class="errbox">${e.message}</div>`; }
}

document.getElementById('btn-search').onclick=search;
document.getElementById('q').addEventListener('keydown',e=>{ if(e.key==='Enter') search(); });
document.getElementById('btn-back-1').onclick=()=>setStep(1);
document.getElementById('btn-back-2').onclick=()=>setStep(2);
document.getElementById('btn-to-sim').onclick=runSim;
document.getElementById('btn-rerun').onclick=runSim;
"""
