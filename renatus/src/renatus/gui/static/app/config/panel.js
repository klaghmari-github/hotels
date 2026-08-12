/**
 * ConfigPanel — controleur UI du panneau config (F0054-S2).
 */
import { el } from "../state.js";
import { UiController } from "../ui-base.js";
import {
  cancelEditField,
  commitEditField,
  enterConfigPresentation,
  startEditField,
  wireConfigPresentation,
} from "./pencil.js";
import { wireFileDropzone } from "./file-field.js";
import {
  buildStep,
  deleteStep,
  flushAutoSave,
  persistCurrentStep,
  saveStepSilent,
  selectStep,
} from "./step-crud.js";
import {
  configFromForm,
  formToYamlEditor,
  syncFormVisibility,
  yamlEditorToForm,
} from "./form-sync.js";

/**
 * Facade OO autour du panneau de configuration step.
 */
export class ConfigPanel extends UiController {
  constructor(root) {
    super(root || (el && el.configForm) || null);
  }

  selectStep(id) {
    return selectStep(id);
  }

  save() {
    // F0083: autosave flush (compat API)
    return flushAutoSave();
  }

  saveSilent() {
    return saveStepSilent();
  }

  persist(opts) {
    return persistCurrentStep(opts || {});
  }

  build() {
    return buildStep();
  }

  delete() {
    return deleteStep();
  }

  enterPresentation() {
    return enterConfigPresentation();
  }

  startEditField(editId) {
    return startEditField(editId);
  }

  cancelEditField(field) {
    return cancelEditField(field);
  }

  commitEditField(field) {
    return commitEditField(field);
  }

  syncVisibility(type) {
    return syncFormVisibility(type);
  }

  formToYaml() {
    return formToYamlEditor();
  }

  yamlToForm() {
    return yamlEditorToForm();
  }

  configFromForm() {
    return configFromForm();
  }

  /** Branche crayons + dropzone fichier. */
  wire() {
    wireConfigPresentation();
    wireFileDropzone();
    return this;
  }

  render() {
    return this;
  }
}

/** Instance module partagee (wrappers + GuiApp). */
export const configPanel = new ConfigPanel();
