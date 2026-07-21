/* Comparaison XGBoost vs reseau de neurones (MAE train / LOOCV). */

function escHtml(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function fmtMae(v) {
  return v == null || Number.isNaN(v) ? '—' : Number(v).toFixed(2);
}

function winnerLabel(winner) {
  if (winner === 'xgboost') return 'XGBoost';
  if (winner === 'neural') return 'Réseau de neurones';
  return '—';
}

function renderModelComparison(containerId, chartCanvasId, cfg, existingChart) {
  const el = document.getElementById(containerId);
  if (!el) return existingChart;

  const cmp = cfg?.model_comparison;
  const nn = cfg?.neural_network;
  const production = cfg?.production_model || 'xgboost';

  if (!cmp && (!nn || nn.status === 'absent')) {
    el.innerHTML = '<p class="muted">Comparaison indisponible — relancer <code>./init.sh</code> ou <code>train_model --force</code>.</p>';
    if (existingChart) existingChart.destroy();
    return null;
  }

  if (nn?.status === 'skipped') {
    el.innerHTML = `<p class="warn-text">Réseau de neurones non entraîné : ${escHtml(nn.reason || 'tensorflow absent')}.</p>`;
    if (existingChart) existingChart.destroy();
    return null;
  }

  const xgbMae = cmp?.xgboost_train_mae ?? cfg?.train_mae;
  const nnMae = cmp?.neural_train_mae ?? nn?.train_mae;
  const loocv = cmp?.neural_loocv_mae ?? nn?.loocv_mae;
  const winner = cmp?.winner_train_mae;
  const ratio = cmp?.neural_vs_xgb_ratio;

  el.innerHTML = `
    <div class="model-comparison-grid">
      <div class="comparison-card ${production === 'xgboost' ? 'is-production' : ''}">
        <span class="comparison-badge">Production</span>
        <strong>XGBoost</strong>
        <p class="comparison-metric">MAE train <em>${fmtMae(xgbMae)}</em></p>
        <small>MultiOutputRegressor · 120 arbres × 24 sorties</small>
      </div>
      <div class="comparison-card ${production === 'neural' ? 'is-production' : ''}">
        <span class="comparison-badge benchmark">Benchmark</span>
        <strong>Réseau de neurones</strong>
        <p class="comparison-metric">MAE train <em>${fmtMae(nnMae)}</em></p>
        <p class="comparison-metric secondary">LOOCV <em>${fmtMae(loocv)}</em></p>
        <small>${escHtml(nn?.architecture || 'seasonal_dual_tower')} · ${nn?.n_params ?? '—'} paramètres</small>
      </div>
      <div class="comparison-card summary">
        <span class="comparison-badge">Verdict train</span>
        <strong>${winnerLabel(winner)}</strong>
        <p class="comparison-metric">${ratio != null ? `NN / XGB = ×${ratio}` : '—'}</p>
        <small>${escHtml(nn?.description || '')}</small>
      </div>
    </div>`;

  const canvas = document.getElementById(chartCanvasId);
  if (!canvas || typeof Chart === 'undefined') return existingChart;

  if (existingChart) existingChart.destroy();

  const labels = ['MAE train XGBoost', 'MAE train NN', 'LOOCV NN'];
  const values = [xgbMae, nnMae, loocv].map(v => (v == null ? 0 : Number(v)));

  return new Chart(canvas, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'MAE (plus bas = mieux)',
        data: values,
        backgroundColor: ['#1e3a5f', '#7c3aed', '#a78bfa'],
        borderRadius: 6,
      }],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label(ctx) {
              const v = ctx.raw;
              return v == null ? '—' : `MAE : ${Number(v).toFixed(2)}`;
            },
          },
        },
      },
      scales: {
        y: {
          beginAtZero: true,
          title: { display: true, text: 'MAE' },
          ticks: { color: '#64748b' },
          grid: { color: '#e2e8f0' },
        },
        x: {
          ticks: { color: '#334155', font: { size: 11 } },
          grid: { display: false },
        },
      },
    },
  });
}