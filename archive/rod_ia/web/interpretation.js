let globalChart = null;
let hotelChart = null;
let modelComparisonChart = null;

function pct(v) { return (v || 0).toFixed(4); }

function loadPayload() {
  const raw = sessionStorage.getItem('rod_last_simulation');
  if (!raw) return null;
  try { return JSON.parse(raw); } catch { return null; }
}

function renderRules(listId, rules) {
  const el = document.getElementById(listId);
  if (!rules?.length) {
    el.innerHTML = '<li class="muted">Aucune règle disponible.</li>';
    return;
  }
  el.innerHTML = rules.map(r => `
    <li>
      <strong>${r.rule_id || 'RULE'}</strong>
      <span>${r.description || r.business_description || ''}</span>
      <small>${[r.source, r.python_method, r.workbook].filter(Boolean).join(' · ')}</small>
    </li>`).join('');
}

function renderConfig(cfg) {
  const el = document.getElementById('model_config');
  if (!cfg) { el.innerHTML = '<p class="muted">Modèle non chargé.</p>'; return; }
  const params = Object.entries(cfg.xgboost_params || {})
    .map(([k, v]) => `<li>${k}: <code>${v}</code></li>`).join('');
  el.innerHTML = `
    <div><span>Algorithme</span><strong>${cfg.algorithm || '—'}</strong></div>
    <div><span>Hôtels entraînement</span><strong>${cfg.n_hotels_train ?? '—'}</strong></div>
    <div><span>Features</span><strong>${cfg.n_features ?? '—'}</strong></div>
    <div><span>Targets</span><strong>${cfg.n_targets ?? '—'}</strong></div>
    <div><span>MAE train</span><strong>${cfg.train_mae != null ? cfg.train_mae.toFixed(2) : '—'}</strong></div>
    <div><span>Disponible</span><strong>${cfg.model_available ? 'Oui' : 'Non'}</strong></div>
    <div class="config-params"><span>Hyperparamètres XGBoost</span><ul>${params}</ul></div>
    ${(cfg.warnings || []).map(w => `<p class="warn-text">${w}</p>`).join('')}`;
}

function renderHighlights(data) {
  const el = document.getElementById('interp_highlights');
  const g = data.global_top_feature;
  const p = data.prediction_top_feature;
  el.innerHTML = `
    <div class="highlight-card">
      <span>Plus importante globalement</span>
      <strong>${g ? g.label : '—'}</strong>
      <small>${g ? `score ${pct(g.score)}` : ''}</small>
    </div>
    <div class="highlight-card accent">
      <span>Plus importante pour cette prédiction</span>
      <strong>${p ? p.label : '—'}</strong>
      <small>${p ? `valeur ${pct(p.value)} · écart vs train ${pct(p.value - (p.train_mean || 0))}` : ''}</small>
    </div>`;
}

function barChart(canvasId, rows, label, existing) {
  if (existing) existing.destroy();
  const ctx = document.getElementById(canvasId);
  if (!rows?.length) return null;
  return new Chart(ctx, {
    type: 'bar',
    data: {
      labels: rows.map(r => r.label),
      datasets: [{ label, data: rows.map(r => r.score), backgroundColor: '#2563eb' }]
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: '#64748b' }, grid: { color: '#e2e8f0' } },
        y: { ticks: { color: '#334155', font: { size: 10 } }, grid: { display: false } },
      },
    }
  });
}

async function loadInterpretation() {
  const payload = loadPayload();
  const context = document.getElementById('context_info');
  if (!payload) {
    context.innerHTML = 'Aucune simulation en mémoire — lancez une simulation puis revenez ici, ou utilisez les valeurs par défaut.';
  }
  const body = {
    ...(payload || {
      identity: { hotel_name: 'Ibis budget Nice', city: 'Nice', brand: 'IBIS_BUDGET' },
      operating: { nb_chambres: 129, taux_occupation: 0.8, guests_per_chambre: 1.7 },
      store: { mix: { fb_share: 0.7, non_fb_share: 0.3 } },
      enriched: {}
    }),
    concept: document.getElementById('concept_select').value
  };

  const res = await fetch('/api/model-interpretation', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  if (!res.ok) {
    context.innerHTML = 'Erreur chargement interprétation.';
    return;
  }
  const data = await res.json();
  context.innerHTML = `
    <strong>${data.hotel_name || 'Hôtel'}</strong>
    (${data.hotel_id || 'non identifié'}) — concept <strong>${data.concept}</strong>
    · recommandé : ${data.recommended_concept}`;

  renderConfig(data.model_config);
  modelComparisonChart = renderModelComparison(
    'model_comparison',
    'chart_model_comparison',
    data.model_config,
    modelComparisonChart,
  );
  renderHighlights(data);
  globalChart = barChart('chart_global', data.global_feature_importance, 'Importance globale', globalChart);
  hotelChart = barChart('chart_hotel', data.hotel_feature_importance, 'Importance hôtel', hotelChart);
  renderRules('global_rules', data.global_rules);
  renderRules('hotel_rules', data.hotel_rules);
}

document.addEventListener('DOMContentLoaded', () => {
  const params = new URLSearchParams(location.search);
  if (params.get('concept')) {
    document.getElementById('concept_select').value = params.get('concept');
  }
  document.getElementById('btn_refresh').addEventListener('click', loadInterpretation);
  document.getElementById('concept_select').addEventListener('change', loadInterpretation);
  loadInterpretation();
});