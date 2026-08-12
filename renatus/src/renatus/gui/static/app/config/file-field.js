/**
 * Dropzone upload fichier source (F0054-S2).
 */
import { state, el } from "../state.js";
import { toast } from "../api.js";
import { formToYamlEditor } from "./form-sync.js";
import { refreshFieldDisplays, updateFileFieldMode } from "./pencil.js";

export async function uploadLocalFile(file) {
  if (!file) return;
  if (!state.connected) {
    toast("Workspace non connecte", "error");
    return;
  }
  if (state.workspace && state.workspace.read_only) {
    toast("Lecture seule", "error");
    return;
  }
  const body = new FormData();
  body.append("file", file, file.name);
  try {
    const res = await fetch("/gui/upload?subdir=input", {
      method: "POST",
      body: body,
    });
    let data = null;
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) data = await res.json();
    else data = { detail: await res.text() };
    if (!res.ok) {
      const msg = (data && (data.error || data.detail)) || res.statusText;
      throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
    }
    el.cfgFile.value = data.path || "";
    if (el.fileDropStatus) {
      el.fileDropStatus.textContent =
        "Fichier : " + data.path + " (" + (data.size || file.size) + " o)";
    }
    refreshFieldDisplays();
    updateFileFieldMode();
    formToYamlEditor();
    toast(data.message || "Upload OK", "success");
  } catch (e) {
    toast("Upload: " + e.message, "error");
  }
}

export function wireFileDropzone() {
  if (!el.fileDropzone || !el.cfgFilePicker) return;

  el.btnBrowseFile &&
    el.btnBrowseFile.addEventListener("click", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      el.cfgFilePicker.click();
    });

  el.fileDropzone.addEventListener("click", function (ev) {
    if (ev.target === el.btnBrowseFile) return;
    el.cfgFilePicker.click();
  });

  el.cfgFilePicker.addEventListener("change", function () {
    const f = el.cfgFilePicker.files && el.cfgFilePicker.files[0];
    if (f) uploadLocalFile(f);
    el.cfgFilePicker.value = "";
  });

  ["dragenter", "dragover"].forEach(function (evt) {
    el.fileDropzone.addEventListener(evt, function (e) {
      e.preventDefault();
      e.stopPropagation();
      el.fileDropzone.classList.add("dragover");
    });
  });
  ["dragleave", "drop"].forEach(function (evt) {
    el.fileDropzone.addEventListener(evt, function (e) {
      e.preventDefault();
      e.stopPropagation();
      el.fileDropzone.classList.remove("dragover");
    });
  });
  el.fileDropzone.addEventListener("drop", function (e) {
    const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
    if (f) uploadLocalFile(f);
  });
}
