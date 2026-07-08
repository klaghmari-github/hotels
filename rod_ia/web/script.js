/* ROD Onboarding wizard — 5 étapes */

const CONCEPTS = ['SIMPLY', 'LIBERTY', 'CONNECTED'];
const MONTHS = ['Janvier','Février','Mars','Avril','Mai','Juin','Juillet','Août','Septembre','Octobre','Novembre','Décembre'];

const CLIENT_NEEDS = {
  fb: [
    { id: 'fb_soft_drinks', label: 'Boissons non alcoolisées', hint: 'Eau, sodas, jus de fruits…' },
    { id: 'fb_alcohol', label: 'Boissons alcoolisées', hint: 'Bière, vin, champagne…' },
    { id: 'fb_salty_snacks', label: 'Nourriture salée', hint: 'Chips, biscuits apéritif…' },
    { id: 'fb_salty_meals', label: 'Nourriture salée', hint: 'Salades, sandwichs, plats…' },
    { id: 'fb_sweet_snacks', label: 'Nourriture sucrée', hint: 'Barres chocolatées, bonbons…' },
    { id: 'fb_sweet_desserts', label: 'Nourriture sucrée', hint: 'Yaourts, desserts…' },
    { id: 'fb_gourmet', label: 'Épicerie fine', hint: 'Locale ou non' },
  ],
  nfb: [
    { id: 'nfb_sos', label: 'Produits SOS', hint: 'Chargeur, batterie externe, écouteurs…' },
    { id: 'nfb_hygiene', label: 'Hygiène', hint: 'Dentifrice, déodorant…' },
    { id: 'nfb_cosmetics', label: 'Cosmétiques', hint: 'Crème, lait corporel…' },
    { id: 'nfb_kids', label: 'Articles pour enfants', hint: 'Jeux, coloriages, livres…' },
    { id: 'nfb_apparel', label: 'Prêt-à-porter', hint: 'T-shirt, maillot de bain…' },
    { id: 'nfb_accessories', label: 'Accessoires', hint: 'Parapluie, lunettes, tote bag…' },
    { id: 'nfb_souvenirs', label: 'Souvenirs', hint: 'Y compris les goodies de l\'hôtel…' },
  ],
};

const LOBBY_EQUIP = [
  { id: 'lobby_fridge', label: 'Réfrigérée standard', qty: true },
  { id: 'lobby_microwave', label: 'Micro-ondes', qty: true },
  { id: 'lobby_water_fountain', label: 'Fontaine à eau', qty: true },
  { id: 'lobby_coffee_machine', label: 'Machine à café', qty: true },
  { id: 'lobby_kettle', label: 'Bouilloire', qty: true },
  { id: 'lobby_seating', label: 'Assises', qty: false },
  { id: 'lobby_other', label: 'Autre', qty: false },
];

const CONCEPT_EQUIP = {
  SIMPLY: ['Scanner', 'Vitrine réfrigérée'],
  LIBERTY: ['Caisse code-barres', 'Vitrine réfrigérée'],
  CONNECTED: ['Armoire connectée (froid)', 'Armoire connectée (ambiant)'],
};

const CONCEPT_DETAIL_EQUIP = {
  SIMPLY: [
    { id: 'scanner', label: 'Scanner', icon: '📠', monthly: 8 },
    { id: 'vitrine', label: 'Vitrine réfrigérée', icon: '🧊', monthly: 13 },
  ],
  LIBERTY: [
    { id: 'caisse', label: 'Caisse code-barres', icon: '🛒', monthly: 250 },
    { id: 'vitrine', label: 'Vitrine réfrigérée', icon: '🧊', monthly: 13 },
  ],
  CONNECTED: [
    { id: 'armoire_froid', label: 'Armoire connectée (froid)', icon: '❄️', monthly: 45 },
    { id: 'armoire_ambiant', label: 'Armoire connectée (ambiant)', icon: '📦', monthly: 35 },
  ],
};

const AGENCEMENT_TYPES = [
  { id: 'classique', label: 'CLASSIQUE', leaseM2: 12, buyM2: 126 },
  { id: 'premium', label: 'PREMIUM', leaseM2: 14, buyM2: 146 },
  { id: 'sur_mesure', label: 'SUR-MESURE', leaseM2: 26, buyM2: 266 },
];

let currentStep = 0;
let enrichedFeatures = null;
let currentHotelId = null;
let chart = null;
let salesCatalog = null;
let lastSimulationData = null;
let detailState = { concept: null, lease: true, agencement: 'classique', equipQty: {} };
let detailCostsCache = null;
let detailFetchToken = 0;

