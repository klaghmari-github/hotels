"""
Reponses chat pour les questions (pas feature / anomalie).

Sans cle API externe: repond a partir du contexte local (statut file,
features/anomalies, regles de gestion, FAQ projet).
Avec XAI_API_KEY: appelle l API xAI (Grok) pour une reponse plus libre.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from queue_store import QueueStore


def answer_question(text: str, store: "QueueStore") -> str:
    """Produit une reponse assistant pour une question utilisateur."""
    text = (text or "").strip()
    if not text:
        return "Je n ai pas recu de question. Reformule en une phrase."

    # 1) reponses structurees temps-reel (statut PC / file)
    local = _answer_from_local_context(text, store)
    if local:
        return local

    # 2) FAQ regles + historique questions
    faq = _answer_from_knowledge(text, store.gestion_dir)
    if faq:
        return faq

    # 3) LLM xAI si cle presente
    api_key = (
        os.environ.get("XAI_API_KEY")
        or os.environ.get("GROK_API_KEY")
        or os.environ.get("XAI_KEY")
        or ""
    ).strip()
    if api_key:
        try:
            return _answer_via_xai(text, store, api_key)
        except Exception as exc:  # noqa: BLE001
            return (
                _fallback_unknown(text, store)
                + f"\n\n(Note: appel Grok API en echec: {exc})"
            )

    return _fallback_unknown(text, store)


def _norm(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^\w\s\?\%\']", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s)
    return s


def _answer_from_local_context(text: str, store: "QueueStore") -> str | None:
    t = _norm(text)
    st = store.get_status()
    queue = store.list_queue()
    pending = [q for q in queue if q.get("status") == "pending"]
    running = [q for q in queue if q.get("status") == "in_progress"]
    done = [q for q in queue if q.get("status") == "done"]
    feat_open, ano_open = store.count_open_csv()

    # saluts
    if t in {"salut", "hello", "hi", "bonjour", "bonsoir", "hey", "coucou"}:
        return (
            "Salut. Je suis la console Grok de gestion renatus sur ton PC. "
            "Pose une question, ou demande une feature / signale une anomalie. "
            f"Etat: {len(pending)} en file, {len(running)} en cours, "
            f"{feat_open} features ouvertes, {ano_open} anomalies ouvertes."
        )

    # libre / occupe / taches
    if any(
        k in t
        for k in (
            "libre",
            "occupe",
            "occupé",
            "dispo",
            "disponible",
            "tache",
            "tâche",
            "en cours",
            "busy",
            "tu fais quoi",
            "que fais",
            "status",
            "statut",
            "ca avance",
            "ça avance",
        )
    ):
        if running or st.get("thinking"):
            cur = st.get("current_task") or (
                running[0].get("linked_id") or running[0].get("id")
                if running
                else "?"
            )
            thought = st.get("thought") or "travail en cours"
            return (
                f"Je ne suis pas totalement libre: je traite encore "
                f"**{cur}**.\n"
                f"Pensee courante: {thought}\n"
                f"File restante: {len(pending)} · terminees session: {len(done)}\n"
                f"Features ouvertes CSV: {feat_open} · anomalies: {ano_open}."
            )
        if pending:
            return (
                f"Je suis libre de discuter, mais il reste **{len(pending)}** "
                f"demande(s) en file d attente a inscrire/traiter.\n"
                f"Prochaine: {(pending[0].get('text') or '')[:160]}\n"
                f"Features ouvertes: {feat_open} · anomalies: {ano_open}."
            )
        return (
            "Oui, je suis libre pour le moment — file d attente vide.\n"
            f"Features ouvertes (CSV): {feat_open} · anomalies: {ano_open}.\n"
            "Envoie une question, une feature ou un bug quand tu veux."
        )

    # qui es tu
    if any(
        k in t
        for k in (
            "qui es tu",
            "t es qui",
            "tu es qui",
            "c est quoi cette",
            "c'est quoi cette",
            "presentation",
            "présente",
        )
    ):
        return (
            "Je suis l interface web de **gestion renatus** branchee sur ton PC "
            "via tunnel Cloudflare. Je peux:\n"
            "• repondre a des questions (chat)\n"
            "• enregistrer des **features** (Fxxxx) et **anomalies** (Axxxx)\n"
            "• te dire mon statut toutes les minutes\n"
            "Le code produit reste dans `src/renatus/` ; ici c est la couche gestion."
        )

    # lien / url
    if any(k in t for k in ("lien", "url", "adresse", "tunnel")):
        url_path = store.gestion_dir / "agentic" / "web_console" / "PUBLIC_URL.txt"
        url = ""
        if url_path.is_file():
            url = url_path.read_text(encoding="utf-8").strip()
        if url:
            return f"Le lien public actuel est:\n{url}\n(ephemere tant que le tunnel tourne)"
        return "Pas d URL publique enregistree. Relance `./start.sh` dans web_console."

    # derniere feature
    if "derniere feature" in t or "dernière feature" in t or "last feature" in t:
        last = _last_csv_id(store.gestion_dir / "features.csv")
        return f"Derniere feature vue dans features.csv: **{last or 'aucune'}**."

    return None


def _last_csv_id(path: Path) -> str | None:
    if not path.is_file():
        return None
    last = None
    for line in path.read_text(encoding="utf-8").splitlines()[1:]:
        if not line.strip():
            continue
        last = line.split(",", 1)[0].strip()
    return last


def _answer_from_knowledge(text: str, gestion_dir: Path) -> str | None:
    t = _norm(text)
    # questions deja repondues
    qr = gestion_dir / "questions_reponses_.csv"
    if qr.is_file():
        for line in qr.read_text(encoding="utf-8").splitlines()[1:]:
            parts = _split_csv_line(line)
            if len(parts) < 3:
                continue
            q, a = parts[1], parts[2]
            if not q or not a or a.startswith("(en attente"):
                continue
            if _overlap(_norm(q), t) >= 0.45:
                return f"{a}\n\n_(reponse issue du journal questions_reponses_)_"

    # regles de gestion — extraits par mots cles
    rules = gestion_dir / "regles_de_gestion.md"
    if rules.is_file():
        content = rules.read_text(encoding="utf-8")
        hit = _search_bullets(content, t)
        if hit:
            return (
                "D apres les regles de gestion du projet:\n\n"
                + hit
                + "\n\n_(extrait de regles_de_gestion.md)_"
            )

    # themes connus
    themes = {
        (
            "feature",
            "features.csv",
            "backlog",
        ): (
            "Les features sont dans `gestion_projet/features.csv` "
            "(id F00xx, status creee → en cours → terminee). "
            "Une feature majeure peut avoir des sous-stories F00xx-Sn."
        ),
        (
            "anomalie",
            "bug",
            "anomalies",
        ): (
            "Les anomalies sont dans `gestion_projet/anomalies.csv` (A00xx). "
            "En general: gestionnaire + correctif, le test existe deja."
        ),
        (
            "git",
            "branche",
            "merge",
            "fastforward",
        ): (
            "Git fast-forward only: branche feature depuis main, merge → develop "
            "puis develop → main, avec locks pour eviter les merges paralleles."
        ),
        (
            "watchdog",
            "agent",
            "agents",
        ): (
            "Le watchdog ecoute `gestion_projet/` et notifie le gestionnaire. "
            "Une feature implique en general gestionnaire + dev + testeur."
        ),
        (
            "poo",
            "orientee objet",
            "f0053",
            "f0054",
        ): (
            "F0053/F0054 ont structure le code en POO: Steps Python, modules ES "
            "GUI, ConfigPanel, GraphOps. Voir doc/ARCHITECTURE.md."
        ),
        (
            "gui",
            "interface",
            "gui",
        ): (
            "Renatus GUI se lance avec renatus-gui. Console gestion web: "
            "`gestion_projet/web_console/start.sh`."
        ),
    }
    for keys, ans in themes.items():
        if any(k in t for k in keys):
            return ans
    return None


def _split_csv_line(line: str) -> list[str]:
    # simple split tolerant quotes
    out: list[str] = []
    cur = []
    in_q = False
    for ch in line:
        if ch == '"':
            in_q = not in_q
            continue
        if ch == "," and not in_q:
            out.append("".join(cur).strip())
            cur = []
            continue
        cur.append(ch)
    out.append("".join(cur).strip())
    return out


def _overlap(a: str, b: str) -> float:
    wa = set(a.split())
    wb = set(b.split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / max(len(wa), len(wb))


def _search_bullets(md: str, query: str) -> str | None:
    words = [w for w in query.split() if len(w) > 3][:8]
    if not words:
        return None
    bullets = []
    for line in md.splitlines():
        s = line.strip()
        if not s.startswith("-"):
            continue
        low = s.lower()
        score = sum(1 for w in words if w in low)
        if score >= max(1, len(words) // 3):
            bullets.append((score, s.lstrip("- ").strip()))
    if not bullets:
        return None
    bullets.sort(key=lambda x: -x[0])
    return "\n".join(f"• {b}" for _, b in bullets[:4])


def _fallback_unknown(text: str, store: "QueueStore") -> str:
    st = store.get_status()
    return (
        f"Tu as demande: « {text[:300]} »\n\n"
        "Je n ai pas de reponse specialisee en base locale pour ca. "
        "Tu peux:\n"
        "• reformuler plus precisement (git, features, gui, agents…)\n"
        "• choisir le type **Feature** pour que je l inscrive en F00xx\n"
        "• choisir **Anomalie** pour un bug A00xx\n\n"
        f"Etat actuel: {st.get('thought') or 'idle'}\n"
        "Astuce: exporte `XAI_API_KEY` avant `./start.sh` pour des reponses "
        "Grok completes via l API xAI."
    )


def _answer_via_xai(text: str, store: "QueueStore", api_key: str) -> str:
    st = store.get_status()
    system = (
        "Tu es Grok, assistant du projet renatus (pipeline data + GUI). "
        "Reponds en francais, concis et utile. "
        "Contexte statut: "
        f"thinking={st.get('thinking')} task={st.get('current_task')} "
        f"thought={st.get('thought')} "
        f"queue_pending={st.get('queue_pending')}."
    )
    body = {
        "model": os.environ.get("XAI_MODEL", "grok-2-latest"),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ],
        "temperature": 0.4,
    }
    req = urllib.request.Request(
        "https://api.x.ai/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"].strip()
