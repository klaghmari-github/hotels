"""
CLI renatus : oneshot et REPL interactif sur ConnectionPipeline.

Usages:
  python renatus.py <db> <pipeline_dir> p_table_view v_sales
  python -m renatus <db> <pipeline_dir>
  renatus <db> <pipeline_dir> table_view v_achats
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from renatus.pipeline import ConnectionPipeline


# ---------------------------------------------------------------------------
# Affichage
# ---------------------------------------------------------------------------


class ResultPrinter:
    """
    Formate et affiche les resultats CLI (relations DuckDB ou messages).

    Limite d'affichage des lignes pour rester lisible en console.
    """

    DEFAULT_MAX_ROWS = 200

    def __init__(
        self,
        out: TextIO | None = None,
        err: TextIO | None = None,
        max_rows: int = DEFAULT_MAX_ROWS,
    ) -> None:
        self._out = out if out is not None else sys.stdout
        self._err = err if err is not None else sys.stderr
        self.max_rows = max_rows

    def print_ok(self, message: str = "OK") -> None:
        self._out.write(f"{message}\n")
        self._out.flush()

    def print_error(self, message: str) -> None:
        self._err.write(f"Erreur: {message}\n")
        self._err.flush()

    def print_info(self, message: str) -> None:
        self._out.write(f"{message}\n")
        self._out.flush()

    def print_relation(self, relation: Any) -> None:
        """
        Affiche un result set DuckDB en tableau texte simple.

        Si plus de max_rows lignes, tronque et indique le reste.
        """
        columns = [col[0] for col in relation.description]
        # +1 pour detecter le depassement sans tout charger
        rows = relation.limit(self.max_rows + 1).fetchall()
        truncated = len(rows) > self.max_rows
        if truncated:
            rows = rows[: self.max_rows]

        if not columns:
            self._out.write("(aucun resultat)\n")
            self._out.flush()
            return

        str_rows = [
            [self._cell(value) for value in row] for row in rows
        ]
        widths = [len(name) for name in columns]
        for row in str_rows:
            for i, cell in enumerate(row):
                if len(cell) > widths[i]:
                    widths[i] = len(cell)

        header = " | ".join(
            name.ljust(widths[i]) for i, name in enumerate(columns)
        )
        sep = "-+-".join("-" * w for w in widths)
        self._out.write(header + "\n")
        self._out.write(sep + "\n")
        for row in str_rows:
            line = " | ".join(
                cell.ljust(widths[i]) for i, cell in enumerate(row)
            )
            self._out.write(line + "\n")

        count = len(str_rows)
        if truncated:
            self._out.write(
                f"\n({count} lignes affichees, resultat tronque "
                f"a {self.max_rows})\n"
            )
        else:
            self._out.write(f"\n({count} ligne{'s' if count != 1 else ''})\n")
        self._out.flush()

    @staticmethod
    def _cell(value: Any) -> str:
        if value is None:
            return "NULL"
        return str(value)


# ---------------------------------------------------------------------------
# Execution des commandes
# ---------------------------------------------------------------------------


@dataclass
class CommandResult:
    """Resultat d'une commande CLI (relation, message, ou erreur)."""

    ok: bool
    relation: Any = None
    message: str | None = None
    quit: bool = False