function euros(v) { return Math.round(v || 0).toLocaleString('fr-FR') + ' €'; }
function num(v) { return Number.parseFloat(String(v || 0).replace(',', '.')); }
function pct(v) { return (v || 0).toFixed(1) + ' %'; }
function pctErr(v) { return (v >= 0 ? '+' : '') + (v || 0).toFixed(1) + ' %'; }
function debounce(fn, ms) { let t; return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); }; }

function caMensuel(result) {
  return result.ca_mensuel_moyen || (result.ca_annuel / 12) || 0;
}

function fillYearSelects() {
  const years = [];
  for (let y = 2026; y >= 1990; y--) years.push(y);
  document.querySelectorAll('.year-select').forEach(sel => {
    sel.innerHTML = years.map(y => `<option value="${y}">${y}</option>`).join('');
    sel.value = '2025';
  });
}

function fillMonthSelects() {
  const opts = MONTHS.map((m, i) => `<option value="${i + 1}">${m}</option>`).join('');
  document.getElementById('occ_min_month').innerHTML = opts;
  document.getElementById('occ_max_month').innerHTML = opts;
  document.getElementById('occ_max_month').value = '8';
}

function fillPctSelects() {
  const opts = Array.from({ length: 21 }, (_, i) => i * 5)
    .map(v => `<option value="${v}">${v} %</option>`).join('');
  document.querySelectorAll('.pct-select').forEach(sel => { sel.innerHTML = opts; });
  document.getElementById('leisure_pct').value = '30';
  document.getElementById('business_pct').value = '70';
  document.getElementById('national_pct').value = '60';
  document.getElementById('international_pct').value = '40';
  ['leisure_ind_pct','leisure_grp_pct','business_ind_pct','business_grp_pct'].forEach(id => {
    document.getElementById(id).value = '50';
  });
}

function renderNeedsPanel(containerId, syncAssortiment = false) {
  const el = document.getElementById(containerId);
  const renderCol = (type, items) => `
    <div class="needs-col ${type}">
      <h4>${type === 'fb' ? 'F&B' : 'Non-F&B'} <span title="Besoins clients">?</span></h4>
      ${items.map(n => `
        <div class="need-row">
          <span>${n.label}<small>${n.hint}</small></span>
          <label class="toggle"><input type="checkbox" class="need-toggle" data-need="${n.id}" checked /><span></span></label>
        </div>`).join('')}
    </div>`;
  el.innerHTML = renderCol('fb', CLIENT_NEEDS.fb) + renderCol('nfb', CLIENT_NEEDS.nfb);

  el.querySelectorAll('.need-toggle').forEach(input => {
    input.addEventListener('change', () => {
      if (syncAssortiment) syncNeedsFromAssortiment();
      updateMixBars();
      if (currentStep === 4) debounce(runSimulation, 600)();
    });
  });
}

function renderLobbyEquipment() {
  const el = document.getElementById('lobby_equipment');
  el.innerHTML = LOBBY_EQUIP.map(eq => `
    <div class="lobby-item" data-lobby="${eq.id}">
      <span>${eq.label}</span>
      <div style="display:flex;align-items:center;gap:8px">
        ${eq.qty ? `<div class="stepper-input"><button type="button" data-lobby-qty="${eq.id}" data-delta="-1">−</button>
          <input type="number" id="${eq.id}_qty" value="1" min="0" /><button type="button" data-lobby-qty="${eq.id}" data-delta="1">+</button></div>` : ''}
        <label class="toggle"><input type="checkbox" id="${eq.id}" ${eq.id !== 'lobby_fridge' && eq.id !== 'lobby_other' ? 'checked' : ''} /><span></span></label>
      </div>
    </div>`).join('');
}

function syncNeedsFromAssortiment() {
  document.querySelectorAll('#assortiment_panel .need-toggle').forEach(src => {
    const id = src.dataset.need;
    const tgt = document.querySelector(`#client_needs_panel .need-toggle[data-need="${id}"]`);
    if (tgt) tgt.checked = src.checked;
  });
}

function syncAssortimentFromNeeds() {
  document.querySelectorAll('#client_needs_panel .need-toggle').forEach(src => {
    const id = src.dataset.need;
    const tgt = document.querySelector(`#assortiment_panel .need-toggle[data-need="${id}"]`);
    if (tgt) tgt.checked = src.checked;
  });
}

function getClientNeeds() {
  const needs = {};
  document.querySelectorAll('#client_needs_panel .need-toggle').forEach(el => {
    needs[el.dataset.need] = el.checked;
  });
  return needs;
}

