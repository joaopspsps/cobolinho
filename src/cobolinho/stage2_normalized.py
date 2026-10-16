"""Texto normalizado: linhas lógicas com continuações colapsadas e mapa para o texto cru."""

import bisect
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Self

from .diagnostics import Diagnostic, Severity
from .stage0_source import CobolSource, Span
from .stage1_lines import BOUNDS_A, BOUNDS_BODY, CobolLine, CobolLineKind, CobolLines

WIDTH_BODY = BOUNDS_BODY[1] - BOUNDS_BODY[0] + 1
"""Tamanho da área do corpo (colunas 8 a 72)."""

WIDTH_A = BOUNDS_A[1] - BOUNDS_A[0] + 1
"""Tamanho da área A."""

QUOTES = "\"'"


@dataclass(slots=True, frozen=True)
class Segment:
    """Trecho contíguo do texto normalizado.

    Um segmento não sintético corresponde caractere a caractere a `raw[raw_start : raw_end]`. Um
    segmento sintético (por exemplo, o preenchimento virtual de um literal continuado numa linha
    curta) não existe no texto cru: tem tamanho zero no texto cru e fica ancorado em `raw_start`.
    """

    norm_start: int
    raw_start: int
    norm_length: int
    synthetic: bool = False

    @property
    def norm_end(self) -> int:
        return self.norm_start + self.norm_length

    @property
    def raw_end(self) -> int:
        return self.raw_start if self.synthetic else self.raw_start + self.norm_length

    def to_raw_offset(self, i: int) -> int:
        """Offset cru do caractere normalizado `i` (que deve estar no segmento ou no seu fim)."""
        return self.raw_start if self.synthetic else self.raw_start + (i - self.norm_start)


@dataclass(slots=True, frozen=True)
class NormalizedCobolSourceMap:
    """Mapa do texto normalizado para offsets do texto cru.

    Os segmentos são ordenados, contíguos e cobrem todo o texto normalizado.
    """

    segments: list[Segment]
    _norm_starts: list[int] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_norm_starts", [s.norm_start for s in self.segments])

    @property
    def norm_length(self) -> int:
        return self.segments[-1].norm_end if self.segments else 0

    def _find_segment_index(self, i: int) -> int:
        if not 0 <= i <= self.norm_length:
            e = IndexError(f"offset normalizado fora do texto: {i}")
            raise e

        if i == self.norm_length:
            return len(self.segments) - 1
        return bisect.bisect_right(self._norm_starts, i) - 1

    def find_segment(self, i: int) -> Segment:
        """Segmento que contém o caractere normalizado `i`."""
        return self.segments[self._find_segment_index(i)]

    def to_raw_offset(self, i: int) -> int:
        """Offset cru do caractere normalizado `i` (`i == len(texto)` mapeia para o fim)."""
        if not self.segments:
            if i != 0:
                e = IndexError(f"offset normalizado fora do texto: {i}")
                raise e
            return 0
        return self.find_segment(i).to_raw_offset(i)

    def to_raw_spans(self, start: int, end: int) -> list[Span]:
        """Converte o intervalo normalizado `[start, end)` em spans crus.

        Um token continuado em várias linhas físicas resulta em vários spans. Caracteres
        sintéticos são omitidos; se o intervalo for vazio ou só sintético, retorna um único
        span vazio na âncora.
        """
        if start > end:
            e = ValueError(f"intervalo inválido: {start}..{end}")
            raise e

        spans = []
        if start < end:
            for segment in self.segments[self._find_segment_index(start) :]:
                if segment.norm_start >= end:
                    break
                if segment.synthetic:
                    continue
                norm_lo = max(start, segment.norm_start)
                norm_hi = min(end, segment.norm_end)
                raw_lo = segment.to_raw_offset(norm_lo)
                raw_hi = segment.to_raw_offset(norm_hi)
                if spans and spans[-1].end == raw_lo:
                    spans[-1] = Span(spans[-1].start, raw_hi)
                else:
                    spans.append(Span(raw_lo, raw_hi))

        if not spans:
            anchor = self.to_raw_offset(start)
            spans.append(Span(anchor, anchor))

        return spans


