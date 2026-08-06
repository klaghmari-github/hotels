#!/usr/bin/env python3
"""
Page d evaluation leave-one-out des modeles XGBoost (IA).

  python run_eval_ia.py --rebuild [--trials 20]
  python run_eval_ia.py
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

from archive.accor_1_0_6.eval_common import (
    COMMON_CSS,
    EXCEL_IA,
    export_ia_loo_excel,
    load_excel_sheets,
    open_pipeline,
)

DEFAULT_PORT = 5059
app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False

PAGE = r"""
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Evaluation IA XGBoost</title>
  <style>__CSS__</style>
</head>
<body>
  <header>
    <h1>Evaluation IA <span>XGBoost · leave-one-hotel-out</span></h1>
    <div style="display:flex;gap:.6rem;align-items:center">
      <span id="status"></span>
      <a class="link" href="/download">Telecharger Excel</a>
    </div>
  </header>
  <main id="main"><p class="muted">Chargement…</p></main>
  <script>
    const fmt=(n,d=2)=>{if(n==null||n===''||Number.isNaN(Number(n)))return '—';return Number(n).toLocaleString('fr-FR',{maximumFractionDigits:d});};
    const tag=s=>`<span class="tag ${(s||'').toString().toLowerCase()}">${s??''}</span>`;
    function table(cols,rows,nums=[]){
      const N=new Set(nums);
      let h='<div class="scroll"><table><thead><tr>'+cols.map(c=>`<th class="${N.has(c.k)?'num':''}">${c.l}</th>`).join('')+'</tr></thead><tbody>';
      for(const r of rows){
        h+='<tr>'+cols.map(c=>{
          let v=r[c.k];
          if(c.k==='solution'||c.k==='target') v=v==null?'—':(c.k==='solution'?tag(v):v);
          else if(N.has(c.k)) v=fmt(v,c.d??2);
          else if(v==null) v='—';
          return `<td class="${N.has(c.k)?'num':''}">${v}</td>`;
        }).join('')+'</tr>';
      }
      return h+'</tbody></table></div>';
    }
    fetch('/api/results').then(r=>r.json()).then(data=>{
      if(!data.ok){document.getElementById('main').innerHTML=`<div class="errbox">${data.error||'Erreur'}</div>`;return;}
      const cards=(data.metrics||[]).map(m=>`
        <div class="card">
          <div class="lbl">${m.target_label||m.target||''}</div>
          <div class="val">${fmt(m.mae)}</div>
          <div class="sub">MAE · RMSE ${fmt(m.rmse)} · MAPE ${fmt(m.mape,1)} %</div>
        </div>`).join('');
      let html=`<div class="grid">${cards||'<div class="card"><div class="lbl">Pas de metriques</div></div>'}</div>`;
      html+=`<h2>Predictions par hotel</h2>`+table(
        [{k:'hotel_code',l:'Hotel'},{k:'solution',l:'Solution'},
         {k:'montant_ventes_par_mois_reel',l:'CA reel'},{k:'montant_ventes_par_mois_predit',l:'CA predit'},
         {k:'montant_ventes_par_mois_erreur_absolue',l:'|err| CA'},
         {k:'montant_marge_par_mois_reel',l:'Marge reel'},{k:'montant_marge_par_mois_predit',l:'Marge pred'},
         {k:'montant_marge_par_mois_erreur_absolue',l:'|err| marge'},
         {k:'montant_marge_selon_coef_par_mois_reel',l:'Marge coef reel'},
         {k:'montant_marge_selon_coef_par_mois_predit',l:'Marge coef pred'},
         {k:'montant_marge_selon_coef_par_mois_erreur_absolue',l:'|err| marge coef'}],
        data.predictions||[],
        ['montant_ventes_par_mois_reel','montant_ventes_par_mois_predit','montant_ventes_par_mois_erreur_absolue',
         'montant_marge_par_mois_reel','montant_marge_par_mois_predit','montant_marge_par_mois_erreur_absolue',
         'montant_marge_selon_coef_par_mois_reel','montant_marge_selon_coef_par_mois_predit',
         'montant_marge_selon_coef_par_mois_erreur_absolue']
      );
      if((data.vs_sim_v2||[]).length){
        html+=`<h2>Comparaison avec sim_v2 (si disponible)</h2>`+table(
          [{k:'modele',l:'Modele'},{k:'methode',l:'Methode'},{k:'target',l:'Cible'},
           {k:'mae',l:'MAE'},{k:'rmse',l:'RMSE'},{k:'mape',l:'MAPE'},{k:'biais',l:'Biais'}],
          data.vs_sim_v2, ['mae','rmse','mape','biais']
        );
      }
      document.getElementById('main').innerHTML=html;
      document.getElementById('status').textContent=data.source||'';
    }).catch(e=>{document.getElementById('main').innerHTML=`<div class="errbox">${e.message}</div>`;});
  </script>
</body>
</html>
""".replace("__CSS__", COMMON_CSS)


def rebuild_ia_excel(optuna_trials: int = 20, cv_splits: int = 3) -> Path:
    """
    Entraine / evalue le workflow XGBoost en LOO hotel et exporte l Excel UI.

    Le nombre d essais Optuna est volontairement reduit par defaut pour un
    rebuild raisonnable ; le notebook peut utiliser 80 essais.
    """
    from archive.accor_1_0_6.ml_xgboost import MLConfig, XGBoostWorkflow

    cp = open_pipeline(read_only=False)
    try:
        # Le dataset ML depend de t_dataset_pivot deja present.
        config = MLConfig(
            optuna_trials=optuna_trials,
            cv_splits=cv_splits,
        )
        workflow = XGBoostWorkflow(cp=cp, config=config, project_dir=_ROOT)
        result = workflow.run()
        return export_ia_loo_excel(
            result["loo_predictions"],
            result["loo_metrics"],
            result.get("model_comparison"),
            EXCEL_IA,
        )
    finally:
        cp.close()


def payload_from_excel() -> dict:
    sheets = load_excel_sheets(EXCEL_IA)
    if not sheets:
        return {
            "ok": False,
            "error": "Fichier eval_ia_loo.xlsx introuvable. Lancer : python run_eval_ia.py --rebuild",
        }

    def clean(df: pd.DataFrame) -> list:
        if df is None or df.empty:
            return []
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
        "source": EXCEL_IA.name,
        "predictions": clean(sheets.get("predictions", pd.DataFrame())),
        "metrics": clean(sheets.get("metrics", pd.DataFrame())),
        "vs_sim_v2": clean(sheets.get("vs_sim_v2", pd.DataFrame())),
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
    if not EXCEL_IA.exists():
        return jsonify({"ok": False, "error": "Excel introuvable"}), 404
    return send_file(EXCEL_IA, as_attachment=True, download_name=EXCEL_IA.name)


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "service": "eval_ia", "excel": str(EXCEL_IA), "exists": EXCEL_IA.exists()})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluation LOO IA XGBoost")
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--trials", type=int, default=20, help="Essais Optuna par cible")
    parser.add_argument("--cv-splits", type=int, default=3)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)

    if args.rebuild or not EXCEL_IA.exists():
        print(f"Recalcul LOO IA (trials={args.trials})…")
        path = rebuild_ia_excel(args.trials, args.cv_splits)
        print(f"Excel ecrit : {path}")
        if args.rebuild:
            return 0

    print(f"Evaluation IA — http://127.0.0.1:{args.port}/")
    app.run(host=args.host, port=args.port, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
