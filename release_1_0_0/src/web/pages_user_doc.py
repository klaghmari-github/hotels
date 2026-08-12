"""Page /user/doc — documentation simulateur (theme sombre projet)."""

DOC_CSS = """
.doc-wrap { max-width: 960px; margin: 0 auto; }
.doc-hero {
  background: linear-gradient(135deg, #152030 0%, #1a3355 45%, #134e4a 100%);
  border: 1px solid var(--line);
  border-radius: 16px;
  padding: 1.5rem 1.4rem 1.35rem;
  margin-bottom: 1.1rem;
  box-shadow: 0 12px 32px rgba(0,0,0,.28);
}
.doc-hero h2 { margin: 0 0 .4rem; font-size: 1.35rem; }
.doc-hero p { margin: 0; color: #c5d4ea; max-width: 46rem; }
.doc-pills { display:flex; flex-wrap:wrap; gap:.4rem; margin-top: .9rem; }
.doc-pill {
  font-size:.75rem; font-weight:700; letter-spacing:.03em;
  padding:.22rem .6rem; border-radius:999px;
  background: rgba(61,139,253,.15); border:1px solid rgba(61,139,253,.35); color:#93c5fd;
}
.doc-pill.teal { background: rgba(61,214,140,.12); border-color: rgba(61,214,140,.35); color:#86efac; }
.doc-pill.violet { background: rgba(196,181,253,.12); border-color: rgba(196,181,253,.35); color:#c4b5fd; }

.doc-toc {
  display:flex; flex-wrap:wrap; gap:.4rem .7rem;
  padding:.7rem .9rem; margin-bottom:1rem;
  background: var(--card); border:1px solid var(--line); border-radius:12px;
  position: sticky; top: .5rem; z-index: 5;
}
.doc-toc a {
  color: var(--accent); text-decoration:none; font-size:.84rem; font-weight:650;
}
.doc-toc a:hover { text-decoration: underline; }

.doc-section {
  background: var(--card); border:1px solid var(--line); border-radius:14px;
  padding: 1.15rem 1.25rem 1.25rem; margin-bottom: 1rem;
}
.doc-section h3 {
  margin: 0 0 .65rem; font-size: 1.05rem; color: #dbeafe; font-weight: 650;
}
.doc-section h4 {
  margin: 1rem 0 .4rem; font-size: .95rem; color: #93c5fd; font-weight: 650;
}
.doc-section p { margin: .4rem 0; color: var(--text); }
.doc-section .muted { color: var(--muted); }

.flow {
  display: flex; flex-direction: column; gap: .5rem; margin: .9rem 0 .3rem;
}
.flow-row { display: grid; grid-template-columns: 40px 1fr; gap: .65rem; align-items: stretch; }
.flow-num {
  width: 40px; height: 40px; border-radius: 11px;
  display:flex; align-items:center; justify-content:center;
  font-weight: 800; color: #fff; font-size: .9rem;
  background: linear-gradient(145deg, #3d8bfd, #2563eb);
  box-shadow: 0 4px 12px rgba(61,139,253,.3);
}
.flow-num.g2 { background: linear-gradient(145deg, #0d9488, #14b8a6); }
.flow-num.g3 { background: linear-gradient(145deg, #7c3aed, #8b5cf6); }
.flow-num.g4 { background: linear-gradient(145deg, #c2410c, #f59e0b); }
.flow-body {
  border: 1px solid var(--line); border-radius: 12px; padding: .65rem .85rem;
  background: #141c28;
}
.flow-body strong { display:block; color: #e7eef7; margin-bottom: .1rem; font-size: .95rem; }
.flow-body span { font-size: .88rem; color: var(--muted); }
.flow-arrow { width: 40px; text-align: center; color: #4b5d75; font-size: 1rem; margin: -.1rem 0; }

.formula {
  background: #101820;
  border: 1px solid #2a3a4f;
  border-left: 3px solid var(--accent);
  border-radius: 10px;
  padding: .75rem .9rem;
  margin: .65rem 0;
  font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  font-size: .86rem;
  color: #dbeafe;
  overflow-x: auto;
  white-space: pre-wrap;
}
.callout {
  border-left: 3px solid var(--accent);
  background: rgba(61,139,253,.08);
  padding: .7rem .9rem;
  border-radius: 0 10px 10px 0;
  margin: .75rem 0;
  font-size: .92rem;
}
.callout.ok { border-left-color: var(--ok); background: rgba(61,214,140,.08); }
.callout.warn { border-left-color: var(--warn); background: rgba(245,165,36,.08); }

.grid2 {
  display: grid; grid-template-columns: 1fr 1fr; gap: .75rem; margin-top: .7rem;
}
@media (max-width: 760px) { .grid2 { grid-template-columns: 1fr; } }
.mini {
  background: #141c28; border: 1px solid var(--line); border-radius: 12px; padding: .75rem .85rem;
}
.mini h5 { margin: 0 0 .3rem; font-size: .88rem; color: #93c5fd; }
.mini p { margin: 0; font-size: .88rem; color: var(--muted); }

.schema {
  background: #0a1018;
  border: 1px solid #243044;
  border-radius: 12px;
  padding: .9rem 1rem;
  overflow-x: auto;
  font-family: ui-monospace, Menlo, Consolas, monospace;
  font-size: .76rem;
  line-height: 1.35;
  color: #a8bdd6;
  white-space: pre;
  margin: .7rem 0 0;
}

.doc-section table {
  width: 100%; border-collapse: collapse; font-size: .88rem; margin-top: .5rem;
  background: #141c28; border: 1px solid var(--line); border-radius: 10px; overflow: hidden;
}
.doc-section th, .doc-section td {
  text-align: left; padding: .45rem .55rem; border-bottom: 1px solid var(--line); vertical-align: top;
}
.doc-section th {
  color: var(--muted); font-size: .75rem; text-transform: uppercase;
  background: #152030; font-weight: 650;
}
.doc-section tr:last-child td { border-bottom: 0; }

.tag-pill {
  display: inline-block; font-size: .72rem; font-weight: 700;
  padding: .1rem .45rem; border-radius: 999px; margin-right: .2rem;
}
.tag-pill.obs { background: rgba(125,211,252,.15); color: #7dd3fc; }
.tag-pill.sim { background: rgba(134,239,172,.15); color: #86efac; }
.tag-pill.ml { background: rgba(196,181,253,.15); color: #c4b5fd; }
.tag-pill.est { background: rgba(245,165,36,.15); color: #f5a524; }

.doc-footer {
  text-align: center; color: var(--muted); font-size: .82rem; margin: 1.2rem 0 .5rem;
}
.doc-back {
  display: inline-flex; align-items: center; gap: .35rem;
  margin-bottom: .85rem;
}

/* Schema cliquable */
.schema-flow {
  display: flex; flex-wrap: wrap; align-items: center; gap: .45rem .55rem;
  margin: .85rem 0 .35rem;
}
.schema-node {
  display: inline-flex; flex-direction: column; align-items: flex-start; gap: .15rem;
  padding: .55rem .75rem; border-radius: 12px;
  border: 1px solid rgba(61,139,253,.45);
  background: rgba(61,139,253,.1);
  color: #93c5fd; cursor: pointer; text-align: left;
  font-family: ui-monospace, Menlo, Consolas, monospace; font-size: .82rem;
  transition: border-color .12s, background .12s, color .12s;
}
.schema-node:hover {
  background: rgba(61,139,253,.22); border-color: var(--accent); color: #fff;
}
.schema-node .sn-id { font-weight: 700; font-size: .88rem; }
.schema-node .sn-desc { font-family: inherit; font-size: .72rem; color: var(--muted); font-weight: 500; }
.schema-node:hover .sn-desc { color: #c5d4ea; }
.schema-arrow { color: #4b5d75; font-weight: 700; font-size: 1rem; user-select: none; }
.schema-hint { font-size: .8rem; color: var(--muted); margin: .35rem 0 0; }

/* Popups dataset */
.doc-pop-host {
  position: fixed; inset: 0; pointer-events: none; z-index: 80;
}
.doc-pop {
  pointer-events: auto;
  position: fixed;
  width: min(920px, 94vw);
  max-height: min(78vh, 720px);
  display: flex; flex-direction: column;
  background: #121a24; border: 1px solid var(--line); border-radius: 14px;
  box-shadow: 0 18px 50px rgba(0,0,0,.45);
  overflow: hidden;
}
.doc-pop-head {
  display: flex; align-items: center; gap: .5rem; flex-wrap: wrap;
  padding: .65rem .85rem; border-bottom: 1px solid var(--line);
  background: #152030; cursor: move; user-select: none;
}
.doc-pop-head h4 {
  margin: 0; flex: 1; font-size: .95rem; min-width: 8rem;
}
.doc-pop-head .muted { font-size: .78rem; font-weight: 500; }
.doc-pop-tools {
  display: flex; align-items: center; gap: .35rem; flex-wrap: wrap;
}
.doc-pop-tools input[type=search] {
  width: 9rem; padding: .3rem .45rem; border-radius: 8px;
  border: 1px solid var(--line); background: #101820; color: var(--text); font-size: .82rem;
}
.doc-pop-tools .btn {
  padding: .3rem .55rem; font-size: .78rem;
}
.doc-pop-body {
  overflow: auto; flex: 1; padding: .5rem .65rem .75rem;
}
.doc-pop-meta {
  font-size: .78rem; color: var(--muted); margin: 0 0 .4rem;
}
.doc-pop-body table {
  width: 100%; border-collapse: collapse; font-size: .78rem;
  background: #141c28; border: 1px solid var(--line); border-radius: 8px;
}
.doc-pop-body th, .doc-pop-body td {
  text-align: left; padding: .3rem .4rem; border-bottom: 1px solid var(--line);
  white-space: nowrap; max-width: 220px; overflow: hidden; text-overflow: ellipsis;
}
.doc-pop-body th {
  position: sticky; top: 0; background: #152030; color: var(--muted);
  font-size: .7rem; text-transform: uppercase; z-index: 1;
}
.doc-pop-body tr:last-child td { border-bottom: 0; }
.doc-pop-body .num { text-align: right; font-variant-numeric: tabular-nums; }
.doc-pop-err {
  margin: .4rem 0; padding: .55rem .7rem; border-radius: 8px; font-size: .85rem;
  border: 1px solid #5a2a35; background: #2a1520; color: #f5a0b0;
}
"""

