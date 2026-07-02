let enrichedFeatures = null;
let currentHotelId = null;
let chart = null;
let salesCatalog = null;
const CONCEPTS = ['SIMPLY', 'LIBERTY', 'CONNECTED'];
const mixState = { types: {}, gammes: {} };

function euros(v) { return Math.round(v || 0).toLocaleString('fr-FR') + ' €'; }
function num(v) { return Number.parseFloat(v || 0); }
function pct(v) { return (v || 0).toFixed(1) + ' %'; }
function pctErr(v) { return (v >= 0 ? '+' : '') + (v || 0).toFixed(1) + ' %'; }
function checkedValues(selector) { return Array.from(document.querySelectorAll(selector + ':checked')).map(x => x.value); }
function debounce(fn, ms) { let t; return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); }; }

function caMensuel(result) {
  return result.ca_mensuel_moyen || (result.ca_annuel / 12) || 0;
}

function mixKey(typeLabel, gamme) {
  return `${typeLabel}::${gamme}`;
}

function sumMixValues(bucket) {
  return Object.values(bucket).reduce((a, b) => a + b, 0);
}

function collectSubcategoryShares() {
  const shares = {};
  Object.entries(mixState.gammes).forEach(([key, pct]) => {
    if (pct > 0) shares[key] = pct / 100;
  });
  return shares;
}

function collectRodInputs() {
  const fb = mixState.types['F&B'] ?? 70;
  const nfb = mixState.types['NON-F&B'] ?? 30;
  const subcategoryShares = collectSubcategoryShares();
  const excluded = Object.entries(mixState.gammes)
    .filter(([, pct]) => pct <= 0)
    .map(([key]) => key.split('::')[1]);

  return {
    identity: {
      hotel_id: currentHotelId,
      hotel_name: document.getElementById('hotel_name').value,
      address: document.getElementById('address').value,
      city: document.getElementById('city').value,
      brand: document.getElementById('brand').value
    },
    operating: {
      nb_chambres: parseInt(document.getElementById('nb_chambres').value || '0', 10),
      taux_occupation: num(document.getElementById('taux_occupation').value),
      guests_per_chambre: num(document.getElementById('guests_per_chambre').value)
    },
    constraints: {
      excluded_categories: excluded,
      locked_fields: checkedValues('.locked')
    },
    store: {
      mix: {
        fb_share: fb / 100,
        non_fb_share: nfb / 100,
        subcategory_shares: subcategoryShares
      }
    },
    enriched: enrichedFeatures || {}
  };
}

function updateRemainingBanner(el, remaining) {
  const abs = Math.abs(remaining);
  el.className = 'mix-remaining ' + (abs < 0.05 ? 'ok' : 'warn');
  el.textContent = abs < 0.05
    ? 'Répartition complète (100 %)'
    : `Reste à distribuer : ${remaining.toFixed(1)} %`;
}

