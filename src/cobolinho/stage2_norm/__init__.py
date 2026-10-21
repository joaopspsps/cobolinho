"""Texto normalizado: linhas lógicas com continuações colapsadas e mapa para o texto cru."""

import bisect
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Self

from cobolinho.diagnostics import Diagnostic, DiagnosticSeverity
from cobolinho.stage0_raw import CobolRawSource, Position, Span
from cobolinho.stage1_lines import (
    COBOL_COLS_A,
    COBOL_COLS_BODY,
    CobolLine,
    CobolLineKind,
    CobolLines,
)

COBOL_QUOTES = "\"'"


@dataclass(slots=True, frozen=True)
class CobolNormSegment:
    """Trecho contíguo do texto normalizado.

    Um segmento não sintético corresponde caractere a caractere a `raw.text[raw_start :
    raw_end]`. Um segmento sintético (por exemplo, o preenchimento virtual de um literal continuado
    numa linha curta) não existe no texto cru: tem tamanho zero no texto cru e fica ancorado em
    `raw_start`.
    """

    raw_start: int
    norm_start: int
    length: int
    synthetic: bool = False

    @property
    def norm_end(self) -> int:
        return self.norm_start + self.length

    @property
    def raw_end(self) -> int:
        return self.raw_start if self.synthetic else self.raw_start + self.length

    def to_raw_offset(self, offset: int) -> int:
        """Offset cru do offset normalizado (deve estar no segmento ou no seu fim)."""
        return self.raw_start if self.synthetic else self.raw_start + offset - self.norm_start


