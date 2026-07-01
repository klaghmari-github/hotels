let chart = null;
let currentTab = 0;

function showTab(tabIndex) {
  document.querySelectorAll('.tab-content').forEach((el, i) => {
    el.classList.toggle('hidden', i !== tabIndex);
  });
  document.querySelectorAll('.tab-btn').forEach((el, i) => {
    el.classList.toggle('active', i === tabIndex);
    el.classList.toggle('border-b-2', i === tabIndex);
    el.classList.toggle('border-white', i === tabIndex);
  });
  currentTab = tabIndex;
}

function collectAllFeatureOverrides() {
  const overrides = {};
  document.querySelectorAll('.feature-input, input[data-col], select[data-col]').forEach(el => {
    const col = el.dataset.col || el.getAttribute('data-col');
    if (col && el.value !== '' && el.value != null) {
      let val = el.value;
      if (el.type === 'number' || !isNaN(parseFloat(val))) {
        val = parseFloat(val);
      }
      overrides[col] = val;
    }
  });

  // Location + m_lin / f_b_share from tab 4
  const loc = document.getElementById('location');
  if (loc) overrides.location = loc.value;

  const mlin = document.getElementById('m_lin');
  if (mlin) overrides.m_lin = parseFloat(mlin.value);

  const fb = document.getElementById('f_b_share');
  if (fb) overrides.f_b_share = parseFloat(fb.value);

  // JSON overrides (highest priority)
  const jsonBox = document.getElementById('feat_overrides_json');
  if (jsonBox && jsonBox.value.trim()) {
    try {
      const parsed = JSON.parse(jsonBox.value);
      Object.assign(overrides, parsed);
    } catch (e) {
      alert("JSON d'overrides invalide");
    }
  }

  return overrides;
}

async function collectAndPredict() {
  const overrides = collectAllFeatureOverrides();
  const loc = overrides.location || 'centre_ville_dense';

  const payload = {
    location: loc,
    overrides: overrides
  };

  const res = await fetch('/api/predict', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });

  if (!res.ok) {
    alert("Erreur lors de la prédiction");
    return;
  }

  const data = await res.json();

  // Show results
  document.getElementById('results').style.display = 'block';

  document.getElementById('kpi_ca').innerText = (data.total_ca || 0).toLocaleString('fr-FR');
  document.getElementById('kpi_ventes').innerText = (data.total_ventes || 0).toLocaleString('fr-FR');
  document.getElementById('kpi_fb').innerText = ((data.fb_share || 0) * 100).toFixed(0) + '%';

  // Store for what-if and export
  window.lastPrediction = data;

  // Breakdown by GAMME table
  renderByGamme(data.by_gamme || {});

  // Setup what-if exclusion checkboxes
  setupExclusionControls(Object.keys(data.by_gamme || {}));

  // Sample targets
  const sampleDiv = document.getElementById('sample_targets');
  if (data.sample_targets) {
    sampleDiv.innerHTML = Object.entries(data.sample_targets)
      .map(([k, v]) => `${k}: ${v}`).join('<br>');
  }

  // Monthly chart
  if (data.monthly_ca) {
    renderMonthlyChart(data.monthly_ca);
  }
}

function renderMonthlyChart(monthly) {
  const ctx = document.getElementById('monthlyChart');
  const labels = Object.keys(monthly || {});
  const values = Object.values(monthly || {});

  if (window._rodChart) window._rodChart.destroy();
  window._rodChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'CA mensuel prédit',
        data: values,
        backgroundColor: '#10b98130',
        borderColor: '#10b981',
        borderWidth: 1
      }]
    },
    options: {
      responsive: true,
      scales: { y: { beginAtZero: true } },
      plugins: { legend: { display: false } }
    }
  });
}

