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
"""

DOC_BODY = """
<div class="doc-wrap">
  <a class="link doc-back" href="/user">← Retour au parcours</a>

  <div class="doc-hero">
    <h2>Documentation simulateur</h2>
    <p>
      Construction du nuage de données à partir des tickets pilotes, calcul des coefficients
      par solution, estimation d’un hôtel cible, et rôle du modèle ML de conversion.
    </p>
    <div class="doc-pills">
      <span class="doc-pill">sim_v2</span>
      <span class="doc-pill teal">Scénarios</span>
      <span class="doc-pill violet">ML conversion</span>
    </div>
  </div>

  <nav class="doc-toc">
    <a href="#obj">Objet</a>
    <a href="#schema">Pipeline</a>
    <a href="#obs">Observation</a>
    <a href="#sim">Simulation</a>
    <a href="#coef">Coefficients</a>
    <a href="#est">Estimation</a>
    <a href="#ml">ML</a>
    <a href="#parcours">Parcours UI</a>
    <a href="#limites">Limites</a>
  </nav>

  <section class="doc-section" id="obj">
    <h3>1. Objet</h3>
    <p>
      Estimer le CA mensuel d’un hôtel cible (chambres, TO, guests/chambre, m_lin, mix)
      pour les concepts Simply, Liberty et Connected.
    </p>
    <p>
      Le modèle part des tickets des hôtels pilotes. Des assortiments réduits sont simulés
      par retrait de natures et redistribution du volume. On en déduit des coefficients
      d’intensité (CA par guest, m_lin et part de mix), appliqués aux leviers de la cible.
    </p>
    <div class="grid2">
      <div class="mini">
        <h5><span class="tag-pill obs">OBS</span> Observation</h5>
        <p>Scénario vide : ventes réelles agrégées au mois, mix observé.</p>
      </div>
      <div class="mini">
        <h5><span class="tag-pill sim">SIM</span> Simulation</h5>
        <p>Même hôtel, natures retirées, volumes réalloués, CA et mix recalculés.</p>
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
          <span>Rangs de natures → listes de retraits (+ scénario vide)</span>
        </div>
      </div>
      <div class="flow-arrow">↓</div>
      <div class="flow-row">
        <div class="flow-num g2">3</div>
        <div class="flow-body">
          <strong>Simulation</strong>
          <span>Scénario × hôtel → lignes <code>t_dataset_pivot</code></span>
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
          <span>Leviers × coeffs (sim_v2) ; ML ajuste la conversion</span>
        </div>
      </div>
    </div>
    <div class="schema">t_sales  →  scénarios  →  t_dataset_pivot  →  coeffs / solution
                                              ↓
                         estimation cible  ←  sim_v2 × scale ML</div>
  </section>

  <section class="doc-section" id="obs">
    <h3>3. Observation</h3>
    <p>Sur la période des tickets d’un pilote :</p>
    <div class="formula">guests_mois = chambres × TO_annuel × guests/chambre × 30,5

taux_conversion = nombre_ventes / guests
CA_mois, marge_mois = agrégats tickets ramenés au mois</div>
    <p>Le facteur 30,5 convertit l’occupation journalière en flux mensuel (convention ROD).</p>
  </section>

  <section class="doc-section" id="sim">
    <h3>4. Simulation</h3>
    <h4>Scénarios</h4>
    <p>
      Une nature est une référence catalogue. Le scénario vide reprend l’observation.
      Les autres retirent des natures selon des rangs (type, gamme, catégorie, marque…)
      pour couvrir des corners plus petits.
    </p>
    <h4>Redistribution</h4>
    <p>Le volume des natures retirées est réinjecté sur les natures conservées :</p>
    <div class="formula">part(h, n) = ventes(h,n) / ventes_totales(h)

volume_ajoute(h, n) =
  ventes_retirées(h) × taux_conversion(h) × part(h, n)

