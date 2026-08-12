/**
 * StepType — base OOP pour les types de composants GUI (F0053-S4).
 *
 * Parallele front de pipeline.steps.Step (Python) :
 * defaultConfig / applyVisibility / toConfig / fromConfig.
 */

/**
 * Split requires CSV → liste (sans dependre de config.js).
 * @param {string|string[]|null|undefined} s
 * @returns {string[]}
 */
export function splitRequiresList(s) {
  if (Array.isArray(s)) {
    return s.map(function (x) { return String(x).trim(); }).filter(Boolean);
  }
  return String(s || "")
    .split(",")
    .map(function (x) { return x.trim(); })
    .filter(Boolean);
}

/**
 * Lit les requires depuis le miroir hidden (F0095: plus de checkboxes UI).
 * @param {object} form refs DOM (el)
 * @returns {string[]}
 */
export function readSelectedRequires(form) {
  return splitRequiresList(
    form && form.cfgRequires ? form.cfgRequires.value : ""
  );
}

/**
 * Ecrit le miroir hidden requires.
 * @param {object} form
 * @param {string[]} list
 */
export function writeRequiresMirror(form, list) {
  const arr = Array.isArray(list) ? list : splitRequiresList(list);
  if (form && form.cfgRequires) {
    form.cfgRequires.value = arr.join(", ");
  }
  return arr;
}

/**
 * Classe de base d un type de step front.
 */
export class StepType {
  /**
   * @param {string} type cle YAML (dataframe, table, …)
   */
  constructor(type) {
    this.type = type;
  }

  /**
   * Config par defaut a la creation d un nœud.
   * @param {string} [name] id/label propose
   * @returns {object}
   */
  defaultConfig(name) {
    const label = name || this.type;
    return { type: this.type, label: label };
  }

  /**
   * Visibilite des blocs formulaire (sous-classes surchargent).
   * F0067: ``script`` unifie (SQL ou Python) — plus de champ sql separe.
   * @returns {{file:boolean, mode:boolean, relationName:boolean, requires:boolean, script:boolean, iter:boolean, venv?:boolean}}
   */
  fieldVisibility() {
    return {
      file: false,
      mode: false,
      relationName: false,
      requires: false,
      script: false,
      iter: false,
      venv: false,
      zoneObjects: false,
      zoneWorkers: false,
      zoneRenatusMode: false,
      autoObject: false,
      autoConvert: false,
    };
  }

  /**
   * Applique la visibilite des champs config selon le type.
   * @param {object} formEls refs DOM (el)
   */
  /**
   * Masque/affiche un champ config (attribut hidden + aria).
   * @param {HTMLElement|null|undefined} node
   * @param {boolean} visible
   */
  setFieldVisible(node, visible) {
    if (!node) return;
    if (visible) {
      node.hidden = false;
      node.removeAttribute("hidden");
    } else {
      node.hidden = true;
      node.setAttribute("hidden", "");
    }
  }