class CommandRunner:
    """
    Interprete les tokens de commande et appelle ConnectionPipeline.

    Commandes reconnues:
      p_table_view NAME   — lineage + creation deps + SELECT *
      table_view NAME     — SELECT * si relation existe (pas de lineage)
      process NAME        — process simple (sans requires)
      process_with_requires NAME / un token cle pipeline — avec requires
      p_iteration NAME    — iteration avec requires
      help                — aide
      quit / exit         — quitter le REPL
    """

    HELP_TEXT = """\
Commandes disponibles:
  p_table_view <name>           lineage + creation + SELECT *
  table_view <name>             SELECT * (erreur si absent, sans lineage)
  process <name>                execute l'etape seule
  process_with_requires <name>  execute l'etape et ses dependances
  p_iteration <name>            lance une iteration
  <name>                        si cle pipeline: process_with_requires
  help                          cette aide
  quit / exit                   quitter
"""

    def __init__(self, connection: ConnectionPipeline) -> None:
        self._connection = connection

    @property
    def connection(self) -> ConnectionPipeline:
        return self._connection

    def run(self, tokens: list[str]) -> CommandResult:
        if not tokens:
            return CommandResult(ok=True, message="")

        cmd = tokens[0]
        args = tokens[1:]

        if cmd in {"quit", "exit"}:
            return CommandResult(ok=True, quit=True, message="Au revoir.")

        if cmd == "help":
            return CommandResult(ok=True, message=self.HELP_TEXT.rstrip())

        if cmd == "p_table_view":
            return self._cmd_p_table_view(args)

        if cmd == "table_view":
            return self._cmd_table_view(args)

        if cmd == "process":
            return self._cmd_process(args)

        if cmd == "process_with_requires":
            return self._cmd_process_with_requires(args)

        if cmd == "p_iteration":
            return self._cmd_p_iteration(args)

        # Un seul token = cle pipeline => process_with_requires
        if len(tokens) == 1 and cmd in self._connection.pipeline:
            return self._run_process_with_requires(cmd)

        return CommandResult(
            ok=False,
            message=(
                f"Commande inconnue: {cmd!r}. "
                "Tapez 'help' pour la liste des commandes."
            ),
        )

    def _require_name(self, args: list[str], command: str) -> str:
        if not args:
            raise ValueError(
                f"{command} requiert un nom (ex: {command} v_sales)"
            )
        if len(args) > 1:
            raise ValueError(
                f"{command} n accepte qu un seul argument, recu: {args}"
            )
        return args[0]

    def _cmd_p_table_view(self, args: list[str]) -> CommandResult:
        name = self._require_name(args, "p_table_view")
        if name not in self._connection.pipeline:
            raise KeyError(f"Objet absent du pipeline : {name}")
        relation = self._connection.p_table_view(name)
        return CommandResult(ok=True, relation=relation)

    def _cmd_table_view(self, args: list[str]) -> CommandResult:
        name = self._require_name(args, "table_view")
        if not self._connection.relation_exists(name):
            raise LookupError(
                f"Relation absente de la base : {name} "
                "(table_view ne cree pas de dependances; "
                "utilisez p_table_view pour le lineage)"
            )
        relation = self._connection.table_view(name)
        return CommandResult(ok=True, relation=relation)

    def _cmd_process(self, args: list[str]) -> CommandResult:
        name = self._require_name(args, "process")
        if name not in self._connection.pipeline:
            raise KeyError(f"Objet absent du pipeline : {name}")
        self._connection.process(name)
        return CommandResult(ok=True, message=f"OK process {name}")

    def _cmd_process_with_requires(self, args: list[str]) -> CommandResult:
        name = self._require_name(args, "process_with_requires")
        return self._run_process_with_requires(name)

    def _run_process_with_requires(self, name: str) -> CommandResult:
        if name not in self._connection.pipeline:
            raise KeyError(f"Objet absent du pipeline : {name}")
        self._connection.process_with_requires(name)
        return CommandResult(
            ok=True,
            message=f"OK process_with_requires {name}",
        )

    def _cmd_p_iteration(self, args: list[str]) -> CommandResult:
        name = self._require_name(args, "p_iteration")
        if name not in self._connection.pipeline:
            raise KeyError(f"Objet absent du pipeline : {name}")
        self._connection.p_iteration(name)
        return CommandResult(ok=True, message=f"OK p_iteration {name}")


# ---------------------------------------------------------------------------
# CLI principal
# ---------------------------------------------------------------------------


