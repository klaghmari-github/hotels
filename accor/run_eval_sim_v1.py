#!/usr/bin/env python3
"""
Interface d'evaluation du simulateur ROD v1.

Source : data/eval_sim_v1_loo.xlsx
  - data          : indicateurs par hotel
  - eval_<code>   : prediction leave-one-out d'un hotel
  - eval          : synthese et erreurs moyennes

  python run_eval_sim_v1.py
  python run_eval_sim_v1.py --rebuild
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

import pandas as pd
from flask import Flask, jsonify, render_template_string, send_file

from accor.data_io import DATA_DIR

DEFAULT_PORT = 5057
EXCEL_PATH = DATA_DIR / "eval_sim_v1_loo.xlsx"

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False

PAGE_HTML = r"""
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Evaluation simulateur v1</title>
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
    <h1>Evaluation simulateur v1 <span>leave-one-out</span></h1>
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
    const pct = (n) => {
      if (n === null || n === undefined || n === '' || Number.isNaN(Number(n))) return '—';
      let x = Number(n);
      if (x <= 1 && x >= 0) x = x * 100;
      return fmt(x, 1) + ' %';
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
          if (c.key === 'solution' || c.key === 'concept') v = tag(v);
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
        <div class="card"><div class="lbl">Hotels</div><div class="val">${m.n_hotels ?? '—'}</div><div class="sub">leave-one-out</div></div>
      </div>`;
    }

    function panelData(dataRows) {
      const cols = [
        {key:'hotel_code', label:'Code'},
        {key:'hotel_label', label:'Label'},
        {key:'hotel_name', label:'Nom'},
        {key:'solution', label:'Solution'},
        {key:'nb_chambres', label:'Chambres'},
        {key:'taux_occupation', label:'TO'},
        {key:'guests_per_chambre', label:'Guests'},
        {key:'m_lin', label:'m lin.'},
        {key:'clients_mois', label:'Clients / mois'},
        {key:'mix_fb', label:'Mix F&B'},
        {key:'mix_nf', label:'Mix N-F&B'},
        {key:'ca_ht_mensuel', label:'CA HT mensuel'},
        {key:'ca_fb_mensuel', label:'CA F&B'},
        {key:'ca_nf_mensuel', label:'CA N-F&B'},
        {key:'nb_ventes_mensuel', label:'Ventes / mois'},
        {key:'taux_conversion_acheteur', label:'Taux conversion'},
        {key:'panier_moyen_ht', label:'Panier moyen HT'},
        {key:'ca_par_client_heberge', label:'CA / client'},
        {key:'marge_mensuel', label:'Marge mensuelle'},
        {key:'n_mois', label:'n mois'},
      ];
      const nums = ['nb_chambres','taux_occupation','guests_per_chambre','m_lin','clients_mois',
        'mix_fb','mix_nf','ca_ht_mensuel','ca_fb_mensuel','ca_nf_mensuel','nb_ventes_mensuel',
        'taux_conversion_acheteur','panier_moyen_ht','ca_par_client_heberge','marge_mensuel','n_mois'];
      // format TO and mix as percent-ish numbers as-is (0-1)
      const rows = dataRows.map(r => ({...r}));
      return `<h2>Indicateurs par hotel</h2>
        <p class="muted">Moyennes mensuelles sur l'ensemble des periodes disponibles. Ces champs alimentent les regles du simulateur v1.</p>
        ${tableFromRows(cols, rows, nums)}`;
    }

    function panelHotel(h) {
      const s = h.summary || {};
      const cols = [
        {key:'etape', label:'Etape'},
        {key:'variable', label:'Variable'},
        {key:'valeur', label:'Valeur'},
        {key:'source', label:'Source'},
      ];
      const top = `<div class="grid" style="margin-bottom:.8rem">
        <div class="card"><div class="lbl">CA reel</div><div class="val">${fmt(h.true_ca)}</div><div class="sub">EUR / mois</div></div>
        <div class="card"><div class="lbl">CA predit</div><div class="val">${fmt(h.pred_ca)}</div><div class="sub">regles R1 a R4</div></div>
        <div class="card"><div class="lbl">Erreur abs. CA</div><div class="val">${fmt(h.err_ca)}</div><div class="sub">EUR / mois</div></div>
        <div class="card"><div class="lbl">Erreur abs. marge</div><div class="val">${fmt(h.err_marge)}</div><div class="sub">EUR / mois</div></div>
      </div>
      <p class="muted">Hotel ${h.hotel_code} — ${h.hotel_name || ''} — solution ${tag(h.concept)} —
      pairs de reference : ${(h.peers||[]).join(', ') || '—'}</p>
      <h3>Parametres hotel et reference</h3>
      <div class="grid" style="margin-bottom:.8rem">
        <div class="card"><div class="lbl">Chambres</div><div class="val" style="font-size:1.1rem">${fmt(s.nb_chambres,1)}</div></div>
        <div class="card"><div class="lbl">TO</div><div class="val" style="font-size:1.1rem">${fmt(s.taux_occupation,3)}</div></div>
        <div class="card"><div class="lbl">Clients / mois</div><div class="val" style="font-size:1.1rem">${fmt(s.clients_mois,1)}</div></div>
        <div class="card"><div class="lbl">m lin.</div><div class="val" style="font-size:1.1rem">${fmt(s.m_lin,1)}</div></div>
        <div class="card"><div class="lbl">Mix F&B hotel</div><div class="val" style="font-size:1.1rem">${fmt(s.mix_fb,3)}</div></div>
        <div class="card"><div class="lbl">Taux conversion hotel</div><div class="val" style="font-size:1.1rem">${fmt(s.taux_conversion_hotel,4)}</div></div>
        <div class="card"><div class="lbl">Panier moyen hotel</div><div class="val" style="font-size:1.1rem">${fmt(s.panier_moyen_hotel,2)}</div></div>
        <div class="card"><div class="lbl">Taux conversion ref.</div><div class="val" style="font-size:1.1rem">${fmt(s.taux_conversion_ref,4)}</div></div>
        <div class="card"><div class="lbl">Panier moyen ref.</div><div class="val" style="font-size:1.1rem">${fmt(s.panier_moyen_ref,2)}</div></div>
      </div>
      <h3>Detail des regles appliquees</h3>`;
      return top + tableFromRows(cols, h.inputs || [], ['valeur']);
    }

    function panelEval(evalRows, metrics, bySol) {
      const hotels = (evalRows || []).filter(r => r.hotel_code && !String(r.hotel_code).startsWith('MAE') && r.hotel_code !== 'MAPE_CA_PCT');
      const cols = [
        {key:'hotel_code', label:'Code'},
        {key:'hotel_name', label:'Nom'},
        {key:'solution', label:'Solution'},
        {key:'pairs', label:'Pairs'},
        {key:'ca_ht_reel', label:'CA reel'},
        {key:'ca_ht_pred', label:'CA predit'},
        {key:'erreur_abs_ca', label:'|err| CA'},
        {key:'marge_reel', label:'Marge reelle'},
        {key:'marge_pred', label:'Marge predite'},
        {key:'erreur_abs_marge', label:'|err| marge'},
        {key:'n_mois', label:'n mois'},
      ];
      const nums = ['ca_ht_reel','ca_ht_pred','erreur_abs_ca','marge_reel','marge_pred','erreur_abs_marge','n_mois'];
      let solHtml = '<div class="grid" style="margin:.8rem 0">';
      for (const [sol, v] of Object.entries(bySol || {})) {
        solHtml += `<div class="card"><div class="lbl">${sol}</div>
          <div class="sub">n = ${v.n ?? '—'}</div>
          <div style="margin-top:.4rem">MAE CA <strong>${fmt(v.mae_ca)}</strong></div>
          <div>MAE marge <strong>${fmt(v.mae_marge)}</strong></div></div>`;
      }
      solHtml += '</div>';
      return `${kpis(metrics)}
        <h2 style="margin-top:1.2rem">Erreur par solution</h2>
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
      const items = [];
      items.push({id: 'data', label: 'data'});
      for (const h of (payload.per_hotel || [])) {
        items.push({id: 'eval_' + h.hotel_code, label: 'eval_' + h.hotel_code});
      }
      items.push({id: 'eval', label: 'eval'});

      tabs.innerHTML = items.map((t,i) =>
        `<button type="button" class="tab${i===0?' active':''}" data-id="${t.id}">${t.label}</button>`
      ).join('');

      let html = '';
      html += `<div class="panel active" id="panel-data">${panelData(payload.data || [])}</div>`;
      for (const h of (payload.per_hotel || [])) {
        html += `<div class="panel" id="panel-eval_${h.hotel_code}">${panelHotel(h)}</div>`;
      }
      html += `<div class="panel" id="panel-eval">${panelEval(payload.eval_rows || [], payload.metrics || {}, payload.by_solution || {})}</div>`;
      main.innerHTML = html;

      tabs.querySelectorAll('.tab').forEach(btn => {
        btn.addEventListener('click', () => activate(btn.dataset.id));
      });
      document.getElementById('status').textContent = payload.source || '';
    }

    fetch('/api/results')
      .then(r => {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(data => {
        if (!data.ok) {
          document.getElementById('main').innerHTML =
            `<div class="errbox">${data.error || 'Chargement impossible'}</div>`;
          document.getElementById('status').textContent = 'Erreur';
          return;
        }
        build(data);
      })
      .catch(e => {
        document.getElementById('main').innerHTML =
          `<div class="errbox">Impossible de charger les resultats (${e.message}). Verifiez que le fichier Excel est present.</div>`;
        document.getElementById('status').textContent = 'Erreur';
      });
  </script>
</body>
</html>
"""


def _clean(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (int, float)):
        return float(v) if not isinstance(v, bool) else v
    return str(v)


def load_results_from_excel(path: Path | None = None) -> dict:
    path = path or EXCEL_PATH
    if not path.exists():
        return {
            "ok": False,
            "error": f"Fichier introuvable : {path.name}. Executer : python run_eval_sim_v1.py --rebuild",
        }

    xl = pd.ExcelFile(path)
    sheets = xl.sheet_names

    data = pd.read_excel(path, sheet_name="data") if "data" in sheets else pd.DataFrame()
    data_rows = [
        {c: _clean(r[c]) for c in data.columns}
        for _, r in data.iterrows()
    ]

    per_hotel = []
    for name in sheets:
        if not name.startswith("eval_") or name == "eval":
            continue
        code = name.replace("eval_", "", 1)
        df = pd.read_excel(path, sheet_name=name)
        inputs = []
        summary_vals = {}
        for _, r in df.iterrows():
            etape = str(r.get("etape") or "")
            var = str(r.get("variable") or "")
            val = r.get("valeur")
            src = str(r.get("source") or "")
            if etape == "RESUME":
                summary_vals[var] = _clean(val)
                continue
            inputs.append(
                {
                    "etape": etape,
                    "variable": var,
                    "valeur": _clean(val),
                    "source": src,
                }
            )
        # derive fields from resume / inputs
        def _from_inputs(var_name: str):
            for it in inputs:
                if it["variable"] == var_name:
                    return it["valeur"]
            return summary_vals.get(var_name)

        s = {}
        for k in (
            "nb_chambres",
            "taux_occupation",
            "guests_per_chambre",
            "clients_mois",
            "m_lin",
            "mix_fb",
        ):
            # find in inputs hotel evalue
            for it in inputs:
                if it["variable"] == k:
                    s[k] = it["valeur"]
                    break
        for it in inputs:
            if it["variable"] == "taux_conversion_ref":
                s["taux_conversion_ref"] = it["valeur"]
            if it["variable"] == "panier_moyen_ref":
                s["panier_moyen_ref"] = it["valeur"]
            if it["variable"] == "taux_acheteur" and it["etape"].startswith("R1"):
                pass
        # hotel conversion from data row if present
        drow = next((x for x in data_rows if x.get("hotel_code") == code), {})
        s["taux_conversion_hotel"] = drow.get("taux_conversion_acheteur")
        s["panier_moyen_hotel"] = drow.get("panier_moyen_ht")
        s["ca_par_client_hotel"] = drow.get("ca_par_client_heberge")
        if "clients_mois" not in s:
            s["clients_mois"] = drow.get("clients_mois")

        peers_s = str(summary_vals.get("pairs") or "")
        peers = [p.strip() for p in peers_s.split(",") if p.strip()]
        per_hotel.append(
            {
                "hotel_code": code,
                "hotel_name": summary_vals.get("hotel_name") or drow.get("hotel_name") or "",
                "hotel_brand": drow.get("hotel_brand") or "",
                "concept": summary_vals.get("solution") or drow.get("solution") or "",
                "peers": peers,
                "true_ca": summary_vals.get("ca_ht_reel") or _from_inputs("ca_ht_reel"),
                "pred_ca": summary_vals.get("ca_ht_pred") or _from_inputs("ca_ht_pred"),
                "err_ca": summary_vals.get("erreur_abs_ca") or _from_inputs("erreur_abs_ca"),
                "true_marge": summary_vals.get("marge_reel") or _from_inputs("marge_reel"),
                "pred_marge": summary_vals.get("marge_pred") or _from_inputs("marge_pred"),
                "err_marge": summary_vals.get("erreur_abs_marge") or _from_inputs("erreur_abs_marge"),
                "n_mois": drow.get("n_mois"),
                "inputs": inputs,
                "summary": s,
            }
        )

    # stable order from data sheet
    order = {str(r.get("hotel_code")): i for i, r in enumerate(data_rows)}
    per_hotel.sort(key=lambda h: order.get(h["hotel_code"], 999))

    eval_rows = []
    metrics = {"mae_ca_mensuel": None, "mae_marge_mensuel": None, "mape_ca_pct": None, "n_hotels": len(per_hotel)}
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
                sol = code.replace("MAE_", "")
                by_solution[sol] = {
                    "n": _clean(r.get("n_mois")),
                    "mae_ca": _clean(r.get("erreur_abs_ca")),
                    "mae_marge": _clean(r.get("erreur_abs_marge")),
                }
                continue
            eval_rows.append({c: _clean(r[c]) for c in ev.columns})

    if not by_solution:
        for sol in ("SIMPLY", "LIBERTY", "CONNECTED"):
            sub = [h for h in per_hotel if h.get("concept") == sol]
            if not sub:
                continue
            by_solution[sol] = {
                "n": len(sub),
                "mae_ca": round(sum(float(h["err_ca"] or 0) for h in sub) / len(sub), 2),
                "mae_marge": round(sum(float(h["err_marge"] or 0) for h in sub) / len(sub), 2),
            }

    return {
        "ok": True,
        "source": path.name,
        "data": data_rows,
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
            "service": "eval_sim_v1",
            "excel": str(EXCEL_PATH),
            "exists": EXCEL_PATH.exists(),
        }
    )


@app.get("/download")
def download():
    if not EXCEL_PATH.exists():
        return jsonify({"ok": False, "error": "Excel introuvable"}), 404
    return send_file(EXCEL_PATH, as_attachment=True, download_name="eval_sim_v1_loo.xlsx")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluation simulateur ROD v1")
    parser.add_argument("--rebuild", action="store_true", help="Recalcule et reecrit l'Excel")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)

    if args.rebuild or not EXCEL_PATH.exists():
        from accor.eval_sim_v1 import evaluate_loo_sim_v1, metrics_summary, write_eval_excel

        print("Calcul leave-one-out…")
        result = evaluate_loo_sim_v1()
        print(metrics_summary(result))
        out = write_eval_excel(result, EXCEL_PATH)
        print(f"Ecrit : {out}")
        if args.rebuild:
            return 0

    print(f"Evaluation v1 — http://127.0.0.1:{args.port}/")
    print(f"  Excel : {EXCEL_PATH}")
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