DOC_BODY = """
<div class="doc-wrap">
  <a class="link doc-back" href="/user">← Retour au parcours</a>

  <div class="doc-hero">
    <h2>Documentation du fonctionnement global</h2>
  </div>

  <nav class="doc-toc">
    <a href="#obj">Objet</a>
    <a href="#schema">Pipeline</a>
    <a href="#obs">Observation</a>
    <a href="#sim">Simulation &amp; rangs</a>
    <a href="#coef">Coefficients</a>
    <a href="#est">Estimation</a>
    <a href="#ml">ML</a>
    <a href="#marge">Marge ventes, ROI, coûts</a>
    <a href="#parcours">Parcours UI</a>
  </nav>

  <section class="doc-section" id="obj">
    <h3>1. Objet</h3>
    <p>
      Estimer le CA d’un hôtel cible (chambres, TO, guests/chambre, m_lin, mix)
      pour Simply, Liberty et Connected, à partir des tickets pilotes.
    </p>
    <div class="grid2">
      <div class="mini">
        <h5><span class="tag-pill obs">OBS</span> Observation</h5>
        <p>Scénario vide : ventes réelles au mois, mix observé.</p>
      </div>
      <div class="mini">
        <h5><span class="tag-pill sim">SIM</span> Simulation</h5>
        <p>Natures retirées, volumes réalloués, CA et mix recalculés.</p>
      </div>
    </div>
  </section>

  <section class="doc-section" id="schema">
    <h3>2. Pipeline</h3>
    <div class="flow">
      <div class="flow-row">
        <div class="flow-num">1</div>
        <div class="flow-body">
          <strong>Tickets</strong>
          <span><code>t_sales</code> — pilotes, hors hôtels exclus</span>
        </div>
      </div>
      <div class="flow-arrow">↓</div>
      <div class="flow-row">
        <div class="flow-num">2</div>
        <div class="flow-body">
          <strong>Scénarios</strong>
          <span>Rangs de natures → listes de retraits (+ scénario vide), communes à tous les pilotes</span>
        </div>
      </div>
      <div class="flow-arrow">↓</div>
      <div class="flow-row">
        <div class="flow-num g2">3</div>
        <div class="flow-body">
          <strong>Simulation</strong>
          <span>Chaque scénario × chaque hôtel pilote → lignes <code>t_dataset_pivot</code></span>
        </div>
      </div>
      <div class="flow-arrow">↓</div>
      <div class="flow-row">
        <div class="flow-num g3">4</div>
        <div class="flow-body">
          <strong>Coefficients</strong>
          <span>Moyennes par solution : CA / (guests × m_lin × part)</span>
        </div>
      </div>
      <div class="flow-arrow">↓</div>
      <div class="flow-row">
        <div class="flow-num g4">5</div>
        <div class="flow-body">
          <strong>Estimation</strong>
          <span>sim_v2 (leviers × coeffs) ; moteur ML = ml_tc → ml_tc_sim_v2 → ml_ca</span>
        </div>
      </div>
    </div>

    <div class="schema-flow" id="schema-flow">
      <button type="button" class="schema-node" data-ds="t_sales" title="Ouvrir t_sales">
        <span class="sn-id">t_sales</span>
        <span class="sn-desc">tickets pilotes</span>
      </button>
      <span class="schema-arrow">→</span>
      <button type="button" class="schema-node" data-ds="t_scenarios" title="Ouvrir t_scenarios">
        <span class="sn-id">t_scenarios</span>
        <span class="sn-desc">définitions scénarios</span>
      </button>
      <span class="schema-arrow">→</span>
      <button type="button" class="schema-node" data-ds="t_dataset_pivot" title="Ouvrir t_dataset_pivot">
        <span class="sn-id">t_dataset_pivot</span>
        <span class="sn-desc">scénarios × hôtels</span>
      </button>
      <span class="schema-arrow">→</span>
      <button type="button" class="schema-node" data-ds="coeffs" title="Ouvrir coefficients">
        <span class="sn-id">coeffs</span>
        <span class="sn-desc">par solution</span>
      </button>
    </div>
    <div class="schema-flow">
      <button type="button" class="schema-node" data-ds="sales_obs" title="Ouvrir sales_obs">
        <span class="sn-id">sales_obs</span>
        <span class="sn-desc">baseline hôtels</span>
      </button>
      <span class="schema-arrow">·</span>
      <button type="button" class="schema-node" data-ds="sales_sim" title="Ouvrir sales_sim">
        <span class="sn-id">sales_sim</span>
        <span class="sn-desc">simulations légères</span>
      </button>
      <span class="schema-arrow">·</span>
      <button type="button" class="schema-node" data-ds="conversion" title="Ouvrir conversion">
        <span class="sn-id">conversion</span>
        <span class="sn-desc">taux par solution</span>
      </button>
      <span class="schema-arrow">·</span>
      <button type="button" class="schema-node" data-ds="pilot_concepts" title="Ouvrir pilot concepts">
        <span class="sn-id">t_pilot_concepts</span>
        <span class="sn-desc">hôtel ↔ solution</span>
      </button>
    </div>
    <div id="doc-pop-host" class="doc-pop-host" aria-live="polite"></div>
  </section>

  <section class="doc-section" id="obs">
    <h3>3. Observation</h3>
    <p>Sur la période des tickets d’un pilote :</p>
    <div class="formula">guests_mois = chambres × TO_annuel × guests/chambre × 30,5

taux_conversion = nombre_ventes / guests
CA_mois, marge_mois = agrégats tickets ramenés au mois</div>
    <p>Facteur 30,5 : occupation journalière → flux mensuel.</p>
  </section>

  <section class="doc-section" id="sim">
    <h3>4. Simulation</h3>
    <h4>Rangs produits</h4>
    <p>
      Rang = ordre par <strong>marge</strong> tickets (somme sur l’hôtel),
      du moins au plus intéressant — base des retraits de natures.
    </p>
    <p>Trois niveaux par hôtel :</p>
    <table>
      <tr><th>Niveau</th><th>Périmètre</th></tr>
      <tr><td>Global</td><td>Rang de la nature parmi toutes les natures de l’hôtel</td></tr>
      <tr><td>Type</td><td>Rang de la nature au sein du type F&amp;B ou Non F&amp;B</td></tr>
      <tr><td>Gamme</td><td>Rang de la nature au sein de sa gamme (alcool, accessoires, etc.)</td></tr>
    </table>
    <h4>Nature produit</h4>
    <p>
      <code>NATURE_PRODUIT</code> regroupe les SKU de même nature
      (ex. plusieurs chocolats → nature <em>chocolat</em>).
      Rangs et retraits portent sur ces natures.
    </p>
    <h4>Scénarios</h4>
    <p>
      Scénario vide = observation. Les autres retirent des natures par rang (marge basse d’abord).
      Chaque scénario est appliqué à <strong>tous</strong> les hôtels pilotes.
    </p>
    <h4>Redistribution</h4>
    <p>Volume retiré réinjecté sur les natures conservées :</p>
    <div class="formula">part(h, n) = ventes(h,n) / ventes_totales(h)

volume_ajoute(h, n) =
  ventes_retirées(h) × taux_conversion(h) × part(h, n)

q_scénario = q_ligne + volume_ajoute × (q_ligne / ventes_nature)</div>
    <p>CA et marges suivent le ratio de quantités.</p>
    <h4>Surface et mix</h4>
    <div class="formula">m_lin_scénario ≈ (m_lin_obs / n_natures_obs) × n_natures_restantes</div>
    <p>
      Mix type / gamme = parts en <strong>nombre de natures distinctes</strong> du scénario
      (pas en volume de ventes).
    </p>
  </section>

  <section class="doc-section" id="coef">
    <h3>5. Coefficients</h3>
    <p>
      Chaque ligne du pivot (obs ou sim) est dépliée par variable de mix
      (<code>type_*</code>, <code>gamme_*</code>). Intensité unitaire :
    </p>
    <div class="formula">coeff(solution, variable) =
  AVG[ CA_mois / (guests_mois × m_lin × part_mix) ]
  sur les lignes de cette solution</div>
    <p>
      Unité : € CA / mois / guest / m_lin / point de mix.
      Calcul séparé pour Simply, Liberty et Connected.
    </p>
  </section>

  <section class="doc-section" id="est">
    <h3>6. Estimation (sim_v2)</h3>
    <div class="formula">guests = chambres × TO × guests/chambre × 30,5
m_lin  = mètres linéaires
mix    = parts type / gammes (global)</div>
    <div class="formula">CA_var = coeff(solution, variable) × guests × m_lin × part(variable)

CA_famille = moyenne des CA_var (type ou gamme)
CA_solution = moyenne des CA_famille</div>

  </section>

  <section class="doc-section" id="ml">
    <h3>7. ML — chaîne ml_tc → ml_tc_sim_v2 → ml_ca</h3>
    <p>
      Le moteur <strong>ml</strong> (évaluations admin et estimations utilisateur)
      n’est <em>pas</em> un simple scale du CA sim_v2 par un taux de conversion.
      Un TC prédit « au sens ventes/guests » n’est en général pas le TC qui,
      réappliqué à sim_v2, redonne le bon CA — d’où une chaîne en trois étapes
      <strong>par solution</strong> (simply / liberty / connected séparés).
    </p>
    <table>
      <tr><th>Étape</th><th>Rôle</th></tr>
      <tr>
        <td><code>ml_tc</code></td>
        <td>XGBoost → taux de conversion réel (<code>ventes / guests</code>)</td>
      </tr>
      <tr>
        <td><code>ml_tc_sim_v2</code></td>
        <td>Intermédiaire : <code>sim_v2_brut × (TC_ml_tc / TC_baseline)</code></td>
      </tr>
      <tr>
        <td><code>ml_ca</code></td>
        <td>XGBoost → <strong>CA final</strong> (décision reportée par le moteur ml)</td>
      </tr>
    </table>
    <div class="formula">taux_conversion = nombre_ventes_par_mois / nombre_guests_par_mois

ml_tc_sim_v2 = sim_v2_brut × (TC_ml_tc / TC_baseline_solution)

CA_ml = ml_ca(descriptives, sim_v2_brut, ml_tc_sim_v2)</div>
    <p>
      Apprentissage sur les scénarios sim_v2 (obs + sim) enrichis par
      <code>sim_v2_brut</code> (restitution pure) puis par la sortie
      <code>ml_tc_sim_v2</code> après entraînement de <code>ml_tc</code>.
    </p>
    <table>
      <tr><th>Famille de features</th><th>Contenu</th></tr>
      <tr><td>Hôtel</td><td>chambres, TO, guests/chambre, m_lin, mix type / gammes</td></tr>
      <tr><td>Services</td><td>bar, restaurant, piscine, sport, spa…</td></tr>
      <tr><td>Marque</td><td>stats marque (nb hôtels, catégories…)</td></tr>
      <tr><td>Proximité</td><td>commerces concurrents (type × rayon)</td></tr>
      <tr><td>Météo</td><td>temp., précip., humidité… moyennés par hôtel</td></tr>
      <tr><td>sim_v2_brut</td><td>CA / marges restitution pure (feature de ml_tc et ml_ca)</td></tr>
      <tr><td>ml_tc_sim_v2</td><td>CA sim_v2 avec TC de ml_tc (feature additionnelle de ml_ca)</td></tr>
    </table>
    <p>
      Modèles globaux user : <code>models/super/&#123;solution&#125;/ml_tc.json</code>
      et <code>ml_ca.json</code>.
      LOO admin : couple de modèles par hôtel sous
      <code>…/loo/&#123;hotel&#125;/</code> ;
      exclusion seulement si la solution a plus d’un hôtel
      (sinon <code>eval_biased</code>).
      Eval LOO : <code>eval_ml_loo.xlsx</code>.
      Marge, coûts et recommandation : règles communes (rubrique suivante).
    </p>
    <div class="schema">hôtel + mix + services + marque + proximité + météo + sim_v2_brut
       ──▶ ml_tc ──▶ TC
sim_v2_brut × (TC / baseline) ──▶ ml_tc_sim_v2
descriptives + ml_tc_sim_v2 ──▶ ml_ca ──▶ CA_final (= moteur « ml »)</div>
  </section>

  <section class="doc-section" id="marge">
    <h3>8. Marge ventes, ROI et coûts</h3>
    <p>
      Les moteurs se distinguent sur le <strong>CA</strong> uniquement.
      Marge ventes, ROI, coûts, amortissement et recommandation :
      <strong>mêmes règles sim_v1</strong>.
    </p>
    <h4>Marge ventes</h4>
    <p>
      Marge de vente = prix vente − prix achat (via coefficients fixes
      F&amp;B / Non F&amp;B par solution), appliquée de façon identique après le CA
      des trois moteurs.
    </p>
    <h4>ROI</h4>
    <p>
      <strong>ROI</strong> = marge ventes − coûts mensuels de la solution
      (gain net des ventes après charges techno / annexes / agencement).
      La recommandation de solution maximise le ROI annuel.
    </p>
    <h4>Coûts et amortissement</h4>
    <p>
      Capex et charges : grille coûts sim_v1 par solution.
      Amortissement (mois) = capex / ROI mensuel si ROI &gt; 0.
    </p>
    <div class="formula">marge_ventes = f(CA, solution)   # PV − PA
ROI = marge_ventes − coûts_mensuels(solution)
payback_mois = capex(solution) / ROI   (si ROI &gt; 0)</div>
  </section>

  <section class="doc-section" id="parcours">
    <h3>9. Parcours utilisateur</h3>
    <table>
      <tr><th>Étape</th><th>Contenu</th></tr>
      <tr><td>1 · Hôtel</td><td>Sélection</td></tr>
      <tr><td>2 · Infos générales</td><td>Exploitation, services, proximité</td></tr>
      <tr><td>3 · Choix gammes</td><td>Périmètre types / gammes</td></tr>
      <tr><td>4 · Mix reco</td><td>Mix et CA recommandés</td></tr>
      <tr><td>5 · Choisir mix</td><td>Mix éditable</td></tr>
      <tr><td>6 · Estimation</td><td>CA, marge ventes, ROI, coûts, amortissement</td></tr>
    </table>
  </section>

  <p class="doc-footer">
    Accor ROD · release 1.0.0<br/>
    <a class="link" href="/user" style="margin-top:.5rem;display:inline-block">Retour au parcours</a>
  </p>
</div>
"""

