import sys
from pathlib import Path

from .cli import parser_init
from .stage0_source import CobolSource
from .stage1_lines import CobolLines

STAGES = ("source", "lines")


def dump_lines(source: CobolSource) -> None:
    """Imprime as linhas físicas classificadas, uma por linha."""
    for line in CobolLines.from_source(source):
        body = source[line.span.body].rstrip(" ")
        indicator = source[line.span.indicator].rstrip(" ")
        print(f"{line.number:>8} {line.kind.name:<12} {indicator:>1}|{body}")


def main() -> None:
    parser = parser_init(description="Analisador léxico de programas COBOL em formato fixo.")
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
        help="Estágio do pipeline cuja saída será impressa (número ou nome do estágio).",
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


if __name__ == "__main__":
    main()