function renderTypeMix(catalog) {
  const panel = document.getElementById('type_mix_panel');
  const types = catalog.types || [];
  if (!types.length) {
    panel.innerHTML = '<p class="muted">Catalogue ventes indisponible — ./init.sh</p>';
    return;
  }
  types.forEach(t => {
    if (mixState.types[t] == null) mixState.types[t] = t === 'F&B' ? 70 : 30;
  });
  panel.innerHTML = `
    <h3>Catégories (TYPE)</h3>
    ${types.map(typeLabel => `
      <div class="mix-row" data-mix-type="${typeLabel}">
        <span>${typeLabel}</span>
        <input type="range" min="0" max="100" step="1" value="${mixState.types[typeLabel] || 0}"
          data-mix-kind="type" data-type="${typeLabel}">
        <span class="mix-value">${(mixState.types[typeLabel] || 0).toFixed(0)} %</span>
      </div>`).join('')}
    <div id="type_remaining" class="mix-remaining"></div>
    <div class="mix-actions">
      <button type="button" class="secondary" id="btn_distribute_types">Distribuer équitablement (catégories)</button>
    </div>`;

  const remainingEl = document.getElementById('type_remaining');
  const refreshTypeRemaining = () => {
    const sum = sumMixValues(mixState.types);
    updateRemainingBanner(remainingEl, 100 - sum);
  };
  refreshTypeRemaining();

  panel.querySelectorAll('input[data-mix-kind="type"]').forEach(input => {
    input.addEventListener('input', () => {
      const typeLabel = input.dataset.type;
      const newVal = parseInt(input.value, 10);
      const others = (catalog.types || []).filter(t => t !== typeLabel);
      if (newVal >= 100) {
        mixState.types[typeLabel] = 100;
        others.forEach(t => { mixState.types[t] = 0; });
      } else {
        mixState.types[typeLabel] = newVal;
        const otherSum = others.reduce((a, t) => a + (mixState.types[t] || 0), 0);
        const targetOther = 100 - newVal;
        if (otherSum > 0) {
          others.forEach(t => {
            mixState.types[t] = Math.round((mixState.types[t] / otherSum) * targetOther);
          });
        } else if (others.length) {
          others.forEach(t => { mixState.types[t] = Math.round(targetOther / others.length); });
        }
      }
      renderTypeMix(catalog);
      renderGammeMix(catalog);
      debounce(runSimulation, 500)();
    });
  });

  document.getElementById('btn_distribute_types')?.addEventListener('click', () => {
    const types = catalog.types || [];
    const sum = sumMixValues(mixState.types);
    const remaining = 100 - sum;
    const targets = types.filter(t => (mixState.types[t] || 0) > 0);
    const pool = targets.length ? targets : types;
    const add = remaining / pool.length;
    pool.forEach(t => { mixState.types[t] = Math.max(0, (mixState.types[t] || 0) + add); });
    const fix = 100 - sumMixValues(mixState.types);
    if (pool.length) mixState.types[pool[0]] += fix;
    renderTypeMix(catalog);
    renderGammeMix(catalog);
    runSimulation();
  });
}