function updateMixBars() {
  const needs = getClientNeeds();
  let fbOn = 0, nfbOn = 0;
  Object.entries(needs).forEach(([k, on]) => {
    if (!on) return;
    if (k.startsWith('fb_')) fbOn++;
    if (k.startsWith('nfb_')) nfbOn++;
  });
  const total = fbOn + nfbOn || 1;
  const fbPct = Math.round((fbOn / total) * 100);
  const nfbPct = 100 - fbPct;
  document.getElementById('bar_fb').style.width = fbPct + '%';
  document.getElementById('bar_nfb').style.width = nfbPct + '%';
  document.getElementById('fb_pct_out').textContent = fbPct + ' %';
  document.getElementById('nfb_pct_out').textContent = nfbPct + ' %';
}

function collectRodInputs() {
  const needs = getClientNeeds();
  const excluded = [];
  Object.entries(needs).forEach(([key, enabled]) => {
    if (!enabled) {
      const gamme = NEED_TO_GAMME[key];
      if (gamme && !excluded.includes(gamme)) excluded.push(gamme);
    }
  });

  let fbOn = 0, nfbOn = 0;
  Object.entries(needs).forEach(([k, on]) => {
    if (!on) return;
    if (k.startsWith('fb_')) fbOn++;
    if (k.startsWith('nfb_')) nfbOn++;
  });
  const total = fbOn + nfbOn || 1;
  const fbShare = fbOn / total;
  const nfbShare = nfbOn / total;

  const adults = num(document.getElementById('adults_per_room').value);
  const children = num(document.getElementById('children_per_room').value);
  const toAnnual = num(document.getElementById('taux_occupation').value);
  const toRate = toAnnual > 1 ? toAnnual / 100 : toAnnual;

  const lobby = {};
  LOBBY_EQUIP.forEach(eq => {
    const enabled = document.getElementById(eq.id)?.checked || false;
    const qty = eq.qty ? parseInt(document.getElementById(`${eq.id}_qty`)?.value || '0', 10) : 0;
    lobby[eq.id] = { enabled, quantity: qty };
  });

  return {
    identity: {
      hotel_id: currentHotelId,
      hotel_name: document.getElementById('hotel_name').value,
      address: document.getElementById('address').value,
      city: document.getElementById('city').value,
      brand: document.getElementById('brand').value,
    },
    operating: {
      nb_chambres: parseInt(document.getElementById('nb_chambres').value || '0', 10),
      taux_occupation: toRate,
      guests_per_chambre: adults + children || num(document.getElementById('sim_guests')?.value || 1.7),
    },
    general: {
      contract_signed_year: parseInt(document.getElementById('contract_year').value || '0', 10) || null,
      contract_type: document.getElementById('contract_type').value,
      owner: document.getElementById('owner').value,
      dom_dof: document.getElementById('dom_dof').value,
      adults_per_room: adults,
      children_per_room: children,
      panier_moyen: num(document.getElementById('panier_moyen').value),
      last_hotel_renovation: parseInt(document.getElementById('reno_hotel').value, 10),
      last_lobby_renovation: parseInt(document.getElementById('reno_lobby').value, 10),
      pms: document.getElementById('pms').value,
      monthly_occupancy: {
        min_month: parseInt(document.getElementById('occ_min_month').value, 10),
        max_month: parseInt(document.getElementById('occ_max_month').value, 10),
        min_pct: num(document.getElementById('occ_min_pct').value),
        max_pct: num(document.getElementById('occ_max_pct').value),
      },
    },
    services: {
      bar: { count: parseInt(document.getElementById('bar_count').value, 10), name: document.getElementById('bar_name').value },
      restaurant: { count: parseInt(document.getElementById('restaurant_count').value, 10), name: document.getElementById('restaurant_name').value },
      room_service: document.getElementById('room_service').checked,
      minibar: document.getElementById('minibar').checked,
      minibar_rooms: parseInt(document.getElementById('minibar_rooms').value, 10),
      minibar_filled: parseInt(document.getElementById('minibar_filled').value, 10),
      meeting_rooms: document.getElementById('meeting_rooms').checked,
      gym: document.getElementById('gym').checked,
      spa: document.getElementById('spa').checked,
      pool: document.getElementById('pool').checked,
      other_service: document.getElementById('other_service').checked,
      lobby_fridge: lobby.lobby_fridge,
      lobby_microwave: lobby.lobby_microwave,
      lobby_water_fountain: lobby.lobby_water_fountain,
      lobby_coffee_machine: lobby.lobby_coffee_machine,
      lobby_kettle: lobby.lobby_kettle,
      lobby_seating: lobby.lobby_seating?.enabled || document.getElementById('lobby_seating')?.checked,
      lobby_other: lobby.lobby_other?.enabled || document.getElementById('lobby_other')?.checked,
    },
    client_profile: {
      leisure_pct: num(document.getElementById('leisure_pct').value),
      leisure_individual_pct: num(document.getElementById('leisure_ind_pct').value),
      leisure_group_pct: num(document.getElementById('leisure_grp_pct').value),
      business_pct: num(document.getElementById('business_pct').value),
      business_individual_pct: num(document.getElementById('business_ind_pct').value),
      business_group_pct: num(document.getElementById('business_grp_pct').value),
      national_pct: num(document.getElementById('national_pct').value),
      international_pct: num(document.getElementById('international_pct').value),
      client_needs: needs,
    },
    corner: {
      has_existing_corner: document.getElementById('has_corner').checked,
      m_lin: parseFloat(document.getElementById('m_lin').value || '5'),
      emplacement: document.getElementById('emplacement').value,
    },
    analyze_with_ai: document.getElementById('analyze_with_ai')?.checked || false,
    constraints: { excluded_categories: excluded },
    store: {
      m_lin: parseFloat(document.getElementById('m_lin').value || '5'),
      mix: { fb_share: fbShare, non_fb_share: nfbShare },
      excluded_categories: excluded,
    },
    enriched: enrichedFeatures || {},
  };
}