@dataclass(slots=True)
class _Builder:
    """Acumulador do texto normalizado e dos segmentos do mapa."""

    source: CobolSource
    parts: list[str] = field(default_factory=list)
    segments: list[Segment] = field(default_factory=list)
    norm_length: int = 0

    def add_raw(self, span: Span) -> None:
        if not span:
            return
        self.parts.append(self.source[span])
        last = self.segments[-1] if self.segments else None
        if last is not None and not last.synthetic and last.raw_end == span.start:
            self.segments[-1] = Segment(
                last.norm_start, last.raw_start, last.norm_length + len(span)
            )
        else:
            self.segments.append(Segment(self.norm_length, span.start, len(span)))
        self.norm_length += len(span)

    def add_synthetic(self, text: str, anchor: int) -> None:
        if not text:
            return
        self.parts.append(text)
        last = self.segments[-1] if self.segments else None
        if last is not None and last.synthetic and last.raw_start == anchor:
            self.segments[-1] = Segment(last.norm_start, anchor, last.norm_length + len(text), True)
        else:
            self.segments.append(Segment(self.norm_length, anchor, len(text), True))
        self.norm_length += len(text)


@dataclass(slots=True, frozen=True)
class NormalizedCobolSource:
    """Texto normalizado: linhas lógicas, com continuações colapsadas.

    Cada linha lógica contém o corpo (colunas 8 a 72) da sua primeira linha física, seguido pelos
    trechos das linhas de continuação. Linhas de comentário e em branco são omitidas.
    """

    lines: CobolLines = field(repr=False, compare=False)
    text: str
    map: NormalizedCobolSourceMap
    diagnostics: list[Diagnostic]

    @classmethod
    def from_lines(
        cls, lines: CobolLines, *, include_debug: bool = False, include_other: bool = True
    ) -> Self:
        """Normaliza `lines`.

        Parameters
        ----------
        include_debug:
            Inclui linhas de debug (`D`).
        include_other:
            Inclui como código linhas com indicadores desconhecidos (por exemplo, marcadores de
            opção do EXEC85)
        """
        source = lines.source
        diagnostics = []
        groups = _group_lines(lines, diagnostics, include_other, include_debug)

        builder = _Builder(source)
        newline_offset = None
        for group in groups:
            mark = (len(builder.parts), len(builder.segments), builder.norm_length)
            if newline_offset is not None:
                builder.add_raw(Span(newline_offset, newline_offset + 1))
            line_start = builder.norm_length
            _build_logical_line(source, group, builder, diagnostics)

            if builder.norm_length == line_start:
                # Linha lógica vazia: desfaz o newline adicionado
                parts_len, segments_len, builder.norm_length = mark
                del builder.parts[parts_len:]
                del builder.segments[segments_len:]
                continue

            newline_offset = _find_newline_offset(source, group[-1])

        text = "".join(builder.parts)
        return cls(lines, text, NormalizedCobolSourceMap(builder.segments), diagnostics)

    @property
    def source(self) -> CobolSource:
        """Atalho para `lines.source`."""
        return self.lines.source

    def to_raw_line_col(self, i: int) -> tuple[int, int]:
        """`(linha, coluna)` crus do caractere normalizado `i`."""
        return self.source.to_line_col(self.map.to_raw_offset(i))

    def format_location(self, i: int) -> str:
        """Formata o caractere normalizado `i` como `nome:linha:coluna` crus."""
        return self.source.format_location(self.map.to_raw_offset(i))

    def to_raw_col(self, i: int) -> int:
        """Coluna crua (começando em 1) do caractere normalizado `i`."""
        return self.to_raw_line_col(i)[1]

    def starts_in_area_a(self, i: int) -> bool:
        """Indica se o caractere normalizado `i` está na área A (colunas 8 a 11)."""
        if i >= self.map.norm_length or self.map.find_segment(i).synthetic:
            return False
        return 8 <= self.to_raw_col(i) < 8 + WIDTH_A

    def iter_logical_lines(self) -> Iterator[tuple[int, str]]:
        """Itera sobre `(offset normalizado, texto)` de cada linha lógica."""
        if not self.text:
            return

        offset = 0
        for line in self.text.split("\n"):
            yield offset, line
            offset += len(line) + 1


