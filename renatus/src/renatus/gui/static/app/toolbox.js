/**
 * Palette outils + creation de steps (F0053-S2 / F0053-S4 / F0054-S2).
 * Toolbox : methodes reelles; exports fonctionnels = wrappers.
 */
import { state, el } from "./state.js";
import { api, toast } from "./api.js";
import { selectStep } from "./config.js";
import { refreshGraph } from "./graph.js";
import { typeIconSvg } from "./icons.js";
import { stepTypeRegistry } from "./step-types/registry.js";
import { refreshTabs } from "./tabs.js";
import { withProgress } from "./progress-dialog.js";
import { UiController } from "./ui-base.js";
import { escapeHtml, pad2 } from "./util.js";

/**
 * F0139: dialog pour choisir la zone parent (flat zone).
 * @returns {Promise<string|null>}
 */
async function pickParentZoneForFlat() {
  let zones = [];
  try {
    const data = await api("/gui/tabs");
    zones = (data.tabs || []).map(function (t) {
      return { id: t.id, label: t.label || t.id };
    });
  } catch (_) {
    zones = [{ id: "default", label: "default" }];
  }
  if (!zones.length) zones = [{ id: "default", label: "default" }];
  const active = state.activeTab || "default";

  return new Promise(function (resolve) {
    const dlg = document.createElement("dialog");
    dlg.className = "props-dialog confirm-dialog";
    dlg.setAttribute("data-testid", "flat-parent-dialog");
    const opts = zones
      .map(function (z) {
        const sel = z.id === active ? " selected" : "";
        return (
          '<option value="' +
          escapeHtml(z.id) +
          '"' +
          sel +
          ">" +
          escapeHtml(z.label || z.id) +
          "</option>"
        );
      })
      .join("");
    dlg.innerHTML =
      '<form method="dialog" class="props-form confirm-form flat-parent-form">' +
      '<div class="dialog-head">' +
      '<div class="dialog-icon dialog-icon-info" aria-hidden="true">⧉</div>' +
      '<div class="confirm-dialog-text">' +
      "<h3>Flat zone — zone parent</h3>" +
      '<p class="dialog-sub">Tous les composants (feuilles) de cette zone ' +
      "seront copies recursivement dans la nouvelle zone.</p>" +
      "</div></div>" +
      '<div class="flat-parent-field" data-testid="flat-parent-field">' +
      '<label for="flat-parent-select" class="flat-parent-label">Zone source</label>' +
      '<p class="flat-parent-hint muted">Liste deroulante — cliquez pour choisir</p>' +
      '<div class="renatus-select-wrap flat-parent-select-wrap">' +
      '<select id="flat-parent-select" class="renatus-select" data-testid="flat-parent-select" ' +
      'aria-label="Zone source (liste deroulante)">' +
      opts +
      "</select>" +
      "</div>" +
      "</div>" +
      '<div class="props-actions">' +
      '<button type="submit" class="btn" value="cancel" data-testid="flat-parent-cancel">Annuler</button>' +
      '<button type="submit" class="btn primary" value="ok" data-testid="flat-parent-ok">Creer</button>' +
      "</div></form>";
    document.body.appendChild(dlg);
    function done(val) {
      try {
        if (dlg.open) dlg.close();
      } catch (_) {}
      try {
        dlg.remove();
      } catch (_) {}
      resolve(val);
    }
    dlg.addEventListener("close", function () {
      const rv = dlg.returnValue || "cancel";
      if (rv === "ok") {
        const sel = dlg.querySelector("#flat-parent-select");
        done(sel && sel.value ? sel.value : "default");
      } else {
        done(null);
      }
    });
    try {
      dlg.showModal();
      // F0141: enhance select + fleche apres insertion DOM
      const sel = dlg.querySelector("#flat-parent-select");
      import("./renatus-select.js").then(function (mod) {
        if (mod && typeof mod.enhanceRenatusSelect === "function" && sel) {
          mod.enhanceRenatusSelect(sel);
        }
      });
    } catch (_) {
      done(active || "default");
    }
  });
}

/**
 * Controleur palette outils (F0054-S2 thick).
 */
export class Toolbox extends UiController {
  constructor(root) {
    super(root || (el && el.toolbox) || null);
  }

