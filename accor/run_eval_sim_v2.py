#!/usr/bin/env python3
"""
Page d evaluation leave-one-out du simulateur v2 (restitution A/B).

  python run_eval_sim_v2.py --rebuild   # recalcule LOO + Excel
  python run_eval_sim_v2.py             # affiche data/eval_sim_v2_loo.xlsx
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

from eval_common import (
    COMMON_CSS,
    EXCEL_V2,
    export_v2_loo_excel,
    load_excel_sheets,
    open_pipeline,
)

DEFAULT_PORT = 5058
app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False

PAGE = r"""
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Evaluation simulateur v2</title>
  <style>__CSS__</style>
</head>
<body>
  <header>
    <h1>Evaluation simulateur v2 <span>leave-one-out · restitution A/B</span></h1>
    <div style="display:flex;gap:.6rem;align-items:center">
      <span id="status"></span>
      <a class="link" href="/download">Telecharger Excel</a>
    </div>
  </header>
  <main id="main"><p class="muted">Chargement…</p></main>
  <script>
    const fmt = (n,d=2)=>{
      if(n===null||n===undefined||n===''||Number.isNaN(Number(n))) return '—';
      return Number(n).toLocaleString('fr-FR',{maximumFractionDigits:d});
    };
    const tag = s => `<span class="tag ${(s||'').toString().toLowerCase()}">${s??''}</span>`;
    function table(cols, rows, nums=[]) {
      const N=new Set(nums);
      let h='<div class="scroll"><table><thead><tr>'+cols.map(c=>`<th class="${N.has(c.k)?'num':''}">${c.l}</th>`).join('')+'</tr></thead><tbody>';
      for(const r of rows){
        h+='<tr>'+cols.map(c=>{
          let v=r[c.k];
          if(c.k==='methode'||c.k==='solution') v=tag(v);
          else if(N.has(c.k)) v=fmt(v,c.d??2);
          else if(v==null) v='—';
          return `<td class="${N.has(c.k)?'num':''}">${v}</td>`;
        }).join('')+'</tr>';
      }
      return h+'</tbody></table></div>';
    }
    fetch('/api/results').then(r=>r.json()).then(data=>{
      if(!data.ok){ document.getElementById('main').innerHTML=`<div class="errbox">${data.error||'Erreur'}</div>`; return; }
      const m=data.metrics_global||[];
      const cards=m.map(x=>`
        <div class="card">
          <div class="lbl">Methode ${x.methode||''}</div>
          <div class="sub">hotels : ${x.nombre_hotels??'—'}</div>
          <div style="margin-top:.4rem">MAE CA <strong>${fmt(x.montant_ventes_mae)}</strong></div>
          <div>MAE marge marche <strong>${fmt(x.marge_mae)}</strong></div>
          <div>MAE marge coef <strong>${fmt(x.marge_selon_coef_mae)}</strong></div>
        </div>`).join('');
      let html=`<div class="grid">${cards||'<div class="card"><div class="lbl">Pas de metriques</div></div>'}</div>`;
      if((data.method_comparison||[]).length){
        html+=`<h2>Classement des methodes</h2>`+table(
          [{k:'methode',l:'Methode'},{k:'montant_ventes_mae',l:'MAE CA'},{k:'marge_selon_coef_mae',l:'MAE marge coef'},
           {k:'marge_mae',l:'MAE marge marche'},{k:'rang_ca',l:'Rang CA'},{k:'rang_marge',l:'Rang marge'}],
          data.method_comparison,
          ['montant_ventes_mae','marge_selon_coef_mae','marge_mae','rang_ca','rang_marge']
        );
      }
      html+=`<h2>Detail par hotel</h2>`+table(
        [{k:'hotel_code',l:'Hotel'},{k:'solution',l:'Solution'},{k:'methode',l:'Methode'},
         {k:'montant_ventes_par_mois_reel',l:'CA reel'},{k:'montant_ventes_par_mois_predit',l:'CA predit'},
         {k:'montant_ventes_erreur_absolue',l:'|err| CA'},
         {k:'montant_marge_par_mois_reel',l:'Marge reel'},{k:'montant_marge_par_mois_predite',l:'Marge pred'},
         {k:'montant_marge_erreur_absolue',l:'|err| marge'},
         {k:'montant_marge_selon_coef_par_mois_reel',l:'Marge coef reel'},
         {k:'montant_marge_selon_coef_par_mois_predite',l:'Marge coef pred'},
         {k:'montant_marge_selon_coef_erreur_absolue',l:'|err| marge coef'}],
        data.predictions||[],
        ['montant_ventes_par_mois_reel','montant_ventes_par_mois_predit','montant_ventes_erreur_absolue',
         'montant_marge_par_mois_reel','montant_marge_par_mois_predite','montant_marge_erreur_absolue',
         'montant_marge_selon_coef_par_mois_reel','montant_marge_selon_coef_par_mois_predite',
         'montant_marge_selon_coef_erreur_absolue']
      );
      if((data.metrics_by_solution||[]).length){
        html+=`<h2>Metriques par solution</h2>`+table(
          [{k:'methode',l:'Methode'},{k:'solution',l:'Solution'},{k:'nombre_hotels',l:'n'},
           {k:'montant_ventes_mae',l:'MAE CA'},{k:'marge_mae',l:'MAE marge'},{k:'marge_selon_coef_mae',l:'MAE marge coef'}],
          data.metrics_by_solution,
          ['nombre_hotels','montant_ventes_mae','marge_mae','marge_selon_coef_mae']
        );
      }
      document.getElementById('main').innerHTML=html;
      document.getElementById('status').textContent=data.source||'';
    }).catch(e=>{
      document.getElementById('main').innerHTML=`<div class="errbox">${e.message}</div>`;
    });
  </script>