  applyVisibility(formEls) {
    if (!formEls) return;
    const v = this.fieldVisibility();
    // Mode (create_*) = table/view uniquement — jamais zone / execute / iterate
    this.setFieldVisible(formEls.fieldFile, !!v.file);
    this.setFieldVisible(formEls.fieldMode, !!v.mode);
    this.setFieldVisible(formEls.fieldRelationName, !!v.relationName);
    this.setFieldVisible(formEls.fieldRequires, !!v.requires);
    // F0067: un seul champ Script (ex-sql + script python)
    const showScript = !!(v.script || v.sql);
    this.setFieldVisible(formEls.fieldScript, showScript);
    this.setFieldVisible(formEls.fieldSql, false);
    this.setFieldVisible(formEls.fieldIter, !!v.iter);
    this.setFieldVisible(formEls.fieldVenv, !!v.venv);
    this.setFieldVisible(formEls.fieldZoneObjects, !!v.zoneObjects);
    this.setFieldVisible(formEls.fieldZoneWorkers, !!v.zoneWorkers);
    this.setFieldVisible(
      formEls.fieldZoneRenatusMode,
      !!v.zoneRenatusMode
    );
    this.setFieldVisible(formEls.fieldAutoObject, !!v.autoObject);
    this.setFieldVisible(formEls.fieldAutoConvert, !!v.autoConvert);
    if (formEls.cfgScriptLabel) {
      formEls.cfgScriptLabel.textContent = "Script";
    }
    // A0011: purger les valeurs des champs masques (evite fuite file sur zone…)
    if (!v.file) {
      if (formEls.cfgFile) formEls.cfgFile.value = "";
      if (formEls.fileDropStatus) {
        formEls.fileDropStatus.textContent = "Aucun fichier selectionne";
      }
      if (formEls.fileSummaryName) formEls.fileSummaryName.textContent = "—";
      if (formEls.fileSummaryPath) formEls.fileSummaryPath.textContent = "—";
      if (formEls.fileSummary) formEls.fileSummary.hidden = true;
    }
    if (!v.mode && formEls.cfgMode) {
      /* mode non applicable — ne pas forcer une valeur persistable */
    }
    if (!v.relationName && formEls.cfgRelationName) {
      formEls.cfgRelationName.value = "";
    }
    if (!showScript) {
      if (formEls.cfgScript) formEls.cfgScript.value = "";
      if (formEls.cfgSql) formEls.cfgSql.value = "";
    }
    if (!v.venv && formEls.cfgVenv) formEls.cfgVenv.value = "";
    if (!v.iter) {
      if (formEls.cfgTarget) formEls.cfgTarget.value = "";
      if (formEls.cfgScenarios) formEls.cfgScenarios.value = "";
      if (formEls.cfgStepView) formEls.cfgStepView.value = "";
    }
    if (!v.requires && formEls.cfgRequires) {
      formEls.cfgRequires.value = "";
    }
    if (!v.zoneObjects && formEls.cfgZoneObjects) {
      formEls.cfgZoneObjects.value = "";
    }
    if (!v.zoneWorkers && formEls.cfgZoneWorkers) {
      formEls.cfgZoneWorkers.value = "auto";
    }
    if (!v.zoneRenatusMode && formEls.cfgZoneRenatusMode) {
      formEls.cfgZoneRenatusMode.value = "required_for_leaves";
    }
  }

  /**
   * Construit la config YAML depuis le formulaire.
   * @param {object} form refs DOM
   * @param {{selected?: string|null}} [ctx] contexte (selected step id)
   * @returns {object}
   */
  toConfig(form, ctx) {
    const config = { type: this.type };
    const label = form && form.cfgName ? form.cfgName.value.trim() : "";
    if (label) config.label = label;
    return config;
  }

  /**
   * Remplit le formulaire depuis une config (champs generiques).
   * @param {object} config
   * @param {object} form refs DOM
   */
  fromConfig(config, form) {
    if (!form || !config) return;
    const cfg = config || {};
    if (form.cfgFile) form.cfgFile.value = cfg.file || "";
    if (form.fileDropStatus) {
      form.fileDropStatus.textContent = cfg.file
        ? "Fichier : " + cfg.file
        : "Aucun fichier selectionne";
    }
    if (form.cfgMode) form.cfgMode.value = cfg.mode || "create_or_replace";
    if (form.cfgRelationName) {
      form.cfgRelationName.value =
        cfg.name != null && String(cfg.name).trim()
          ? String(cfg.name).trim()
          : "";
    }
    const requires = Array.isArray(cfg.requires)
      ? cfg.requires.slice()
      : splitRequiresList(cfg.requires);
    writeRequiresMirror(form, requires);
    // F0067: script unifie (legacy sql accepte en lecture)
    const body =
      cfg.script != null && String(cfg.script)
        ? String(cfg.script)
        : cfg.sql != null
          ? String(cfg.sql)
          : "";
    if (form.cfgScript) form.cfgScript.value = body;
    if (form.cfgSql) form.cfgSql.value = body;
    if (form.cfgVenv) {
      form.cfgVenv.value =
        cfg.venv != null && String(cfg.venv).trim()
          ? String(cfg.venv).trim()
          : "";
    }
    if (form.cfgTarget) form.cfgTarget.value = cfg.target || "";
    if (form.cfgScenarios) form.cfgScenarios.value = cfg.scenarios || "";
    if (form.cfgStepView) form.cfgStepView.value = cfg.step_view || "";
    if (form.cfgName && cfg.label != null && String(cfg.label).trim()) {
      form.cfgName.value = String(cfg.label).trim();
    }
  }
}
