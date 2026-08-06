# Backlog corrections (FIFO)

Mode de travail :
1. Reception tache → preparation (analyse + plan) **sans modifier** si un autre item est en cours d'application.
2. Application **par ordre d'arrivee** quand le slot est libre.
3. Status : `queued` | `prepared` | `applying` | `done` | `blocked`

---

## B001 — Aligner CA reel sim_v1 sur ventes sim_v2/ML + libelle « estime »
- Status: **done** (2026-08-06)
- Resume: t_hotel_params depuis t_dataset_pivot/t_sales ; UI CA estime

## B002 — User UI : separer gammes F&B / Non F&B
- Status: **done** (2026-08-06)
- Application :
  - `pages_user.py` : 2 MixPanel (`mix_gamme_fb` / `mix_gamme_nfb`) + `combineGammeMix`
  - `styles.py` : grille 2 colonnes + teintes F&B / Non F&B
  - `api/app.py` : defaults `gamme_mix_fb` / `gamme_mix_nfb` + plat
- Contrat API conserve : `gamme_mix` plat somme ~1

## B003 — User sim : sim_v1 « Pas de prediction pour ce moteur »
- Status: **done** (2026-08-06)
- Cause : `predict_hotel` exige hotel pilote + ignore leviers + 1 seule solution
- Fix :
  - `SimV1Service.predict_from_levers` : R1–R4 + `v1_pilot_defaults` / JSON
  - leviers : chambres, TO, guests, m_lin, mix F&B (type_mix), frigos Connected
  - `/api/user/simulate` et `/api/predict/sim_v1` branchent sur les leviers
  - 3 solutions (simply/liberty/connected) toujours estimees

## B004 — Estimation + Optimisation (balayage mix 10 %)
- Status: **done** (2026-08-06)
- Step 4 renomme Estimation
- Step 5 Optimisation : sous-onglets Parametres / Estimations
- API `POST /api/user/optimize` : vary_one + sim_v1/v2/ml, best CA + reco
- Module `src/user/optimize.py`

## B005 — ml1 / ml2 XGBoost
- Status: **done** (2026-08-06)
- ml1 : XGB sur v_ml_training_dataset (simulations sim_v2 seules)
- ml2 : XGB t_rich_data + brand (px, wx moyenne mensuelle, hd, br_)
- Admin eval LOO : boutons ml1 / ml2
- User estimation : engines ml1 / ml2
- CLI : `python run.py ml1` / `ml2` ; warm entraine les 3
