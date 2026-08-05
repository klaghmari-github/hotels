#!/usr/bin/env python3
"""
Interface d'evaluation du simulateur ROD v2 (assortiment / mix gammes).

Leave-one-out : pour chaque hotel, prediction du CA et de la marge a partir
des simulations des pairs (meme logique de page que v1).

Source : data/eval_sim_v2_loo.xlsx
  - data        : mix gammes et cibles baseline
  - eval_<code> : detail leave-one-out
  - eval        : synthese MAE

  python run_eval_sim_v2.py
  python run_eval_sim_v2.py --rebuild
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
from flask import Flask, jsonify, render_template_string, send_file

DATA_DIR = _ROOT / "data"
DEFAULT_PORT = 5058
EXCEL_PATH = DATA_DIR / "eval_sim_v2_loo.xlsx"

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False

PAGE_HTML = r"""
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Evaluation simulateur v2</title>
  <style>
    :root {
      --bg: #0f1419; --card: #1a2332; --line: #2a3a4f;
      --text: #e7eef7; --muted: #8b9bb0; --accent: #3d8bfd;
      --tab: #141c28; --tab-on: #243044;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0; font-family: "Segoe UI", system-ui, sans-serif;
      background: var(--bg); color: var(--text); line-height: 1.45;
    }
    header {
      padding: 1rem 1.25rem; border-bottom: 1px solid var(--line);
      display: flex; flex-wrap: wrap; gap: .75rem; align-items: center;
      justify-content: space-between;
    }
    h1 { font-size: 1.1rem; margin: 0; font-weight: 600; }
    h1 span { color: var(--muted); font-weight: 400; font-size: .85rem; margin-left: .4rem; }
    a.link {
      color: var(--text); border: 1px solid var(--line); border-radius: 8px;
      padding: .4rem .85rem; text-decoration: none; font-size: .85rem; font-weight: 600;
    }
    a.link:hover { border-color: var(--accent); color: var(--accent); }
    .tabs {
      display: flex; flex-wrap: wrap; gap: .35rem; padding: .75rem 1.25rem;
      border-bottom: 1px solid var(--line); background: var(--tab);
      position: sticky; top: 0; z-index: 5;
    }
    .tab {
      border: 1px solid var(--line); background: transparent; color: var(--muted);
      border-radius: 999px; padding: .35rem .8rem; cursor: pointer; font-size: .8rem;
      font-weight: 600;
    }
    .tab:hover { color: var(--text); }
    .tab.active { background: var(--tab-on); color: var(--text); border-color: var(--accent); }
    main { padding: 1.1rem 1.25rem 2.5rem; max-width: 1280px; margin: 0 auto; }
    .panel { display: none; }
    .panel.active { display: block; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: .7rem; }
    .card {
      background: var(--card); border: 1px solid var(--line); border-radius: 12px;
      padding: .9rem 1rem;
    }
    .card .lbl { color: var(--muted); font-size: .72rem; text-transform: uppercase; letter-spacing: .03em; }
    .card .val { font-size: 1.35rem; font-weight: 700; margin-top: .2rem; }
    .card .sub { color: var(--muted); font-size: .78rem; margin-top: .15rem; }
    h2 { font-size: 1rem; margin: 1.1rem 0 .5rem; font-weight: 600; }
    h3 { font-size: .9rem; margin: .9rem 0 .4rem; color: var(--muted); font-weight: 600; }
    table {
      width: 100%; border-collapse: collapse; font-size: .82rem;
      background: var(--card); border: 1px solid var(--line); border-radius: 10px;
      overflow: hidden;
    }
    th, td { text-align: left; padding: .5rem .55rem; border-bottom: 1px solid var(--line); vertical-align: top; }
    th { color: var(--muted); font-weight: 600; font-size: .72rem; text-transform: uppercase; background: #152030; }
    tr:last-child td { border-bottom: 0; }
    tr:hover td { background: rgba(61,139,253,.05); }
    .num { font-variant-numeric: tabular-nums; text-align: right; white-space: nowrap; }
    .tag {
      display: inline-block; padding: .1rem .45rem; border-radius: 999px;
      font-size: .7rem; font-weight: 600; background: #243044; color: var(--muted);
    }
    .tag.simply { color: #7dd3fc; }
    .tag.liberty { color: #c4b5fd; }
    .tag.connected { color: #86efac; }
    .scroll { overflow: auto; max-width: 100%; }
    .muted { color: var(--muted); font-size: .85rem; }
    .errbox {
      margin: 1rem 0; padding: .8rem 1rem; border: 1px solid #5a2a35;
      background: #2a1520; border-radius: 8px; color: #f5a0b0;
    }
    #status { color: var(--muted); font-size: .82rem; }
  </style>
</head>
<body>
  <header>
    <h1>Evaluation simulateur v2 <span>leave-one-out · mix gammes</span></h1>
    <div style="display:flex;gap:.6rem;align-items:center">
      <span id="status"></span>
      <a class="link" href="/download">Telecharger Excel</a>
    </div>
  </header>
  <nav class="tabs" id="tabs"></nav>
  <main id="main"></main>
  <script>
    const fmt = (n, d=2) => {
      if (n === null || n === undefined || n === '') return '—';
      if (typeof n === 'string' && n.trim() !== '' && Number.isNaN(Number(n))) return n;
      const x = Number(n);
      if (Number.isNaN(x)) return String(n);
      return x.toLocaleString('fr-FR', { maximumFractionDigits: d, minimumFractionDigits: 0 });
    };
    const tag = (s) => `<span class="tag ${(s||'').toLowerCase()}">${s||''}</span>`;

    function tableFromRows(cols, rows, numCols) {
      const nums = new Set(numCols || []);
      let h = '<div class="scroll"><table><thead><tr>' +
        cols.map(c => `<th class="${nums.has(c.key)?'num':''}">${c.label}</th>`).join('') +
        '</tr></thead><tbody>';
      for (const r of rows) {
        h += '<tr>' + cols.map(c => {
          let v = r[c.key];
          if (c.key === 'solution') v = tag(v);
          else if (nums.has(c.key)) v = fmt(v, c.digits ?? 2);
          else if (v === null || v === undefined) v = '—';
          else v = String(v);
          return `<td class="${nums.has(c.key)?'num':''}">${v}</td>`;
        }).join('') + '</tr>';
      }
      return h + '</tbody></table></div>';
    }

    function kpis(m) {
      return `<div class="grid">
        <div class="card"><div class="lbl">MAE CA mensuel</div><div class="val">${fmt(m.mae_ca_mensuel)}</div><div class="sub">EUR / mois</div></div>
        <div class="card"><div class="lbl">MAE marge mensuel</div><div class="val">${fmt(m.mae_marge_mensuel)}</div><div class="sub">EUR / mois</div></div>
        <div class="card"><div class="lbl">MAPE CA</div><div class="val">${m.mape_ca_pct != null ? fmt(m.mape_ca_pct,1)+' %' : '—'}</div><div class="sub">erreur relative</div></div>
        <div class="card"><div class="lbl">Hotels</div><div class="val">${m.n_hotels ?? '—'}</div><div class="sub">${m.n_scenarios_total ?? '—'} scenarios source</div></div>
      </div>`;
    }

    function panelData(dataRows, gcols) {
      const cols = [
        {key:'hotel_code', label:'Code'},
        {key:'solution', label:'Solution'},
        {key:'montant_ventes_par_mois', label:'CA mensuel'},
        {key:'montant_marge_par_mois', label:'Marge mensuelle'},
        {key:'nombre_ventes_par_mois', label:'Ventes / mois'},
        {key:'nombre_natures', label:'Natures'},
        {key:'nombre_gammes', label:'Gammes'},
        {key:'metres_lineaires', label:'m lin.'},
        {key:'nombre_guests_par_mois', label:'Guests / mois'},
      ];
      for (const c of (gcols || [])) {
        const short = c.replace('gamme_','').replace('_part_natures','');
        cols.push({key:c, label:'part '+short});
      }
      const nums = cols.map(c => c.key).filter(k => k !== 'hotel_code' && k !== 'solution');
      return `<h2>Baseline et mix gammes</h2>
        <p class="muted">Scenario vide (aucune nature retiree). Les parts de gammes servent de cible pour trouver la simulation la plus proche chez chaque pair.</p>
        ${tableFromRows(cols, dataRows || [], nums)}`;
    }

    function panelHotel(h) {
      const t = h.true || {};
      const by = h.by_solution || {};
      let solCards = '<div class="grid" style="margin:.6rem 0">';
      for (const sol of ['simply','liberty','connected']) {
        const b = by[sol] || {};
        solCards += `<div class="card">
          <div class="lbl">${tag(sol)}</div>
          <div class="sub">pairs utilises : ${b.n_used ?? 0}</div>
          <div style="margin-top:.35rem">CA predit <strong>${fmt(b.pred_montant_ventes_par_mois)}</strong></div>
          <div>Marge predite <strong>${fmt(b.pred_montant_marge_par_mois)}</strong></div>
        </div>`;
      }
      solCards += '</div>';

      let peersHtml = '';
      for (const sol of ['simply','liberty','connected']) {
        const peers = (by[sol] || {}).peers || [];
        if (!peers.length) continue;
        peersHtml += `<h3>Pairs ${sol}</h3>`;
        peersHtml += tableFromRows(
          [
            {key:'peer_hotel', label:'Hotel pair'},
            {key:'distance_mix_l2', label:'Distance L2 mix'},
            {key:'scenario_id', label:'Scenario (hash court)'},
            {key:'n_natures_retirees', label:'Natures retirees'},
            {key:'montant_ventes_par_mois', label:'CA simule'},
            {key:'montant_marge_par_mois', label:'Marge simulee'},
          ],
          peers.map(p => ({...p, scenario_id: (p.scenario_id||'').slice(0,12)})),
          ['distance_mix_l2','n_natures_retirees','montant_ventes_par_mois','montant_marge_par_mois']
        );
      }

      const cols = [
        {key:'etape', label:'Etape'},
        {key:'variable', label:'Variable'},
        {key:'valeur', label:'Valeur'},
        {key:'source', label:'Source'},
      ];
      return `
        <div class="grid" style="margin-bottom:.8rem">
          <div class="card"><div class="lbl">CA reel</div><div class="val">${fmt(t.montant_ventes_par_mois)}</div><div class="sub">EUR / mois</div></div>
          <div class="card"><div class="lbl">CA predit</div><div class="val">${fmt(h.pred_ca)}</div><div class="sub">solution ${tag(h.solution)}</div></div>
          <div class="card"><div class="lbl">Erreur abs. CA</div><div class="val">${fmt(h.err_ca)}</div><div class="sub">EUR / mois</div></div>
          <div class="card"><div class="lbl">Erreur abs. marge</div><div class="val">${fmt(h.err_marge)}</div><div class="sub">EUR / mois</div></div>
        </div>
        <p class="muted">Hotel ${h.hotel_code} — solution reelle ${tag(h.solution)}. Prediction = moyenne des simulations les plus proches (mix gammes) des hotels pairs, par solution.</p>
        <h3>Predictions par solution</h3>
        ${solCards}
        ${peersHtml}
        <h3>Detail des regles de selection</h3>
        ${tableFromRows(cols, h.inputs || [], ['valeur'])}
      `;
    }

    function panelEval(evalRows, metrics, bySol) {
      const hotels = (evalRows || []).filter(r => r.hotel_code && !String(r.hotel_code).startsWith('MAE') && r.hotel_code !== 'MAPE_CA_PCT');
      const cols = [
        {key:'hotel_code', label:'Code'},
        {key:'solution', label:'Solution'},
        {key:'ca_ht_reel', label:'CA reel'},
        {key:'ca_ht_pred', label:'CA predit'},
        {key:'erreur_abs_ca', label:'|err| CA'},
        {key:'marge_reel', label:'Marge reelle'},
        {key:'marge_pred', label:'Marge predite'},
        {key:'erreur_abs_marge', label:'|err| marge'},
        {key:'pred_simply_ca', label:'Pred simply CA'},
        {key:'pred_liberty_ca', label:'Pred liberty CA'},
        {key:'pred_connected_ca', label:'Pred connected CA'},
      ];
      const nums = ['ca_ht_reel','ca_ht_pred','erreur_abs_ca','marge_reel','marge_pred','erreur_abs_marge','pred_simply_ca','pred_liberty_ca','pred_connected_ca'];
      let solHtml = '<div class="grid" style="margin:.8rem 0">';
      for (const [sol, v] of Object.entries(bySol || {})) {
        solHtml += `<div class="card"><div class="lbl">${tag(sol)}</div>
          <div class="sub">n = ${v.n ?? '—'}</div>
          <div style="margin-top:.4rem">MAE CA <strong>${fmt(v.mae_ca)}</strong></div>
          <div>MAE marge <strong>${fmt(v.mae_marge)}</strong></div></div>`;
      }
      solHtml += '</div>';
      return `${kpis(metrics)}
        <h2 style="margin-top:1.2rem">Erreur par solution reelle</h2>
        ${solHtml}
        <h2>Detail par hotel</h2>
        ${tableFromRows(cols, hotels, nums)}`;
    }

    function activate(id) {
      document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.id === id));
      document.querySelectorAll('.panel').forEach(p => p.classList.toggle('active', p.id === 'panel-' + id));
    }

    function build(payload) {
      const tabs = document.getElementById('tabs');
      const main = document.getElementById('main');
      const items = [{id:'data', label:'data'}];
      for (const h of (payload.per_hotel || [])) {
        items.push({id: 'eval_' + h.hotel_code, label: 'eval_' + h.hotel_code});
      }
      items.push({id:'eval', label:'eval'});
      tabs.innerHTML = items.map((t,i) =>
        `<button type="button" class="tab${i===0?' active':''}" data-id="${t.id}">${t.label}</button>`
      ).join('');

      let html = `<div class="panel active" id="panel-data">${panelData(payload.data||[], payload.gamme_columns||[])}</div>`;
      for (const h of (payload.per_hotel || [])) {
        html += `<div class="panel" id="panel-eval_${h.hotel_code}">${panelHotel(h)}</div>`;
      }
      html += `<div class="panel" id="panel-eval">${panelEval(payload.eval_rows||[], payload.metrics||{}, payload.by_solution||{})}</div>`;
      main.innerHTML = html;
      tabs.querySelectorAll('.tab').forEach(btn => btn.addEventListener('click', () => activate(btn.dataset.id)));
      document.getElementById('status').textContent = payload.source || '';
    }

    fetch('/api/results')
      .then(r => { if (!r.ok) throw new Error('HTTP '+r.status); return r.json(); })
      .then(data => {
        if (!data.ok) {
          document.getElementById('main').innerHTML = `<div class="errbox">${data.error||'Chargement impossible'}</div>`;
          document.getElementById('status').textContent = 'Erreur';
          return;
        }
        build(data);
      })
      .catch(e => {
        document.getElementById('main').innerHTML =
          `<div class="errbox">Impossible de charger les resultats (${e.message}).</div>`;
        document.getElementById('status').textContent = 'Erreur';
      });
  </script>
</body>
</html>
"""


def _clean(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    return str(v)


def load_results_from_excel(path: Path | None = None) -> dict:
    path = path or EXCEL_PATH
    if not path.exists():
        return {
            "ok": False,
            "error": f"Fichier introuvable : {path.name}. Executer : python run_eval_sim_v2.py --rebuild",
        }

    xl = pd.ExcelFile(path)
    sheets = xl.sheet_names
    data = pd.read_excel(path, sheet_name="data") if "data" in sheets else pd.DataFrame()
    data_rows = [{c: _clean(r[c]) for c in data.columns} for _, r in data.iterrows()]
    gcols = [c for c in data.columns if str(c).startswith("gamme_") and str(c).endswith("_part_natures")]

    per_hotel = []
    for name in sheets:
        if not name.startswith("eval_") or name == "eval":
            continue
        code = name.replace("eval_", "", 1)
        df = pd.read_excel(path, sheet_name=name)
        inputs = []
        summary: dict = {}
        by_solution: dict = {s: {"peers": [], "n_used": 0} for s in ("simply", "liberty", "connected")}
        for _, r in df.iterrows():
            etape = str(r.get("etape") or "")
            var = str(r.get("variable") or "")
            val = _clean(r.get("valeur"))
            src = str(r.get("source") or "")
            if etape == "RESUME":
                summary[var] = val
                if var.startswith("pred_") and var.endswith("_ca"):
                    sol = var[len("pred_") : -len("_ca")]
                    by_solution.setdefault(sol, {})["pred_montant_ventes_par_mois"] = val
                if var.startswith("pred_") and var.endswith("_marge"):
                    sol = var[len("pred_") : -len("_marge")]
                    by_solution.setdefault(sol, {})["pred_montant_marge_par_mois"] = val
                    # n_peers from source
                    if "n_peers=" in src:
                        try:
                            by_solution[sol]["n_used"] = int(src.split("n_peers=")[1].split()[0])
                        except Exception:
                            pass
                continue
            inputs.append({"etape": etape, "variable": var, "valeur": val, "source": src})
            # rebuild peer lines
            if etape.startswith("Pair ") and var.endswith("_scenario"):
                sol = etape.replace("Pair ", "").strip()
                peer = var.replace("_scenario", "")
                dist = None
                if "distance L2" in src:
                    try:
                        dist = float(src.split("=")[-1].strip())
                    except Exception:
                        dist = None
                by_solution.setdefault(sol, {"peers": []})
                by_solution[sol].setdefault("peers", []).append(
                    {
                        "peer_hotel": peer,
                        "scenario_id": val,
                        "distance_mix_l2": dist,
                    }
                )
            if etape.startswith("Pair ") and var.endswith("_ca"):
                sol = etape.replace("Pair ", "").strip()
                peer = var.replace("_ca", "")
                peers = by_solution.get(sol, {}).get("peers") or []
                for p in peers:
                    if p.get("peer_hotel") == peer:
                        p["montant_ventes_par_mois"] = val
            if etape.startswith("Pair ") and var.endswith("_marge"):
                sol = etape.replace("Pair ", "").strip()
                peer = var.replace("_marge", "")
                peers = by_solution.get(sol, {}).get("peers") or []
                for p in peers:
                    if p.get("peer_hotel") == peer:
                        p["montant_marge_par_mois"] = val

        drow = next((x for x in data_rows if x.get("hotel_code") == code), {})
        per_hotel.append(
            {
                "hotel_code": code,
                "solution": summary.get("solution") or drow.get("solution"),
                "true": {
                    "montant_ventes_par_mois": summary.get("ca_ht_reel")
                    or drow.get("montant_ventes_par_mois"),
                    "montant_marge_par_mois": summary.get("marge_reel")
                    or drow.get("montant_marge_par_mois"),
                },
                "pred_ca": summary.get("ca_ht_pred"),
                "pred_marge": summary.get("marge_pred"),
                "err_ca": summary.get("erreur_abs_ca"),
                "err_marge": summary.get("erreur_abs_marge"),
                "by_solution": by_solution,
                "inputs": inputs,
            }
        )

    order = {str(r.get("hotel_code")): i for i, r in enumerate(data_rows)}
    per_hotel.sort(key=lambda h: order.get(h["hotel_code"], 999))

    eval_rows = []
    metrics = {
        "mae_ca_mensuel": None,
        "mae_marge_mensuel": None,
        "mape_ca_pct": None,
        "n_hotels": len(per_hotel),
        "n_scenarios_total": None,
    }
    by_solution: dict = {}
    if "eval" in sheets:
        ev = pd.read_excel(path, sheet_name="eval")
        for _, r in ev.iterrows():
            code = str(r.get("hotel_code") or "")
            if code == "MAE_GLOBAL":
                metrics["mae_ca_mensuel"] = _clean(r.get("erreur_abs_ca"))
                metrics["mae_marge_mensuel"] = _clean(r.get("erreur_abs_marge"))
                continue
            if code == "MAPE_CA_PCT":
                metrics["mape_ca_pct"] = _clean(r.get("erreur_abs_ca"))
                continue
            if code.startswith("MAE_"):
                sol = code.replace("MAE_", "").lower()
                by_solution[sol] = {
                    "n": None,
                    "mae_ca": _clean(r.get("erreur_abs_ca")),
                    "mae_marge": _clean(r.get("erreur_abs_marge")),
                }
                continue
            eval_rows.append({c: _clean(r[c]) for c in ev.columns})

    for sol in ("simply", "liberty", "connected"):
        sub = [h for h in per_hotel if h.get("solution") == sol]
        if sol not in by_solution:
            by_solution[sol] = {"n": len(sub), "mae_ca": None, "mae_marge": None}
        else:
            by_solution[sol]["n"] = len(sub)

    return {
        "ok": True,
        "source": path.name,
        "data": data_rows,
        "gamme_columns": gcols,
        "per_hotel": per_hotel,
        "eval_rows": eval_rows,
        "metrics": metrics,
        "by_solution": by_solution,
    }


@app.get("/")
def index():
    return render_template_string(PAGE_HTML)


@app.get("/api/results")
def api_results():
    try:
        return jsonify(load_results_from_excel())
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.get("/api/health")
def health():
    return jsonify(
        {
            "ok": True,
            "service": "eval_sim_v2",
            "excel": str(EXCEL_PATH),
            "exists": EXCEL_PATH.exists(),
        }
    )


@app.get("/download")
def download():
    if not EXCEL_PATH.exists():
        return jsonify({"ok": False, "error": "Excel introuvable"}), 404
    return send_file(EXCEL_PATH, as_attachment=True, download_name="eval_sim_v2_loo.xlsx")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluation simulateur ROD v2")
    parser.add_argument("--rebuild", action="store_true", help="Recalcule et reecrit l'Excel")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)

    if args.rebuild or not EXCEL_PATH.exists():
        from eval_sim_v2 import evaluate_loo_sim_v2, metrics_summary, write_eval_excel

        print("Calcul leave-one-out v2…")
        result = evaluate_loo_sim_v2()
        print(metrics_summary(result))
        out = write_eval_excel(result, EXCEL_PATH)
        print(f"Ecrit : {out}")
        if args.rebuild:
            return 0

    print(f"Evaluation v2 — http://127.0.0.1:{args.port}/")
    print(f"  Excel : {EXCEL_PATH}")
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