DOC_SCRIPT = r"""
// Ancres douces
document.querySelectorAll('.doc-toc a').forEach(a=>{
  a.addEventListener('click', e=>{
    const id=a.getAttribute('href');
    if(id && id.startsWith('#')){
      const el=document.querySelector(id);
      if(el){ e.preventDefault(); el.scrollIntoView({behavior:'smooth', block:'start'}); }
    }
  });
});

// ---------- Popups dataset (schema cliquable) ----------
const DOC_POP = {
  // id → { el, page, q, total, pageSize, z }
  open: Object.create(null),
  zBase: 100,
  zTop: 100,
  offset: 0,
};

function esc(s){
  return String(s??'')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function fmtCell(v){
  if(v==null || v==='') return '—';
  if(typeof v==='number' && Number.isFinite(v)){
    return Number(v).toLocaleString('fr-FR',{maximumFractionDigits:4});
  }
  const s=String(v);
  return esc(s.length>80?s.slice(0,77)+'…':s);
}
function isNumCol(rows, col){
  if(!rows||!rows.length) return false;
  let n=0, t=0;
  for(const r of rows.slice(0,12)){
    const v=r[col];
    if(v==null||v==='') continue;
    t++;
    if(typeof v==='number' || (typeof v==='string' && v.trim()!=='' && !Number.isNaN(Number(v)))) n++;
  }
  return t>0 && n/t>0.7;
}

function bringToFront(id){
  const st=DOC_POP.open[id];
  if(!st||!st.el) return;
  DOC_POP.zTop += 1;
  st.el.style.zIndex = String(DOC_POP.zTop);
}

function closeDocPop(id){
  const st=DOC_POP.open[id];
  if(!st) return;
  if(st.el && st.el.parentNode) st.el.parentNode.removeChild(st.el);
  delete DOC_POP.open[id];
}

function ensurePopShell(id, label){
  if(DOC_POP.open[id] && DOC_POP.open[id].el){
    bringToFront(id);
    return DOC_POP.open[id];
  }
  const host=document.getElementById('doc-pop-host');
  if(!host) return null;
  DOC_POP.offset = (DOC_POP.offset + 1) % 8;
  const top = 56 + DOC_POP.offset * 28;
  const left = 24 + DOC_POP.offset * 32;
  DOC_POP.zTop += 1;

  const el=document.createElement('div');
  el.className='doc-pop';
  el.dataset.ds=id;
  el.style.top=top+'px';
  el.style.left=left+'px';
  el.style.zIndex=String(DOC_POP.zTop);
  el.innerHTML=`
    <div class="doc-pop-head" data-drag>
      <h4>${esc(label||id)} <span class="muted" data-sub></span></h4>
      <div class="doc-pop-tools">
        <input type="search" data-q placeholder="Filtrer…" />
        <button type="button" class="btn" data-prev>Prev</button>
        <span class="muted" data-page style="min-width:5.5rem;text-align:center"></span>
        <button type="button" class="btn" data-next>Next</button>
        <button type="button" class="btn" data-close title="Fermer">✕</button>
      </div>
    </div>
    <div class="doc-pop-body">
      <div class="doc-pop-meta" data-meta>Chargement…</div>
      <div data-table></div>
    </div>`;
  host.appendChild(el);

  const st={ el, page:1, pageSize:40, q:'', total:0, totalPages:1, label:label||id };
  DOC_POP.open[id]=st;

  el.querySelector('[data-close]').onclick=()=>closeDocPop(id);
  el.querySelector('[data-prev]').onclick=()=>{
    if(st.page>1){ st.page--; loadDocPop(id); }
  };
  el.querySelector('[data-next]').onclick=()=>{
    if(st.page<st.totalPages){ st.page++; loadDocPop(id); }
  };
  const qEl=el.querySelector('[data-q]');
  qEl.addEventListener('keydown', e=>{
    if(e.key==='Enter'){
      st.q=qEl.value.trim();
      st.page=1;
      loadDocPop(id);
    }
  });
  el.addEventListener('mousedown', ()=>bringToFront(id));

  // drag
  const head=el.querySelector('[data-drag]');
  let drag=null;
  head.addEventListener('mousedown', e=>{
    if(e.target.closest('button,input')) return;
    drag={
      x:e.clientX, y:e.clientY,
      left:el.offsetLeft, top:el.offsetTop
    };
    e.preventDefault();
  });
  window.addEventListener('mousemove', e=>{
    if(!drag || !DOC_POP.open[id]) return;
    const nx=drag.left + (e.clientX-drag.x);
    const ny=drag.top + (e.clientY-drag.y);
    el.style.left=Math.max(8, nx)+'px';
    el.style.top=Math.max(8, ny)+'px';
  });
  window.addEventListener('mouseup', ()=>{ drag=null; });

  return st;
}

async function loadDocPop(id){
  const st=DOC_POP.open[id];
  if(!st) return;
  const body=st.el.querySelector('[data-table]');
  const meta=st.el.querySelector('[data-meta]');
  const pageEl=st.el.querySelector('[data-page]');
  const sub=st.el.querySelector('[data-sub]');
  meta.textContent='Chargement…';
  body.innerHTML='';
  try{
    const url=new URL('/api/doc/datasets/'+encodeURIComponent(id), location.origin);
    url.searchParams.set('page', String(st.page));
    url.searchParams.set('page_size', String(st.pageSize));
    if(st.q) url.searchParams.set('q', st.q);
    const res=await fetch(url);
    const data=await res.json();
    if(!data.ok) throw new Error(data.error||'erreur');
    const cols=data.columns||[];
    const rows=data.rows||[];
    st.total=data.total||0;
    st.totalPages=Math.max(1, Math.ceil(st.total/st.pageSize));
    const label=(data.dataset&&data.dataset.label)||id;
    const desc=(data.dataset&&data.dataset.description)||'';
    st.el.querySelector('h4').childNodes[0].textContent=label+' ';
    if(sub) sub.textContent=desc?('· '+desc):'';
    meta.textContent=`${st.total.toLocaleString('fr-FR')} lignes · page ${st.page}/${st.totalPages}`
      +(data.total_all!=null && data.total_all!==st.total
        ? ` (filtre sur ${Number(data.total_all).toLocaleString('fr-FR')})` : '');
    if(pageEl) pageEl.textContent=`${st.page} / ${st.totalPages}`;

    if(!cols.length){
      body.innerHTML='<p class="muted">Aucune colonne.</p>';
      return;
    }
    // limiter colonnes affichees si tres large
    const showCols=cols.slice(0,24);
    const numMap={};
    for(const c of showCols) numMap[c]=isNumCol(rows,c);
    let h='<table><thead><tr>';
    for(const c of showCols) h+=`<th>${esc(c)}</th>`;
    if(cols.length>showCols.length) h+='<th>…</th>';
    h+='</tr></thead><tbody>';
    for(const r of rows){
      h+='<tr>';
      for(const c of showCols){
        const v=r[c];
        h+=`<td class="${numMap[c]?'num':''}">${fmtCell(v)}</td>`;
      }
      if(cols.length>showCols.length) h+='<td class="muted">…</td>';
      h+='</tr>';
    }
    h+='</tbody></table>';
    if(!rows.length) h='<p class="muted">Aucune ligne.</p>';
    body.innerHTML=h;
  }catch(e){
    meta.textContent='';
    body.innerHTML=`<div class="doc-pop-err">${esc(e.message)}</div>`;
  }
}

function openDocDataset(id, label){
  if(!id) return;
  // une seule popup par table : si deja ouverte, focus + reload page courante
  const existing=DOC_POP.open[id];
  if(existing && existing.el){
    bringToFront(id);
    loadDocPop(id);
    return;
  }
  const st=ensurePopShell(id, label||id);
  if(st) loadDocPop(id);
}

document.querySelectorAll('.schema-node[data-ds]').forEach(btn=>{
  btn.addEventListener('click', ()=>{
    openDocDataset(btn.getAttribute('data-ds'), btn.querySelector('.sn-id')?.textContent||'');
  });
});
"""