const NEED_TO_GAMME = {
  fb_soft_drinks: 'SANS ALCOOL', fb_alcohol: 'ALCOOL',
  fb_salty_snacks: 'FOOD SALEE', fb_salty_meals: 'FOOD SALEE',
  fb_sweet_snacks: 'FOOD SUCREE', fb_sweet_desserts: 'FOOD SUCREE',
  fb_gourmet: 'FOOD SALEE',
  nfb_sos: 'SOS', nfb_hygiene: 'COSMETIQUE', nfb_cosmetics: 'COSMETIQUE',
  nfb_kids: 'JEUX / ENFANTS', nfb_apparel: 'PAP',
  nfb_accessories: 'ACCESSOIRES', nfb_souvenirs: 'SOUVENIRS',
};

function goToStep(step) {
  currentStep = Math.max(0, Math.min(4, step));
  document.querySelectorAll('.wizard-panel').forEach(p =>
    p.classList.toggle('active', parseInt(p.dataset.panel, 10) === currentStep));
  document.querySelectorAll('.stepper .step').forEach((s, i) => {
    s.classList.toggle('active', i === currentStep);
    s.classList.toggle('done', i < currentStep);
  });
  document.getElementById('btn_back').disabled = currentStep === 0;
  document.getElementById('btn_next').textContent = currentStep === 4 ? 'Terminer' : 'Valider';
  if (currentStep === 4) syncStep5FromForm();
  if (currentStep === 4) runSimulation();
}

function syncStep5FromForm() {
  const ch = document.getElementById('nb_chambres').value;
  document.getElementById('sim_chambres').textContent = ch;
  const adults = num(document.getElementById('adults_per_room').value);
  const children = num(document.getElementById('children_per_room').value);
  const guests = adults + children || 1.7;
  document.getElementById('sim_guests').value = guests;
  document.getElementById('sim_guests_out').textContent = guests.toLocaleString('fr-FR');
  const to = num(document.getElementById('taux_occupation').value);
  document.getElementById('sim_occ').value = to;
  document.getElementById('sim_occ_out').textContent = to + ' %';
  document.getElementById('sim_emplacement').value = document.getElementById('emplacement').value;
  syncAssortimentFromNeeds();
  updateMixBars();
}

function updatePreview() {
  document.getElementById('preview_name').textContent = document.getElementById('hotel_name').value;
  document.getElementById('user_name').textContent = document.getElementById('hotel_name').value;
}

function renderProximity(features) {
  const el = document.getElementById('proximity_panel');
  if (!features?.poi) {
    el.innerHTML = '<p class="muted">Enrichissez l\'hôtel pour afficher les POI</p>';
    return;
  }
  const poi = features.poi;
  const at100 = poi.d_poi_fb_0_0_1km || poi.poi_fb_0_0_1km || 0;
  const at500 = poi.d_poi_fb_0_0_5km || poi.poi_fb_0_0_5km || 0;
  const nf100 = poi.d_poi_not_fb_0_0_1km || poi.poi_not_fb_0_0_1km || 0;
  const nf500 = poi.d_poi_not_fb_0_0_5km || poi.poi_not_fb_0_0_5km || 0;
  el.innerHTML = `
    <div class="dist-block"><strong>À 100 m</strong><ul>
      <li>Restauration / F&B (${Math.round(at100)})</li>
      <li>Commerces non alimentaires (${Math.round(nf100)})</li>
    </ul></div>
    <div class="dist-block"><strong>À 500 m</strong><ul>
      <li>Restauration / F&B (${Math.round(at500)})</li>
      <li>Commerces non alimentaires (${Math.round(nf500)})</li>
    </ul></div>`;
}

