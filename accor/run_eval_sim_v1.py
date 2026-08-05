#!/usr/bin/env python3
"""
Évaluation leave-one-out du simulateur ROD v1 (règles Excel).

  python run_eval_sim_v1.py              # serveur web :5057
  python run_eval_sim_v1.py --cli        # sortie JSON + résumé terminal
  python run_eval_sim_v1.py --port 5057

Ne remplace pas run_admin / run_user / run_dev — page d'évaluation dédiée.
Moteur : accor.eval_sim_v1 (sans mutation des données ni du simu production).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# racine projet dans le path si lancé hors install
_ROOT = Path(__file__).resolve().parent
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from flask import Flask, jsonify, render_template_string, request

from accor.eval_sim_v1 import evaluate_loo_sim_v1, metrics_summary

DEFAULT_PORT = 5057

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False

# cache en mémoire du dernier run (évite de relire Excel à chaque refresh UI)
_CACHE: dict = {}


PAGE_HTML = r"""
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Éval Simulateur v1 — Leave-One-Out</title>
  <style>
    :root {
      --bg: #0f1419; --card: #1a2332; --line: #2a3a4f;
      --text: #e7eef7; --muted: #8b9bb0; --accent: #3d8bfd;
      --ok: #3dd68c; --warn: #f5a524; --bad: #f31260;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0; font-family: "Segoe UI", system-ui, sans-serif;
      background: var(--bg); color: var(--text); line-height: 1.45;
    }
    header {
      padding: 1.25rem 1.5rem; border-bottom: 1px solid var(--line);
      display: flex; flex-wrap: wrap; gap: 1rem; align-items: center;
      justify-content: space-between;
    }
    h1 { font-size: 1.15rem; margin: 0; font-weight: 600; }
    h1 span { color: var(--muted); font-weight: 400; font-size: .9rem; }
    .btn {
      background: var(--accent); color: #fff; border: 0; border-radius: 8px;
      padding: .55rem 1rem; font-weight: 600; cursor: pointer; font-size: .9rem;
    }
    .btn:disabled { opacity: .5; cursor: wait; }
    .btn.secondary { background: transparent; border: 1px solid var(--line); color: var(--text); }
    main { padding: 1.25rem 1.5rem 3rem; max-width: 1200px; margin: 0 auto; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: .75rem; }
    .card {
      background: var(--card); border: 1px solid var(--line); border-radius: 12px;
      padding: 1rem 1.1rem;
    }
    .card .lbl { color: var(--muted); font-size: .75rem; text-transform: uppercase; letter-spacing: .04em; }
    .card .val { font-size: 1.45rem; font-weight: 700; margin-top: .25rem; }
    .card .sub { color: var(--muted); font-size: .8rem; margin-top: .2rem; }
    p.desc { color: var(--muted); font-size: .9rem; max-width: 70ch; }
    table {
      width: 100%; border-collapse: collapse; font-size: .85rem; margin-top: 1rem;
    }
    th, td { text-align: left; padding: .55rem .6rem; border-bottom: 1px solid var(--line); }
    th { color: var(--muted); font-weight: 600; font-size: .75rem; text-transform: uppercase; }
    tr:hover td { background: rgba(61,139,253,.06); }
    .num { font-variant-numeric: tabular-nums; text-align: right; }
    .tag {
      display: inline-block; padding: .1rem .45rem; border-radius: 999px;
      font-size: .7rem; font-weight: 600; background: #243044; color: var(--muted);
    }
    .tag.simply { color: #7dd3fc; } .tag.liberty { color: #c4b5fd; } .tag.connected { color: #86efac; }
    .err { color: var(--bad); }
    #status { color: var(--muted); font-size: .85rem; }
    details { margin-top: 1.5rem; }
    summary { cursor: pointer; color: var(--accent); font-weight: 600; }
    pre {
      background: #0a0e14; border: 1px solid var(--line); border-radius: 8px;
      padding: 1rem; overflow: auto; font-size: .75rem; color: #c9d4e3;
    }
  </style>
</head>
<body>
  <header>
    <h1>Éval Simulateur v1 <span>leave-one-out · règles Excel ROD</span></h1>
    <div style="display:flex;gap:.5rem;align-items:center">
      <span id="status">Prêt</span>
      <button class="btn secondary" id="btnJson" type="button">JSON</button>
      <button class="btn" id="btnRun" type="button">Lancer l'évaluation</button>
    </div>
  </header>
  <main>
    <p class="desc">
      Toutes les données de ventes (toutes années) → moyenne mensuelle par hôtel.
      Pour chaque pilote on <strong>exclut</strong> l'hôtel, on reconstruit la référence
      solution avec les pairs restants, puis on projette CA HT et marge produit via
      les règles Excel (R1→R4). Métrique : <strong>MAE</strong> moyenne sur les hôtels.
      L'existant admin/user n'est pas modifié.
    </p>
    <div class="grid" id="kpis">
      <div class="card"><div class="lbl">MAE CA mensuel</div><div class="val" id="maeCa">—</div><div class="sub">€ / mois</div></div>
      <div class="card"><div class="lbl">MAE marge mensuel</div><div class="val" id="maeMarge">—</div><div class="sub">€ / mois</div></div>
      <div class="card"><div class="lbl">MAPE CA</div><div class="val" id="mapeCa">—</div><div class="sub">%</div></div>
      <div class="card"><div class="lbl">Hôtels</div><div class="val" id="nHotels">—</div><div class="sub" id="yearsLbl">années —</div></div>
    </div>

    <div class="card" style="margin-top:1rem">
      <div class="lbl">MAE par solution</div>
      <div id="bySol" style="margin-top:.6rem;display:flex;flex-wrap:wrap;gap:.75rem"></div>
    </div>

    <div class="card" style="margin-top:1rem;overflow:auto">
      <div class="lbl">Détail leave-one-out</div>
      <table>
        <thead>
          <tr>
            <th>Hôtel</th><th>Solution</th><th>Pairs</th>
            <th class="num">Vrai CA</th><th class="num">Pred CA</th><th class="num">|err| CA</th>
            <th class="num">Vrai marge</th><th class="num">Pred marge</th><th class="num">|err| marge</th>
            <th class="num">n mois</th>
          </tr>
        </thead>
        <tbody id="tbody"></tbody>
      </table>
    </div>

    <details>
      <summary>Réponse JSON complète</summary>
      <pre id="raw">{}</pre>
    </details>
  </main>
  <script>
    const € = n => n == null || Number.isNaN(n) ? '—' : Number(n).toLocaleString('fr-FR', {maximumFractionDigits: 2});
    const tagClass = c => (c || '').toLowerCase();

    function render(data) {
      const m = data.metrics || {};
      document.getElementById('maeCa').textContent = €(m.mae_ca_mensuel);
      document.getElementById('maeMarge').textContent = €(m.mae_marge_mensuel);
      document.getElementById('mapeCa').textContent = m.mape_ca_pct != null ? m.mape_ca_pct + ' %' : '—';
      document.getElementById('nHotels').textContent = data.n_hotels ?? '—';
      document.getElementById('yearsLbl').textContent = 'années ' + ((data.years_all || []).join(', ') || '—');

      const by = data.by_solution || {};
      document.getElementById('bySol').innerHTML = Object.keys(by).map(sol => {
        const v = by[sol];
        return `<div style="min-width:140px">
          <span class="tag ${tagClass(sol)}">${sol}</span>
          <div style="margin-top:.35rem;font-size:.9rem">
            n=${v.n}<br/>
            MAE CA <strong>${€(v.mae_ca_mensuel)}</strong><br/>
            MAE marge <strong>${€(v.mae_marge_mensuel)}</strong>
          </div>
        </div>`;
      }).join('');

      const tb = document.getElementById('tbody');
      tb.innerHTML = (data.hotels || []).map(r => {
        if (r.error) {
          return `<tr><td>${r.hotel_code}</td><td colspan="9" class="err">${r.error}</td></tr>`;
        }
        const t = r.true || {}, p = r.pred || {}, e = r.abs_error || {};
        return `<tr>
          <td><strong>${r.hotel_code}</strong><br/><span style="color:var(--muted);font-size:.75rem">${r.hotel_name || ''}</span></td>
          <td><span class="tag ${tagClass(r.concept)}">${r.concept || ''}</span></td>
          <td style="font-size:.75rem;color:var(--muted)">${(r.peers || []).join(', ') || '—'}</td>
          <td class="num">${€(t.ca_mensuel)}</td>
          <td class="num">${€(p.ca_mensuel)}</td>
          <td class="num"><strong>${€(e.ca)}</strong></td>
          <td class="num">${€(t.marge_mensuel)}</td>
          <td class="num">${€(p.marge_mensuel)}</td>
          <td class="num"><strong>${€(e.marge)}</strong></td>
          <td class="num">${r.n_mois ?? '—'}</td>
        </tr>`;
      }).join('');

      document.getElementById('raw').textContent = JSON.stringify(data, null, 2);
    }

    async function run(force) {
      const btn = document.getElementById('btnRun');
      const st = document.getElementById('status');
      btn.disabled = true; st.textContent = 'Calcul en cours…';
      try {
        const url = force ? '/api/eval?refresh=1' : '/api/eval';
        const res = await fetch(url);
        const data = await res.json();
        if (!data.ok) throw new Error(data.error || 'échec');
        window.__last = data;
        render(data);
        st.textContent = 'OK — ' + new Date().toLocaleTimeString('fr-FR');
      } catch (e) {
        st.textContent = 'Erreur : ' + e.message;
      } finally {
        btn.disabled = false;
      }
    }

    document.getElementById('btnRun').onclick = () => run(true);
    document.getElementById('btnJson').onclick = () => {
      const w = window.open('', '_blank');
      w.document.write('<pre>' + JSON.stringify(window.__last || {}, null, 2) + '</pre>');
    };
    run(false);
  </script>
</body>
</html>
"""


def _run_eval(force: bool = False) -> dict:
    global _CACHE
    if _CACHE and not force:
        return _CACHE
    result = evaluate_loo_sim_v1()
    _CACHE = result
    return result


@app.get("/")
def index():
    return render_template_string(PAGE_HTML)


@app.get("/api/eval")
def api_eval():
    force = request.args.get("refresh") in ("1", "true", "yes")
    try:
        return jsonify(_run_eval(force=force))
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "service": "eval_sim_v1", "port": DEFAULT_PORT})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Éval leave-one-out simulateur ROD v1")
    parser.add_argument("--cli", action="store_true", help="Exécute l'éval et imprime le résumé")
    parser.add_argument("--json", action="store_true", help="Avec --cli : dump JSON complet")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)

    if args.cli:
        result = evaluate_loo_sim_v1()
        print(metrics_summary(result))
        print()
        for h in result.get("hotels") or []:
            if h.get("error"):
                print(f"  {h['hotel_code']}: ERROR {h['error']}")
                continue
            t, p, e = h.get("true") or {}, h.get("pred") or {}, h.get("abs_error") or {}
            print(
                f"  {h['hotel_code']:6s} [{h.get('concept')}] "
                f"CA vrai={t.get('ca_mensuel')} pred={p.get('ca_mensuel')} |err|={e.get('ca')}  "
                f"marge vrai={t.get('marge_mensuel')} pred={p.get('marge_mensuel')} |err|={e.get('marge')}"
            )
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        out = _ROOT / "data" / "eval_sim_v1_loo.json"
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n→ {out}")
        return 0 if result.get("ok") else 1

    print(f"Éval sim v1 — http://127.0.0.1:{args.port}/")
    print("  GET /api/eval  ·  GET /api/eval?refresh=1")
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