def _find_newline_offset(source: CobolSource, line: CobolLine) -> int:
    """Offset do `\\n` que termina a linha física `line`."""
    end = line.span.full.end
    if source.text.startswith("\r\n", end):
        return end + 1
    return end


def _group_lines(
    lines: CobolLines,
    diagnostics: list[Diagnostic],
    include_other: bool,
    include_debug: bool,
) -> list[list[CobolLine]]:
    """Agrupa as linhas físicas relevantes em linhas lógicas."""
    groups: list[list[CobolLine]] = []
    skipping = False  # Linha excluída: suas continuações também são excluídas

    for line in lines:
        kind = line.kind
        if kind.is_comment_like:
            continue

        if (kind is CobolLineKind.DEBUG and not include_debug) or (
            kind is CobolLineKind.OTHER and not include_other
        ):
            skipping = True
            continue

        if kind is CobolLineKind.CONTINUATION:
            if skipping:
                continue
            if groups:
                groups[-1].append(line)
                continue
            message = "linha de continuação sem linha de código anterior"
            diagnostics.append(Diagnostic(Severity.ERROR, message, line.span.indicator))

        skipping = False
        groups.append([line])

    return groups


def _build_logical_line(
    source: CobolSource,
    group: list[CobolLine],
    builder: _Builder,
    diagnostics: list[Diagnostic],
) -> None:
    """Adiciona ao builder a linha lógica formada pelas linhas físicas de `group`."""
    parts_start = len(builder.parts)
    first, *continuations = group
    pending = first.span.body  # Trecho pendente, ainda sem strip_end
    pending_body = pending  # Corpo da linha física de `pending`

    for line in continuations:
        logical_text = "".join(builder.parts[parts_start:]) + source[pending]
        quote = _find_open_quote(logical_text)
        body = line.span.body
        content = _strip_start(source, body)

        if content and content.start - body.start < WIDTH_A:
            message = "continuação com conteúdo na área A"
            diagnostics.append(
                Diagnostic(Severity.ERROR, message, Span(content.start, content.start + 1))
            )

        if quote is None:
            builder.add_raw(_strip_end(source, pending))
            pending, pending_body = content, body
            continue

        # Literal aberto: estende até a coluna 72, com preenchimento virtual se a linha for curta
        builder.add_raw(pending)
        padding = WIDTH_BODY - (pending.end - pending_body.start)
        builder.add_synthetic(" " * padding, pending.end)
        pending_body = body
        if content and source[content.start] == quote:
            pending = Span(content.start + 1, content.end)
        else:
            message = f"continuação de literal deve começar com {quote}"
            where = Span(content.start, content.start + 1) if content else line.span.indicator
            diagnostics.append(Diagnostic(Severity.ERROR, message, where))
            pending = content

    builder.add_raw(_strip_end(source, pending))


def _strip_start(source: CobolSource, span: Span) -> Span:
    """Remove espaços do início do span."""
    text = source[span].lstrip(" ")
    return Span(span.end - len(text), span.end)


def _strip_end(source: CobolSource, span: Span) -> Span:
    """Remove espaços do fim do span."""
    text = source[span].rstrip(" ")
    return Span(span.start, span.start + len(text))


def _find_open_quote(text: str) -> str | None:
    """Encontra aspa do literal alfanumérico que continua aberto no fim de `text`, se houver.

    Aspas duplicadas dentro do literal são escapes; uma aspa no fim do texto fecha o literal.
    """
    quote: str | None = None
    i = 0
    while i < len(text):
        c = text[i]
        if quote is None:
            if c in QUOTES:
                quote = c
        elif c == quote:
            if text.startswith(quote, i + 1):
                i += 1
            else:
                quote = None
        i += 1
    return quote
