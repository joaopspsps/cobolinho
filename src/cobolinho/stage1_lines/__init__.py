"""Linhas do formato fixo classificadas pelo indicador."""

import enum
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Self

from cobolinho.stage0_raw import CobolRawSource, Span

# Recortes das áreas por colunas, inclusivas, a partir de 1
COBOL_COLS_SEQUENCE = 1, 6
COBOL_COLS_INDICATOR = 7, 7
COBOL_COLS_A = 8, 11
COBOL_COLS_B = 12, 72
COBOL_COLS_BODY = COBOL_COLS_A[0], COBOL_COLS_B[1]
COBOL_COLS_IDENTIFICATION = 73, 80


class CobolLineKind(enum.Enum):
    """Tipo de linha segundo o indicador."""

    CODE = enum.auto()
    """Linha de código (indicador vazio e corpo não vazio)."""

    BLANK = enum.auto()
    """Linha vazia (indicador e corpo vazios)"""

    COMMENT = enum.auto()
    """Linha de comentário (`*`)."""

    PAGE = enum.auto()
    """Quebra de página (`/`), funciona como comentário."""

    DEBUG = enum.auto()
    """Linha de debug (`D` ou `d`), execução depende de `WITH DEBUGGING MODE`."""

    CONTINUATION = enum.auto()
    """Continuação da linha anterior (`-`)."""

    OTHER = enum.auto()
    """Qualquer outro indicador (por exemplo, marcadores de opção do EXEC85: A, B, S, Y)."""

    @property
    def is_comment_like(self) -> bool:
        """Linha sem efeito no programa (comentário, página ou branco)."""
        return self in (CobolLineKind.BLANK, CobolLineKind.COMMENT, CobolLineKind.PAGE)


@dataclass(slots=True, frozen=True)
class CobolLineSpan:
    """Áreas do formato fixo."""

    full: Span
    """Span da linha inteira, excluindo o terminador (`\\n`, `\\r\\n` ou EOF)."""

    @property
    def sequence(self) -> Span:
        """Span da área de sequência."""
        return self._slice(COBOL_COLS_SEQUENCE)

    @property
    def indicator(self) -> Span:
        """Span da área do indicador."""
        return self._slice(COBOL_COLS_INDICATOR)

    @property
    def a(self) -> Span:
        """Span da área A."""
        return self._slice(COBOL_COLS_A)

    @property
    def b(self) -> Span:
        """Span da área B."""
        return self._slice(COBOL_COLS_B)

    @property
    def body(self) -> Span:
        """Span da área do corpo (A e B)."""
        return self._slice(COBOL_COLS_BODY)

    @property
    def identification(self) -> Span:
        """Span da área de identificação."""
        return self._slice(COBOL_COLS_IDENTIFICATION)

    def _slice(self, cols: tuple[int, int]) -> Span:
        """Span das colunas `col_first` a `col_last` (inclusivas), truncado ao fim da linha."""
        col_first, col_last = cols
        area_start = min(self.full.start + col_first - 1, self.full.end)
        area_end = min(self.full.start + col_last, self.full.end)
        return Span(area_start, area_end)


@dataclass(slots=True, frozen=True)
class CobolLine:
    """Linha do programa recortada nas áreas do formato fixo."""

    number: int
    """Número da linha do arquivo (a partir de 1)."""

    kind: CobolLineKind
    """Tipo de linha segundo o indicador."""

    span: CobolLineSpan
    """Span da linha inteira, excluindo o terminador (`\\n`, `\\r\\n` ou EOF)."""


@dataclass(slots=True, frozen=True)
class CobolLines:
    """Linhas do texto cru classificadas pelo indicador."""

    raw: CobolRawSource = field(repr=False, compare=False)
    lines: list[CobolLine]

    @classmethod
    def from_raw(cls, raw: CobolRawSource) -> Self:
        """Gera as linhas classificadas pelo indicador.

        Para cada linha, `span.full` vem de `CobolRawSource.get_line_span` (ver documentação).
        """
        lines = []

        for number in range(1, raw.line_count + 1):
            line_span = CobolLineSpan(raw.get_line_span(number))
            kind = _classify(raw, line_span)
            line = CobolLine(number, kind, line_span)
            lines.append(line)

        return cls(raw, lines)

    def get_line(self, number: int) -> CobolLine:
        """Obtém a linha `number` (começando em 1)."""
        return self.lines[number - 1]

    def __len__(self) -> int:
        return len(self.lines)

    def __iter__(self) -> Iterator[CobolLine]:
        return iter(self.lines)


# Código interno
# --------------


def _classify(raw: CobolRawSource, line_span: CobolLineSpan) -> CobolLineKind:
    if span := line_span.indicator:
        indicator = raw.slice(span)
    else:
        indicator = " "

    match indicator:
        case " ":
            body = raw.slice(line_span.body)
            body_is_empty = len(body.strip(" ")) == 0
            return CobolLineKind.BLANK if body_is_empty else CobolLineKind.CODE
        case "*":
            return CobolLineKind.COMMENT
        case "/":
            return CobolLineKind.PAGE
        case "D" | "d":
            return CobolLineKind.DEBUG
        case "-":
            return CobolLineKind.CONTINUATION
        case _:
            return CobolLineKind.OTHER
