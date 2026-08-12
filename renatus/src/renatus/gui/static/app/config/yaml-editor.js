/**
 * YAML editor: parse/dump, highlight, scroll, status (F0054-S2).
 */
import { el } from "../state.js";
import { escapeHtml } from "../util.js";

export function yamlLib() {
  if (typeof jsyaml === "undefined") {
    throw new Error("js-yaml non charge");
  }
  return jsyaml;
}

export function configToYaml(config) {
  return yamlLib().dump(config, {
    lineWidth: 100,
    noRefs: true,
    sortingKeys: false,
  });
}

export function yamlToConfig(text) {
  const parsed = yamlLib().load(text || "");
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("YAML doit decrire un objet (mapping)");
  }
  return parsed;
}

/**
 * Message d erreur YAML actionnable (ligne / colonne si dispo).
 * js-yaml expose YAMLException.mark { line, column, snippet }.
 */
export function formatYamlError(err) {
  if (!err) return "YAML invalide";
  const reason = err.reason || err.message || String(err);
  if (err.mark && typeof err.mark.line === "number") {
    const line = err.mark.line + 1;
    const col = (err.mark.column || 0) + 1;
    let msg =
      "Erreur parsing YAML — ligne " +
      line +
      ", colonne " +
      col +
      " : " +
      reason;
    if (err.mark.snippet) {
      msg += "\n" + String(err.mark.snippet).trim();
    }
    return msg;
  }
  return "YAML invalide : " + reason;
}

export function spanToken(cls, text) {
  return '<span class="' + cls + '">' + escapeHtml(text) + "</span>";
}

/**
 * Coloration syntaxique legere YAML (cles / valeurs / types).
 * Couvre le sous-ensemble utilise par les steps renatus.
 */
export function highlightYaml(src) {
  const text = src == null ? "" : String(src);
  if (!text) {
    return "";
  }
  const lines = text.split("\n");
  return lines
    .map(function (line) {
      return highlightYamlLine(line);
    })
    .join("\n");
}

export function highlightYamlValue(raw) {
  if (raw === "") return "";
  // commentaire en fin de ligne apres un espace
  const hash = raw.indexOf(" #");
  let value = raw;
  let comment = "";
  if (hash >= 0) {
    value = raw.slice(0, hash);
    comment = raw.slice(hash);
  } else if (/^\s*#/.test(raw)) {
    return spanToken("y-comment", raw);
  }
  const m = value.match(/^(\s*)(.*?)(\s*)$/);
  const lead = m ? m[1] : "";
  const core = m ? m[2] : value;
  const trail = m ? m[3] : "";
  let tokenCls = "y-string";
  if (/^(true|false)$/i.test(core)) tokenCls = "y-bool";
  else if (/^(null|~)$/i.test(core)) tokenCls = "y-null";
  else if (/^[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?$/.test(core)) {
    tokenCls = "y-number";
  }
  let body =
    escapeHtml(lead) + spanToken(tokenCls, core) + escapeHtml(trail);
  if (comment) {
    body += spanToken("y-comment", comment);
  }
  return body;
}

export function highlightYamlLine(line) {
  // ligne commentaire seule
  if (/^\s*#/.test(line)) {
    return spanToken("y-comment", line);
  }
  // ligne vide
  if (line === "") {
    return "";
  }
  // liste: "  - value" ou "  - key: value"
  const listMatch = line.match(/^(\s*)(-)(\s+)(.*)$/);
  if (listMatch) {
    const head =
      escapeHtml(listMatch[1]) +
      spanToken("y-dash", listMatch[2]) +
      escapeHtml(listMatch[3]);
    const rest = listMatch[4];
    // - key: value
    const kv = rest.match(/^([A-Za-z_][\w.-]*)(:)(\s*)(.*)$/);
    if (kv) {
      return (
        head +
        spanToken("y-key", kv[1]) +
        spanToken("y-punct", kv[2]) +
        escapeHtml(kv[3]) +
        highlightYamlValue(kv[4])
      );
    }
    return head + highlightYamlValue(rest);
  }
  // key: value  (cle simple)
  const kvMatch = line.match(
    /^(\s*)([A-Za-z_][\w.-]*|["'][^"']+["'])(:)(\s*)(.*)$/
  );
  if (kvMatch) {
    return (
      escapeHtml(kvMatch[1]) +
      spanToken("y-key", kvMatch[2]) +
      spanToken("y-punct", kvMatch[3]) +
      escapeHtml(kvMatch[4]) +
      (kvMatch[5] === "" ? "" : highlightYamlValue(kvMatch[5]))
    );
  }
  return spanToken("y-plain", line);
}

export function updateYamlHighlight() {
  if (!el.yamlHighlight || !el.editor) return;
  // newline final: aligne hauteur de scroll avec le textarea
  el.yamlHighlight.innerHTML = highlightYaml(el.editor.value) + "\n";
}

export function syncYamlScroll() {
  if (!el.yamlHighlight || !el.editor) return;
  el.yamlHighlight.scrollTop = el.editor.scrollTop;
  el.yamlHighlight.scrollLeft = el.editor.scrollLeft;
}

export function setYamlStatus(msg, kind) {
  if (!el.yamlStatus) return;
  // F0021: n afficher le bandeau que pour les erreurs (pas de messages ok redondants)
  if (kind === "err") {
    el.yamlStatus.textContent = msg || "";
    el.yamlStatus.className = "yaml-status meta err";
    el.yamlStatus.hidden = false;
  } else {
    el.yamlStatus.textContent = "";
    el.yamlStatus.className = "yaml-status meta muted";
    el.yamlStatus.hidden = true;
  }
  if (el.editor) {
    el.editor.classList.toggle("yaml-error", kind === "err");
  }
  if (el.yamlEditor) {
    el.yamlEditor.classList.toggle("is-error", kind === "err");
    el.yamlEditor.classList.toggle("is-ok", kind === "ok");
  }
}
