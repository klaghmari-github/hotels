"""
Worker local : heartbeat 1 min + traitement de la file web.

- Inscrit les demandes en features.csv / anomalies.csv / questions
- Met a jour status.json toutes les 60s
- Ne touche jamais au package produit renatus/
"""

from __future__ import annotations

import argparse
import signal
import sys
import time
from pathlib import Path

# import local
sys.path.insert(0, str(Path(__file__).resolve().parent))
from queue_store import QueueStore  # noqa: E402


class WebConsoleWorker:
    def __init__(self, store: QueueStore, interval: int = 60) -> None:
        self.store = store
        self.interval = max(15, int(interval))
        self._stop = False

    def stop(self, *_args: object) -> None:
        self._stop = True

    def run(self) -> None:
        self.store.append_assistant(
            "Worker local demarre. Statut remonte toutes les "
            f"{self.interval}s. File d'attente active."
        )
        self.store.update_status(
            thinking=False,
            thought="Worker pret — en attente de demandes.",
            message="Worker demarre",
            current_task=None,
        )
        while not self._stop:
            try:
                self.tick()
            except Exception as exc:  # noqa: BLE001
                self.store.update_status(
                    thinking=False,
                    thought=f"Erreur worker: {exc}",
                    message=str(exc),
                )
            # sleep par pas de 1s pour arret propre
            for _ in range(self.interval):
                if self._stop:
                    break
                time.sleep(1)

    def tick(self) -> None:
        queue = self.store.list_queue()
        pending = [q for q in queue if q.get("status") == "pending"]
        running = [q for q in queue if q.get("status") == "in_progress"]
        done = [q for q in queue if q.get("status") in {"done", "error", "failed"}]
        feat_open, ano_open = self.store.count_open_csv()

        # Traiter un item pending (serie par defaut; parallel_ok reserve)
        item = self.store.next_pending(allow_parallel=False)
        if item is None and not running:
            # essayer parallel si que des parallel_ok pending
            item = self.store.next_pending(allow_parallel=True)

        if item:
            self._process_item(item)
            queue = self.store.list_queue()
            pending = [q for q in queue if q.get("status") == "pending"]
            running = [q for q in queue if q.get("status") == "in_progress"]
            done = [
                q for q in queue if q.get("status") in {"done", "error", "failed"}
            ]

        current = running[0] if running else None
        if current:
            thought = (
                f"Traitement de {current.get('linked_id') or current['id']} "
                f"({current.get('kind')}) : "
                f"{(current.get('text') or '')[:120]}"
            )
            thinking = True
            task = current.get("linked_id") or current["id"]
        elif pending:
            thought = (
                f"{len(pending)} demande(s) en file. "
                f"Prochaine: {(pending[0].get('text') or '')[:100]}"
            )
            thinking = True
            task = pending[0]["id"]
        else:
            thought = (
                "Idle. Aucune demande en file. "
                f"Features ouvertes: {feat_open}, anomalies: {ano_open}."
            )
            thinking = False
            task = None

        self.store.update_status(
            thinking=thinking,
            current_task=task,
            thought=thought,
            queue_pending=len(pending),
            queue_in_progress=len(running),
            queue_done=len(done),
            features_open=feat_open,
            anomalies_open=ano_open,
            message=thought,
        )

    def _process_item(self, item: dict) -> None:
        item_id = item["id"]
        kind = item.get("kind") or "feature"
        text = item.get("text") or ""
        self.store.mark_item(item_id, status="in_progress")
        self.store.update_status(
            thinking=True,
            current_task=item_id,
            thought=f"Inscription {kind}: {text[:100]}",
            message=f"Traitement {item_id}",
        )
        titre = text.strip().split("\n")[0][:80] or "demande web"
        try:
            if kind == "anomaly":
                linked = self.store.register_anomaly(titre, text)
                summary = (
                    f"Anomalie {linked} inscrite dans anomalies.csv. "
                    "Le gestionnaire / agents locaux peuvent la prendre en charge "
                    "sur ce PC (watchdog + session Grok)."
                )
            elif kind == "question":
                # reponse chat si encore pending (ex: message avant fix chat)
                from chat_brain import answer_question

                reply = answer_question(text, self.store)
                linked = self.store.register_question(text, answer=reply)
                summary = reply
                self.store.mark_item(
                    item_id,
                    status="done",
                    linked_id=linked,
                    result_summary=summary[:500],
                )
                self.store.append_assistant(reply, queue_id=item_id)
                return
            else:
                linked = self.store.register_feature(titre, text)
                summary = (
                    f"Feature {linked} inscrite (status creee) dans features.csv. "
                    "Spec web sous agentic/specs/. "
                    "Traitement code sur ce PC via agents / session Grok."
                )
            self.store.mark_item(
                item_id,
                status="done",
                linked_id=linked,
                result_summary=summary,
            )
            self.store.append_assistant(
                f"Termine: {summary}",
                queue_id=item_id,
            )
        except Exception as exc:  # noqa: BLE001
            self.store.mark_item(
                item_id,
                status="error",
                error=str(exc),
                result_summary=f"Echec: {exc}",
            )
            self.store.append_assistant(
                f"Echec traitement {item_id}: {exc}",
                queue_id=item_id,
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Worker console web gestion")
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Secondes entre heartbeats (defaut 60)",
    )
    parser.add_argument(
        "--gestion-dir",
        type=str,
        default=None,
        help="Chemin gestion_projet (auto si omis)",
    )
    args = parser.parse_args()
    gestion = Path(args.gestion_dir) if args.gestion_dir else None
    store = QueueStore(gestion)
    worker = WebConsoleWorker(store, interval=args.interval)
    signal.signal(signal.SIGINT, worker.stop)
    signal.signal(signal.SIGTERM, worker.stop)
    worker.run()


if __name__ == "__main__":
    main()