  renderToolbox() {
    // F0075: regions Datasets / Execute / Flow
    const REGIONS = [
      {
        id: "datasets",
        label: "Datasets",
        types: ["dataframe", "table", "view"],
      },
      {
        id: "execute",
        label: "Execute",
        types: [
          "execute_sql",
          "execute_python",
          "notebook",
          "execute_shell",
        ],
      },
      {
        id: "flow",
        label: "Flow",
        types: ["iterate", "zone"],
      },
      {
        id: "auto",
        label: "Auto",
        types: ["flatzone", "backzone", "forzone", "bidzone"],
      },
    ];
    const fallback = [
      {
        id: "dataframe",
        label: "Dataframe",
        type: "dataframe",
        region: "datasets",
      },
      { id: "table", label: "Table", type: "table", region: "datasets" },
      { id: "view", label: "Vue", type: "view", region: "datasets" },
      {
        id: "execute_sql",
        label: "SQL",
        type: "execute_sql",
        region: "execute",
      },
      {
        id: "execute_python",
        label: "Python",
        type: "execute_python",
        region: "execute",
      },
      {
        id: "notebook",
        label: "Notebook",
        type: "notebook",
        region: "execute",
      },
      {
        id: "execute_shell",
        label: "Shell",
        type: "execute_shell",
        region: "execute",
      },
      {
        id: "iterate",
        label: "Iteration",
        type: "iterate",
        region: "flow",
      },
      { id: "zone", label: "Zone", type: "zone", region: "flow" },
      {
        id: "flatzone",
        label: "Flat zone",
        type: "flatzone",
        region: "auto",
        description:
          "Zone initialisee avec tous les composants d une zone parent (recursif)",
      },
      {
        id: "backzone",
        label: "Back zone",
        type: "backzone",
        region: "auto",
        description: "Zone initialisee avec le lineage requires (amont)",
      },
      {
        id: "forzone",
        label: "For zone",
        type: "forzone",
        region: "auto",
        description: "Zone initialisee avec le lineage required_by (aval)",
      },
      {
        id: "bidzone",
        label: "Bid zone",
        type: "bidzone",
        region: "auto",
        description: "Zone initialisee avec le lineage bidirectionnel",
      },
    ];
    const tools = state.tools.length ? state.tools : fallback;
    const byType = {};
    tools.forEach(function (t) {
      byType[t.type || t.id] = t;
    });

    el.toolbox.innerHTML = "";
    REGIONS.forEach(function (region) {
      const section = document.createElement("div");
      section.className = "toolbox-region";
      section.setAttribute("data-testid", "toolbox-region-" + region.id);
      const head = document.createElement("div");
      head.className = "toolbox-region-title";
      head.textContent = region.label;
      section.appendChild(head);

      region.types.forEach(function (type) {
        const t = byType[type];
        if (!t) return;
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "tool tool-" + t.type;
        btn.setAttribute("data-testid", "palette-" + t.type);
        // F0077: pas de label blanc redondant — icone + badge type suffisent
        btn.innerHTML =
          '<div class="t-title">' +
          '<span class="tool-icon-wrap badge ' +
          t.type +
          '" aria-hidden="true">' +
          typeIconSvg(t.type, { size: 18, className: "tool-icon" }) +
          "</span>" +
          '<span class="badge type-tag ' +
          t.type +
          '">' +
          escapeHtml(t.type) +
          "</span>" +
          "</div>";
        btn.title = t.description || t.label || t.type;
        btn.setAttribute("aria-label", t.label || t.type);
        btn.addEventListener("click", function () {
          openNewStep(t);
        });
        section.appendChild(btn);
      });
      el.toolbox.appendChild(section);
    });
  }