async function runRodSim() {
  const overrides = collectAllFeatureOverrides();
  const payload = {
    nb_ch: overrides['etape_rod__1_informations_generales__sous_etape_rod__donnees_admin__data__nb_de_chambres'] || 180,
    m_lin: overrides.m_lin || 5.0,
    f_b_share: overrides.f_b_share || 0.5,
    concept: 'SIMPLY',   // can be extended
    to: 0.78,
    guests_per_ch: 1.7
  };

  const res = await fetch('/api/rod_simulate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  const data = await res.json();
  alert("Simulation ROD (basée sur les inputs des écrans) :\n\n" + JSON.stringify(data, null, 2));
}

function downloadCSV() {
  if (!window.lastPrediction || !window.lastPrediction.full_targets) {
    alert("Pas de prédiction complète en mémoire. Relancez d'abord la prédiction.");
    return;
  }
  const data = window.lastPrediction;
  let csv = "variable,value\n";
  Object.entries(data.full_targets).forEach(([k, v]) => {
    csv += `${k},${v}\n`;
  });

  const blob = new Blob([csv], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'variables_cibles_predites_286.csv';
  a.click();
}

// === What-if / Coherence handling ===

let currentExclusions = new Set();

function renderByGamme(by_gamme) {
  const container = document.getElementById('by_gamme_table');
  if (!container) return;
  container.innerHTML = '';

  const total = Object.values(by_gamme).reduce((a, b) => a + b, 0);

  Object.entries(by_gamme).sort((a,b) => b[1]-a[1]).forEach(([gamme, val]) => {
    const pct = total > 0 ? ((val / total) * 100).toFixed(1) : 0;
    const div = document.createElement('div');
    div.className = 'bg-zinc-800 px-2 py-1 rounded text-xs flex justify-between';
    div.innerHTML = `
      <span>${gamme}</span>
      <span class="font-mono">${val.toLocaleString('fr-FR')} <span class="text-zinc-400">(${pct}%)</span></span>
    `;
    container.appendChild(div);
  });
}

function setupExclusionControls(gammes) {
  const container = document.getElementById('exclusion_controls');
  if (!container) return;
  container.innerHTML = '';
  currentExclusions = new Set();

  // Common interesting exclusions
  const commonExclusions = {
    'ALCOOL': true,
    'SANS_ALCOOL': false,
    'FOOD_SALEE': false,
    'FOOD_SUCREE': false
  };

  const defaultExclude = new Set(['ALCOOL']); // common example

  gammes.forEach(g => {
    const label = document.createElement('label');
    label.className = 'flex items-center gap-1 text-sm cursor-pointer bg-zinc-800 px-2 py-1 rounded';

    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = defaultExclude.has(g);
    if (cb.checked) currentExclusions.add(g);

    cb.onchange = () => {
      if (cb.checked) currentExclusions.add(g);
      else currentExclusions.delete(g);
      updateFilteredCA();
    };

    label.appendChild(cb);
    label.appendChild(document.createTextNode(` ${g}`));
    container.appendChild(label);
  });

  // Initial filtered value
  setTimeout(updateFilteredCA, 30);
}

function updateFilteredCA() {
  if (!window.lastPrediction || !window.lastPrediction.by_gamme) return;

  const byG = window.lastPrediction.by_gamme;
  let filtered = 0;
  let excludedSum = 0;

  Object.entries(byG).forEach(([g, val]) => {
    if (currentExclusions.has(g)) {
      excludedSum += val;
    } else {
      filtered += val;
    }
  });

  const total = window.lastPrediction.total_ca || 0;

  document.getElementById('kpi_filtered').innerText = filtered.toLocaleString('fr-FR');

  const deltaEl = document.getElementById('filtered_delta');
  if (deltaEl) {
    const delta = total - filtered;
    deltaEl.innerText = delta > 0 ? `-${delta.toLocaleString('fr-FR')} (-${((delta/total)*100).toFixed(1)}%)` : '';
  }
}

async function applyMixRedistribution() {
  if (!window.lastPrediction || !window.lastPrediction.by_gamme) {
    alert("Faites d'abord une prédiction");
    return;
  }

  const desiredFb = parseFloat(document.getElementById('desired_fb_pct').value) / 100 || 0.1;
  const desiredAlcoolInFb = parseFloat(document.getElementById('desired_alcool_pct').value) / 100 || 0;

  // Build desired_mix for the backend reallocate (example: set ALCOOL to 0, adjust F&B)
  const desired = {
    "ALCOOL": 0,
    "FOOD_SALEE": 0,   // will be redistributed
    "FOOD_SUCREE": 0,
    "SANS_ALCOOL": 0
  };

  // Simpler: tell the backend the target F&B and ALCOOL
  // The backend reallocate will handle proportional
  const res = await fetch('/api/reallocate', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      base_by_gamme: window.lastPrediction.by_gamme,
      total_ca: window.lastPrediction.total_ca,
      desired_mix: {
        "ALCOOL": desiredAlcoolInFb * desiredFb,
        "FOOD_SALEE": 0,
        "FOOD_SUCREE": 0,
        "SANS_ALCOOL": 0
      }
    })
  });

  const r = await res.json();
  const newBy = r.new_by_gamme || window.lastPrediction.by_gamme;

  // Update UI
  document.getElementById('kpi_filtered').innerText = r.new_total_ca.toLocaleString('fr-FR');

  const container = document.getElementById('by_gamme_table');
  container.innerHTML = '';
  Object.entries(newBy).sort((a,b)=>b[1]-a[1]).forEach(([g,v]) => {
    const pct = r.new_total_ca > 0 ? (v / r.new_total_ca * 100).toFixed(1) : 0;
    const div = document.createElement('div');
    div.className = 'bg-zinc-800 px-2 py-1 rounded text-xs flex justify-between';
    div.innerHTML = `<span>${g} (redist.)</span><span>${v.toFixed(0)} (${pct}%)</span>`;
    container.appendChild(div);
  });

  alert("Redistribution appliquée via logique proportionnelle (les parts des autres augmentent pour garder 100%).");
}

