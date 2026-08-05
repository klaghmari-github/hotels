"""CSS partage (style pro sombre, inspire eval_common)."""

COMMON_CSS = """
:root {
  --bg: #0f1419; --card: #1a2332; --line: #2a3a4f;
  --text: #e7eef7; --muted: #8b9bb0; --accent: #3d8bfd;
  --tab: #141c28; --tab-on: #243044; --ok: #3dd68c; --warn: #f5a524;
}
* { box-sizing: border-box; }
body {
  margin: 0; font-family: "Segoe UI", system-ui, sans-serif;
  background: var(--bg); color: var(--text); line-height: 1.45;
}
header {
  padding: 1rem 1.25rem; border-bottom: 1px solid var(--line);
  display: flex; flex-wrap: wrap; gap: .75rem; align-items: center;
  justify-content: space-between;
}
h1 { font-size: 1.1rem; margin: 0; font-weight: 600; }
h1 span { color: var(--muted); font-weight: 400; font-size: .85rem; margin-left: .4rem; }
nav { display: flex; flex-wrap: wrap; gap: .4rem; }
a.link, button.btn {
  color: var(--text); border: 1px solid var(--line); border-radius: 8px;
  padding: .4rem .85rem; text-decoration: none; font-size: .85rem; font-weight: 600;
  background: transparent; cursor: pointer;
}
a.link:hover, button.btn:hover { border-color: var(--accent); color: var(--accent); }
a.link.active, button.btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
main { padding: 1.1rem 1.25rem 2.5rem; max-width: 1280px; margin: 0 auto; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: .7rem; }
.card {
  background: var(--card); border: 1px solid var(--line); border-radius: 12px;
  padding: .9rem 1rem;
}
.card .lbl { color: var(--muted); font-size: .72rem; text-transform: uppercase; letter-spacing: .03em; }
.card .val { font-size: 1.25rem; font-weight: 700; margin-top: .2rem; }
.card .sub { color: var(--muted); font-size: .78rem; margin-top: .15rem; }
h2 { font-size: 1rem; margin: 1.1rem 0 .5rem; font-weight: 600; }
table {
  width: 100%; border-collapse: collapse; font-size: .82rem;
  background: var(--card); border: 1px solid var(--line); border-radius: 10px; overflow: hidden;
}
th, td { text-align: left; padding: .5rem .55rem; border-bottom: 1px solid var(--line); vertical-align: top; }
th { color: var(--muted); font-weight: 600; font-size: .72rem; text-transform: uppercase; background: #152030; }
tr:last-child td { border-bottom: 0; }
tr:hover td { background: rgba(61,139,253,.05); }
.num { font-variant-numeric: tabular-nums; text-align: right; white-space: nowrap; }
.tag {
  display: inline-block; padding: .1rem .45rem; border-radius: 999px;
  font-size: .7rem; font-weight: 600; background: #243044; color: var(--muted);
}
.tag.simply, .tag.A { color: #7dd3fc; }
.tag.liberty, .tag.B { color: #c4b5fd; }
.tag.connected, .tag.ML, .tag.catboost { color: #86efac; }
.muted { color: var(--muted); font-size: .85rem; }
.errbox {
  margin: 1rem 0; padding: .8rem 1rem; border: 1px solid #5a2a35;
  background: #2a1520; border-radius: 8px; color: #f5a0b0;
}
.scroll { overflow: auto; max-width: 100%; }
form.card label { display: block; font-size: .78rem; color: var(--muted); margin-top: .55rem; }
form.card input, form.card select, form.card textarea {
  width: 100%; margin-top: .2rem; padding: .45rem .55rem; border-radius: 6px;
  border: 1px solid var(--line); background: #101820; color: var(--text);
}
form.card .row { display: grid; grid-template-columns: 1fr 1fr; gap: .6rem; }
@media (max-width: 700px) { form.card .row { grid-template-columns: 1fr; } }
.layout { display: grid; grid-template-columns: 320px 1fr; gap: 1rem; }
@media (max-width: 900px) { .layout { grid-template-columns: 1fr; } }
"""
