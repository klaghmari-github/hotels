# F0054 — 2e tour POO

## Backend
- GuiService -> modules services (graph, tabs, build, project glue)
- Step: build_kind / is_table_like helpers pour GUI.build
- engine: schema helpers module; composition ConnectionUtils si stable

## Front
- config.js monolithe -> config/* + ConfigPanel
- project/changelogs/dataview en classes UiController
- GraphCanvas/Toolbox/PipelineTabs: methodes reelles pas juste wrap

## Gate
Full pytest; zero behavior change.
