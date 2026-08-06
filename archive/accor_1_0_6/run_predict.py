#!/usr/bin/env python3
"""
Interface de prediction pour un hotel cible.

- Restitution simulateur v2 (methodes A et B, 3 solutions)
- Prediction XGBoost si les modeles sont presents dans models/xgboost

  python run_predict.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import numpy as np
import pandas as pd
from flask import Flask, jsonify, render_template_string, request
from xgboost import XGBRegressor

from archive.accor_1_0_6.eval_common import COMMON_CSS, open_pipeline
from archive.accor_1_0_6.main import run_restitution

DEFAULT_PORT = 5061
MODELS_DIR = _ROOT / "models" / "xgboost"
DENSE_MODELS_DIR = _ROOT / "models" / "dense"

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False

PAGE = r"""
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Prediction hotel cible</title>
  <style>__CSS__</style>
</head>
<body>
  <header>
    <h1>Prediction <span>restitution v2 · IA</span></h1>
    <span id="status" class="muted"></span>
  </header>
  <main>
    <form class="card" id="form" onsubmit="return false;">
      <h2 style="margin-top:0">Parametres hotel</h2>
      <div class="row">
        <div><label>Chambres</label><input name="hotel_nb_chambres" type="number" step="1" value="100"/></div>
        <div><label>TO annuel (0-1)</label><input name="hotel_to_annuel" type="number" step="0.01" value="0.70"/></div>
      </div>
      <div class="row">
        <div><label>Guests / chambre</label><input name="hotel_guests_per_chambre" type="number" step="0.1" value="1.7"/></div>
        <div><label>Metres lineaires</label><input name="metres_lineaires" type="number" step="0.1" value="6"/></div>
      </div>
      <label>Solution (pour IA)</label>
      <select name="solution">
        <option value="simply">simply</option>
        <option value="liberty">liberty</option>
        <option value="connected">connected</option>
      </select>
      <label>Mix type (JSON, somme = 1)</label>
      <textarea name="type_mix" rows="2">{"F&B": 0.7, "NON F&B": 0.3}</textarea>
      <label>Mix gamme (JSON, somme = 1)</label>
      <textarea name="gamme_mix" rows="3">{"sans alcool": 0.35, "food salee": 0.25, "food sucree": 0.15, "accessoires": 0.15, "sos": 0.10}</textarea>
      <div style="margin-top:1rem;display:flex;gap:.5rem;flex-wrap:wrap">
        <button class="btn primary" id="btnV2" type="button">Predire sim_v2</button>
        <button class="btn" id="btnIA" type="button">Predire XGBoost</button>
        <button class="btn" id="btnDense" type="button">Predire dense</button>
      </div>
    </form>
    <div id="out" style="margin-top:1rem"></div>
  </main>
  <script>
    const fmt=(n,d=2)=>{if(n==null||n===''||Number.isNaN(Number(n)))return '—';return Number(n).toLocaleString('fr-FR',{maximumFractionDigits:d});};
    const tag=s=>`<span class="tag ${(s||'').toString().toLowerCase()}">${s??''}</span>`;
    function bodyFromForm(){
      const fd=new FormData(document.getElementById('form'));
      return {
        hotel_nb_chambres: Number(fd.get('hotel_nb_chambres')),
        hotel_to_annuel: Number(fd.get('hotel_to_annuel')),
        hotel_guests_per_chambre: Number(fd.get('hotel_guests_per_chambre')),
        metres_lineaires: Number(fd.get('metres_lineaires')),
        solution: fd.get('solution'),
        type_mix: JSON.parse(fd.get('type_mix')),
        gamme_mix: JSON.parse(fd.get('gamme_mix')),
      };
    }
    function showTable(title, rows, cols){
      let h=`<h2>${title}</h2><div class="scroll"><table><thead><tr>${cols.map(c=>`<th>${c.l}</th>`).join('')}</tr></thead><tbody>`;
      for(const r of rows){
        h+='<tr>'+cols.map(c=>{
          let v=r[c.k];
          if(c.k==='solution'||c.k==='methode') v=tag(v);
          else if(typeof v==='number') v=fmt(v);
          else if(v==null) v='—';
          return `<td class="${typeof r[c.k]==='number'?'num':''}">${v}</td>`;
        }).join('')+'</tr>';
      }
      return h+'</tbody></table></div>';
    }
    async function call(url){
      const status=document.getElementById('status');
      const out=document.getElementById('out');
      status.textContent='Calcul…';
      try{
        const res=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(bodyFromForm())});
        const data=await res.json();
        if(!data.ok) throw new Error(data.error||'echec');
        if(data.predictions){
          out.innerHTML=showTable('Restitution sim_v2', data.predictions, [
            {k:'solution',l:'Solution'},{k:'methode',l:'Methode'},
            {k:'montant_ventes_par_mois_predit',l:'CA mensuel'},
            {k:'montant_marge_par_mois_predite',l:'Marge marche'},
            {k:'montant_marge_selon_coef_par_mois_predite',l:'Marge coef'},
          ]);
        } else if(data.prediction){
          const p=data.prediction;
          const title=data.model||'ML';
          out.innerHTML=`<h2>Prediction ${title} (${tag(p.solution)})</h2>
            <div class="grid">
              <div class="card"><div class="lbl">CA mensuel</div><div class="val">${fmt(p.montant_ventes_par_mois)}</div></div>
              <div class="card"><div class="lbl">Marge marche</div><div class="val">${fmt(p.montant_marge_par_mois)}</div></div>
              <div class="card"><div class="lbl">Marge coef</div><div class="val">${fmt(p.montant_marge_selon_coef_par_mois)}</div></div>
            </div>`;
        }
        status.textContent='OK';
      }catch(e){
        out.innerHTML=`<div class="errbox">${e.message}</div>`;
        status.textContent='Erreur';
      }
    }
    document.getElementById('btnV2').onclick=()=>call('/api/predict/v2');
    document.getElementById('btnIA').onclick=()=>call('/api/predict/ia');
    document.getElementById('btnDense').onclick=()=>call('/api/predict/dense');
  </script>
