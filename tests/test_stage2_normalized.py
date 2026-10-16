from pathlib import Path

import pytest

from cobolinho.diagnostics import Severity
from cobolinho.stage0_source import CobolSource, Span
from cobolinho.stage1_lines import CobolLines
from cobolinho.stage2_normalized import NormalizedCobolSource

CORPUS_DIR = Path(__file__).parent.parent / "cbl" / "ccvs85"
CORPUS_NC_FILES = sorted(CORPUS_DIR.glob("NC*.CBL"))


def normalize(source: CobolSource, **kwargs: bool) -> NormalizedCobolSource:
    lines = CobolLines.from_source(source)
    return NormalizedCobolSource.from_lines(lines, **kwargs)


def load(name: str, **kwargs: bool) -> NormalizedCobolSource:
    text = (CORPUS_DIR / name).read_text(newline="")
    source = CobolSource(name, text)
    return normalize(source, **kwargs)


def make(*lines: str, **kwargs: bool) -> NormalizedCobolSource:
    """Monta um programa a partir de linhas `(indicador + corpo)`, prefixando a sequência."""
    text = "".join(f"{n:06}{line}\n" for n, line in enumerate(lines, start=1))
    return normalize(CobolSource("t", text), **kwargs)


def find_logical_line(normalized: NormalizedCobolSource, needle: str) -> tuple[int, str]:
    """Encontra a primeira linha lógica que contém `needle`."""
    return next((o, t) for o, t in normalized.iter_logical_lines() if needle in t)


def extract_literal_value(text: str) -> str:
    """Extrai o conteúdo do primeiro literal com aspas duplas em `text`, sem desescapar."""
    start = text.index('"') + 1
    i = start
    while True:
        if text[i] == '"':
            if text.startswith('"', i + 1):
                i += 2
                continue
            return text[start:i]
        i += 1


@pytest.mark.parametrize("path", CORPUS_NC_FILES, ids=lambda path: path.name)
def test_corpus_invariant(path: Path) -> None:
    normalized = load(path.name)
    assert normalized.diagnostics == []
    source_map = normalized.map
    assert source_map.norm_length == len(normalized.text)
    for i, c in enumerate(normalized.text):
        if not source_map.find_segment(i).synthetic:
            assert c == normalized.source[source_map.to_raw_offset(i)]
    # Os segmentos são contíguos no texto normalizado
    for a, b in zip(source_map.segments, source_map.segments[1:], strict=False):
        assert a.norm_end == b.norm_start


def test_drop_comments_and_blanks() -> None:
    normalized = make(
        "     MOVE A TO B.",
        "*   COMENTÁRIO",
        "/",
        "",
        "     STOP RUN.",
    )
    assert normalized.text == "    MOVE A TO B.\n    STOP RUN."
    # O newline mapeia para o `\n` da linha que termina a linha lógica
    newline = normalized.text.index("\n")
    assert normalized.source is normalized.lines.source
    assert normalized.to_raw_line_col(newline) == (1, len("000001     MOVE A TO B.") + 1)


def test_continuation_word_nc205a() -> None:
    normalized = load("NC205A.CBL")
    offset, text = find_logical_line(normalized, "CONT-A ")
    assert text == '77  CONT-A             PICTURE X(10) VALUE               "GOVERNMENT".'
    assert (
        find_logical_line(normalized, "PROCEDUREDIVISION")[1] == "77  PROCEDUREDIVISION PICTURE X."
    )
    assert find_logical_line(normalized, "S9(6)")[1].strip() == "PIC S9(6)V9(6)."
    assert "MOVE     -999.777 TO CONT-B." in normalized.text

    source_map = normalized.map
    picture_start = offset + text.index("PICTURE")
    # `PIC` na linha 50, `TURE` na linha 51
    spans = source_map.to_raw_spans(picture_start, picture_start + len("PICTURE"))
    assert len(spans) == 2
    assert [normalized.source[s] for s in spans] == ["PIC", "TURE"]
    assert normalized.to_raw_line_col(picture_start) == (50, 31)
    assert normalized.to_raw_line_col(picture_start + 3) == (51, 34)

    literal_start = offset + text.index('"')
    spans = source_map.to_raw_spans(literal_start, literal_start + len('"GOVERNMENT"'))
    assert [normalized.source[s] for s in spans] == ['"GOVERNM', 'ENT"']


