"""
agentic — etat persistant et helpers pour les agents de gestion.

Donnees : gestion_projet/agentic/
Code     : gestion_projet/src/agentic/

Aucun couplage avec le package produit renatus.
"""

from agentic.etat import (
    Etat,
    EtatSchema,
    EtatSchemaError,
    EtatStore,
    GitInfo,
    LocksInfo,
    WatchdogInfo,
)
from agentic.git_check import (
    GitCommandRunner,
    GitStatus,
    GitStatusChecker,
    SubprocessGitRunner,
)
from agentic.paths import AgenticPaths
from agentic.session import AgenticSession

__all__ = [
    "AgenticPaths",
    "AgenticSession",
    "Etat",
    "EtatSchema",
    "EtatSchemaError",
    "EtatStore",
    "GitCommandRunner",
    "GitInfo",
    "GitStatus",
    "GitStatusChecker",
    "LocksInfo",
    "SubprocessGitRunner",
    "WatchdogInfo",
]