</body>
</html>
""".replace("__CSS__", COMMON_CSS)


def _normalize_mix_keys(family: str, mix: dict) -> dict[str, float]:
    """Les cles utilisateur sont des libelles ; run_restitution les normalise deja."""
    return {str(k): float(v) for k, v in mix.items()}


def predict_v2(body: dict) -> dict:
    cp = open_pipeline(read_only=False)
    try:
        df = run_restitution(
            cp,
            hotel_nb_chambres=float(body["hotel_nb_chambres"]),
            hotel_to_annuel=float(body["hotel_to_annuel"]),
            hotel_guests_per_chambre=float(body["hotel_guests_per_chambre"]),
            metres_lineaires=float(body["metres_lineaires"]),
            type_mix=_normalize_mix_keys("type", body.get("type_mix") or {}),
            gamme_mix=_normalize_mix_keys("gamme", body.get("gamme_mix") or {}),
        )
        records = df.where(pd.notnull(df), None).to_dict(orient="records")
        return {"ok": True, "predictions": records}
    finally:
        cp.close()


def _mix_feature_name(family: str, label: str) -> str:
    from archive.accor_1_0_6.main import normalized_mix_name

    return normalized_mix_name(family, label)


def predict_ia(body: dict) -> dict:
    """
    Charge les modeles XGBoost sauvegardes et predit les 3 cibles.
    Necessite un entrainement prealable (run_eval_ia --rebuild ou notebook).
    """
    targets = [
        "montant_ventes_par_mois",
        "montant_marge_par_mois",
        "montant_marge_selon_coef_par_mois",
    ]
    meta_path = MODELS_DIR / f"{targets[0]}_metadata.json"
    if not meta_path.exists():
        return {
            "ok": False,
            "error": "Modeles absents. Lancer d abord : python run_eval_ia.py --rebuild",
        }

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    feature_names: list[str] = meta["feature_names"]

    guests = (
        float(body["hotel_nb_chambres"])
        * float(body["hotel_to_annuel"])
        * float(body["hotel_guests_per_chambre"])
        * 30.5
    )
    # vecteur features
    row = {name: 0.0 for name in feature_names}
    row["hotel_nb_chambres"] = float(body["hotel_nb_chambres"])
    row["hotel_to_annuel"] = float(body["hotel_to_annuel"])
    row["hotel_guests_per_chambre"] = float(body["hotel_guests_per_chambre"])
    row["metres_lineaires"] = float(body["metres_lineaires"])

    sol = str(body.get("solution") or "simply").lower()
    sol_col = f"solution_{sol}"
    if sol_col in row:
        row[sol_col] = 1.0
    else:
        # fallback : activer la premiere solution connue
        for name in feature_names:
            if name.startswith("solution_"):
                row[name] = 1.0 if name.endswith(sol) else 0.0

    for family, mix in (
        ("type", body.get("type_mix") or {}),
        ("gamme", body.get("gamme_mix") or {}),
    ):
        for label, part in mix.items():
            col = _mix_feature_name(family, str(label))
            if col in row:
                row[col] = float(part)

    x = pd.DataFrame([row])[feature_names].astype(float)
    pred: dict[str, float] = {"solution": sol}
    for target in targets:
        model_path = MODELS_DIR / f"{target}.json"
        if not model_path.exists():
            return {"ok": False, "error": f"Modele manquant : {model_path.name}"}
        model = XGBRegressor()
        model.load_model(model_path)
        pred[target] = max(float(model.predict(x)[0]), 0.0)

    return {"ok": True, "model": "xgboost", "prediction": pred}


def predict_dense(body: dict) -> dict:
    """
    Charge les reseaux densés (.pt + scalers) et predit les 3 cibles.
    Necessite un entrainement (run_eval_dense --rebuild).
    """
    import joblib
    import torch
    from archive.accor_1_0_6.ml_dense import DenseRegressor

    targets = [
        "montant_ventes_par_mois",
        "montant_marge_par_mois",
        "montant_marge_selon_coef_par_mois",
    ]
    meta_path = DENSE_MODELS_DIR / f"{targets[0]}_metadata.json"
    if not meta_path.exists():
        return {
            "ok": False,
            "error": "Modeles dense absents. Lancer : python run_eval_dense.py --rebuild",
        }

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    feature_names: list[str] = meta["feature_names"]

    row = {name: 0.0 for name in feature_names}
    row["hotel_nb_chambres"] = float(body["hotel_nb_chambres"])
    row["hotel_to_annuel"] = float(body["hotel_to_annuel"])
    row["hotel_guests_per_chambre"] = float(body["hotel_guests_per_chambre"])
    row["metres_lineaires"] = float(body["metres_lineaires"])

    sol = str(body.get("solution") or "simply").lower()
    sol_col = f"solution_{sol}"
    if sol_col in row:
        row[sol_col] = 1.0
    else:
        for name in feature_names:
            if name.startswith("solution_"):
                row[name] = 1.0 if name.endswith(sol) else 0.0

    for family, mix in (
        ("type", body.get("type_mix") or {}),
        ("gamme", body.get("gamme_mix") or {}),
    ):
        for label, part in mix.items():
            col = _mix_feature_name(family, str(label))
            if col in row:
                row[col] = float(part)

    x_df = pd.DataFrame([row])[feature_names].astype(float)
    pred: dict[str, float] = {"solution": sol}

    for target in targets:
        model_path = DENSE_MODELS_DIR / f"{target}.pt"
        scaler_path = DENSE_MODELS_DIR / f"{target}_scalers.joblib"
        if not model_path.exists() or not scaler_path.exists():
            return {
                "ok": False,
                "error": f"Artefacts dense manquants pour {target}",
            }
        payload = torch.load(model_path, map_location="cpu", weights_only=False)
        scalers = joblib.load(scaler_path)
        params = payload.get("params") or {}
        model = DenseRegressor(
            input_size=int(payload["input_size"]),
            hidden_width=int(params.get("hidden_width", 64)),
            residual_blocks=int(params.get("residual_blocks", 2)),
            dropout=float(params.get("dropout", 0.0)),
        )
        model.load_state_dict(payload["state_dict"])
        model.eval()

        x_scaled = scalers["feature_scaler"].transform(x_df.to_numpy(dtype=float))
        with torch.no_grad():
            y_scaled = model(
                torch.from_numpy(x_scaled.astype(np.float32))
            ).numpy()
        y = scalers["target_scaler"].inverse_transform(
            y_scaled.reshape(-1, 1)
        ).ravel()
        pred[target] = max(float(y[0]), 0.0)

    return {"ok": True, "model": "dense", "prediction": pred}


@app.get("/")
def index():
    return render_template_string(PAGE)


@app.post("/api/predict/v2")
def api_predict_v2():
    try:
        return jsonify(predict_v2(request.get_json(force=True) or {}))
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.post("/api/predict/ia")
def api_predict_ia():
    try:
        return jsonify(predict_ia(request.get_json(force=True) or {}))
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.post("/api/predict/dense")
def api_predict_dense():
    try:
        return jsonify(predict_dense(request.get_json(force=True) or {}))
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.get("/api/health")
def health():
    xgb_ok = (MODELS_DIR / "montant_ventes_par_mois.json").exists()
    dense_ok = (DENSE_MODELS_DIR / "montant_ventes_par_mois.pt").exists()
    return jsonify(
        {
            "ok": True,
            "service": "predict",
            "models_ready": xgb_ok,
            "dense_ready": dense_ok,
        }
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Interface de prediction hotel")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)
    print(f"Prediction — http://127.0.0.1:{args.port}/")
    app.run(host=args.host, port=args.port, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
