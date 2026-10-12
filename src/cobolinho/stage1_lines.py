"""Formato fixo: classificação das linhas pelo indicador."""

import enum
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Self

from .stage0_source import CobolSource, Span


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

    @property
    def sequence(self) -> Span:
        """Span da área de sequência."""
        return self._area(1, 6)

    @property
    def indicator(self) -> Span:
        """Span da área do indicador."""
        return self._area(7, 7)

    @property
    def a(self) -> Span:
        """Span da área A."""
        return self._area(8, 11)

    @property
    def b(self) -> Span:
        """Span da área B."""
        return self._area(12, 72)

    @property
    def body(self) -> Span:
        """Span da área do corpo (A e B)."""
        return self._area(8, 72)

    @property
    def identification(self) -> Span:
        """Span da área de identificação."""
        return self._area(73, 80)

    def _area(self, relative_start: int, relative_end: int) -> Span:
        """Span da área dentro do span da linha, truncado ao fim da linha."""
        area_start = min(self.full.start + relative_start - 1, self.full.end)
        area_end = min(self.full.start + relative_end, self.full.end)
        return Span(area_start, area_end)


@dataclass(slots=True, frozen=True)
class CobolLine:
    """Linha física do programa, já recortada nas áreas do formato fixo.

    Todos os spans são offsets no texto cru e são truncados ao fim da linha:
    numa linha curta, as colunas ausentes simplesmente não têm span (espaços
    virtuais).
    """

    number: int
    kind: CobolLineKind
    span: CobolLineSpan


@dataclass(slots=True, frozen=True)
class CobolLines:
    lines: list[CobolLine]

    @classmethod
    def from_source(cls, source: CobolSource) -> Self:
        """Gera as linhas físicas de `source` classificadas pelo indicador."""
        lines = []

        for number in range(1, source.line_count + 1):
            line_span = CobolLineSpan(source.line_span(number))
            kind = _classify(source, line_span)
            line = CobolLine(number, kind, line_span)
            lines.append(line)

        return cls(lines)

    def line(self, number: int) -> CobolLine:
        """Linha `number` começando de 1."""
        return self.lines[number - 1]

    def __len__(self) -> int:
        return len(self.lines)

    def __iter__(self) -> Iterator[CobolLine]:
        return iter(self.lines)


def _classify(source: CobolSource, line_span: CobolLineSpan) -> CobolLineKind:
    if line_span.indicator:
        indicator = source[line_span.indicator]
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