</body>
</html>
""".replace("__CSS__", COMMON_CSS)


def rebuild_v2_excel() -> Path:
    """Recalcule le LOO restitution v2 et exporte l Excel."""
    from main import run_leave_one_out

    cp = open_pipeline(read_only=False)
    try:
        loo = run_leave_one_out(cp, rebuild=True)
        return export_v2_loo_excel(
            loo["results"],
            loo["metrics"],
            loo["method_comparison"],
            EXCEL_V2,
        )
    finally:
        cp.close()


def payload_from_excel() -> dict:
    sheets = load_excel_sheets(EXCEL_V2)
    if not sheets:
        return {
            "ok": False,
            "error": "Fichier eval_sim_v2_loo.xlsx introuvable. Lancer : python run_eval_sim_v2.py --rebuild",
        }

    metrics = sheets.get("metrics", pd.DataFrame())
    metrics_global = []
    metrics_by_solution = []
    if not metrics.empty:
        if "solution" in metrics.columns:
            metrics_global = metrics[metrics["solution"].isna()].to_dict(orient="records")
            metrics_by_solution = metrics[metrics["solution"].notna()].to_dict(orient="records")
            if not metrics_global:
                metrics_global = metrics.to_dict(orient="records")
        else:
            metrics_global = metrics.to_dict(orient="records")

    preds = sheets.get("predictions", pd.DataFrame())
    comp = sheets.get("method_comparison", pd.DataFrame())

    def clean_records(df: pd.DataFrame) -> list:
        if df is None or df.empty:
            return []
        # to_dict + where(None) laisse des NaN float ; on nettoie cellule par cellule.
        records = []
        for rec in df.to_dict(orient="records"):
            cleaned = {}
            for key, value in rec.items():
                if value is None or (isinstance(value, float) and pd.isna(value)):
                    cleaned[key] = None
                else:
                    cleaned[key] = value
            records.append(cleaned)
        return records

    return {
        "ok": True,
        "source": EXCEL_V2.name,
        "predictions": clean_records(preds),
        "metrics_global": clean_records(pd.DataFrame(metrics_global)) if metrics_global else clean_records(metrics),
        "metrics_by_solution": clean_records(pd.DataFrame(metrics_by_solution)),
        "method_comparison": clean_records(comp),
    }


@app.get("/")
def index():
    return render_template_string(PAGE)


@app.get("/api/results")
def api_results():
    try:
        return jsonify(payload_from_excel())
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.get("/download")
def download():
    if not EXCEL_V2.exists():
        return jsonify({"ok": False, "error": "Excel introuvable"}), 404
    return send_file(EXCEL_V2, as_attachment=True, download_name=EXCEL_V2.name)


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "service": "eval_sim_v2", "excel": str(EXCEL_V2), "exists": EXCEL_V2.exists()})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluation LOO simulateur v2")
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)

    if args.rebuild or not EXCEL_V2.exists():
        print("Recalcul LOO sim_v2…")
        path = rebuild_v2_excel()
        print(f"Excel ecrit : {path}")
        if args.rebuild:
            return 0

    print(f"Evaluation v2 — http://127.0.0.1:{args.port}/")
    app.run(host=args.host, port=args.port, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