  /**
   * Ajoute un nœud directement sur le graphe (sans popup).
   * Dataframe: nom dataframe_YYYY_MM_DD_hh_mm_ss puis config a droite.
   */
  async openNewStep(tool) {
    if (!state.connected) {
      toast("Workspace non connecte", "error");
      return;
    }
    if (state.workspace && state.workspace.read_only) {
      toast("Lecture seule", "error");
      return;
    }

    // F0139: templates Auto → zone physique (init differente)
    if (
      tool.type === "flatzone" ||
      tool.type === "allzone" ||
      tool.type === "backzone" ||
      tool.type === "forzone" ||
      tool.type === "bidzone"
    ) {
      try {
        let objectId = null;
        let parentId = null;
        const kind = tool.type === "allzone" ? "flatzone" : tool.type;

        if (kind === "flatzone") {
          // choisir la zone parent source (contenu a aplatir)
          parentId = await pickParentZoneForFlat();
          if (!parentId) {
            toast("Creation annulee — zone parent requise", "error");
            return;
          }
        } else {
          objectId = state.selected;
          if (!objectId) {
            toast(
              "Selectionnez d abord un composant de reference, puis " +
                tool.label,
              "error"
            );
            return;
          }
          const selNode = (state.graph.nodes || []).find(function (n) {
            return n && n.id === objectId;
          });
          const st = (selNode && selNode.type) || "";
          if (
            st === "zone" ||
            st === "flatzone" ||
            st === "allzone" ||
            st === "backzone" ||
            st === "forzone" ||
            st === "bidzone"
          ) {
            toast(
              "Choisissez un composant (pas une zone) comme reference",
              "error"
            );
            return;
          }
        }

        // F0142: pop progression (copie YAML peut prendre plusieurs secondes)
        const titleByKind = {
          flatzone: "Création Flat zone",
          backzone: "Création Back zone",
          forzone: "Création For zone",
          bidzone: "Création Bid zone",
        };
        const srcHint =
          kind === "flatzone"
            ? "parent « " + parentId + " »"
            : "réf. « " + objectId + " »";

        await withProgress(
          {
            title: titleByKind[kind] || "Création de zone",
            message: "Initialisation depuis " + srcHint + "…",
            mode: "percent",
            percent: 8,
          },
          async function (prog) {
            prog.set({
              percent: 15,
              message:
                kind === "flatzone"
                  ? "Collecte des composants sous « " +
                    parentId +
                    " » et copie des YAML…"
                  : "Calcul du lineage et copie des YAML…",
            });

            // Avance visuelle pendant l attente serveur
            let pulsePct = 15;
            const pulse = setInterval(function () {
              if (pulsePct < 70) {
                pulsePct = Math.min(70, pulsePct + 8);
                prog.set({
                  percent: pulsePct,
                  message:
                    kind === "flatzone"
                      ? "Copie des composants (" + pulsePct + " %)…"
                      : "Création de la zone (" + pulsePct + " %)…",
                });
              }
            }, 400);

            let res;
            try {
              res = await api("/gui/auto-zone", {
                method: "POST",
                body: JSON.stringify({
                  type: kind,
                  object: objectId,
                  parent: parentId,
                }),
              });
            } finally {
              clearInterval(pulse);
            }

            const sid = res.id || res.name;
            const n =
              res.member_count != null
                ? res.member_count
                : (res.copied && res.copied.length) || 0;

            prog.set({
              percent: 78,
              message:
                n > 0
                  ? n + " composant(s) copiés — mise à jour des zones…"
                  : "Mise à jour des zones…",
            });
            await refreshTabs();

            prog.set({
              percent: 88,
              message: "Ouverture de la zone « " + (sid || "") + " »…",
            });
            if (res.zone_path || res.active_tab || sid) {
              try {
                const { switchTab } = await import("./tabs.js");
                await switchTab(res.zone_path || res.active_tab || sid);
              } catch (_) {
                await refreshGraph();
              }
            } else {
              await refreshGraph();
            }

            prog.set({ percent: 96, message: "Finalisation…" });
            if (sid) await selectStep(sid);

            prog.done(
              n > 0
                ? "Zone créée · " + n + " composant(s)"
                : "Zone créée"
            );
            toast(res.message || "Zone " + sid + " créée", "success");
          }
        );
      } catch (e) {
        toast("Auto-zone: " + e.message, "error");
      }
      return;
    }

    // F0017 / F0052: creation directe sur le graphe (dont zone)
    if (
      tool.type === "dataframe" ||
      tool.type === "table" ||
      tool.type === "view" ||
      tool.type === "execute" ||
      tool.type === "execute_sql" ||
      tool.type === "execute_python" ||
      tool.type === "notebook" ||
      tool.type === "execute_shell" ||
      tool.type === "iterate" || tool.type === "iteration" ||
      tool.type === "zone"
    ) {
      const name = timestampStepName(tool.type);
      const config = defaultConfig(tool.type, name);
      try {
        // F0031: name = id applicatif immutable; label initial = id
        config.label = name;
        await api("/gui/steps", {
          method: "POST",
          body: JSON.stringify({
            name: name,
            config: config,
            tab: state.activeTab || "default",
          }),
        });
        toast(
          tool.type === "zone"
            ? "Zone " + name + " ajoutee (double-clic pour ouvrir)"
            : "Step " + name + " ajoutee au graphe",
          "success"
        );
        await refreshTabs();
        await refreshGraph();
        await selectStep(name);
      } catch (e) {
        toast("Create: " + e.message, "error");
      }
      return;
    }

    // Fallback dialogue (outils futurs)
    state.pendingTool = tool;
    if (el.newStepDialog) {
      el.newStepTitle.textContent = "Ajouter · " + tool.label;
      el.newStepDesc.textContent = tool.description || "";
      el.newStepName.value = timestampStepName(tool.type);
      el.newStepDialog.showModal();
    }
  }

  defaultConfig(type, name) {
    return defaultConfig(type, name);
  }

  render() {
    this.renderToolbox();
    return this;
  }
}

/** Instance module partagee. */
export const toolbox = new Toolbox();

export function renderToolbox() {
  return toolbox.renderToolbox();
}

/**
 * Nom unique horodate: type_YYYY_MM_DD_hh_mm_ss
 * Ex: dataframe_2026_08_08_14_30_05
 */
export function timestampStepName(type) {
  const d = new Date();
  const stamp =
    d.getFullYear() +
    "_" +
    pad2(d.getMonth() + 1) +
    "_" +
    pad2(d.getDate()) +
    "_" +
    pad2(d.getHours()) +
    "_" +
    pad2(d.getMinutes()) +
    "_" +
    pad2(d.getSeconds());
  const prefix = type === "dataframe" ? "dataframe" : type;
  return prefix + "_" + stamp;
}

/**
 * Config par defaut a la creation — delegue au StepTypeRegistry (F0053-S4).
 * Signature exportee conservee pour tests / bootstrap.
 */
export function defaultConfig(type, name) {
  return stepTypeRegistry.defaultConfig(type, name);
}

/**
 * Ajoute un nœud directement sur le graphe (sans popup).
 * Dataframe: nom dataframe_YYYY_MM_DD_hh_mm_ss puis config a droite.
 */
export async function openNewStep(tool) {
  return toolbox.openNewStep(tool);
}
