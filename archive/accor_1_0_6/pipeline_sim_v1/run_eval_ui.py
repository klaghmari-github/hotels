#!/usr/bin/env python3
"""
UI Flask : comparaison LOO sim_v1 old vs new (6 hotels).

  python pipeline_sim_v1/run_eval_ui.py
  python pipeline_sim_v1/run_eval_ui.py --rebuild --port 5062
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
from flask import Flask, jsonify, render_template_string, send_file

DEFAULT_PORT = 5062

try:
    from archive.accor_1_0_6.eval_common import COMMON_CSS
except Exception:
    COMMON_CSS = """
:root {
  --bg: #0f1419; --card: #1a2332; --line: #2a3a4f;
  --text: #e7eef7; --muted: #8b9bb0; --accent: #3d8bfd;
  --ok: #3dd68c; --warn: #f5a524;
}
* { box-sizing: border-box; }
body {
  margin: 0; font-family: "Segoe UI", system-ui, sans-serif;
  background: var(--bg); color: var(--text); line-height: 1.45;
}
"""

from archive.accor_1_0_6.pipeline_sim_v1.constants import (
    EVAL_CODES,
    EXCEL_COMPARE,
    EXCEL_NEW,
    EXCEL_OLD,
    EXCLUDED_HOTELS,
)

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False

PAGE = r"""
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>sim_v1 LOO old vs new</title>
  <style>
    __COMMON_CSS__
    header {
      padding: 1rem 1.25rem; border-bottom: 1px solid var(--line);
      display: flex; flex-wrap: wrap; gap: .75rem; align-items: center;
      justify-content: space-between;
    }
    h1 { font-size: 1.1rem; margin: 0; font-weight: 600; }
    h1 span { color: var(--muted); font-weight: 400; font-size: .85rem; margin-left: .4rem; }
    a.link, button.btn {
      color: var(--text); border: 1px solid var(--line); border-radius: 8px;
      padding: .4rem .85rem; text-decoration: none; font-size: .85rem; font-weight: 600;
      background: transparent; cursor: pointer;
    }
    a.link:hover, button.btn:hover { border-color: var(--accent); color: var(--accent); }
    button.btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
    main { padding: 1.1rem 1.25rem 2.5rem; max-width: 1280px; margin: 0 auto; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: .7rem; }
    .card {
      background: var(--card); border: 1px solid var(--line); border-radius: 12px;
      padding: .9rem 1rem;
    }
    .card .lbl { color: var(--muted); font-size: .72rem; text-transform: uppercase; letter-spacing: .03em; }
    .card .val { font-size: 1.2rem; font-weight: 700; margin-top: .2rem; }
    .card .sub { color: var(--muted); font-size: .78rem; margin-top: .15rem; }
    h2 { font-size: 1rem; margin: 1.1rem 0 .5rem; font-weight: 600; }
    table {
      width: 100%; border-collapse: collapse; font-size: .82rem;
      background: var(--card); border: 1px solid var(--line); border-radius: 10px; overflow: hidden;
    }
    th, td { text-align: left; padding: .5rem .55rem; border-bottom: 1px solid var(--line); }
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
    .muted { color: var(--muted); font-size: .85rem; }
    .errbox {
      margin: 1rem 0; padding: .8rem 1rem; border: 1px solid #5a2a35;
      background: #2a1520; border-radius: 8px; color: #f5a0b0;
    }
    .scroll { overflow: auto; max-width: 100%; }
    #status { color: var(--muted); font-size: .82rem; }
    .pos { color: var(--warn); }
    .neg { color: var(--ok); }
  </style>
