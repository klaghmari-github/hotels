/**
 * Auto-zone templates (F0128 / F0139).
 *
 * F0139: a la creation → zone physique (type zone). Ces StepType ne servent
 * qu a d eventuels YAML legacy encore charges en lecture seule + convert.
 * flatzone | allzone | backzone | forzone | bidzone
 */
import { StepType } from "./base.js";

function autoVisibility() {
  return {
    file: false,
    mode: false,
    relationName: false,
    requires: false,
    sql: false,
    iter: false,
    script: false,
    venv: false,
    zoneObjects: true,
    zoneWorkers: false,
    zoneRenatusMode: false,
  };
}

export class AutoZoneStepType extends StepType {
  constructor(type) {
    super(type || "flatzone");
  }

  defaultConfig(name) {
    const label = name || this.type;
    const cfg = { type: this.type, label: label };
    if (this.type === "flatzone" || this.type === "allzone") {
      cfg.parent = "default";
    } else {
      cfg.object = "";
    }
    return cfg;
  }

  fieldVisibility() {
    const v = autoVisibility();
    const flat = this.type === "flatzone" || this.type === "allzone";
    v.autoObject = !flat;
    v.autoConvert = true;
    v.zoneObjects = true;
    return v;
  }

  applyVisibility(formEls) {
    super.applyVisibility(formEls);
    const pencils = formEls.configForm
      ? formEls.configForm.querySelectorAll(".btn-pencil")
      : [];
    pencils.forEach(function (p) {
      p.hidden = true;
      p.setAttribute("hidden", "");
    });
  }

  toConfig(form, ctx) {
    const label = form.cfgName ? form.cfgName.value.trim() : "";
    const cfg = {
      type: this.type,
      label: label || this.type,
    };
    if (
      this.type !== "flatzone" &&
      this.type !== "allzone" &&
      form.cfgAutoObject
    ) {
      const o = form.cfgAutoObject.value.trim();
      if (o) cfg.object = o;
    }
    return cfg;
  }

  fromConfig(config, form) {
    super.fromConfig(config, form);
    const cfg = config || {};
    if (form.cfgAutoObject) {
      form.cfgAutoObject.value = cfg.object || cfg.parent || "";
      form.cfgAutoObject.readOnly = true;
      form.cfgAutoObject.disabled = true;
    }
    if (form.cfgName) {
      form.cfgName.readOnly = true;
    }
    if (form.editor) {
      form.editor.readOnly = true;
    }
  }
}

export class FlatZoneStepType extends AutoZoneStepType {
  constructor() {
    super("flatzone");
  }
}
export class AllZoneStepType extends AutoZoneStepType {
  constructor() {
    super("allzone");
  }
}
export class BackZoneStepType extends AutoZoneStepType {
  constructor() {
    super("backzone");
  }
}
export class ForZoneStepType extends AutoZoneStepType {
  constructor() {
    super("forzone");
  }
}
export class BidZoneStepType extends AutoZoneStepType {
  constructor() {
    super("bidzone");
  }
}