async function enrichHotel() {
  const status = document.getElementById('enrich_status');
  status.textContent = 'Enrichissement…';
  const res = await fetch('/api/enrich', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...collectRodInputs(), force_refresh: false }),
  });
  if (!res.ok) { status.textContent = 'Erreur enrichissement'; return; }
  const data = await res.json();
  enrichedFeatures = data.features;
  currentHotelId = data.hotel_id;
  document.getElementById('user_hotel_id').textContent = data.hotel_id || '—';
  status.textContent = `OK — ${data.hotel_id}`;
  renderProximity(enrichedFeatures);
}

async function runSimulation() {
  if (currentStep !== 4) return;
  const payload = collectRodInputs();
  sessionStorage.setItem('rod_last_simulation', JSON.stringify(payload));
  const res = await fetch('/api/simulate', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) { alert('Erreur simulation'); return; }
  renderResults(await res.json());
}

async function runOptimize() {
  const res = await fetch('/api/optimize', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(collectRodInputs()),
  });
  if (!res.ok) { alert('Erreur optimisation'); return; }
  const data = await res.json();
  if (data.request?.m_lin) document.getElementById('m_lin').value = data.request.m_lin;
  runSimulation();
}

function renderConceptShowcase(concept, rod, isRecommended) {
  const margeM = (rod.marge_annuelle || 0) / 12;
  const equip = CONCEPT_EQUIP[concept].map(e => `<div class="equip">${e}</div>`).join('');
  const altLabel = !isRecommended ? '<div class="alt-label">Solution alternative</div>' : '';
  const recoBadge = isRecommended ? '<span class="badge-reco">Recommandé</span>' : '';

  let actions = '';
  if (isRecommended) {
    actions = `
      <p class="muted" style="font-size:10px">Revenue mensuel estimé</p>
      <button type="button" class="btn-detail" data-concept="${concept}" data-action="detail">Voir le détail</button>
      ${equip}
      <button type="button" class="btn-contact" data-action="contact">Contacter</button>`;
  } else {
    actions = `${equip}
      <button type="button" class="btn-select" data-concept="${concept}" data-action="detail">Sélectionnez</button>`;
  }

  return `
    <article class="concept-card ${isRecommended ? 'recommended' : 'alt'}" data-concept="${concept}">
      ${altLabel}${recoBadge}
      <h3>${concept} STORE</h3>
      <div class="margin">${euros(margeM)}<small> /mois</small></div>
      <p class="muted" style="font-size:11px">Marge nette</p>
      ${actions}
    </article>`;
}

function financingPayload() {
  return {
    mode: detailState.lease ? 'lease' : 'buy',
    agencement_type: detailState.agencement,
    equipment_qty: detailState.equipQty,
  };
}

async function fetchDetailCosts() {
  if (!lastSimulationData || !detailState.concept) return null;
  const token = ++detailFetchToken;
  const payload = {
    base: collectRodInputs(),
    concept: detailState.concept,
    financing: financingPayload(),
  };
  const res = await fetch('/api/simulate/detail', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) return null;
  const data = await res.json();
  if (token !== detailFetchToken) return null;
  detailCostsCache = data;
  return data;
}

function agencementPriceLabel(ag) {
  return detailState.lease
    ? `${ag.leaseM2} €/M²`
    : `${ag.buyM2} €/M²`;
}

