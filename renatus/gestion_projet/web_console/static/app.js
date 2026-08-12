/**
 * Console gestion — poll statut 60s + messages 5s.
 */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const el = {
    chip: $("status-chip"),
    thought: $("thought"),
    qPending: $("q-pending"),
    qRunning: $("q-running"),
    qDone: $("q-done"),
    fOpen: $("f-open"),
    aOpen: $("a-open"),
    heartbeat: $("heartbeat"),
    messages: $("messages"),
    queue: $("queue"),
    form: $("composer"),
    text: $("text"),
    kind: $("kind"),
    parallel: $("parallel"),
  };

  async function api(path, options) {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      ...options,
    });
    const data = await res.json().catch(function () {
      return {};
    });
    if (!res.ok) {
      throw new Error(data.detail || data.error || res.statusText);
    }
    return data;
  }

  function fmtTime(iso) {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleString();
    } catch (_) {
      return iso;
    }
  }

  async function refreshStatus() {
    try {
      const st = await api("/api/status");
      el.thought.textContent = st.thought || st.message || "—";
      el.qPending.textContent = st.queue_pending != null ? st.queue_pending : "0";
      el.qRunning.textContent = st.queue_in_progress != null ? st.queue_in_progress : "0";
      el.qDone.textContent = st.queue_done != null ? st.queue_done : "0";
      el.fOpen.textContent = st.features_open != null ? st.features_open : "0";
      el.aOpen.textContent = st.anomalies_open != null ? st.anomalies_open : "0";
      el.heartbeat.textContent = fmtTime(st.last_heartbeat || st.updated_at);
      el.chip.textContent = st.thinking
        ? "Reflexion · " + (st.current_task || "…")
        : "Idle";
      el.chip.className = "chip " + (st.thinking ? "thinking" : "idle");
    } catch (e) {
      el.thought.textContent = "Statut indisponible: " + e.message;
      el.chip.textContent = "Offline";
      el.chip.className = "chip idle";
    }
  }

  function renderMessages(list) {
    el.messages.innerHTML = "";
    (list || []).forEach(function (m) {
      const div = document.createElement("div");
      div.className = "bubble " + (m.role === "user" ? "user" : "assistant");
      const meta = document.createElement("span");
      meta.className = "meta";
      meta.textContent =
        (m.role === "user" ? "Toi" : "Grok") +
        " · " +
        fmtTime(m.created_at) +
        (m.kind === "answer"
          ? " · reponse"
          : m.kind === "ack"
            ? " · accusé"
            : m.kind
              ? " · " + m.kind
              : "");
      div.appendChild(meta);
      div.appendChild(document.createTextNode(m.text || ""));
      el.messages.appendChild(div);
    });
    el.messages.scrollTop = el.messages.scrollHeight;
  }

  function renderQueue(list) {
    el.queue.innerHTML = "";
    if (!list || !list.length) {
      el.queue.textContent = "File vide.";
      return;
    }
    list
      .slice()
      .reverse()
      .forEach(function (q) {
        const div = document.createElement("div");
        div.className = "q-item";
        const badge = document.createElement("span");
        badge.className = "badge " + (q.status || "pending");
        badge.textContent = q.status || "pending";
        div.appendChild(badge);
        const id = document.createElement("span");
        id.className = "id";
        id.textContent = (q.linked_id || q.id) + " ";
        div.appendChild(id);
        div.appendChild(
          document.createTextNode(
            "[" +
              (q.kind || "?") +
              "] " +
              (q.text || "").slice(0, 140) +
              (q.result_summary ? " → " + q.result_summary.slice(0, 100) : "")
          )
        );
        el.queue.appendChild(div);
      });
  }

  async function refreshMessages() {
    try {
      const data = await api("/api/messages?limit=150");
      renderMessages(data.messages || []);
    } catch (_) {}
  }

  async function refreshQueue() {
    try {
      const data = await api("/api/queue");
      renderQueue(data.queue || []);
    } catch (_) {}
  }

  el.form.addEventListener("submit", async function (ev) {
    ev.preventDefault();
    const text = el.text.value.trim();
    if (!text) return;
    const btn = el.form.querySelector("button");
    btn.disabled = true;
    try {
      await api("/api/messages", {
        method: "POST",
        body: JSON.stringify({
          text: text,
          kind: el.kind.value,
          parallel_ok: el.parallel.checked,
        }),
      });
      el.text.value = "";
      await refreshMessages();
      await refreshQueue();
      await refreshStatus();
    } catch (e) {
      alert("Envoi: " + e.message);
    } finally {
      btn.disabled = false;
    }
  });

  // Poll: statut 60s (demande user), messages/file plus souvent
  refreshStatus();
  refreshMessages();
  refreshQueue();
  setInterval(refreshStatus, 60000);
  setInterval(function () {
    refreshMessages();
    refreshQueue();
  }, 5000);
})();
