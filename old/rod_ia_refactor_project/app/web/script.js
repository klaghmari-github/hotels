let enrichedFeatures = null;
let chart = null;

function euros(v) { return Math.round(v || 0).toLocaleString('fr-FR') + ' €'; }
function num(v) { return Number.parseFloat(v || 0); }
function checkedValues(selector) { return Array.from(document.querySelectorAll(selector + ':checked')).map(x => x.value); }
function debounce(fn, ms) { let t; return (...args) => { clearTimeout(t); t=setTimeout(()=>fn(...args), ms); }; }

function collectRodInputs() {
  const fb = num(document.getElementById('fb_share').value);
  const nonfb = num(document.getElementById('non_fb_share').value);
  return {
    identity: {
      hotel_name: document.getElementById('hotel_name').value,
      address: document.getElementById('address').value,
      city: document.getElementById('city').value,
      brand: document.getElementById('brand').value
    },
    operating: {
      nb_chambres: parseInt(document.getElementById('nb_chambres').value || '0'),
      taux_occupation: num(document.getElementById('taux_occupation').value),
      guests_per_chambre: num(document.getElementById('guests_per_chambre').value)
    },
    store: {
      concept: document.getElementById('concept').value,
      m_lin: num(document.getElementById('m_lin').value),
      mix: { fb_share: fb, non_fb_share: nonfb },
      excluded_categories: checkedValues('.excluded'),
      locked_fields: checkedValues('.locked')
    },
    enriched: enrichedFeatures || {}
  };
}

async function enrichHotel(force=false) {
  const payload = collectRodInputs();
  payload.force_refresh = force;
  const status = document.getElementById('enrich_status');
  status.innerText = 'Enrichissement en cours...';
  const res = await fetch('/api/enrich', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload) });
  if (!res.ok) { status.innerText = 'Erreur enrichissement'; return; }
  const data = await res.json();
  enrichedFeatures = data.features;
  status.innerText = `OK — ${data.hotel_id}`;
  runSimulation();
}

async function runSimulation() {
  const payload = collectRodInputs();
  const res = await fetch('/api/simulate', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) });
  if (!res.ok) { alert('Erreur simulation'); return; }
  const data = await res.json();
  renderResults(data);
}

async function runOptimize() {
  const payload = collectRodInputs();
  const res = await fetch('/api/optimize', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) });
  if (!res.ok) { alert('Erreur optimisation'); return; }
  const data = await res.json();
  document.getElementById('raw_output').innerText = JSON.stringify(data, null, 2);
  if (data.request) {
    document.getElementById('concept').value = data.request.concept;
    document.getElementById('m_lin').value = data.request.m_lin;
    document.getElementById('fb_share').value = data.request.mix.fb_share.toFixed(2);
    document.getElementById('non_fb_share').value = data.request.mix.non_fb_share.toFixed(2);
  }
}

function renderResults(data) {
  document.getElementById('rod_ca').innerText = euros(data.rod.ca_annuel);
  document.getElementById('rod_margin').innerText = euros(data.rod.marge_annuelle);
  document.getElementById('ai_ca').innerText = euros(data.ai.ca_annuel);
  document.getElementById('raw_output').innerText = JSON.stringify(data, null, 2);
  const labels = data.rod.monthly.map(x => 'M' + String(x.month).padStart(2,'0'));
  const rod = data.rod.monthly.map(x => x.ca);
  const ai = data.ai.monthly.map(x => x.ca);
  const ctx = document.getElementById('monthly_chart');
  if (chart) chart.destroy();
  chart = new Chart(ctx, { type: 'line', data: { labels, datasets: [{ label:'ROD', data: rod }, { label:'IA', data: ai }] }, options: { responsive: true } });
}

function setupTabs() {
  document.querySelectorAll('.tab').forEach(btn => btn.addEventListener('click', () => {
    const tab = btn.dataset.tab;
    document.querySelectorAll('.tab').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
    document.querySelectorAll('.panel').forEach(p => p.classList.toggle('active', p.dataset.panel === tab));
  }));
}

document.addEventListener('DOMContentLoaded', () => {
  setupTabs();
  document.getElementById('btn_enrich').addEventListener('click', () => enrichHotel(false));
  document.getElementById('btn_simulate').addEventListener('click', runSimulation);
  document.getElementById('btn_optimize').addEventListener('click', runOptimize);
  const auto = debounce(runSimulation, 500);
  document.querySelectorAll('input, select').forEach(el => el.addEventListener('change', auto));
  runSimulation();
});