function renderDetailPanelContent(costs) {
  if (!costs) {
    document.getElementById('detail_content').innerHTML =
      '<p class="muted">Calcul des coûts…</p>';
    return;
  }
  const c = costs.costs;
  const equipMeta = CONCEPT_DETAIL_EQUIP[detailState.concept] || {};
  const agPills = AGENCEMENT_TYPES.map(a => `
    <button type="button" class="agencement-pill ${detailState.agencement === a.id ? 'active' : ''}"
      data-agencement="${a.id}">
      ${a.label}<span>${agencementPriceLabel(a)}</span>
    </button>`).join('');

  const equipRows = (c.equipment_lines || []).map(line => {
    const meta = equipMeta[line.id] || { icon: '📦' };
    const unit = detailState.lease ? line.lease_monthly_unit : line.monthly_cost / Math.max(line.qty, 1);
    return `
      <div class="detail-equip-item" data-equip="${line.id}">
        <div class="detail-equip-thumb">${meta.icon}</div>
        <div>
          <strong>${line.label}</strong>
          <div class="equip-price">${Math.round(unit)} € / Mois</div>
          <div class="stepper-input">
            <button type="button" data-equip-delta="-1" data-equip="${line.id}">−</button>
            <input type="number" value="${line.qty}" min="0" max="9" readonly />
            <button type="button" data-equip-delta="1" data-equip="${line.id}">+</button>
          </div>
        </div>
      </div>`;
  }).join('');

  document.getElementById('detail_content').innerHTML = `
    <div class="detail-header">
      <div class="detail-sub">Revenu mensuel estimé</div>
      <h2 id="detail_title">${detailState.concept} STORE</h2>
    </div>
    <div class="detail-margin">
      <div class="label">Marge nette</div>
      <div class="value">${euros(c.marge_nette_mensuelle)}<small> /mois</small></div>
    </div>
    <div class="detail-kpis">
      <div><span>F&amp;B</span><strong>${euros(c.ca_fb_ht_mensuel)}</strong></div>
      <div><span>NON-F&amp;B</span><strong>${euros(c.ca_nf_ht_mensuel)}</strong></div>
      <div class="total-row"><span>TOTAL H.T</span><strong>${euros(c.ca_ht_mensuel)}</strong></div>
      <div class="total-row"><span>COÛTS H.T</span><strong>${euros(c.monthly_cost)}</strong></div>
    </div>
    <div class="detail-lease">
      <span class="lease-opt ${detailState.lease ? 'active' : ''}" data-lease="1">Lease (3 ans)</span>
      <label class="toggle"><input type="checkbox" id="detail_lease_toggle" ${detailState.lease ? 'checked' : ''} /><span></span></label>
      <span class="lease-opt ${!detailState.lease ? 'active' : ''}" data-lease="0">Buy</span>
    </div>
    <div class="detail-amort">Amortissement ${c.amort_months} mois</div>
    <div class="detail-agencement">
      <h4>Choisissez un type d'agencement</h4>
      <div class="agencement-pills">${agPills}</div>
    </div>
    <div class="detail-equip-list">${equipRows}</div>
    <div class="detail-footer">
      <button type="button" class="btn-back-detail" data-close-detail>Retour</button>
    </div>`;
}

async function renderDetailPanel() {
  if (!lastSimulationData || !detailState.concept) return;
  renderDetailPanelContent(null);
  const data = await fetchDetailCosts();
  renderDetailPanelContent(data);
}

function openConceptDetail(concept) {
  if (!lastSimulationData?.rod_by_concept?.[concept]) return;
  detailState.concept = concept;
  detailState.lease = true;
  detailState.agencement = 'classique';
  detailState.equipQty = {};
  (CONCEPT_DETAIL_EQUIP[concept] || []).forEach(eq => { detailState.equipQty[eq.id] = 1; });

  void renderDetailPanel();
  const modal = document.getElementById('concept_detail_modal');
  modal.classList.remove('hidden');
  modal.setAttribute('aria-hidden', 'false');
  document.body.style.overflow = 'hidden';
}

function closeConceptDetail() {
  const modal = document.getElementById('concept_detail_modal');
  modal.classList.add('hidden');
  modal.setAttribute('aria-hidden', 'true');
  document.body.style.overflow = '';
}

function bindDetailPanelEvents() {
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeConceptDetail();
  });

  const modal = document.getElementById('concept_detail_modal');
  modal.addEventListener('click', e => {
    if (e.target.closest('[data-close-detail]')) {
      closeConceptDetail();
      return;
    }
    const agBtn = e.target.closest('[data-agencement]');
    if (agBtn) {
      detailState.agencement = agBtn.dataset.agencement;
      void renderDetailPanel();
      return;
    }
    const leaseOpt = e.target.closest('[data-lease]');
    if (leaseOpt) {
      detailState.lease = leaseOpt.dataset.lease === '1';
      void renderDetailPanel();
      return;
    }
    const equipBtn = e.target.closest('[data-equip-delta]');
    if (equipBtn) {
      const id = equipBtn.dataset.equip;
      const delta = parseInt(equipBtn.dataset.equipDelta, 10);
      detailState.equipQty[id] = Math.max(0, (detailState.equipQty[id] ?? 1) + delta);
      void renderDetailPanel();
    }
  });

  modal.addEventListener('change', e => {
    if (e.target.id === 'detail_lease_toggle') {
      detailState.lease = e.target.checked;
      void renderDetailPanel();
    }
  });
}

function bindConceptCardActions() {
  document.getElementById('concept_cards').addEventListener('click', e => {
    const btn = e.target.closest('[data-action]');
    if (!btn) return;
    const action = btn.dataset.action;
    const concept = btn.dataset.concept;
    if (action === 'detail' && concept) openConceptDetail(concept);
    if (action === 'contact') {
      alert('Merci — un conseiller ROD vous contactera sous 48 h.');
    }
  });
}

