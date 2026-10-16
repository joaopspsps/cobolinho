import sys
from pathlib import Path

from .cli import create_parser
from .stage0_source import CobolSource
from .stage1_lines import CobolLines
from .stage2_normalized import NormalizedCobolSource

STAGES = ("source", "lines", "normalized")


def dump_lines(source: CobolSource) -> None:
    """Imprime as linhas físicas classificadas, uma por linha."""
    for line in CobolLines.from_source(source):
        body = source[line.span.body].rstrip(" ")
        indicator = source[line.span.indicator].rstrip(" ")
        print(f"{line.number:>8} {line.kind.name:<12} {indicator:>1}|{body}")


def dump_normalized(source: CobolSource, *, include_debug: bool, include_other: bool) -> None:
    """Imprime as linhas lógicas normalizadas com o intervalo de linhas físicas de origem."""
    lines = CobolLines.from_source(source)
    normalized = NormalizedCobolSource.from_lines(
        lines, include_debug=include_debug, include_other=include_other
    )
    for diagnostic in normalized.diagnostics:
        print(diagnostic.format(source), file=sys.stderr)

    for offset, text in normalized.iter_logical_lines():
        first, _ = normalized.to_raw_line_col(offset)
        last, _ = normalized.to_raw_line_col(offset + max(len(text) - 1, 0))
        lines_fmt = f"{first}" if first == last else f"{first}-{last}"
        print(f"{lines_fmt:>11} |{text}")


def main() -> None:
    parser = create_parser(description="Analisador léxico de programas COBOL em formato fixo.")
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
        default="lines",
        help="""
        Imprime a saída do estágio X, sem avançar para os próximos (número ou nome do
        estágio).
        """,
    )
    parser.add_argument(
        "--include-debug",
        action="store_true",
        help="Trata linhas de debug como código (indicador 'D') em vez de ignorá-las.",
    )
    parser.add_argument(
        "--include-other",
        action="store_true",
        help="""
        Trata linhas com indicadores desconhecidos como código (por exemplo, marcadores de opção
        do EXEC85: A, B, S, Y) em vez de ignorá-las.
        """,
    )
    args = parser.parse_args()

    if args.path is None:
        source = CobolSource("<stdin>", sys.stdin.buffer.read().decode())
    else:
        source = CobolSource(str(args.path), args.path.read_text(newline=""))

    match args.stage:
        case "0" | "source":
            sys.stdout.write(source.text)
        case "1" | "lines":
            dump_lines(source)
        case "2" | "normalized":
            dump_normalized(
                source, include_debug=args.include_debug, include_other=args.include_other
            )


if __name__ == "__main__":
    main()