class RenatusCli:
    """
    Point d'entree POO : connexion DuckDB + pipeline YAML, oneshot ou REPL.

    Arguments:
      db_path       chemin vers le fichier .duckdb
      pipeline_path dossier (ou fichier) YAML du flux (dossier flow/)
      command_tokens tokens de commande oneshot (vide = REPL)
    """

    PROMPT = "renatus> "

    def __init__(
        self,
        db_path: str | Path,
        pipeline_path: str | Path,
        command_tokens: list[str] | None = None,
        read_only: bool = False,
        printer: ResultPrinter | None = None,
        stdin: TextIO | None = None,
    ) -> None:
        self.db_path = Path(db_path).expanduser()
        self.pipeline_path = Path(pipeline_path).expanduser()
        self.command_tokens = list(command_tokens or [])
        self.read_only = read_only
        self._printer = printer if printer is not None else ResultPrinter()
        self._stdin = stdin if stdin is not None else sys.stdin
        self._connection: ConnectionPipeline | None = None
        self._runner: CommandRunner | None = None

    @property
    def connection(self) -> ConnectionPipeline:
        if self._connection is None:
            self._connection = ConnectionPipeline(
                self.db_path,
                self.pipeline_path,
                read_only=self.read_only,
            )
        return self._connection

    @property
    def runner(self) -> CommandRunner:
        if self._runner is None:
            self._runner = CommandRunner(self.connection)
        return self._runner

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None
            self._runner = None

    def __enter__(self) -> RenatusCli:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def run(self) -> int:
        """
        Execute oneshot si des tokens de commande sont fournis, sinon REPL.

        Retourne le code de sortie (0 succes, 1 erreur).
        """
        try:
            # Force l'ouverture (charge YAML + connexion) pour remonter
            # les erreurs de chemin avant la boucle.
            _ = self.connection
        except Exception as exc:
            self._printer.print_error(str(exc))
            return 1

        try:
            if self.command_tokens:
                return self._run_oneshot(self.command_tokens)
            return self._run_repl()
        finally:
            self.close()

    def _run_oneshot(self, tokens: list[str]) -> int:
        try:
            result = self.runner.run(tokens)
        except Exception as exc:
            self._printer.print_error(str(exc))
            return 1

        if not result.ok:
            self._printer.print_error(result.message or "echec")
            return 1

        self._emit(result)
        return 0

    def _run_repl(self) -> int:
        self._printer.print_info(
            "renatus REPL — tapez 'help' pour l'aide, 'quit' pour sortir."
        )
        while True:
            try:
                self._printer._out.write(self.PROMPT)
                self._printer._out.flush()
                line = self._stdin.readline()
            except KeyboardInterrupt:
                self._printer.print_info("\nInterrupted.")
                return 0

            if line == "":
                # EOF (Ctrl-D)
                self._printer.print_info("")
                return 0

            tokens = self.parse_line(line)
            if not tokens:
                continue

            try:
                result = self.runner.run(tokens)
            except Exception as exc:
                self._printer.print_error(str(exc))
                continue

            if not result.ok:
                self._printer.print_error(result.message or "echec")
                continue

            self._emit(result)
            if result.quit:
                return 0

    def _emit(self, result: CommandResult) -> None:
        if result.relation is not None:
            self._printer.print_relation(result.relation)
        elif result.message:
            self._printer.print_ok(result.message)

    @staticmethod
    def parse_line(line: str) -> list[str]:
        """Decoupe une ligne REPL en tokens (split simple, v1)."""
        return line.strip().split()


# ---------------------------------------------------------------------------
# Parsing argv et point d'entree
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="renatus",
        description=(
            "CLI renatus : execute des etapes de pipeline DuckDB "
            "(oneshot ou REPL)."
        ),
    )
    parser.add_argument(
        "db_path",
        help="Chemin vers le fichier DuckDB (ex: main.duckdb)",
    )
    parser.add_argument(
        "pipeline_path",
        help="Dossier ou fichier YAML du flux (dossier flow/)",
    )
    parser.add_argument(
        "command",
        nargs="*",
        help=(
            "Commande oneshot et arguments "
            "(ex: p_table_view v_sales). Absent => REPL."
        ),
    )
    parser.add_argument(
        "--read-only",
        action="store_true",
        default=False,
        help="Ouvre la base en lecture seule (defaut: ecriture autorisee)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """
    Point d'entree script : parse argv, lance RenatusCli, retourne exit code.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    cli = RenatusCli(
        db_path=args.db_path,
        pipeline_path=args.pipeline_path,
        command_tokens=list(args.command),
        read_only=args.read_only,
    )
    return cli.run()


if __name__ == "__main__":
    sys.exit(main())
