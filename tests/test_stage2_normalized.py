"""Testes do estágio 2 normalized."""

from pathlib import Path

import pytest

from cobolinho.diagnostics import DiagnosticSeverity
from cobolinho.stage0_source import Span

from .utils import CORPUS_CCVS85_NC_FILES, make_norm

# Testes específicos
# ------------------


def test_drop_comments_and_blanks() -> None:
    normalized = make_norm("""\
000000     MOVE A TO B.
000000*   COMENTÁRIO
000000/
000000
000000     STOP RUN.""")

    assert normalized.text == "    MOVE A TO B.\n    STOP RUN."

    # O newline mapeia para o `\n` da linha que termina a linha lógica
    newline_offset = normalized.text.index("\n")
    assert normalized.to_raw_line_col(newline_offset) == (1, len("000001     MOVE A TO B.") + 1)


def test_continuation_1() -> None:
    # NC205A:49-53
    normalized = make_norm("""\
004700 77  PROCEDURE                                                    NC2054.2
004800-    DIVISION PICTURE X.                                          NC2054.2
004900 77  CONT-                                                        NC2054.2
005000-         A             PIC                                       NC2054.2
005100-                          TURE X(10) VAL                         NC2054.2
005200-                                        UE               "GOVERNMNC2054.2
005300-    "ENT".                                                       NC2054.2""")

    assert (
        normalized.text
        == """\
77  PROCEDUREDIVISION PICTURE X.
77  CONT-A             PICTURE X(10) VALUE               "GOVERNMENT"."""
    )

    # `VAL` na linha 5100, `UE` na linha 5200
    value_start = normalized.text.index("VALUE")
    raw_spans = normalized.map.to_raw_spans(value_start, value_start + len("VALUE"))
    assert len(raw_spans) == 2
    assert [normalized.source.slice(s) for s in raw_spans] == ["VAL", "UE"]
    raw_span_val, raw_span_ue = raw_spans
    assert normalized.source.to_line_col(raw_span_val.start) == (5, 45)
    assert normalized.source.to_line_col(raw_span_val.end) == (5, 48)
    assert normalized.source.to_line_col(raw_span_ue.start) == (6, 48)
    assert normalized.source.to_line_col(raw_span_ue.end) == (6, 50)

    # `"GOVERNM` na linha 5200, `ENT"` na linha 5300
    literal_start = normalized.text.index('"')
    raw_spans = normalized.map.to_raw_spans(literal_start, literal_start + len('"GOVERNMENT"'))
    assert [normalized.source.slice(s) for s in raw_spans] == ['"GOVERNM', 'ENT"']


def test_continuation_2() -> None:
    # NC107A:95-109
    normalized = make_norm("""\
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
        normalized.text
        == """\
77  DATA-R                              VALUE "LITERAL ENDS AT 72"
    PICTURE X(18).
77  DATA-S             PICTURE X(20) VALUE               "OFFSET CONTINUATION ".
77  DATA-T             PICTURE X(20) VALUE  "OFFSET CONTINUATION ".
77  DATA-U             PICTURE X(20) VALUE                   "OFFSET CONTINUATION "."""
    )


def test_continuation_3() -> None:
    # NC215A:49-50
    normalized = make_norm("""\
004900     THE-BIG-OL-LITERAL-ALPHABET IS "A+0B-1C*2D/3E=4Fl5G,6H;7I.8J"NC2154.2
005000-    ""9K(L)M>N<O PQRSTUVWXYZ".                                   NC2154.2""")
    assert (
        normalized.text
        == '    THE-BIG-OL-LITERAL-ALPHABET IS "A+0B-1C*2D/3E=4Fl5G,6H;7I.8J""9K(L)M>N<O PQRSTUVWXYZ".'
    )


