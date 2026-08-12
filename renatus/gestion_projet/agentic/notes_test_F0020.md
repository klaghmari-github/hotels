# Notes test F0020

## Couverture

`tests/test_f0020_yaml_highlight.py`

- structure HTML dual-layer (highlight + textarea)
- tokens CSS y-key / y-string / …
- helpers JS highlightYaml + formatYamlError
- API from-yaml 400 sur YAML casse (ligne/colonne)
- regression F0015 / F0018 (YAML brut, full width)

## Resultat

PASS avec suite YAML gui.
