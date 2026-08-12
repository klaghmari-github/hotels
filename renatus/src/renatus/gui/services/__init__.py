"""
Sous-modules metier GuiService (F0054-S1).

GuiService reste la facade publique HTTP ; la logique graphe (etc.)
est deleguee ici.
"""

from .graph_ops import GraphOps

__all__ = ["GraphOps"]