q_scénario = q_ligne + volume_ajoute × (q_ligne / ventes_nature)</div>
    <p>CA et marges sont multipliés par le ratio de quantités (substitution proportionnelle).</p>
    <h4>Surface et mix</h4>
    <div class="formula">m_lin_scénario ≈ (m_lin_obs / n_natures_obs) × n_natures_restantes</div>
    <p>Le mix type / gamme est recalculé sur les ventes du scénario.</p>
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
    <p>
      Résultat : intensité moyenne des hôtels de la même solution,
      rejouée sur le trafic, la surface et le mix de la cible.
    </p>
  </section>

  <section class="doc-section" id="ml">
    <h3>7. ML — conversion par solution</h3>
    <p>
      Trois modèles distincts : <code>model_simply</code>, <code>model_liberty</code>,
      <code>model_connected</code>. Aucun mélange de solutions à l’entraînement.
    </p>
    <p>Cible apprise :</p>
    <div class="formula">taux_conversion = nombre_ventes / guests</div>
    <p>Features : structure hôtel (chambres, TO, guests/chambre), m_lin, mix type / gammes.</p>
    <p>Estimation finale :</p>
    <div class="formula">CA_ml = CA_sim_v2 × (conv_ML / conv_baseline_solution)
marge_ml = marge_sim_v2 × (conv_ML / conv_baseline_solution)</div>
    <p>
      sim_v2 fixe la structure (mix, surface, trafic) ; le ML corrige le taux de conversion
      pour le contexte de la cible, au sein de sa solution.
    </p>
    <div class="schema">leviers + mix ──▶ sim_v2 ──▶ CA_sim_v2
       │
       └──▶ model_{solution} ──▶ conv_ML
                    │
                    ▼
         CA_ml = CA_sim_v2 × (conv_ML / baseline)</div>
  </section>

  <section class="doc-section" id="parcours">
    <h3>8. Parcours utilisateur</h3>
    <table>
      <tr><th>Étape</th><th>Contenu</th></tr>
      <tr><td>1 · Hôtel</td><td>Sélection du site</td></tr>
      <tr><td>2 · Infos générales</td><td>Exploitation, services, proximité</td></tr>
      <tr><td>3 · Choix gammes</td><td>Activation types / gammes pour le périmètre d’optimisation</td></tr>
      <tr><td>4 · Mix reco</td><td>Assortiment et mix calculés (product rank) + CA moteurs</td></tr>
      <tr><td>5 · Choisir mix</td><td>Catalogue complet, % éditables, rechargement de la reco</td></tr>
      <tr><td>6 · Estimation</td><td>CA, marge, coûts, amortissement (sim_v1 / sim_v2 / ml)</td></tr>
    </table>
    <p style="margin-top:.7rem">
      Les montants moteur sont mensuels ; l’UI affiche l’annuel (×12) en estimation utilisateur.
    </p>
  </section>

  <section class="doc-section" id="limites">
    <h3>9. Limites</h3>
    <ul style="margin:.3rem 0 0 1.1rem; color:var(--muted); font-size:.92rem">
      <li>Redistribution proportionnelle (pas d’élasticité prix).</li>
      <li>Coefficients et modèles ML strictement par solution.</li>
      <li>Le mapping hôtel ↔ solution doit être exact (sinon biais du nuage).</li>
      <li>Mix très hors distribution observée : extrapolation limitée.</li>
      <li>LOO mono-hôtel par solution : évaluation biaisée (hôtel gardé en train).</li>
    </ul>
    <p style="margin-top:.85rem;color:var(--muted);font-size:.9rem">
      Définitions SQL : <code>pipeline/sim_v2/</code>, <code>pipeline/ml/</code>.
    </p>
  </section>

  <p class="doc-footer">
    Accor ROD · release 1.0.0<br/>
    <a class="link" href="/user" style="margin-top:.5rem;display:inline-block">Retour au parcours</a>
  </p>
</div>
"""

DOC_SCRIPT = """
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
"""
