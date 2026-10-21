"""Testes do estágio 2 norm."""

from pathlib import Path

import pytest

from cobolinho.diagnostics import DiagnosticSeverity
from cobolinho.stage0_raw import Position, Span
from cobolinho.stage2_norm import CobolNormSegment, CobolNormSource

from .utils import CORPUS_NC_FILES, make_norm

# Testes específicos
# ------------------


def test_drop_comments_and_blanks() -> None:
    norm = make_norm("""\
000000     MOVE A TO B.
000000*   COMENTÁRIO
000000/
000000
000000     STOP RUN.""")

    assert norm.text == "    MOVE A TO B.\n    STOP RUN."

    # O newline mapeia para o `\n` da linha que termina a linha lógica
    newline_offset = norm.text.index("\n")
    assert norm.to_raw_position(newline_offset) == Position(1, len("000001     MOVE A TO B.") + 1)


def test_continuation_1() -> None:
    # NC205A:49-53
    norm = make_norm("""\
004700 77  PROCEDURE                                                    NC2054.2
004800-    DIVISION PICTURE X.                                          NC2054.2
004900 77  CONT-                                                        NC2054.2
005000-         A             PIC                                       NC2054.2
005100-                          TURE X(10) VAL                         NC2054.2
005200-                                        UE               "GOVERNMNC2054.2
005300-    "ENT".                                                       NC2054.2""")

    assert (
        norm.text
        == """\
77  PROCEDUREDIVISION PICTURE X.
77  CONT-A             PICTURE X(10) VALUE               "GOVERNMENT"."""
    )

    # `VAL` na linha 5100, `UE` na linha 5200
    value_start = norm.text.index("VALUE")
    raw_spans = norm.to_raw_spans(Span(value_start, value_start + len("VALUE")))
    assert len(raw_spans) == 2
    assert [norm.raw.slice(s) for s in raw_spans] == ["VAL", "UE"]
    raw_span_val, raw_span_ue = raw_spans
    assert norm.raw.to_position(raw_span_val.start) == Position(5, 45)
    assert norm.raw.to_position(raw_span_val.end) == Position(5, 48)
    assert norm.raw.to_position(raw_span_ue.start) == Position(6, 48)
    assert norm.raw.to_position(raw_span_ue.end) == Position(6, 50)

    # `"GOVERNM` na linha 5200, `ENT"` na linha 5300
    literal_start = norm.text.index('"')
    raw_spans = norm.to_raw_spans(Span(literal_start, literal_start + len('"GOVERNMENT"')))
    assert [norm.raw.slice(s) for s in raw_spans] == ['"GOVERNM', 'ENT"']


def test_continuation_2() -> None:
    # NC107A:95-109
    norm = make_norm("""\
009500 77  DATA-R                              VALUE "LITERAL ENDS AT 72NC1074.2
009600-    ""                                                           NC1074.2
009700     PICTURE X(18).                                               NC1074.2
009800 77  DATA-S             PICTURE X(20) VALUE               "OFFSET NC1074.2
009900-             "CONTINUATION ".                                    NC1074.2
010000 77  DATA-T             PICTURE X(20) VALUE  "OFFSET CONTINUATION NC1074.2
010100-                                             "".                 NC1074.2
010200 77  DATA-U             PICTURE X(20) VALUE                   "OFFNC1074.2
010300-                                                             "SETNC1074.2
010400-                                                             " CONC1074.2
010500-                                                             "NTINC1074.2
010600-                                                             "NUANC1074.2
010700-                                                               "TNC1074.2
010800-                                                             "IONNC1074.2
010900-                                                             " ".NC1074.2""")

    assert (
        norm.text
        == """\
77  DATA-R                              VALUE "LITERAL ENDS AT 72"
    PICTURE X(18).
77  DATA-S             PICTURE X(20) VALUE               "OFFSET CONTINUATION ".
77  DATA-T             PICTURE X(20) VALUE  "OFFSET CONTINUATION ".
77  DATA-U             PICTURE X(20) VALUE                   "OFFSET CONTINUATION "."""
    )


def test_continuation_3() -> None:
    # NC215A:49-50
    norm = make_norm("""\
004900     THE-BIG-OL-LITERAL-ALPHABET IS "A+0B-1C*2D/3E=4Fl5G,6H;7I.8J"NC2154.2
005000-    ""9K(L)M>N<O PQRSTUVWXYZ".                                   NC2154.2""")
    assert (
        norm.text
        == '    THE-BIG-OL-LITERAL-ALPHABET IS "A+0B-1C*2D/3E=4Fl5G,6H;7I.8J""9K(L)M>N<O PQRSTUVWXYZ".'
    )


def test_continuation_literal_short_line_padding() -> None:
    norm = make_norm("""\
000000     MOVE "ABC
000000-    "DEF" TO X.""")

    padding_length = 65 - len('    MOVE "ABC')
    assert norm.text == '    MOVE "ABC' + " " * padding_length + 'DEF" TO X.'
    padding_start = norm.text.index("ABC") + 3
    assert all(
        norm.find_segment(i).synthetic for i in range(padding_start, padding_start + padding_length)
    )
    # Ancorado no fim da primeira linha
    assert norm.to_raw_offset(padding_start) == norm.raw.get_line_span(1).end
    assert not norm.find_segment(padding_start + padding_length).synthetic

    literal_start = norm.text.index('"')
    spans = norm.to_raw_spans(
        Span(literal_start, literal_start + len('"ABC') + padding_length + len('DEF"'))
    )
    assert [norm.raw.slice(s) for s in spans] == ['"ABC', 'DEF"']
    # Intervalo só sintético: span vazio na âncora
    anchor = norm.raw.get_line_span(1).end
    assert norm.to_raw_spans(Span(padding_start, padding_start + 1)) == [Span(anchor, anchor)]