function renderGammeMix(catalog) {
  const container = document.getElementById('gamme_mix_panels');
  const byType = catalog.by_type || {};
  container.innerHTML = Object.entries(byType).map(([typeLabel, gammes]) => {
    gammes.forEach(g => {
      const key = mixKey(typeLabel, g);
      if (mixState.gammes[key] == null) {
        mixState.gammes[key] = gammes.length ? Math.round(100 / gammes.length) : 0;
      }
    });
    const sum = gammes.reduce((a, g) => a + (mixState.gammes[mixKey(typeLabel, g)] || 0), 0);
    const remaining = 100 - sum;
    return `
      <div class="mix-panel" data-gamme-type="${typeLabel}">
        <h3>Sous-catégories ${typeLabel} (GAMME)</h3>
        ${gammes.map(g => {
          const key = mixKey(typeLabel, g);
          const val = mixState.gammes[key] || 0;
          return `
            <div class="mix-row">
              <span>${g}</span>
              <input type="range" min="0" max="100" step="1" value="${val}"
                data-mix-kind="gamme" data-type="${typeLabel}" data-gamme="${g}">
              <span class="mix-value">${val.toFixed(0)} %</span>
            </div>`;
        }).join('')}
        <div class="mix-remaining ${Math.abs(remaining) < 0.05 ? 'ok' : 'warn'}" data-remaining-type="${typeLabel}">
          ${Math.abs(remaining) < 0.05 ? 'Répartition complète (100 %)' : `Reste à distribuer : ${remaining.toFixed(1)} %`}
        </div>
        <div class="mix-actions">
          <button type="button" class="secondary btn-distribute-gammes" data-type="${typeLabel}">
            Distribuer équitablement (${typeLabel})
          </button>
        </div>
      </div>`;
  }).join('');

  container.querySelectorAll('input[data-mix-kind="gamme"]').forEach(input => {
    input.addEventListener('input', () => {
      const typeLabel = input.dataset.type;
      const gamme = input.dataset.gamme;
      const key = mixKey(typeLabel, gamme);
      const gammes = byType[typeLabel] || [];
      const newVal = parseInt(input.value, 10);
      const others = gammes.filter(g => g !== gamme);

      if (newVal >= 100) {
        mixState.gammes[key] = 100;
        others.forEach(g => { mixState.gammes[mixKey(typeLabel, g)] = 0; });
      } else {
        mixState.gammes[key] = newVal;
        const otherSum = others.reduce((a, g) => a + (mixState.gammes[mixKey(typeLabel, g)] || 0), 0);
        const targetOther = 100 - newVal;
        if (otherSum > 0) {
          others.forEach(g => {
            const k = mixKey(typeLabel, g);
            mixState.gammes[k] = Math.round((mixState.gammes[k] / otherSum) * targetOther);
          });
        } else if (others.length) {
          others.forEach(g => {
            mixState.gammes[mixKey(typeLabel, g)] = Math.round(targetOther / others.length);
          });
        }
      }
      renderGammeMix(catalog);
      debounce(runSimulation, 500)();
    });
  });

  container.querySelectorAll('.btn-distribute-gammes').forEach(btn => {
    btn.addEventListener('click', () => {
      const typeLabel = btn.dataset.type;
      const gammes = byType[typeLabel] || [];
      const sum = gammes.reduce((a, g) => a + (mixState.gammes[mixKey(typeLabel, g)] || 0), 0);
      const remaining = 100 - sum;
      const targets = gammes.filter(g => (mixState.gammes[mixKey(typeLabel, g)] || 0) > 0);
      const pool = targets.length ? targets : gammes;
      const add = remaining / pool.length;
      pool.forEach(g => {
        const k = mixKey(typeLabel, g);
        mixState.gammes[k] = Math.max(0, (mixState.gammes[k] || 0) + add);
      });
      const fix = 100 - gammes.reduce((a, g) => a + (mixState.gammes[mixKey(typeLabel, g)] || 0), 0);
      if (pool.length) mixState.gammes[mixKey(typeLabel, pool[0])] += fix;
      renderGammeMix(catalog);
      runSimulation();
    });
  });
}

async function loadSalesCatalog() {
  const res = await fetch('/api/sales-catalog');
  if (!res.ok) return;
  salesCatalog = await res.json();
  renderTypeMix(salesCatalog);
  renderGammeMix(salesCatalog);
}

async function loadBrands() {
  const el = document.getElementById('brands_info');
  const res = await fetch('/api/brands');
  if (!res.ok) { el.innerText = 'Marques non disponibles (./init.sh)'; return; }
  const data = await res.json();
  const lines = Object.entries(data.brands || {}).map(([brand, info]) =>
    `${brand}: ${info.total_hotels} hôtels`
  );
  el.innerHTML = lines.length ? lines.join(' · ') : 'Données marques absentes';
}

