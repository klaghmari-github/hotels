"""
Stockage file d'attente + messages + statut (gestion only).

Donnees sous gestion_projet/agentic/web_console/ — hors package renatus.
"""

from __future__ import annotations

import csv
import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class QueueStore:
    """Persistance JSON + inscription features/anomalies CSV."""

    def __init__(self, gestion_dir: Path | None = None) -> None:
        if gestion_dir is None:
            # .../gestion_projet/web_console/queue_store.py -> parents[1] = gestion_projet
            gestion_dir = Path(__file__).resolve().parents[1]
        self.gestion_dir = Path(gestion_dir).resolve()
        self.data_dir = self.gestion_dir / "agentic" / "web_console"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.messages_path = self.data_dir / "messages.json"
        self.queue_path = self.data_dir / "queue.json"
        self.status_path = self.data_dir / "status.json"
        self.lock = threading.RLock()
        self._ensure_files()

    def _ensure_files(self) -> None:
        if not self.messages_path.is_file():
            self._write_json(self.messages_path, [])
        if not self.queue_path.is_file():
            self._write_json(self.queue_path, [])
        if not self.status_path.is_file():
            self._write_json(
                self.status_path,
                {
                    "updated_at": _utc_now(),
                    "thinking": False,
                    "current_task": None,
                    "thought": "En attente de demandes.",
                    "queue_pending": 0,
                    "queue_in_progress": 0,
                    "queue_done": 0,
                    "features_open": 0,
                    "anomalies_open": 0,
                    "last_heartbeat": _utc_now(),
                    "message": "Console web prete.",
                },
            )

    @staticmethod
    def _read_json(path: Path) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return [] if path.name != "status.json" else {}

    @staticmethod
    def _write_json(path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp.replace(path)

    def list_messages(self, limit: int = 200) -> list[dict[str, Any]]:
        with self.lock:
            msgs = self._read_json(self.messages_path) or []
            return list(msgs)[-limit:]

    def list_queue(self) -> list[dict[str, Any]]:
        with self.lock:
            return list(self._read_json(self.queue_path) or [])

    def get_status(self) -> dict[str, Any]:
        with self.lock:
            st = self._read_json(self.status_path) or {}
            st.setdefault("updated_at", _utc_now())
            return st

    def update_status(self, **kwargs: Any) -> dict[str, Any]:
        with self.lock:
            st = self._read_json(self.status_path) or {}
            st.update(kwargs)
            st["updated_at"] = _utc_now()
            st["last_heartbeat"] = _utc_now()
            self._write_json(self.status_path, st)
            return st

    def add_user_message(
        self,
        text: str,
        *,
        kind: str = "auto",
        parallel_ok: bool = True,
    ) -> dict[str, Any]:
        """
        Enregistre un message utilisateur + item de file.

        kind: feature | anomaly | question | auto
        """
        text = (text or "").strip()
        if not text:
            raise ValueError("Message vide")
        kind = (kind or "auto").strip().lower()
        if kind not in {"feature", "anomaly", "question", "auto"}:
            kind = "auto"
        if kind == "auto":
            kind = self._guess_kind(text)

        with self.lock:
            msg_id = "M" + uuid.uuid4().hex[:10]
            item_id = "Q" + uuid.uuid4().hex[:10]
            now = _utc_now()
            user_msg = {
                "id": msg_id,
                "role": "user",
                "text": text,
                "kind": kind,
                "queue_id": item_id,
                "created_at": now,
            }
            msgs = self._read_json(self.messages_path) or []
            msgs.append(user_msg)
            self._write_json(self.messages_path, msgs)

        # Chat: reponse immediate hors lock long
        if kind == "question":
            from chat_brain import answer_question

            reply_text = answer_question(text, self)
            with self.lock:
                item = {
                    "id": item_id,
                    "message_id": msg_id,
                    "kind": "question",
                    "text": text,
                    "status": "done",
                    "parallel_ok": True,
                    "linked_id": None,
                    "created_at": now,
                    "started_at": now,
                    "finished_at": _utc_now(),
                    "result_summary": reply_text[:500],
                    "error": None,
                }
                queue = self._read_json(self.queue_path) or []
                queue.append(item)
                self._write_json(self.queue_path, queue)
                try:
                    qid = self.register_question(text, answer=reply_text)
                    item["linked_id"] = qid
                    # re-save queue with linked id
                    queue = self._read_json(self.queue_path) or []
                    for q in queue:
                        if q.get("id") == item_id:
                            q["linked_id"] = qid
                    self._write_json(self.queue_path, queue)
                except Exception:
                    qid = None
                assistant = {
                    "id": "M" + uuid.uuid4().hex[:10],
                    "role": "assistant",
                    "text": reply_text,
                    "kind": "answer",
                    "queue_id": item_id,
                    "created_at": _utc_now(),
                }
                msgs = self._read_json(self.messages_path) or []
                msgs.append(assistant)
                self._write_json(self.messages_path, msgs)
            return {
                "message": user_msg,
                "queue_item": item,
                "ack": assistant,
                "answer": assistant,
            }

        with self.lock:
            item = {
                "id": item_id,
                "message_id": msg_id,
                "kind": kind,
                "text": text,
                "status": "pending",
                "parallel_ok": bool(parallel_ok),
                "linked_id": None,  # Fxxxx / Axxxx
                "created_at": now,
                "started_at": None,
                "finished_at": None,
                "result_summary": None,
                "error": None,
            }
            queue = self._read_json(self.queue_path) or []
            queue.append(item)
            self._write_json(self.queue_path, queue)

            label = "feature" if kind == "feature" else "anomalie"
            assistant = {
                "id": "M" + uuid.uuid4().hex[:10],
                "role": "assistant",
                "text": (
                    f"OK — j ai pris ta demande comme **{label}**. "
                    f"Elle est en file (id {item_id}). "
                    "Le worker l inscrit dans le CSV et le statut "
                    "se met a jour chaque minute. Tu peux en ajouter d autres."
                ),
                "kind": "ack",
                "queue_id": item_id,
                "created_at": now,
            }
            msgs = self._read_json(self.messages_path) or []
            msgs.append(assistant)
            self._write_json(self.messages_path, msgs)
            return {"message": user_msg, "queue_item": item, "ack": assistant}

    @staticmethod
    def _guess_kind(text: str) -> str:
        t = text.lower().strip()
        if any(
            w in t
            for w in (
                "bug",
                "anomalie",
                "casse",
                "erreur",
                "fail",
                "regression",
                "ne marche pas",
            )
        ):
            return "anomaly"
        # chat / questions conversationnelles
        if any(
            w in t
            for w in (
                "question",
                "pourquoi",
                "comment",
                "?",
                "c'est quoi",
                "c est quoi",
                "est ce que",
                "est-ce que",
                "tu es",
                "t es",
                "libre",
                "occupe",
                "occupé",
                "dispo",
                "salut",
                "bonjour",
                "hello",
                "merci",
                "quoi de neuf",
                "ca va",
                "ça va",
                "tu fais",
                "status",
                "statut",
            )
        ) and not any(
            w in t
            for w in (
                "feature",
                "implemente",
                "implémente",
                "ajoute un",
                "ajouter un",
                "creer un",
                "créer un",
            )
        ):
            return "question"
        return "feature"

    def append_assistant(self, text: str, *, queue_id: str | None = None) -> dict:
        with self.lock:
            msg = {
                "id": "M" + uuid.uuid4().hex[:10],
                "role": "assistant",
                "text": text,
                "kind": "status",
                "queue_id": queue_id,
                "created_at": _utc_now(),
            }
            msgs = self._read_json(self.messages_path) or []
            msgs.append(msg)
            self._write_json(self.messages_path, msgs)
            return msg

    def next_pending(self, *, allow_parallel: bool = True) -> dict | None:
        with self.lock:
            queue = self._read_json(self.queue_path) or []
            in_progress = [q for q in queue if q.get("status") == "in_progress"]
            if in_progress and not allow_parallel:
                # si un non-parallel est en cours, rien
                if any(not q.get("parallel_ok", True) for q in in_progress):
                    return None
            for item in queue:
                if item.get("status") != "pending":
                    continue
                if not item.get("parallel_ok", True) and in_progress:
                    continue
                return dict(item)
            return None

    def mark_item(
        self,
        item_id: str,
        *,
        status: str,
        linked_id: str | None = None,
        result_summary: str | None = None,
        error: str | None = None,
    ) -> dict | None:
        with self.lock:
            queue = self._read_json(self.queue_path) or []
            found = None
            for item in queue:
                if item.get("id") != item_id:
                    continue
                item["status"] = status
                if status == "in_progress" and not item.get("started_at"):
                    item["started_at"] = _utc_now()
                if status in {"done", "error", "failed"}:
                    item["finished_at"] = _utc_now()
                if linked_id is not None:
                    item["linked_id"] = linked_id
                if result_summary is not None:
                    item["result_summary"] = result_summary
                if error is not None:
                    item["error"] = error
                found = dict(item)
                break
            self._write_json(self.queue_path, queue)
            return found

    def count_open_csv(self) -> tuple[int, int]:
        """Compte features / anomalies non terminees."""
        feat = self._count_open(self.gestion_dir / "features.csv")
        ano = self._count_open(self.gestion_dir / "anomalies.csv")
        return feat, ano

    @staticmethod
    def _count_open(path: Path) -> int:
        if not path.is_file():
            return 0
        n = 0
        try:
            with path.open(encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    st = (row.get("status") or "").strip().lower()
                    if st not in {"terminee", "terminée", "done", "annulee", "annulée"}:
                        if row.get("id") or row.get("titre"):
                            n += 1
        except OSError:
            return 0
        return n

    def next_feature_id(self) -> str:
        return self._next_id(self.gestion_dir / "features.csv", "F", 4)

    def next_anomaly_id(self) -> str:
        return self._next_id(self.gestion_dir / "anomalies.csv", "A", 4)

    @staticmethod
    def _next_id(path: Path, prefix: str, width: int) -> str:
        max_n = 0
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            for m in re.finditer(rf"\b{prefix}(\d+)\b", text):
                max_n = max(max_n, int(m.group(1)))
        return f"{prefix}{max_n + 1:0{width}d}"

    def register_feature(self, titre: str, description: str) -> str:
        fid = self.next_feature_id()
        path = self.gestion_dir / "features.csv"
        self._append_csv_row(
            path,
            {
                "id": fid,
                "titre": titre[:120],
                "description": description.replace("\n", " ")[:2000],
                "status": "creee",
                "plan": "web_console",
                "temp_dev_total": "",
                "temps_test_total": "",
                "commentaire": "inscrit via web console",
            },
            [
                "id",
                "titre",
                "description",
                "status",
                "plan",
                "temp_dev_total",
                "temps_test_total",
                "commentaire",
            ],
        )
        # spec
        specs = self.gestion_dir / "agentic" / "specs"
        specs.mkdir(parents=True, exist_ok=True)
        (specs / f"{fid}_web.md").write_text(
            f"# {fid}\n\n{description}\n\nSource: web console\n",
            encoding="utf-8",
        )
        return fid

    def register_anomaly(self, titre: str, description: str) -> str:
        aid = self.next_anomaly_id()
        path = self.gestion_dir / "anomalies.csv"
        # detect header
        headers = [
            "id",
            "titre",
            "description",
            "status",
            "plan",
            "temp_dev_total",
            "temps_test_total",
            "commentaire",
        ]
        if path.is_file():
            first = path.read_text(encoding="utf-8").splitlines()[:1]
            if first and "id" in first[0]:
                headers = [h.strip() for h in first[0].split(",")]
        row = {h: "" for h in headers}
        row["id"] = aid
        if "titre" in row:
            row["titre"] = titre[:120]
        if "description" in row:
            row["description"] = description.replace("\n", " ")[:2000]
        if "status" in row:
            row["status"] = "creee"
        if "commentaire" in row:
            row["commentaire"] = "inscrit via web console"
        self._append_csv_row(path, row, headers)
        return aid

    def register_question(self, text: str, answer: str | None = None) -> str:
        path = self.gestion_dir / "questions_reponses_.csv"
        qid = "Q" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        headers = ["id", "question", "reponse", "date"]
        if path.is_file() and path.stat().st_size > 0:
            first = path.read_text(encoding="utf-8").splitlines()[0]
            if "question" in first.lower():
                headers = [h.strip() for h in first.split(",")]
        row = {h: "" for h in headers}
        reply = (answer or "").replace("\n", " ").strip()[:4000] or (
            "(en attente traitement local)"
        )
        # flexible mapping
        for k in row:
            kl = k.lower()
            if "id" == kl:
                row[k] = qid
            elif "question" in kl:
                row[k] = text.replace("\n", " ")[:2000]
            elif "date" in kl:
                row[k] = _utc_now()
            elif "reponse" in kl:
                row[k] = reply
            elif "source" in kl:
                row[k] = "web_console"
        self._append_csv_row(path, row, headers)
        return qid

    def _append_csv_row(
        self, path: Path, row: dict[str, str], headers: list[str]
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_header = not path.is_file() or path.stat().st_size == 0
        with path.open("a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
            if write_header:
                w.writeheader()
            w.writerow({h: row.get(h, "") for h in headers})