def test_continuation_literal_nc107a() -> None:
    normalized = load("NC107A.CBL")
    assert (
        extract_literal_value(find_logical_line(normalized, "DATA-R ")[1]) == "LITERAL ENDS AT 72"
    )
    for name in ("DATA-S ", "DATA-T ", "DATA-U "):
        assert (
            extract_literal_value(find_logical_line(normalized, name)[1]) == "OFFSET CONTINUATION "
        )

    _, text = find_logical_line(normalized, '""""""')
    value = extract_literal_value(text)
    assert len(value) == 2 * 160 and set(value) == {'"'}


def test_continuation_literal_short_line_padding() -> None:
    normalized = make(
        '     MOVE "ABC',
        '-    "DEF" TO X.',
    )
    padding_length = 65 - len('    MOVE "ABC')
    assert normalized.text == '    MOVE "ABC' + " " * padding_length + 'DEF" TO X.'
    source_map = normalized.map
    padding_start = normalized.text.index("ABC") + 3
    assert all(
        source_map.find_segment(i).synthetic
        for i in range(padding_start, padding_start + padding_length)
    )
    # Ancorado no fim da primeira linha
    assert source_map.to_raw_offset(padding_start) == normalized.source.get_line_span(1).end
    assert not source_map.find_segment(padding_start + padding_length).synthetic

    literal_start = normalized.text.index('"')
    spans = source_map.to_raw_spans(
        literal_start, literal_start + len('"ABC') + padding_length + len('DEF"')
    )
    assert [normalized.source[s] for s in spans] == ['"ABC', 'DEF"']
    # Intervalo só sintético: span vazio na âncora
    anchor = normalized.source.get_line_span(1).end
    assert source_map.to_raw_spans(padding_start, padding_start + 1) == [Span(anchor, anchor)]


def test_continuation_after_comment() -> None:
    normalized = make(
        "     MOVE AB",
        "*   COMENTÁRIO",
        "",
        "-       CD TO X.",
    )
    assert normalized.text == "    MOVE ABCD TO X."


def test_starts_in_area_a() -> None:
    normalized = make(
        " PROCEDURE DIVISION.",
        "     STOP RUN.",
    )
    assert normalized.starts_in_area_a(0)
    assert normalized.to_raw_col(0) == 8
    stop_start = normalized.text.index("STOP")
    assert normalized.to_raw_col(stop_start) == 12
    assert not normalized.starts_in_area_a(stop_start)


def test_include_other_lines() -> None:
    included = load("NC101A.CBL")
    assert "    EXIT PROGRAM." in included.text.split("\n")
    excluded = load("NC101A.CBL", include_other=False)
    assert "    EXIT PROGRAM." not in excluded.text.split("\n")
    assert excluded.diagnostics == []


def test_include_debug_lines() -> None:
    normalized = make("D    DISPLAY X.", "-        Y.", "     STOP RUN.")
    assert normalized.text == "    STOP RUN."
    normalized = make("D    DISPLAY X.", "     STOP RUN.", include_debug=True)
    assert normalized.text == "    DISPLAY X.\n    STOP RUN."


def test_diagnostic_continuation_without_previous_line() -> None:
    normalized = make("*   COMENTÁRIO", "-        MOVE A TO B.")
    (diagnostic,) = normalized.diagnostics
    assert diagnostic.severity is Severity.ERROR
    assert diagnostic.format(normalized.source) == (
        "t:2:7: erro: linha de continuação sem linha de código anterior"
    )
    assert normalized.text == "        MOVE A TO B."


def test_diagnostic_literal_continuation_without_quote() -> None:
    normalized = make('     MOVE "ABC', "-       DEF TO X.")
    (diagnostic,) = normalized.diagnostics
    assert (
        diagnostic.format(normalized.source)
        == 't:2:15: erro: continuação de literal deve começar com "'
    )


def test_diagnostic_continuation_in_area_a() -> None:
    normalized = make("     MOVE AB", "-  CD TO X.")
    (diagnostic,) = normalized.diagnostics
    assert (
        diagnostic.format(normalized.source) == "t:2:10: erro: continuação com conteúdo na área A"
    )
    assert normalized.text == "    MOVE ABCD TO X."


def test_empty_source() -> None:
    normalized = make()
    assert normalized.text == ""
    assert normalized.map.to_raw_offset(0) == 0
    assert list(normalized.iter_logical_lines()) == []