function renderResults(data) {
  lastSimulationData = data;
  document.getElementById('results_area').classList.remove('hidden');
  const reco = data.recommended_concept;
  document.getElementById('reco_banner').innerHTML =
    `<strong>${reco} STORE</strong><span>${data.recommendation_reason || ''}</span>`;

  const order = ['SIMPLY', 'LIBERTY', 'CONNECTED'];
  document.getElementById('concept_cards').innerHTML = order.map(c =>
    renderConceptShowcase(c, data.rod_by_concept[c], c === reco)).join('');

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
        { label: `ROD (${euros(rodM)}/mois)`, data: recoRod.monthly.map(() => rodM), borderColor: '#2563eb', borderDash: [6, 4] },
        { label: `IA profil (${euros(aiM)}/mois)`, data: aiMonthly, borderColor: '#16a34a' },
      ],
    },
    options: { responsive: true, plugins: { legend: { labels: { color: '#475569' } } } },
  });

  document.getElementById('chart_legend').textContent =
    `Concept recommandé : ${reco}. ROD = mois moyen. IA = profil 12 mois.`;
  const rawOutput = document.getElementById('raw_output');
  if (rawOutput) rawOutput.textContent = JSON.stringify(data, null, 2);
}

async function loadPerformance() {
  const tbody = document.querySelector('#perf_table tbody');
  const summary = document.getElementById('perf_summary');
  if (!tbody || !summary) return;
  const res = await fetch('/api/performance');
  if (!res.ok) { summary.textContent = 'Rapport absent — ./init.sh'; return; }
  const data = await res.json();
  const s = data.summary || {};
  const evalYear = data.evaluation_year ?? data.validation_year;
  summary.innerHTML = `<strong>Test & évaluation ${evalYear}</strong> — ${s.n_hotels || 0} hôtels · Écart moyen ROD ${pct(s.mean_abs_rod_error_pct)} · IA ${pct(s.mean_abs_ai_error_pct)}`;
  tbody.innerHTML = (data.rows || []).slice(0, 20).map(r => `
    <tr>
      <td>${r.hotel_name}</td><td>${r.concept || '—'}</td><td>${r.recommended_concept || '—'}</td>
      <td>${r.nb_chambres}</td>
      <td>${pct((r.taux_occupation || 0) * 100)}</td>
      <td>${r.n_months_present}</td>
      <td>${euros(r.actual_ca_period)}</td><td>${euros(r.rod_ca_period)}</td><td>${euros(r.ai_ca_period)}</td>
      <td>${pctErr(r.rod_error_pct)}</td><td>${pctErr(r.ai_error_pct)}</td>
    </tr>`).join('');
}

function setupSteppers() {
  document.querySelectorAll('[data-stepper]').forEach(btn => {
    btn.addEventListener('click', () => {
      const id = btn.dataset.stepper;
      const input = document.getElementById(id);
      const delta = parseInt(btn.dataset.delta, 10);
      input.value = Math.max(parseInt(input.min || '0', 10), parseInt(input.value, 10) + delta);
      if (id === 'm_lin' && currentStep === 4) debounce(runSimulation, 600)();
    });
  });
  document.querySelectorAll('[data-lobby-qty]').forEach(btn => {
    btn.addEventListener('click', () => {
      const id = btn.dataset.lobbyQty + '_qty';
      const input = document.getElementById(id);
      const delta = parseInt(btn.dataset.delta, 10);
      input.value = Math.max(0, parseInt(input.value, 10) + delta);
    });
  });
}

