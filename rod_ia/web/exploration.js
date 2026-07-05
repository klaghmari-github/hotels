/* Exploration donnees et modele */

const MONTHS = ['Jan','Fev','Mar','Avr','Mai','Jun','Jul','Aou','Sep','Oct','Nov','Dec'];

function esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function renderTable(stage) {
  if (!stage.rows || !stage.rows.length) {
    return `<p class="muted">Aucune ligne disponible.</p>`;
  }
  const head = stage.columns.map(c => `<th>${esc(c)}</th>`).join('');
  const body = stage.rows.map(row => {
    const cells = stage.columns.map(c => `<td>${esc(row[c])}</td>`).join('');
    return `<tr>${cells}</tr>`;
  }).join('');
  const meta = `${stage.n_rows_total} lignes, ${stage.n_cols_total} colonnes` +
    (stage.truncated_cols ? ' (colonnes tronquees a l affichage)' : '');
  return `<p class="stage-meta muted">${esc(stage.description)} — ${meta}</p>
    <div class="table-scroll"><table class="explore-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

async function loadDataExploration(hotelId) {
  const q = hotelId ? `?hotel_id=${encodeURIComponent(hotelId)}` : '';
  const res = await fetch(`/api/data-exploration${q}`);
  if (!res.ok) throw new Error('Impossible de charger les donnees');
  return res.json();
}

function fillHotelSelects(hotels) {
  ['data_hotel_select', 'predict_hotel_select'].forEach(id => {
    const sel = document.getElementById(id);
    const keep = sel.querySelector('option');
    sel.innerHTML = '';
    sel.appendChild(keep);
    hotels.forEach(h => {
      const opt = document.createElement('option');
      opt.value = h.hotel_id;
      opt.textContent = `${h.name} (${h.brand || ''})`;
      sel.appendChild(opt);
    });
  });
}

function renderDataStages(payload) {
  const root = document.getElementById('data_stages');
  root.innerHTML = payload.stages.map((s, i) => `
    <details class="card stage-card" ${i < 2 ? 'open' : ''}>
      <summary><strong>${i + 1}. ${esc(s.title)}</strong></summary>
      ${renderTable(s)}
    </details>`).join('');
}

function featureLabel(name, idx) {
  if (name.startsWith('f')) {
    const n = parseInt(name.slice(1), 10);
    return window._featureCols?.[n] || name;
  }
  return name;
}

function renderTreeNode(node, featureCols, depth = 0) {
  if (node.leaf !== undefined) {
    return `<div class="tree-leaf" style="margin-left:${depth * 16}px">Feuille : ${Number(node.leaf).toFixed(2)}</div>`;
  }
  const fname = featureLabel(node.split, null);
  const fidx = node.split?.startsWith('f') ? parseInt(node.split.slice(1), 10) : -1;
  const colName = fidx >= 0 && featureCols[fidx] ? featureCols[fidx] : fname;
  const cond = Number(node.split_condition).toFixed(4);
  const yes = node.children?.[0] ? renderTreeNode(node.children[0], featureCols, depth + 1) : '';
  const no = node.children?.[1] ? renderTreeNode(node.children[1], featureCols, depth + 1) : '';
  return `<div class="tree-node" style="margin-left:${depth * 12}px">
    <div class="tree-split"><code>${esc(colName)}</code> &lt; ${cond}</div>
    <div class="tree-branch yes">Oui ${yes}</div>
    <div class="tree-branch no">Non ${no}</div>
  </div>`;
}

async function loadModelMeta() {
  const res = await fetch('/api/model-exploration/meta');
  const data = await res.json();
  const status = document.getElementById('model_status');
  if (!data.model_available) {
    status.textContent = (data.warnings || ['Modele absent']).join(' — ') + '. Executer ./init.sh.';
    return null;
  }
  status.textContent = `${data.n_outputs} sorties, ${data.n_trees_per_output} arbres par sortie (numeros 1 a ${data.n_trees_per_output}).`;
  const treeInput = document.getElementById('model_tree_number');
  treeInput.max = data.n_trees_per_output;
  const sel = document.getElementById('model_target_select');
  sel.innerHTML = data.targets.map(t =>
    `<option value="${t.index}">${esc(t.label)}</option>`).join('');
  window._featureCols = data.features.map(f => f.name);
  const inputs = document.getElementById('feature_inputs');
  const keyFeatures = data.features.filter(f =>
    /nb_chambres|taux_occupation|guests|clients|taux_acheteur|fb_share|m_lin/.test(f.name)
  ).slice(0, 12);
  inputs.innerHTML = keyFeatures.map(f => `
    <label class="field-card compact">
      <span>${esc(f.label)}</span>
      <input type="number" step="any" data-feature="${esc(f.name)}" placeholder="laisser vide = defaut" />
    </label>`).join('');
  return data;
}

async function loadTree() {
  const target = document.getElementById('model_target_select').value;
  const tree = document.getElementById('model_tree_number').value;
  const res = await fetch(`/api/model-exploration/tree?target_index=${target}&tree_number=${tree}`);
  const data = await res.json();
  const view = document.getElementById('tree_view');
  if (data.error) {
    view.innerHTML = `<p class="error">${esc(data.error)}</p>`;
    return;
  }
  view.innerHTML = `<h3>${esc(data.target_label)} — arbre ${data.tree_number} / ${data.n_trees_total}</h3>
    ${renderTreeNode(data.tree, data.feature_cols)}`;
}

async function runPredict() {
  const overrides = {};
  document.querySelectorAll('[data-feature]').forEach(inp => {
    if (inp.value !== '') overrides[inp.dataset.feature] = parseFloat(inp.value);
  });
  const hotelId = document.getElementById('predict_hotel_select').value || null;
  const res = await fetch('/api/model-exploration/predict', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ hotel_id: hotelId, feature_overrides: overrides }),
  });
  const data = await res.json();
  const box = document.getElementById('predict_results');
  if (data.error) {
    box.innerHTML = `<p class="error">${esc(data.error)}</p>`;
    return;
  }
  const globalRows = data.monthly_global.map(m =>
    `<tr><td>${esc(m.month_label)}</td><td>${m.ca_total}</td><td>${m.ventes_total}</td></tr>`).join('');
  const catRows = (data.breakdown_by_category || []).slice(0, 24).map(r =>
    `<tr><td>${esc(r.month_label)}</td><td>${esc(r.type)}</td><td>${esc(r.gamme)}</td>
     <td>${r.pct}%</td><td>${r.ca_estime}</td><td>${r.ventes_estimees}</td></tr>`).join('');
  box.innerHTML = `
    <h3>Totaux annuels</h3>
    <p>CA annuel : <strong>${data.annual_totals.ca_annuel}</strong> EUR —
       Ventes annuelles : <strong>${data.annual_totals.ventes_annuelles}</strong> —
       CA mensuel moyen : <strong>${data.annual_totals.ca_mensuel_moyen}</strong> EUR</p>
    <h3>Prediction globale par mois</h3>
    <div class="table-scroll"><table class="explore-table">
      <thead><tr><th>Mois</th><th>CA total</th><th>Ventes total</th></tr></thead>
      <tbody>${globalRows}</tbody>
    </table></div>
    <h3>Ventilation type et gamme (estimee)</h3>
    <p class="muted">${esc(data.breakdown_note)}</p>
    <div class="table-scroll"><table class="explore-table">
      <thead><tr><th>Mois</th><th>Type</th><th>Gamme</th><th>%</th><th>CA</th><th>Ventes</th></tr></thead>
      <tbody>${catRows || '<tr><td colspan="6">Pas de repartition disponible</td></tr>'}</tbody>
    </table></div>`;
}

function setupTabs() {
  document.querySelectorAll('.explore-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.explore-tab').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.explore-panel').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById(`panel_${btn.dataset.tab}`).classList.add('active');
    });
  });
}

async function init() {
  setupTabs();
  try {
    const data = await loadDataExploration('');
    fillHotelSelects(data.hotels || []);
    renderDataStages(data);
  } catch (e) {
    document.getElementById('data_stages').innerHTML = `<p class="error">${esc(e.message)}</p>`;
  }
  document.getElementById('btn_reload_data').addEventListener('click', async () => {
    const hid = document.getElementById('data_hotel_select').value;
    const data = await loadDataExploration(hid);
    renderDataStages(data);
  });
  await loadModelMeta();
  document.getElementById('btn_load_tree').addEventListener('click', loadTree);
  document.getElementById('btn_predict').addEventListener('click', runPredict);
}

init();