async function loadPerformance() {
  const res = await fetch('/api/performance');
  const tbody = document.querySelector('#perf_table tbody');
  const summary = document.getElementById('perf_summary');
  if (!res.ok) {
    summary.innerText = 'Rapport absent — exécutez ./init.sh';
    tbody.innerHTML = '';
    return;
  }
  const data = await res.json();
  const s = data.summary || {};
  summary.innerHTML = `
    <strong>Validation ${data.validation_year}</strong> — base : ${data.comparison_basis || 'période'}
    · ${s.n_hotels || 0} hôtels · ~${(s.mean_months_present || 0).toFixed(1)} mois/hôtel
    · Écart moyen période ROD : ${pct(s.mean_abs_rod_error_pct || 0)}
    · Écart moyen période IA : ${pct(s.mean_abs_ai_error_pct || 0)}
    · IA meilleure : ${s.ai_better_count || 0} hôtels
  `;
  tbody.innerHTML = (data.rows || []).map(r => `
    <tr>
      <td>${r.hotel_name}</td>
      <td>${r.nb_chambres}</td>
      <td>${pct((r.taux_occupation || 0) * 100)}</td>
      <td>${r.n_months_present} (${(r.months_present || []).join(',')})</td>
      <td>${euros(r.actual_ca_period)}</td>
      <td>${euros(r.rod_ca_period)}</td>
      <td>${euros(r.ai_ca_period)}</td>
      <td>${euros(r.actual_ca_annualized)}</td>
      <td>${euros(r.rod_ca_annualized)}</td>
      <td>${euros(r.ai_ca_annualized)}</td>
      <td>${pctErr(r.rod_error_pct)}</td>
      <td>${pctErr(r.ai_error_pct)}</td>
    </tr>
  `).join('');
}

