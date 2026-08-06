#!/usr/bin/env python3
"""
Page de comparaison leave-one-out : sim_v1 · sim_v2 · IA.

  python run_eval_compare.py --rebuild
  python run_eval_compare.py
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
    EXCEL_COMPARE,
    EXCEL_DENSE,
    EXCEL_IA,
    EXCEL_V1,
    EXCEL_V2,
    build_compare_excel,
    load_excel_sheets,
)

DEFAULT_PORT = 5060
app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False

PAGE = r"""
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Comparaison evaluations LOO</title>
  <style>__CSS__</style>
</head>
<body>
  <header>
    <h1>Comparaison LOO <span>sim_v1 · sim_v2 · XGBoost · dense</span></h1>
    <div style="display:flex;gap:.6rem;align-items:center;flex-wrap:wrap">
      <span id="status"></span>
      <a class="link" href="/download">Telecharger Excel</a>
      <a class="link" href="http://127.0.0.1:5057/" target="_blank">Eval v1</a>
      <a class="link" href="http://127.0.0.1:5058/" target="_blank">Eval v2</a>
      <a class="link" href="http://127.0.0.1:5059/" target="_blank">Eval XGBoost</a>
      <a class="link" href="http://127.0.0.1:5063/" target="_blank">Eval dense</a>
      <a class="link" href="http://127.0.0.1:5061/" target="_blank">Prediction</a>
    </div>
  </header>
  <main id="main"><p class="muted">Chargement…</p></main>
  <script>
    const fmt=(n,d=2)=>{if(n==null||n===''||Number.isNaN(Number(n)))return '—';return Number(n).toLocaleString('fr-FR',{maximumFractionDigits:d});};
    const tag=s=>`<span class="tag ${(s||'').toString().toLowerCase().replace(/[^a-z0-9_]/g,'')}">${s??''}</span>`;
    function table(cols,rows,nums=[]){
      const N=new Set(nums);
      let h='<div class="scroll"><table><thead><tr>'+cols.map(c=>`<th class="${N.has(c.k)?'num':''}">${c.l}</th>`).join('')+'</tr></thead><tbody>';
      for(const r of rows){
        h+='<tr>'+cols.map(c=>{
          let v=r[c.k];
          if(c.k==='modele'||c.k==='methode') v=tag(v);
          else if(N.has(c.k)) v=fmt(v,c.d??2);
          else if(v==null) v='—';
          return `<td class="${N.has(c.k)?'num':''}">${v}</td>`;
        }).join('')+'</tr>';
      }
      return h+'</tbody></table></div>';
    }
    fetch('/api/results').then(r=>r.json()).then(data=>{
      if(!data.ok){document.getElementById('main').innerHTML=`<div class="errbox">${data.error||'Erreur'}</div>`;return;}
      const byTarget={};
      for(const r of (data.metrics||[])){
        const t=r.cible||r.target||'autre';
        (byTarget[t]=byTarget[t]||[]).push(r);
      }
      let html='';
      for(const [target,rows] of Object.entries(byTarget)){
        const best=rows.filter(x=>x.mae!=null).sort((a,b)=>a.mae-b.mae)[0];
        html+=`<h2>${target}</h2>`;
        if(best) html+=`<p class="muted">Meilleure MAE : ${tag(best.modele)} / ${tag(best.methode)} = <strong>${fmt(best.mae)}</strong></p>`;
        html+=table(
          [{k:'modele',l:'Modele'},{k:'methode',l:'Methode'},{k:'mae',l:'MAE'},{k:'rmse',l:'RMSE'},{k:'mape',l:'MAPE'},{k:'biais',l:'Biais'}],
          rows, ['mae','rmse','mape','biais']
        );
      }
      html+=`<h2>Fichiers sources</h2>
        <div class="grid">
          <div class="card"><div class="lbl">sim_v1</div><div class="val" style="font-size:1rem">${data.sources.v1?'present':'absent'}</div><div class="sub">data/eval_sim_v1_loo.xlsx</div></div>
          <div class="card"><div class="lbl">sim_v2</div><div class="val" style="font-size:1rem">${data.sources.v2?'present':'absent'}</div><div class="sub">data/eval_sim_v2_loo.xlsx</div></div>
          <div class="card"><div class="lbl">XGBoost</div><div class="val" style="font-size:1rem">${data.sources.ia?'present':'absent'}</div><div class="sub">data/eval_ia_loo.xlsx</div></div>
          <div class="card"><div class="lbl">dense</div><div class="val" style="font-size:1rem">${data.sources.dense?'present':'absent'}</div><div class="sub">data/eval_dense_loo.xlsx</div></div>
        </div>
        <p class="muted" style="margin-top:.8rem">MAE = erreur absolue moyenne leave-one-out. MAPE ML en % ; MAPE restitution v2 en ratio (×100 pour %).</p>`;
      document.getElementById('main').innerHTML=html||'<div class="errbox">Aucune metrique disponible. Reconstruire les evals.</div>';
      document.getElementById('status').textContent=data.source||'';
    }).catch(e=>{document.getElementById('main').innerHTML=`<div class="errbox">${e.message}</div>`;});
  </script>
</body>
</html>
""".replace("__CSS__", COMMON_CSS)


def payload() -> dict:
    if not EXCEL_COMPARE.exists():
        build_compare_excel()
    sheets = load_excel_sheets(EXCEL_COMPARE)
    metrics = sheets.get("metrics", pd.DataFrame())
    records = []
    if not metrics.empty:
        # Nettoyage cellule par cellule : pandas retransforme None en NaN sur colonnes float.
        for rec in metrics.to_dict(orient="records"):
            cleaned = {}
            for key, value in rec.items():
                if value is None or (isinstance(value, float) and pd.isna(value)):
                    cleaned[key] = None
                else:
                    cleaned[key] = value
            records.append(cleaned)
    return {
        "ok": True,
        "source": EXCEL_COMPARE.name,
        "metrics": records,
        "sources": {
            "v1": EXCEL_V1.exists(),
            "v2": EXCEL_V2.exists(),
            "ia": EXCEL_IA.exists(),
            "dense": EXCEL_DENSE.exists(),
        },
    }


@app.get("/")
def index():
    return render_template_string(PAGE)


@app.get("/api/results")
def api_results():
    try:
        return jsonify(payload())
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.get("/download")
def download():
    if not EXCEL_COMPARE.exists():
        return jsonify({"ok": False, "error": "Excel introuvable"}), 404
    return send_file(
        EXCEL_COMPARE, as_attachment=True, download_name=EXCEL_COMPARE.name
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Comparaison LOO v1 / v2 / IA")
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)

    if args.rebuild or not EXCEL_COMPARE.exists():
        path = build_compare_excel()
        print(f"Excel comparaison : {path}")
        if args.rebuild:
            return 0

    print(f"Comparaison LOO — http://127.0.0.1:{args.port}/")
    app.run(host=args.host, port=args.port, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
