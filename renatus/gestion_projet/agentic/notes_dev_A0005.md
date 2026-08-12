# Notes A0005

Capture: gestion_projet/agentic/captures/A0005_build_extension_non_supportee.png

## Causes
1. Build sans Save → file encore vide cote serveur → suffixe vide
2. openpyxl non installe par defaut pour xlsx

## Correctif
- saveStepSilent avant Build / Build&afficher
- messages clairs file vide / fichier introuvable / openpyxl
- openpyxl en dependance principale

Temps: ~30 min
