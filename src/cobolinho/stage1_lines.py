"""Formato fixo: classificação das linhas pelo indicador."""

import enum
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Self

from .stage0_source import CobolSource, Span

BOUNDS_SEQUENCE = 1, 6
BOUNDS_INDICATOR = 7, 7
BOUNDS_A = 8, 11
BOUNDS_B = 12, 72
BOUNDS_BODY = BOUNDS_A[0], BOUNDS_B[1]
BOUNDS_IDENTIFICATION = 73, 80


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
    """Áreas do formato fixo (colunas inclusivas a partir de 1)."""

    full: Span
    """Span da linha completa."""

    @property
    def sequence(self) -> Span:
        """Span da área de sequência."""
        return self._slice_area(BOUNDS_SEQUENCE)

    @property
    def indicator(self) -> Span:
        """Span da área do indicador."""
        return self._slice_area(BOUNDS_INDICATOR)

    @property
    def a(self) -> Span:
        """Span da área A."""
        return self._slice_area(BOUNDS_A)

    @property
    def b(self) -> Span:
        """Span da área B."""
        return self._slice_area(BOUNDS_B)

    @property
    def body(self) -> Span:
        """Span da área do corpo (A e B)."""
        return self._slice_area(BOUNDS_BODY)

    @property
    def identification(self) -> Span:
        """Span da área de identificação."""
        return self._slice_area(BOUNDS_IDENTIFICATION)

    def _slice_area(self, bounds: tuple[int, int]) -> Span:
        """Span das colunas `col_start` a `col_end` (inclusivas), truncado ao fim da linha."""
        boundary_left, boundary_right = bounds
        area_start = min(self.full.start + boundary_left - 1, self.full.end)
        area_end = min(self.full.start + boundary_right, self.full.end)
        return Span(area_start, area_end)


@dataclass(slots=True, frozen=True)
class CobolLine:
    """Linha do programa recortada nas áreas do formato fixo.

    Todos os spans são offsets no texto cru e são truncados ao fim da linha: numa linha curta,
    as colunas ausentes não têm span.
    """

    number: int
    kind: CobolLineKind
    span: CobolLineSpan


@dataclass(slots=True, frozen=True)
class CobolLines:
    """Linhas físicas de `source` classificadas pelo indicador."""

    source: CobolSource = field(repr=False, compare=False)
    lines: list[CobolLine]

    @classmethod
    def from_source(cls, source: CobolSource) -> Self:
        """Gera as linhas de `source` classificadas pelo indicador."""
        lines = []

        for number in range(1, source.line_count + 1):
            line_span = CobolLineSpan(source.get_line_span(number))
            kind = _classify(source, line_span)
            line = CobolLine(number, kind, line_span)
            lines.append(line)

        return cls(source, lines)

    def get_line(self, number: int) -> CobolLine:
        """Obtém a linha `number` (começando em 1)."""
        return self.lines[number - 1]

    def __len__(self) -> int:
        return len(self.lines)

    def __iter__(self) -> Iterator[CobolLine]:
        return iter(self.lines)


def _classify(source: CobolSource, line_span: CobolLineSpan) -> CobolLineKind:
    if span := line_span.indicator:
        indicator = source[span]
    else:
        indicator = " "

    match indicator:
        case " ":
            body = source[line_span.body]
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