def test_continuation_literal_short_line_padding() -> None:
    normalized = make_norm("""\
000000     MOVE "ABC
000000-    "DEF" TO X.""")

    padding_length = 65 - len('    MOVE "ABC')
    assert normalized.text == '    MOVE "ABC' + " " * padding_length + 'DEF" TO X.'
    padding_start = normalized.text.index("ABC") + 3
    assert all(
        normalized.map.find_segment(i).synthetic
        for i in range(padding_start, padding_start + padding_length)
    )
    # Ancorado no fim da primeira linha
    assert normalized.map.to_raw_offset(padding_start) == normalized.source.get_line_span(1).end
    assert not normalized.map.find_segment(padding_start + padding_length).synthetic

    literal_start = normalized.text.index('"')
    spans = normalized.map.to_raw_spans(
        literal_start, literal_start + len('"ABC') + padding_length + len('DEF"')
    )
    assert [normalized.source.slice(s) for s in spans] == ['"ABC', 'DEF"']
    # Intervalo só sintético: span vazio na âncora
    anchor = normalized.source.get_line_span(1).end
    assert normalized.map.to_raw_spans(padding_start, padding_start + 1) == [Span(anchor, anchor)]


def test_continuation_after_comment() -> None:
    normalized = make_norm("""\
000000     MOVE AB
000000*   COMENTÁRIO

000000-       CD TO X.""")

    assert normalized.text == "    MOVE ABCD TO X."


def test_starts_in_area_a() -> None:
    normalized = make_norm("""\
000000 PROCEDURE DIVISION.
000000     STOP RUN.""")

    assert normalized.starts_in_area_a(0)
    assert normalized.to_raw_col(0) == 8  # Primeiro offset do corpo
    stop_start = normalized.text.index("STOP")
    assert normalized.to_raw_col(stop_start) == 12
    assert not normalized.starts_in_area_a(stop_start)


@pytest.mark.parametrize(
    "include_debug,normalized_text",
    ((False, "    STOP RUN."), (True, "    DISPLAY XY.\n    STOP RUN.")),
)
def test_include_debug(include_debug: bool, normalized_text: str) -> None:
    text = """\
000000D    DISPLAY X
000000-        Y.
000000     STOP RUN."""

    normalized = make_norm(text, include_debug=include_debug)
    assert normalized.text == normalized_text


@pytest.mark.parametrize(
    "include_other,normalized_text", ((False, ""), (True, "    EXIT PROGRAM."))
)
def test_include_other(include_other: bool, normalized_text: str) -> None:
    normalized = make_norm(
        # NC101A:327
        "032700S    EXIT PROGRAM.                                                NC1014.2",
        include_other=include_other,
    )
    assert normalized.text == normalized_text
    assert normalized.diagnostics == []


def test_diagnostic_continuation_without_previous_line() -> None:
    normalized = make_norm("""\
000000*   COMENTÁRIO
000000-        MOVE A TO B.""")

    (diagnostic,) = normalized.diagnostics
    assert diagnostic.severity is DiagnosticSeverity.ERROR
    assert diagnostic.format(normalized.source) == (
        "t:2:7: erro: linha de continuação sem linha de código anterior"
    )
    assert normalized.text == "        MOVE A TO B."


def test_diagnostic_literal_continuation_without_quote() -> None:
    normalized = make_norm("""\
000000     MOVE "ABC
000000-       DEF TO X.""")

    (diagnostic,) = normalized.diagnostics
    assert (
        diagnostic.format(normalized.source)
        == 't:2:15: erro: continuação de literal deve começar com "'
    )


def test_diagnostic_continuation_in_area_a() -> None:
    normalized = make_norm("""\
000000     MOVE AB
000000-  CD TO X.""")

    (diagnostic,) = normalized.diagnostics
    assert (
        diagnostic.format(normalized.source) == "t:2:10: erro: continuação com conteúdo na área A"
    )
    assert normalized.text == "    MOVE ABCD TO X."


def test_empty_source() -> None:
    normalized = make_norm("")
    assert normalized.text == ""
    assert normalized.map.to_raw_offset(0) == 0
    assert list(normalized.iter_logical_lines()) == []


# Testes gerais sobre o corpus
# ----------------------------


@pytest.mark.parametrize("path", CORPUS_CCVS85_NC_FILES, ids=lambda path: path.name)
def test_corpus_invariant(path: Path) -> None:
    normalized = make_norm(path)
    assert normalized.diagnostics == []
    map = normalized.map
    assert map.length == len(normalized.text)
    for i, c in enumerate(normalized.text):
        if not map.find_segment(i).synthetic:
            assert c == normalized.source.text[map.to_raw_offset(i)]
    # Os segmentos são contíguos no texto normalizado
    for a, b in zip(map.segments, map.segments[1:], strict=False):
        assert a.norm_end == b.norm_start