document.addEventListener('DOMContentLoaded', () => {
  // Show first tab by default
  showTab(0);

  // Make all number inputs trigger nice behavior
  document.querySelectorAll('input[type="number"]').forEach(el => {
    el.addEventListener('focus', () => el.select());
  });
});

// Additional: call full business sim and show P&L + reco in console + UI
console.log("Business logic integrated: funnel, reallocate, P&L, recommendations.");

// Quick helper if user wants to trigger full sim from console
window.runBusiness = runFullBusinessSim;


async function enrichHotel() {
  const name = document.getElementById('hotel_name').value || 'Ibis budget Nice';
  const city = document.getElementById('city').value || 'Nice';
  const status = document.getElementById('enrich_status');
  status.innerText = 'Enrichissement...';
  try {
    const res = await fetch('/api/enrich', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({hotel_name: name, city: city})
    });
    const d = await res.json();
    window.enrichedFeatures = d.enriched_features || {};
    status.innerText = 'POI + Météo auto calculés !';
    console.log('Enriched:', window.enrichedFeatures);
  } catch(e) {
    status.innerText = 'Enrichissement simulé.';
    window.enrichedFeatures = {};
  }
}

function normalizeMix() {
  const fb = parseFloat(document.getElementById('mix_fb').value) || 40;
  const non = document.getElementById('mix_nonfb');
  if (non) non.value = (100 - fb);
  alert('Ajustez les sous % manuellement.');
}

async function predictWithForcedMix() {
  const params = collectRodInputs();
  const desired = {
    'ALCOOL': (parseFloat(document.getElementById('p_alcool').value) || 10) / 100,
    'FOOD_SALEE': (parseFloat(document.getElementById('p_food').value) || 35) / 100,
    'FOOD_SUCREE': (parseFloat(document.getElementById('p_sucre').value) || 30) / 100,
    'SANS_ALCOOL': (parseFloat(document.getElementById('p_sans').value) || 25) / 100
  };
  const payload = Object.assign({}, params, {desired_mix: desired, overrides: params.overrides || {}});
  const res = await fetch('/api/business_simulate', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
  const data = await res.json();
  const t = data.adjusted_profile ? Object.values(data.adjusted_profile).reduce((a,b)=>a+b,0) : (data.base_profile ? data.base_profile.total_ca : 0);
  document.getElementById('kpi_ca').innerText = Math.round(t).toLocaleString('fr-FR');
  alert('Avec votre mix forcé : ' + Math.round(t) + ' € de CA annuel');
  window.lastPrediction = data;
}

async function proposeBestMix() {
  const params = collectRodInputs();
  const payload = Object.assign({}, params, {desired_mix: {}});
  const res = await fetch('/api/business_simulate', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
  const data = await res.json();
  const t = data.base_profile ? data.base_profile.total_ca : 0;
  document.getElementById('kpi_ca').innerText = Math.round(t).toLocaleString('fr-FR');
  if (data.recommendations && data.recommendations.length) {
    const b = data.recommendations[0];
    alert('Meilleur proposé : ' + b.concept + ' m_lin=' + b.m_lin + ' → Marge ' + b.margin + '€');
  }
  window.lastPrediction = data;
}

