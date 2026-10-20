import argparse
import inspect
import sys
import textwrap
from pathlib import Path
from typing import Any

from .stage0_raw import CobolRawSource
from .stage1_lines import CobolLines
from .stage2_norm import CobolNormSource
from .stage3_tokens import CobolTokens

STAGES = ("raw", "lines", "norm", "tokens")


def dump_lines(source: CobolRawSource) -> None:
    """Imprime as linhas físicas classificadas, uma por linha."""
    for line in CobolLines.from_raw(source):
        body = source.slice(line.span.body).rstrip(" ")
        indicator = source.slice(line.span.indicator).rstrip(" ")
        print(f"{line.number:>8} {line.kind.name:<12} {indicator:>1}|{body}")


def dump_norm(raw: CobolRawSource, *, include_debug: bool, include_other: bool) -> None:
    """Imprime as linhas lógicas normalizadas com o intervalo de linhas físicas de origem."""
    lines = CobolLines.from_raw(raw)
    norm = CobolNormSource.from_lines(
        lines, include_debug=include_debug, include_other=include_other
    )
    for diagnostic in norm.diagnostics:
        print(diagnostic.format(raw), file=sys.stderr)

    for offset, text in norm.iter_logical_lines():
        start = norm.to_raw_position(offset)
        end = norm.to_raw_position(offset + max(len(text) - 1, 0))
        lines_fmt = f"{start.line}" if start.line == end.line else f"{start.line}-{end.line}"
        print(f"{lines_fmt:>11} |{text}")


def dump_tokens(source: CobolRawSource, *, include_debug: bool, include_other: bool) -> None:
    """Imprime os tokens, um por linha, com a posição crua do início de cada um."""
    lines = CobolLines.from_raw(source)
    norm = CobolNormSource.from_lines(
        lines, include_debug=include_debug, include_other=include_other
    )
    tokens = CobolTokens.from_norm(norm)
    for diagnostic in norm.diagnostics + tokens.diagnostics:
        print(diagnostic.format(source), file=sys.stderr)

    for token in tokens:
        start = tokens.to_raw_position(token)
        print(f"{start!s:>11} {token.kind.name:<20} {token.text}")


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

    def _get_help_string(self, action: argparse.Action) -> str:
        """Adiciona o valor padrão no fim do texto de help."""
        if action.help is None:
            action.help = ""
        else:
            # Remove espaços gerados por strings multiline (""")
            action.help = action.help.strip()

        if (
            "%(default)" not in action.help
            and action.default is not argparse.SUPPRESS
            and not action.required
        ) and (action.option_strings or action.nargs in (argparse.OPTIONAL, argparse.ZERO_OR_MORE)):
            action.help += " (Padrão: %(default)r)"

        return action.help

    def start_section(self, heading: str | None) -> None:
        """Traduz nomes de seções."""
        if heading == "positional arguments":
            heading = "Argumentos posicionais"
        elif heading == "options":
            heading = "Opções"
        super().start_section(heading)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analisador léxico de programas COBOL em formato fixo.",
        formatter_class=_ArgparseFormatter,
        add_help=False,
    )
    parser.add_argument("--help", "-h", action="help", help="Mostra essa mensagem de ajuda.")
    parser.add_argument(
        "path",
        type=Path,
        nargs="?",
        help="""
        Caminho para o programa COBOL. Se não for dado, lê o conteúdo do programa direto de
        stdin.
        """,
    )
    parser.add_argument(
        "--stage",
        choices=[str(x) for pair in enumerate(STAGES) for x in pair],
        default="tokens",
        help="""
        Imprime a saída do estágio selecionado, sem avançar para os próximos (número ou nome
        do estágio).
        """,
    )
    parser.add_argument(
        "--include-debug",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Trata linhas de debug como código (indicador 'D') em vez de ignorá-las.",
    )
    parser.add_argument(
        "--include-other",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="""
        Trata linhas com indicadores desconhecidos como código (por exemplo, marcadores de opção
        do EXEC85: A, B, S, Y) em vez de ignorá-las.
        """,
    )
    args = parser.parse_args()

    if args.path is None:
        source = CobolRawSource("<stdin>", sys.stdin.buffer.read().decode())
    else:
        source = CobolRawSource(str(args.path), args.path.read_text(newline=""))

    match args.stage:
        case "0" | "raw":
            sys.stdout.write(source.text)
        case "1" | "lines":
            dump_lines(source)
        case "2" | "norm":
            dump_norm(source, include_debug=args.include_debug, include_other=args.include_other)
        case "3" | "tokens":
            dump_tokens(source, include_debug=args.include_debug, include_other=args.include_other)


if __name__ == "__main__":
    main()
