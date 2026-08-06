"""CSS partage (style pro sombre, lisibilite renforcee)."""

COMMON_CSS = """
:root {
  --bg: #0f1419; --card: #1a2332; --line: #2a3a4f;
  --text: #e7eef7; --muted: #8b9bb0; --accent: #3d8bfd;
  --tab: #141c28; --tab-on: #243044; --ok: #3dd68c; --warn: #f5a524;
  --track: #101820; --fill: #3d8bfd;
}
* { box-sizing: border-box; }
body {
  margin: 0; font-family: "Segoe UI", system-ui, sans-serif;
  background: var(--bg); color: var(--text); line-height: 1.5;
  font-size: 15px;
}
header {
  padding: 1rem 1.35rem; border-bottom: 1px solid var(--line);
  display: flex; flex-wrap: wrap; gap: .75rem; align-items: center;
  justify-content: space-between;
}
h1 { font-size: 1.2rem; margin: 0; font-weight: 600; }
h1 a.brand {
  color: inherit; text-decoration: none; font-weight: 600;
}
h1 a.brand:hover { color: var(--accent); }
h1 span { color: var(--muted); font-weight: 400; font-size: .9rem; margin-left: .4rem; }
nav { display: flex; flex-wrap: wrap; gap: .45rem; }
a.link, button.btn {
  color: var(--text); border: 1px solid var(--line); border-radius: 9px;
  padding: .48rem .95rem; text-decoration: none; font-size: .92rem; font-weight: 600;
  background: transparent; cursor: pointer;
}
a.link:hover, button.btn:hover { border-color: var(--accent); color: var(--accent); }
a.link.active, button.btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
main { padding: 1.2rem 1.35rem 2.5rem; max-width: 1320px; margin: 0 auto; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: .75rem; }
.card {
  background: var(--card); border: 1px solid var(--line); border-radius: 12px;
  padding: 1rem 1.1rem;
}
.card .lbl { color: var(--muted); font-size: .78rem; text-transform: uppercase; letter-spacing: .03em; }
.card .val { font-size: 1.35rem; font-weight: 700; margin-top: .2rem; }
.card .sub { color: var(--muted); font-size: .86rem; margin-top: .15rem; }
h2 { font-size: 1.08rem; margin: 1.15rem 0 .55rem; font-weight: 600; }
table {
  width: 100%; border-collapse: collapse; font-size: .9rem;
  background: var(--card); border: 1px solid var(--line); border-radius: 10px; overflow: hidden;
}
th, td { text-align: left; padding: .55rem .6rem; border-bottom: 1px solid var(--line); vertical-align: top; }
th { color: var(--muted); font-weight: 600; font-size: .78rem; text-transform: uppercase; background: #152030; }
tr:last-child td { border-bottom: 0; }
tr:hover td { background: rgba(61,139,253,.05); }
.num { font-variant-numeric: tabular-nums; text-align: right; white-space: nowrap; }
.tag {
  display: inline-block; padding: .12rem .5rem; border-radius: 999px;
  font-size: .78rem; font-weight: 600; background: #243044; color: var(--muted);
}
.tag.simply, .tag.A { color: #7dd3fc; }
.tag.liberty, .tag.B { color: #c4b5fd; }
.tag.connected, .tag.ml, .tag.ML { color: #86efac; }
.tag.sim_v1 { color: #7dd3fc; }
.tag.sim_v2 { color: #c4b5fd; }
.muted { color: var(--muted); font-size: .92rem; }
.errbox {
  margin: 1rem 0; padding: .85rem 1rem; border: 1px solid #5a2a35;
  background: #2a1520; border-radius: 8px; color: #f5a0b0; font-size: .95rem;
}
.scroll { overflow: auto; max-width: 100%; }
form.card label { display: block; font-size: .86rem; color: var(--muted); margin-top: .65rem; }
form.card input, form.card select, form.card textarea {
  width: 100%; margin-top: .25rem; padding: .5rem .6rem; border-radius: 7px;
  border: 1px solid var(--line); background: #101820; color: var(--text); font-size: .95rem;
}
form.card .row { display: grid; grid-template-columns: 1fr 1fr; gap: .65rem; }
@media (max-width: 700px) { form.card .row { grid-template-columns: 1fr; } }
.layout { display: grid; grid-template-columns: minmax(340px, 420px) 1fr; gap: 1.1rem; align-items: start; }
@media (max-width: 960px) { .layout { grid-template-columns: 1fr; } }
.predict-right { display: flex; flex-direction: column; gap: .85rem; min-width: 0; }
.predict-actions { padding: .75rem .9rem; position: sticky; top: .65rem; z-index: 2; }
.predict-actions .btn-row { margin-top: 0; }

/* ---- Mix sliders ---- */
.mix-family-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: .75rem;
  margin-top: .85rem;
}
@media (max-width: 900px) {
  .mix-family-grid { grid-template-columns: 1fr; }
}
.mix-hint { margin: .55rem 0 0; font-size: .8rem; }
.mix-block {
  margin-top: .85rem; padding: .75rem .8rem .85rem;
  border: 1px solid var(--line); border-radius: 10px; background: #141c28;
}
.mix-family-grid .mix-block { margin-top: 0; }
.mix-block-fb { border-color: rgba(61,139,253,.35); box-shadow: inset 0 0 0 1px rgba(61,139,253,.08); }
.mix-block-nfb { border-color: rgba(196,181,253,.35); box-shadow: inset 0 0 0 1px rgba(196,181,253,.08); }
.mix-block-fb .mix-title { color: #93c5fd; }
.mix-block-nfb .mix-title { color: #c4b5fd; }
.mix-block .mix-head {
  display: flex; align-items: center; justify-content: space-between; gap: .5rem;
  margin-bottom: .55rem;
}
.mix-block .mix-title {
  font-size: .88rem; font-weight: 700; color: var(--text); margin: 0;
  text-transform: uppercase; letter-spacing: .04em;
}
.mix-block .mix-sum {
  font-size: .82rem; font-weight: 600; color: var(--ok);
  font-variant-numeric: tabular-nums;
}
.mix-block .mix-sum.warn { color: var(--warn); }
.mix-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  gap: .45rem .55rem;
  align-items: center;
  padding: .4rem 0;
  border-top: 1px solid rgba(42,58,79,.55);
}
.mix-row:first-of-type { border-top: 0; }
.mix-row .mix-label {
  font-size: .9rem; font-weight: 600; color: var(--text);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.mix-row .mix-pct {
  font-size: .92rem; font-weight: 700; min-width: 3.2rem; text-align: right;
  font-variant-numeric: tabular-nums; color: var(--accent);
}
.mix-row.locked .mix-pct { color: var(--muted); }
.mix-row .mix-slider-wrap { grid-column: 1 / -1; display: flex; align-items: center; gap: .55rem; }
.mix-row input[type=range] {
  -webkit-appearance: none; appearance: none;
  width: 100%; height: 6px; border-radius: 999px;
  background: linear-gradient(90deg, var(--fill) var(--pct, 0%), var(--track) var(--pct, 0%));
  outline: none; margin: 0; border: 0; padding: 0; cursor: pointer;
}
.mix-row input[type=range]::-webkit-slider-thumb {
  -webkit-appearance: none; appearance: none;
  width: 16px; height: 16px; border-radius: 50%;
  background: #fff; border: 2px solid var(--accent);
  box-shadow: 0 0 0 3px rgba(61,139,253,.25); cursor: pointer;
}
.mix-row input[type=range]::-moz-range-thumb {
  width: 16px; height: 16px; border-radius: 50%;
  background: #fff; border: 2px solid var(--accent); cursor: pointer;
}
.mix-row input[type=range]:disabled {
  opacity: .55; cursor: not-allowed;
}
.mix-row input[type=range]:disabled::-webkit-slider-thumb {
  border-color: var(--muted); box-shadow: none;
}
/* switch lock */
.sw {
  position: relative; width: 36px; height: 20px; flex-shrink: 0;
}
.sw input { opacity: 0; width: 0; height: 0; position: absolute; }
.sw .slider {
  position: absolute; inset: 0; cursor: pointer;
  background: #243044; border: 1px solid var(--line); border-radius: 999px;
  transition: .15s;
}
.sw .slider:before {
  content: ""; position: absolute; height: 14px; width: 14px; left: 2px; top: 2px;
  background: var(--muted); border-radius: 50%; transition: .15s;
}
.sw input:checked + .slider { background: rgba(61,139,253,.25); border-color: var(--accent); }
.sw input:checked + .slider:before { transform: translateX(16px); background: var(--accent); }
.sw input:disabled + .slider { opacity: .45; cursor: not-allowed; }
.sw-hint {
  font-size: .72rem; color: var(--muted); min-width: 2.2rem; text-align: center;
}
.mix-row.locked { opacity: .92; }
.mix-row.residual .mix-label::after {
  content: " · reste"; font-weight: 500; color: var(--muted); font-size: .78rem;
}
.btn-row { margin-top: 1.05rem; display: flex; gap: .5rem; flex-wrap: wrap; }
/* Eval LOO colors */
.col-reel { color: #7dd3fc !important; }
.col-pred { color: #c4b5fd !important; }
.col-err { color: #f5a524 !important; font-weight: 600; }
td.col-reel { background: rgba(125,211,252,.06); }
td.col-pred { background: rgba(196,181,253,.06); }
td.col-err { background: rgba(245,165,36,.07); }
"""