@dataclass(slots=True, frozen=True)
class CobolNormSource:
    """Texto normalizado: linhas lógicas, com continuações colapsadas.

    Cada linha lógica contém o corpo (colunas 8 a 72) da sua primeira linha física, seguido pelos
    trechos das linhas de continuação.

    `segments` mapeia o texto normalizado para offsets do texto cru: os segmentos são ordenados,
    contíguos e cobrem todo o texto normalizado.
    """

    lines: CobolLines = field(repr=False, compare=False)
    text: str
    segments: list[CobolNormSegment]
    diagnostics: list[Diagnostic]
    _norm_starts: list[int] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Valida a cobertura dos segmentos e salva `_norm_starts` de antemão.

        Montar `_norm_starts` é O(N), enquanto que `bisect_right` é O(log N). Se isso fosse feito
        dentro de `_find_segment_index`, atolaria a eficiência do bisect.
        """
        norm_end = self.segments[-1].norm_end if self.segments else 0
        if norm_end != len(self.text):
            e = ValueError(
                f"segmentos cobrem {norm_end} caracteres, mas o texto tem {len(self.text)}"
            )
            raise e
        object.__setattr__(self, "_norm_starts", [s.norm_start for s in self.segments])

    @classmethod
    def from_lines(
        cls, lines: CobolLines, *, include_debug: bool = False, include_other: bool = True
    ) -> Self:
        """Normaliza `lines`.

        Linhas de comentário e em branco são sempre excluídas.

        Parameters
        ----------
        include_debug:
            Inclui linhas de debug (`D`).
        include_other:
            Inclui linhas com indicadores desconhecidos (por exemplo, marcadores de opção do
            EXEC85).
        """
        diagnostics = []
        groups = _group_lines(lines, diagnostics, include_other, include_debug)
        builder = _Builder(lines.raw)
        newline_offset = None

        for group in groups:
            builder_backtrack = len(builder.parts), len(builder.segments), builder.norm_length
            if newline_offset is not None:
                builder.add_raw(Span(newline_offset, newline_offset + 1))
            line_start = builder.norm_length
            _build_logical_line(lines.raw, group, builder, diagnostics)
            if builder.norm_length == line_start:
                # Linha lógica vazia: desfaz o newline adicionado.
                #
                # O newline é adicionado antes da linha lógica, então só é mantido se houver
                # uma linha lógica não vazia depois dele. Logo, a linha física anterior nunca é
                # a última, e o offset de `_find_newline_offset` sempre contém `\n`.
                orig_len_parts, orig_len_segments, orig_norm_length = builder_backtrack
                del builder.parts[orig_len_parts:]
                del builder.segments[orig_len_segments:]
                builder.norm_length = orig_norm_length
                continue
            newline_offset = _find_newline_offset(lines.raw, group[-1])

        text = "".join(builder.parts)
        return cls(lines, text, builder.segments, diagnostics)

    @property
    def raw(self) -> CobolRawSource:
        """Atalho para o texto cru."""
        return self.lines.raw

    def _find_segment_index(self, offset: int) -> int:
        if not 0 <= offset <= len(self.text):
            e = IndexError(f"offset normalizado fora do texto: {offset}")
            raise e

        if offset == len(self.text):
            return len(self.segments) - 1

        return bisect.bisect_right(self._norm_starts, offset) - 1

    def find_segment(self, offset: int) -> CobolNormSegment:
        """Segmento que contém o offset normalizado."""
        return self.segments[self._find_segment_index(offset)]

    def to_raw_offset(self, offset: int) -> int:
        """Offset cru do offset normalizado (mapeia para o fim quando offset == `len(text)`)."""
        index = self._find_segment_index(offset)
        if index < 0:
            # Texto vazio: o único offset válido é 0
            return 0
        return self.segments[index].to_raw_offset(offset)

    def to_raw_spans(self, span: Span) -> list[Span]:
        """Converte o span normalizado em spans de offsets crus.

        Um token continuado em várias linhas físicas resulta em vários spans. Caracteres
        sintéticos são omitidos; se o intervalo for vazio ou só sintético, retorna um único
        span vazio na âncora.
        """
        spans = []
        if span.start < span.end:
            for i in range(self._find_segment_index(span.start), len(self.segments)):
                segment = self.segments[i]
                if segment.norm_start >= span.end:
                    break
                if segment.synthetic:
                    continue

                norm_lo = max(span.start, segment.norm_start)
                norm_hi = min(span.end, segment.norm_end)
                raw_lo = segment.to_raw_offset(norm_lo)
                raw_hi = segment.to_raw_offset(norm_hi)

                if spans and spans[-1].end == raw_lo:
                    spans[-1] = Span(spans[-1].start, raw_hi)
                else:
                    spans.append(Span(raw_lo, raw_hi))

        if not spans:
            anchor = self.to_raw_offset(span.start)
            spans.append(Span(anchor, anchor))

        return spans

    def to_raw_position(self, offset: int) -> Position:
        """Posição crua do offset normalizado."""
        return self.raw.to_position(self.to_raw_offset(offset))

    def format_location(self, offset: int) -> str:
        """Formata o offset normalizado como `nome:linha:coluna` crus."""
        return self.raw.format_location(self.to_raw_offset(offset))

    def starts_in_area_a(self, offset: int) -> bool:
        """Indica se o offset normalizado está na área A."""
        if offset >= len(self.text) or self.find_segment(offset).synthetic:
            return False
        return COBOL_COLS_A[0] <= self.to_raw_position(offset).col <= COBOL_COLS_A[1]

    def iter_logical_lines(self) -> Iterator[tuple[int, str]]:
        """Itera sobre `(offset normalizado, texto)` de cada linha lógica."""
        if not self.text:
            return

        offset = 0
        for line in self.text.split("\n"):
            yield offset, line
            offset += len(line) + 1

    def slice(self, span: Span) -> str:
        """Obtém uma porção do texto normalizado com um span."""
        return self.text[span.start : span.end]


# Código interno
# --------------


_WIDTH_BODY = COBOL_COLS_BODY[1] - COBOL_COLS_BODY[0] + 1
_WIDTH_A = COBOL_COLS_A[1] - COBOL_COLS_A[0] + 1


@dataclass(slots=True)
class _Builder:
    """Acumulador das partes do texto normalizado e dos segmentos do mapa."""

    raw: CobolRawSource
    parts: list[str] = field(default_factory=list)
    segments: list[CobolNormSegment] = field(default_factory=list)
    norm_length: int = 0

    def add_raw(self, span: Span) -> None:
        if not span:
            return
        self.parts.append(self.raw.slice(span))
        last = self.segments[-1] if self.segments else None
        if last is not None and not last.synthetic and last.raw_end == span.start:
            # Junta ao último segmento cru
            self.segments[-1] = CobolNormSegment(
                last.raw_start, last.norm_start, last.length + len(span)
            )
        else:
            self.segments.append(CobolNormSegment(span.start, self.norm_length, len(span)))
        self.norm_length += len(span)

    def add_synthetic(self, text: str, anchor: int) -> None:
        if not text:
            return
        self.parts.append(text)
        last = self.segments[-1] if self.segments else None
        if last is not None and last.synthetic and last.raw_start == anchor:
            # Junta ao último segmento sintético
            self.segments[-1] = CobolNormSegment(
                anchor, last.norm_start, last.length + len(text), True
            )
        else:
            self.segments.append(CobolNormSegment(anchor, self.norm_length, len(text), True))
        self.norm_length += len(text)


def _find_newline_offset(raw: CobolRawSource, line: CobolLine) -> int:
    """Offset do `\\n` que termina a linha física `line`.

    Requer que a linha venha de `CobolLines.from_raw` e não seja a última física
    para que o contrato seja válido; caso contrário, o offset pode não conter `\\n` (ver
    `CobolLines.from_raw`).
    """
    end = line.span.full.end
    if raw.text.startswith("\r\n", end):
        # Descarta \r
        end += 1
    return end


def _group_lines(
    lines: CobolLines, diagnostics: list[Diagnostic], include_other: bool, include_debug: bool
) -> list[list[CobolLine]]:
    """Agrupa as linhas físicas relevantes em linhas lógicas."""
    groups = []
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
            diagnostics.append(
                Diagnostic(
                    DiagnosticSeverity.ERROR,
                    "linha de continuação sem linha de código anterior",
                    line.span.indicator,
                )
            )

        skipping = False
        groups.append([line])

    return groups


def _build_logical_line(
    raw: CobolRawSource, group: list[CobolLine], builder: _Builder, diagnostics: list[Diagnostic]
) -> None:
    """Adiciona ao builder a linha lógica formada pelas linhas físicas do grupo."""
    orig_len_parts = len(builder.parts)
    first, *continuations = group
    pending_span_lstripped = first.span.body
    pending_span = pending_span_lstripped

    for line in continuations:
        logical_text = "".join(builder.parts[orig_len_parts:]) + raw.slice(pending_span_lstripped)
        open_quote = _find_open_quote(logical_text)
        line_span = line.span.body
        line_span_lstripped = _strip_start(raw, line_span)

        # Aspa na coluna 72 que fecharia o literal, seguida de continuação que começa com a mesma
        # aspa: é a primeira metade de uma aspa escapada (`""`), então o literal continua aberto
        if (
            open_quote is None
            and pending_span_lstripped.end - pending_span.start == _WIDTH_BODY
            and line_span_lstripped
            and logical_text.endswith(raw.text[line_span_lstripped.start])
            and _find_open_quote(logical_text[:-1]) == raw.text[line_span_lstripped.start]
        ):
            open_quote = raw.text[line_span_lstripped.start]

        if line_span_lstripped and line_span_lstripped.start - line_span.start < _WIDTH_A:
            diagnostics.append(
                Diagnostic(
                    DiagnosticSeverity.ERROR,
                    "continuação com conteúdo na área A",
                    Span(line_span_lstripped.start, line_span_lstripped.start + 1),
                )
            )

        if open_quote is None:
            builder.add_raw(_strip_end(raw, pending_span_lstripped))
            pending_span_lstripped, pending_span = line_span_lstripped, line_span
            continue

        # Literal aberto com continuação vazia: não há o que continuar, então a linha é ignorada e
        # o literal fica sem fechamento no fim da linha anterior (sem preenchimento virtual)
        if not line_span_lstripped:
            diagnostics.append(
                Diagnostic(
                    DiagnosticSeverity.ERROR,
                    f"continuação de literal deve começar com {open_quote}",
                    line.span.indicator,
                )
            )
            continue

        # Literal aberto: estende até a coluna 72, com preenchimento virtual se a linha for curta
        builder.add_raw(pending_span_lstripped)
        padding = _WIDTH_BODY - (pending_span_lstripped.end - pending_span.start)
        builder.add_synthetic(" " * padding, pending_span_lstripped.end)
        pending_span = line_span
        if line_span_lstripped and raw.text[line_span_lstripped.start] == open_quote:
            pending_span_lstripped = Span(line_span_lstripped.start + 1, line_span_lstripped.end)
        else:
            diagnostics.append(
                Diagnostic(
                    DiagnosticSeverity.ERROR,
                    f"continuação de literal deve começar com {open_quote}",
                    Span(line_span_lstripped.start, line_span_lstripped.start + 1),
                )
            )
            pending_span_lstripped = line_span_lstripped

    builder.add_raw(_strip_end(raw, pending_span_lstripped))


def _strip_start(raw: CobolRawSource, span: Span) -> Span:
    """Remove espaços do início do span."""
    text = raw.slice(span).lstrip(" ")
    return Span(span.end - len(text), span.end)


def _strip_end(raw: CobolRawSource, span: Span) -> Span:
    """Remove espaços do fim do span."""
    text = raw.slice(span).rstrip(" ")
    return Span(span.start, span.start + len(text))


def _find_open_quote(text: str) -> str | None:
    """Aspa do literal alfanumérico que continua aberto no fim de `text`, se houver.

    Aspas duplicadas dentro do literal são escapes; uma aspa no fim do texto fecha o literal.
    """
    quote = None
    i = 0
    while i < len(text):
        c = text[i]
        if quote is None:
            if c in COBOL_QUOTES:
                quote = c
        elif c == quote:
            if text.startswith(quote, i + 1):
                i += 1
            else:
                quote = None
        i += 1
    return quote