function setupBindings() {
  ['hotel_name', 'nb_chambres'].forEach(id => {
    document.getElementById(id).addEventListener('input', updatePreview);
  });

  document.getElementById('occ_min_pct').addEventListener('input', e => {
    document.getElementById('occ_min_out').textContent = e.target.value + ' %';
  });
  document.getElementById('occ_max_pct').addEventListener('input', e => {
    document.getElementById('occ_max_out').textContent = e.target.value + ' %';
  });

  document.getElementById('minibar_rooms').addEventListener('input', e => {
    document.getElementById('minibar_rooms_out').textContent = e.target.value;
  });
  document.getElementById('minibar_filled').addEventListener('input', e => {
    document.getElementById('minibar_filled_out').textContent = e.target.value;
  });

  document.getElementById('sim_guests').addEventListener('input', e => {
    document.getElementById('sim_guests_out').textContent = num(e.target.value).toLocaleString('fr-FR');
    const total = num(e.target.value);
    document.getElementById('adults_per_room').value = (total * 0.85).toFixed(1);
    document.getElementById('children_per_room').value = (total * 0.15).toFixed(1);
    debounce(runSimulation, 600)();
  });
  document.getElementById('sim_occ').addEventListener('input', e => {
    document.getElementById('sim_occ_out').textContent = e.target.value + ' %';
    document.getElementById('taux_occupation').value = e.target.value;
    debounce(runSimulation, 600)();
  });
  document.getElementById('m_lin').addEventListener('change', () => debounce(runSimulation, 600)());

  document.getElementById('has_corner').addEventListener('change', e => {
    document.getElementById('corner_details').classList.toggle('hidden', !e.target.checked);
  });

  document.getElementById('minibar').addEventListener('change', e => {
    document.getElementById('minibar_sliders').style.opacity = e.target.checked ? '1' : '0.4';
  });

  document.getElementById('btn_enrich').addEventListener('click', enrichHotel);
  document.getElementById('btn_simulate').addEventListener('click', runSimulation);
  document.getElementById('btn_optimize').addEventListener('click', runOptimize);

  document.getElementById('btn_back').addEventListener('click', () => goToStep(currentStep - 1));
  document.getElementById('btn_next').addEventListener('click', async () => {
    if (currentStep === 0) await enrichHotel();
    if (currentStep === 2) syncAssortimentFromNeeds();
    if (currentStep < 4) goToStep(currentStep + 1);
    else goToStep(0);
  });

  document.querySelectorAll('.stepper .step').forEach(btn => {
    btn.addEventListener('click', () => {
      const step = parseInt(btn.dataset.step, 10);
      if (step <= currentStep + 1) goToStep(step);
    });
  });

  const linkPerf = document.getElementById('link_perf');
  if (linkPerf) {
    linkPerf.addEventListener('click', e => {
      e.preventDefault();
      document.querySelector('.perf-section')?.scrollIntoView({ behavior: 'smooth' });
      loadPerformance();
    });
  }
}

async function applyFieldWiringMarkers() {
  let registry = [];
  try {
    const res = await fetch('/api/param-wiring');
    if (res.ok) registry = (await res.json()).fields || [];
  } catch { /* fallback below */ }

  if (!registry.length) {
    registry = [
      { id: 'nb_chambres', rod: true, ai: true },
      { id: 'taux_occupation', rod: true, ai: true },
      { id: 'adults_per_room', rod: true, ai: true },
      { id: 'children_per_room', rod: true, ai: true },
      { id: 'm_lin', rod: true, ai: true },
      { id: 'sim_guests', rod: true, ai: true },
      { id: 'sim_occ', rod: true, ai: true },
    ];
  }

  const engines = f => {
    const parts = [];
    if (f.rod) parts.push('ROD');
    if (f.ai) parts.push('IA');
    if (f.optimizer) parts.push('Optimiseur');
    return parts.join(' · ') || 'Non connecté';
  };

  registry.forEach(field => {
    if (field.id === 'client_needs') {
      document.querySelectorAll('.need-row').forEach(row => {
        row.classList.add('field-wired');
        row.title = 'Assortiment → ROD · IA';
      });
      return;
    }
    if (field.id === 'services_step' || field.id === 'client_profile_pct') return;

    const el = document.getElementById(field.id);
    if (!el) return;

    const host = el.closest('label') || el.closest('.field-card')
      || el.closest('.toggle-row') || el.closest('.sim-kpi')
      || el.closest('.occ-row') || el.closest('.assortiment-header');
    if (!host) return;

    const active = field.rod || field.ai || field.optimizer;
    host.classList.add(active ? 'field-wired' : 'field-inactive');
    host.title = field.note || engines(field);

    if (!active) {
      const titleSpan = host.querySelector(':scope > span') || host.querySelector('span');
      if (titleSpan && !titleSpan.querySelector('.wire-mark')) {
        titleSpan.insertAdjacentHTML('beforeend', ' <em class="wire-mark">*</em>');
      }
    }
  });

  document.querySelectorAll(
    '#leisure_pct,#business_pct,#national_pct,#international_pct,' +
    '#leisure_ind_pct,#leisure_grp_pct,#business_ind_pct,#business_grp_pct'
  ).forEach(el => {
    const block = el.closest('.profile-block');
    if (block) {
      block.classList.add('field-inactive');
      block.title = 'Répartition clients — non utilisée par les moteurs';
    }
  });
}

document.addEventListener('DOMContentLoaded', () => {
  fillYearSelects();
  fillMonthSelects();
  fillPctSelects();
  renderNeedsPanel('client_needs_panel');
  renderNeedsPanel('assortiment_panel', true);
  renderLobbyEquipment();
  setupSteppers();
  setupBindings();
  bindDetailPanelEvents();
  bindConceptCardActions();
  applyFieldWiringMarkers();
  updatePreview();
  updateMixBars();
  if (document.getElementById('perf_table')) loadPerformance();
  if (location.hash === '#perf') loadPerformance();
  goToStep(0);
});