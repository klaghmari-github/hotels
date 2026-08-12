"""
Facade session agentic pour le gestionnaire (et scripts de demarrage).

Responsabilites :
- charger ou creer etat.json
- check git local/remote
- persister le resultat dans l'etat
- lire/ecrire session.md
- helpers agents / features / locks
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentic.etat import Etat, EtatStore, GitInfo
from agentic.git_check import GitStatus, GitStatusChecker
from agentic.paths import AgenticPaths


class AgenticSession:
    """Point d'entree POO pour demarrer ou reprendre une session agents."""

    def __init__(
        self,
        paths: AgenticPaths | None = None,
        store: EtatStore | None = None,
        git_checker: GitStatusChecker | None = None,
        repo_root: str | Path | None = None,
    ):
        self._paths = paths
        self._store = store
        self._git_checker = git_checker
        self._repo_root = Path(repo_root).resolve() if repo_root is not None else None

    @property
    def paths(self) -> AgenticPaths:
        if self._paths is None:
            self._paths = AgenticPaths().ensure()
        return self._paths

    @property
    def store(self) -> EtatStore:
        if self._store is None:
            self._store = EtatStore(paths=self.paths)
        return self._store

    @property
    def git_checker(self) -> GitStatusChecker:
        if self._git_checker is None:
            root = self._repo_root
            if root is None:
                # gestion_projet parent = racine projet typique
                root = self.paths.gestion_dir.parent
            self._git_checker = GitStatusChecker(repo_root=root)
        return self._git_checker

    def load_or_create(self) -> Etat:
        self.paths.ensure()
        return self.store.load_or_create()

    def startup(self, fetch: bool = True) -> dict[str, Any]:
        """
        Demarrage session : etat + check git + persistance.

        Retourne un rapport machine-lisible pour le gestionnaire.
        ok=False si derriere le remote (behind > 0) ou erreur git bloquante.
        """
        etat = self.load_or_create()
        git_status = self.git_checker.check(fetch=fetch)
        self._apply_git_to_etat(etat, git_status)
        self.store.write(etat)

        behind = git_status.behind
        has_hard_error = bool(git_status.error) and git_status.local_tip is None
        ok = (not has_hard_error) and behind == 0

        return {
            "ok": ok,
            "warnings": self._warnings(git_status),
            "git": git_status.to_dict(),
            "etat_path": str(self.paths.etat_path),
            "features_en_cours": list(etat.features_en_cours),
            "anomalies_en_cours": list(etat.anomalies_en_cours),
            "agents": list(etat.agents),
        }

    def _apply_git_to_etat(self, etat: Etat, git_status: GitStatus) -> None:
        etat.git = GitInfo(
            local_branch=git_status.local_branch,
            local_tip=git_status.local_tip,
            remote_tip=git_status.remote_tip,
            ahead=git_status.ahead,
            behind=git_status.behind,
            dirty=git_status.dirty,
            fetch_ok=git_status.fetch_ok,
            checked_at=git_status.checked_at,
            main_local=git_status.main_local,
            main_origin=git_status.main_origin,
            develop_local=git_status.develop_local,
            develop_origin=git_status.develop_origin,
        )

    def _warnings(self, git_status: GitStatus) -> list[str]:
        warnings: list[str] = []
        if not git_status.fetch_ok:
            warnings.append("git fetch a echoue : remote peut etre obsolete")
        if git_status.behind > 0:
            warnings.append(
                f"branche locale derriere le remote de {git_status.behind} commit(s) "
                ": pull/rebase avant de continuer"
            )
        if git_status.ahead > 0:
            warnings.append(
                f"branche locale en avance de {git_status.ahead} commit(s) : penser a push"
            )
        if git_status.dirty:
            warnings.append("working tree non propre (fichiers modifies non commités)")
        if git_status.remote_tip is None and git_status.local_branch:
            warnings.append(
                f"pas de ref remote {git_status.remote}/{git_status.local_branch}"
            )
        if git_status.error:
            warnings.append(git_status.error)
        return warnings

    def write_session_summary(self, text: str) -> None:
        """Ecrit le resume humain de session (session.md)."""
        self.paths.ensure()
        self.paths.session_path.write_text(text, encoding="utf-8")

    def read_session_summary(self) -> str:
        """Lit session.md ou chaine vide si absent."""
        path = self.paths.session_path
        if not path.is_file():
            return ""
        return path.read_text(encoding="utf-8")

    def set_agent(
        self,
        role: str,
        feature: str | None = None,
        status: str = "en_cours",
        notes: str = "",
    ) -> Etat:
        """Ajoute ou met a jour un agent par role dans l'etat."""
        etat = self.load_or_create()
        updated = False
        for agent in etat.agents:
            if agent.get("role") == role:
                agent["feature"] = feature
                agent["status"] = status
                agent["notes"] = notes
                updated = True
                break
        if not updated:
            etat.agents.append(
                {
                    "role": role,
                    "feature": feature,
                    "status": status,
                    "notes": notes,
                }
            )
        self.store.write(etat)
        return etat

    def set_feature_en_cours(self, feature_id: str, active: bool = True) -> Etat:
        """Active ou retire une feature de la liste en cours."""
        etat = self.load_or_create()
        current = list(etat.features_en_cours)
        if active:
            if feature_id not in current:
                current.append(feature_id)
        else:
            current = [f for f in current if f != feature_id]
        etat.features_en_cours = current
        self.store.write(etat)
        return etat

    def set_anomaly_en_cours(self, anomaly_id: str, active: bool = True) -> Etat:
        """Active ou retire une anomalie de la liste en cours."""
        etat = self.load_or_create()
        current = list(etat.anomalies_en_cours)
        if active:
            if anomaly_id not in current:
                current.append(anomaly_id)
        else:
            current = [a for a in current if a != anomaly_id]
        etat.anomalies_en_cours = current
        self.store.write(etat)
        return etat

    def set_lock(self, name: str, holder: str | None) -> Etat:
        """
        Pose ou libere un lock merge.

        name : 'develop' ou 'main'
        holder : id feature (ex. F0007) ou None pour liberer
        """
        if name not in {"develop", "main"}:
            raise ValueError("lock name doit etre 'develop' ou 'main'")
        etat = self.load_or_create()
        if name == "develop":
            etat.locks.develop = holder
        else:
            etat.locks.main = holder
        self.store.write(etat)
        return etat