</head>
<body>
  <header>
    <h1>sim_v1 LOO <span>old (RevenueRules) · new (R1–R4)</span></h1>
    <div style="display:flex;gap:.6rem;align-items:center;flex-wrap:wrap">
      <span id="status"></span>
      <button class="btn primary" id="rebuild">Recalculer</button>
      <a class="link" href="/download/compare">Excel comparatif</a>
    </div>
  </header>
  <main>
    <p class="muted">Hotels : __HOTELS__ · exclus : __EXCL__</p>
    <div id="err" class="errbox" style="display:none"></div>
    <div class="grid" id="cards"></div>
    <h2>Metriques (MAE)</h2>
    <div class="scroll"><table id="t-metrics"><thead></thead><tbody></tbody></table></div>
    <h2>Predictions par hotel</h2>
    <div class="scroll"><table id="t-pred"><thead></thead><tbody></tbody></table></div>
  </main>
  <script>
    const fmt = (v, d=2) => {
      if (v === null || v === undefined || Number.isNaN(v)) return '—';
      return Number(v).toLocaleString('fr-FR', {maximumFractionDigits:d, minimumFractionDigits:d});
    };
    const solClass = s => (s||'').toLowerCase();
    function fillTable(table, cols, rows, numCols=new Set()) {
      const th = table.querySelector('thead');
      const tb = table.querySelector('tbody');
      th.innerHTML = '<tr>' + cols.map(c => `<th>${c.label}</th>`).join('') + '</tr>';
      tb.innerHTML = rows.map(r => {
        return '<tr>' + cols.map(c => {
          let v = r[c.key];
          if (c.key === 'solution') {
            return `<td><span class="tag ${solClass(v)}">${v||'—'}</span></td>`;
          }
          if (numCols.has(c.key) || c.num) {
            const n = Number(v);
            let cls = 'num';
            if (c.delta && !Number.isNaN(n)) cls += n > 0 ? ' pos' : (n < 0 ? ' neg' : '');
            return `<td class="${cls}">${fmt(v, c.digits ?? 2)}</td>`;
          }
          return `<td>${v ?? '—'}</td>`;
        }).join('') + '</tr>';
      }).join('');
    }
    async function load() {
      const st = document.getElementById('status');
      const err = document.getElementById('err');
      st.textContent = 'Chargement…';
      err.style.display = 'none';
      try {
        const res = await fetch('/api/summary');
        const data = await res.json();
        if (!data.ok) throw new Error(data.error || 'Erreur API');
        const g = (data.metrics || []).find(m => m.scope === 'GLOBAL') || {};
        document.getElementById('cards').innerHTML = `
          <div class="card"><div class="lbl">MAE CA old</div><div class="val">${fmt(g.mae_ca_old)}</div><div class="sub">EUR / mois</div></div>
          <div class="card"><div class="lbl">MAE CA new</div><div class="val">${fmt(g.mae_ca_new)}</div><div class="sub">EUR / mois</div></div>
          <div class="card"><div class="lbl">Δ MAE CA</div><div class="val">${fmt(g.delta_mae_ca)}</div><div class="sub">new − old</div></div>
          <div class="card"><div class="lbl">MAE marge old</div><div class="val">${fmt(g.mae_marge_old)}</div></div>
          <div class="card"><div class="lbl">MAE marge new</div><div class="val">${fmt(g.mae_marge_new)}</div></div>
          <div class="card"><div class="lbl">Hotels</div><div class="val">${data.n_hotels ?? '—'}</div><div class="sub">leave-one-out</div></div>
        `;
        fillTable(document.getElementById('t-metrics'), [
          {key:'scope', label:'Scope'},
          {key:'mae_ca_old', label:'MAE CA old', num:true},
          {key:'mae_ca_new', label:'MAE CA new', num:true},
          {key:'delta_mae_ca', label:'Δ CA', num:true, delta:true},
          {key:'mae_marge_old', label:'MAE marge old', num:true},
          {key:'mae_marge_new', label:'MAE marge new', num:true},
          {key:'delta_mae_marge', label:'Δ marge', num:true, delta:true},
        ], data.metrics || []);
        fillTable(document.getElementById('t-pred'), [
          {key:'hotel_code', label:'Hotel'},
          {key:'solution', label:'Solution'},
          {key:'ca_reel', label:'CA reel', num:true},
          {key:'ca_pred_old', label:'CA pred old', num:true},
          {key:'ca_pred_new', label:'CA pred new', num:true},
          {key:'ca_err_old', label:'|err| old', num:true},
          {key:'ca_err_new', label:'|err| new', num:true},
          {key:'delta_ca_err', label:'Δ |err|', num:true, delta:true},
          {key:'marge_err_old', label:'|err m| old', num:true},
          {key:'marge_err_new', label:'|err m| new', num:true},
        ], data.predictions || []);
        st.textContent = data.updated_at ? `Maj ${data.updated_at}` : 'OK';
      } catch (e) {
        err.style.display = 'block';
        err.textContent = e.message || String(e);
        st.textContent = 'Erreur';
      }
    }
    document.getElementById('rebuild').onclick = async () => {
      const st = document.getElementById('status');
      st.textContent = 'Recalcul LOO…';
      try {
        const res = await fetch('/api/rebuild', {method:'POST'});
        const data = await res.json();
        if (!data.ok) throw new Error(data.error || 'Echec rebuild');
        await load();
      } catch (e) {
        document.getElementById('err').style.display = 'block';
        document.getElementById('err').textContent = e.message || String(e);
        st.textContent = 'Erreur';
      }
    };
    load();
  </script>
</body>
</html>
""".replace("__COMMON_CSS__", COMMON_CSS).replace(
    "__HOTELS__", ", ".join(EVAL_CODES)
).replace("__EXCL__", ", ".join(sorted(EXCLUDED_HOTELS)))


def _summary_payload() -> dict:
    from datetime import datetime

    if not EXCEL_COMPARE.exists():
        return {
            "ok": False,
            "error": "Fichier comparatif absent. Cliquez Recalculer ou lancez run_all.py",
        }
    metrics = pd.read_excel(EXCEL_COMPARE, sheet_name="metrics_side_by_side")
    pred = pd.read_excel(EXCEL_COMPARE, sheet_name="predictions_merged")
    mtime = datetime.fromtimestamp(EXCEL_COMPARE.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    return {
        "ok": True,
        "n_hotels": int(len(pred)),
        "updated_at": mtime,
        "metrics": metrics.where(pd.notna(metrics), None).to_dict(orient="records"),
        "predictions": pred.where(pd.notna(pred), None).to_dict(orient="records"),
    }


@app.get("/")
def index():
    return render_template_string(PAGE)


@app.get("/api/summary")
def api_summary():
    return jsonify(_summary_payload())


@app.post("/api/rebuild")
def api_rebuild():
    try:
        from archive.accor_1_0_6.pipeline_sim_v1.compare import run as run_compare

        run_compare(rerun=True)
        return jsonify({"ok": True, **_summary_payload()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.get("/download/compare")
def download_compare():
    if not EXCEL_COMPARE.exists():
        return jsonify({"ok": False, "error": "absent"}), 404
    return send_file(
        EXCEL_COMPARE,
        as_attachment=True,
        download_name="eval_sim_v1_old_vs_new.xlsx",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="UI LOO sim_v1 old vs new")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--rebuild", action="store_true", help="Recalcule avant demarrage")
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    if args.rebuild or not EXCEL_COMPARE.exists():
        print("Recalcul LOO old + new…")
        from archive.accor_1_0_6.pipeline_sim_v1.compare import run as run_compare

        r = run_compare(rerun=True)
        print(r["metrics_side_by_side"].to_string(index=False))
        print(f"→ {r['excel_path']}")

    print(f"UI sim_v1 LOO — http://{args.host}:{args.port}/")
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
