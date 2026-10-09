import sys
from pathlib import Path

from .cli import parser_init


def main() -> None:
    parser = parser_init(
        description="Analisador léxico de programas COBOL em formato fixo."
    )
    parser.add_argument(
        "path",
        type=Path,
        nargs="?",
        help="""
        Caminho para o programa COBOL. Se não for dado, lê o conteúdo do programa direto de
        stdin.
        """,
    )
    args = parser.parse_args()

    raw = sys.stdin.read() if args.path is None else args.path.read_text()

    print(raw)


if __name__ == "__main__":
    main()