async function enrichHotel(force = false) {
  const payload = collectRodInputs();
  payload.force_refresh = force;
  const status = document.getElementById('enrich_status');
  status.innerText = 'Enrichissement en cours...';
  const res = await fetch('/api/enrich', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
  if (!res.ok) { status.innerText = 'Erreur enrichissement'; return; }
  const data = await res.json();
  enrichedFeatures = data.features;
  currentHotelId = data.hotel_id;
  status.innerText = `OK — ${data.hotel_id}`;
  runSimulation();
}

async function runSimulation() {
  const res = await fetch('/api/simulate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(collectRodInputs()) });
  if (!res.ok) { alert('Erreur simulation'); return; }
  renderResults(await res.json());
}

async function runOptimize() {
  const res = await fetch('/api/optimize', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(collectRodInputs()) });
  if (!res.ok) { alert('Erreur optimisation'); return; }
  document.getElementById('raw_output').innerText = JSON.stringify(await res.json(), null, 2);
  runSimulation();
}

function renderConceptCard(concept, rod, ai, isRecommended) {
  const store = rod.store_config || {};
  const mix = store.mix || {};
  const bd = rod.breakdown || {};
  const badge = isRecommended ? '<span class="badge">Recommandé</span>' : '';
  const rodM = caMensuel(rod);
  const aiM = caMensuel(ai);
  return `
    <article class="concept-card ${isRecommended ? 'recommended' : ''}">
      <header><h3>${concept} ${badge}</h3>
        <p class="store-out">Config proposée : ${store.m_lin || '—'} m lin · F&B ${pct((mix.fb_share || 0) * 100)}</p>
      </header>
      <section class="source-block">
        <h4>ROD Excel (mois moyen)</h4>
        <div class="mini-kpis">
          <div><span>CA mois moyen</span><strong>${euros(rodM)}</strong></div>
          <div><span>CA annuel (×12)</span><strong>${euros(rod.ca_annuel)}</strong></div>
          <div><span>Marge nette ann.</span><strong class="highlight">${euros(rod.marge_annuelle)}</strong></div>
          <div><span>Coûts annuels</span><strong>${euros(rod.cout_annuel)}</strong></div>
        </div>
        <details><summary>Coûts mensuels</summary>
          <ul class="cost-list">
            <li>Technos ${euros(bd.techno_monthly)}/mois</li>
            <li>Annexes ${euros(bd.annexes_monthly)}/mois</li>
            <li>Agencement ${euros(bd.agencement_monthly)}/mois</li>
          </ul>
        </details>
      </section>
      <section class="source-block ai">
        <h4>IA (profil mensuel)</h4>
        <div class="mini-kpis">
          <div><span>CA mois moyen</span><strong>${euros(aiM)}</strong></div>
          <div><span>CA annuel (Σ12)</span><strong>${euros(ai.ca_annuel)}</strong></div>
          <div><span>Marge nette ann.</span><strong class="highlight">${euros(ai.marge_annuelle)}</strong></div>
          <div><span>Coûts annuels</span><strong>${euros(ai.cout_annuel)}</strong></div>
        </div>
      </section>
    </article>`;
}

function renderPipeline(pipeline) {
  if (!pipeline?.length) return '<p class="muted">Pipeline IA non disponible.</p>';
  return pipeline.map(step => {
    const parts = [];
    if (step.ca_mensuel_moyen != null) parts.push(`CA mois moyen : ${euros(step.ca_mensuel_moyen)}`);
    if (step.ca_annuel != null) parts.push(`CA annuel : ${euros(step.ca_annuel)}`);
    if (step.monthly_ca) parts.push(`Σ12 mois : ${euros(step.monthly_ca.reduce((a,b)=>a+b,0))}`);
    if (step.fallback) parts.push(`Fallback : ${step.fallback}`);
    return `<div class="pipeline-step"><strong>${step.label}</strong><span>${parts.join(' · ')}</span></div>`;
  }).join('');
}

function renderResults(data) {
  const reco = data.recommended_concept;
  document.getElementById('reco_banner').classList.remove('hidden');
  document.getElementById('reco_banner').innerHTML = `
    <strong>Recommandé : ${reco}</strong><span>${data.recommendation_reason || ''}</span>`;
  document.getElementById('concept_cards').innerHTML = CONCEPTS.map(c =>
    renderConceptCard(c, data.rod_by_concept[c], data.ai_by_concept[c], c === reco)).join('');

  const recoRod = data.rod_by_concept[reco];
  const recoAi = data.ai_by_concept[reco];
  const labels = recoRod.monthly.map(x => 'M' + String(x.month).padStart(2, '0'));
  const rodM = caMensuel(recoRod);
  const aiMonthly = recoAi.monthly.map(x => x.ca);
  const aiM = caMensuel(recoAi);

  if (chart) chart.destroy();
  chart = new Chart(document.getElementById('monthly_chart'), {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: `ROD mois moyen (${euros(rodM)})`, data: recoRod.monthly.map(() => rodM), borderColor: '#60a5fa', borderDash: [6,4] },
        { label: `IA profil mensuel (moy. ${euros(aiM)})`, data: aiMonthly, borderColor: '#34d399' },
        { label: `IA mois moyen (${euros(aiM)})`, data: aiMonthly.map(() => aiM), borderColor: '#a78bfa', borderDash: [2,2] }
      ]
    },
    options: { responsive: true, scales: { y: { title: { display: true, text: 'CA HT mensuel (€)' } } } }
  });

  document.getElementById('chart_legend').innerText =
    `Graphique en échelle mensuelle. ROD = ${euros(rodM)}/mois (plat). IA = profil 12 mois, annuel Σ = ${euros(recoAi.ca_annuel)}.`;
  document.getElementById('ai_pipeline').innerHTML = renderPipeline(recoAi.pipeline);
  document.getElementById('raw_output').innerText = JSON.stringify(data, null, 2);
}

function setupTabs() {
  document.querySelectorAll('.tab').forEach(btn => btn.addEventListener('click', () => {
    const tab = btn.dataset.tab;
    document.querySelectorAll('.tab').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
    document.querySelectorAll('.panel').forEach(p => p.classList.toggle('active', p.dataset.panel === tab));
    if (tab === '3') loadPerformance();
  }));
}

document.addEventListener('DOMContentLoaded', () => {
  setupTabs();
  loadBrands();
  loadSalesCatalog();
  loadPerformance();
  document.getElementById('btn_enrich').addEventListener('click', () => enrichHotel(false));
  document.getElementById('btn_simulate').addEventListener('click', runSimulation);
  document.getElementById('btn_optimize').addEventListener('click', runOptimize);
  document.querySelectorAll('input, select').forEach(el => el.addEventListener('change', debounce(runSimulation, 500)));
  runSimulation();
});