def test_continuation_after_comment() -> None:
    norm = make_norm("""\
000000     MOVE AB
000000*   COMENTÁRIO

000000-       CD TO X.""")

    assert norm.text == "    MOVE ABCD TO X."


def test_starts_in_area_a() -> None:
    norm = make_norm("""\
000000 PROCEDURE DIVISION.
000000     STOP RUN.""")

    assert norm.starts_in_area_a(0)
    assert norm.to_raw_position(0).col == 8  # Primeiro offset do corpo
    stop_start = norm.text.index("STOP")
    assert norm.to_raw_position(stop_start).col == 12
    assert not norm.starts_in_area_a(stop_start)


@pytest.mark.parametrize(
    "include_debug,norm_text",
    ((False, "    STOP RUN."), (True, "    DISPLAY XY.\n    STOP RUN.")),
)
def test_include_debug(include_debug: bool, norm_text: str) -> None:
    text = """\
000000D    DISPLAY X
000000-        Y.
000000     STOP RUN."""

    norm = make_norm(text, include_debug=include_debug)
    assert norm.text == norm_text


@pytest.mark.parametrize("include_other,norm_text", ((False, ""), (True, "    EXIT PROGRAM.")))
def test_include_other(include_other: bool, norm_text: str) -> None:
    norm = make_norm(
        # NC101A:327
        "032700S    EXIT PROGRAM.                                                NC1014.2",
        include_other=include_other,
    )
    assert norm.text == norm_text
    assert norm.diagnostics == []


def test_diagnostic_continuation_without_previous_line() -> None:
    norm = make_norm("""\
000000*   COMENTÁRIO
000000-        MOVE A TO B.""")

    (diagnostic,) = norm.diagnostics
    assert diagnostic.severity is DiagnosticSeverity.ERROR
    assert diagnostic.format(norm.raw) == (
        "t:2:7: erro: linha de continuação sem linha de código anterior"
    )
    assert norm.text == "        MOVE A TO B."


def test_diagnostic_literal_continuation_without_quote() -> None:
    norm = make_norm("""\
000000     MOVE "ABC
000000-       DEF TO X.""")

    (diagnostic,) = norm.diagnostics
    assert diagnostic.format(norm.raw) == 't:2:15: erro: continuação de literal deve começar com "'


@pytest.mark.parametrize("empty_line", ["000000-", "000000-" + " " * 65])
def test_diagnostic_literal_continuation_empty(empty_line: str) -> None:
    norm = make_norm(f"""\
000000     DISPLAY "X
{empty_line}
000000     STOP RUN.""")

    (diagnostic,) = norm.diagnostics
    assert diagnostic.format(norm.raw) == 't:2:7: erro: continuação de literal deve começar com "'
    # Sem preenchimento virtual: o literal fica sem fechamento no fim da linha
    assert norm.text == '    DISPLAY "X\n    STOP RUN.'
    assert not any(segment.synthetic for segment in norm.segments)


def test_diagnostic_literal_continuation_empty_then_valid() -> None:
    # A linha vazia é ignorada; a continuação seguinte continua o literal da primeira linha
    norm = make_norm("""\
000000     MOVE "ABC
000000-
000000-    "DEF" TO X.""")

    (diagnostic,) = norm.diagnostics
    assert diagnostic.format(norm.raw) == 't:2:7: erro: continuação de literal deve começar com "'
    padding_length = 65 - len('    MOVE "ABC')
    assert norm.text == '    MOVE "ABC' + " " * padding_length + 'DEF" TO X.'


def test_diagnostic_continuation_in_area_a() -> None:
    norm = make_norm("""\
000000     MOVE AB
000000-  CD TO X.""")

    (diagnostic,) = norm.diagnostics
    assert diagnostic.format(norm.raw) == "t:2:10: erro: continuação com conteúdo na área A"
    assert norm.text == "    MOVE ABCD TO X."


def test_empty_text() -> None:
    norm = make_norm("")
    assert norm.text == ""
    assert norm.to_raw_offset(0) == 0
    assert list(norm.iter_logical_lines()) == []
    with pytest.raises(IndexError):
        norm.to_raw_offset(1)


def test_segments_must_cover_text() -> None:
    lines = make_norm("000000     A.").lines
    with pytest.raises(ValueError, match="segmentos cobrem"):
        CobolNormSource(lines, "AB", [CobolNormSegment(0, 0, 1)], [])
    with pytest.raises(ValueError, match="segmentos cobrem"):
        CobolNormSource(lines, "A", [], [])


# Testes gerais sobre o corpus
# ----------------------------


@pytest.mark.parametrize("path", CORPUS_NC_FILES, ids=lambda path: path.name)
def test_corpus_invariant(path: Path) -> None:
    norm = make_norm(path)
    assert norm.diagnostics == []
    for i, c in enumerate(norm.text):
        if not norm.find_segment(i).synthetic:
            assert c == norm.raw.text[norm.to_raw_offset(i)]
    # Os segmentos são contíguos no texto normalizado
    for a, b in zip(norm.segments, norm.segments[1:], strict=False):
        assert a.norm_end == b.norm_start
