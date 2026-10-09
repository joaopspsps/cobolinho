"""Utilidades para a CLI."""

import argparse
import inspect
import textwrap
from typing import Any


class _ArgparseFormatter(argparse.HelpFormatter):
    """Formatter argparse traduzido."""

    def _format_usage(self, *args: Any, **kwargs: Any) -> str:
        """Traduz e simplifica a string de uso."""
        t = self._theme  # ty: ignore[unresolved-attribute]
        return f"{t.usage}Uso" + super()._format_usage(*args, **kwargs).removeprefix(
            f"{t.usage}usage"
        )

    def _fill_text(self, text: str, width: int, indent: str) -> str:
        """Formata descrição como docstring sem fazer wrap."""
        del width  # Não usado
        return textwrap.indent(inspect.cleandoc(text), indent)

    def _split_lines(self, text: str, width: int) -> list[str]:
        """Faz wrap de help text."""
        del width  # Não usado
        return textwrap.wrap(inspect.cleandoc(text), 70, break_on_hyphens=False)

    def start_section(self, heading: str | None) -> None:
        """Traduz nomes de seções."""
        if heading == "positional arguments":
            heading = "Argumentos posicionais"
        elif heading == "options":
            heading = "Opções"
        super().start_section(heading)


def parser_init(**kwargs: Any) -> argparse.ArgumentParser:
    """Cria parser argparse com o formatter customizado."""
    kwargs_default: dict[str, Any] = kwargs | {
        "formatter_class": _ArgparseFormatter,
        "add_help": False,
    }
    parser = argparse.ArgumentParser(**kwargs_default)
    parser.add_argument(
        "--help", "-h", action="help", help="Mostra essa mensagem de ajuda."
    )
    return parser
