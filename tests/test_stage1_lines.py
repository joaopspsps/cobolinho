from pathlib import Path

import pytest

from cobolinho.stage0_source import CobolSource
from cobolinho.stage1_lines import CobolLineKind, CobolLines

CORPUS = Path(__file__).parent.parent / "cbl" / "ccvs85"
NC_FILES = sorted(CORPUS.glob("NC*.CBL"))


def load(name: str) -> tuple[CobolSource, CobolLines]:
    path = CORPUS / name
    source = CobolSource(name, path.read_text(newline=""))
    lines = CobolLines.from_source(source)
    return source, lines


def make(line: str) -> tuple[CobolSource, CobolLines]:
    source = CobolSource("t", line)
    lines = CobolLines.from_source(source)
    return source, lines


@pytest.mark.parametrize(
    ("indicator", "kind"),
    [
        (" ", CobolLineKind.CODE),
        ("*", CobolLineKind.COMMENT),
        ("/", CobolLineKind.PAGE),
        ("D", CobolLineKind.DEBUG),
        ("d", CobolLineKind.DEBUG),
        ("-", CobolLineKind.CONTINUATION),
        # Marcadores de opção do EXEC85 e outros
        ("A", CobolLineKind.OTHER),
        ("S", CobolLineKind.OTHER),
        ("Y", CobolLineKind.OTHER),
        ("?", CobolLineKind.OTHER),
    ],
)
def test_indicator_classification(indicator: str, kind: CobolLineKind) -> None:
    source, (line,) = make(f"000100{indicator}    MOVE A TO B.")
    assert line.kind is kind
    assert source[line.span.indicator] == indicator


def test_blank_and_short_lines() -> None:
    source, lines = make("000100 \n0001\n\n" + " " * 80)
    assert [x.kind for x in lines] == [CobolLineKind.BLANK] * 4
    short = lines.line(1)
    assert source[short.span.indicator] == " "
    assert len(source[short.span.body]) == 0 and len(source[short.span.identification]) == 0


def test_column_spans() -> None:
    source, (line,) = make("SEQNUM" + "*" + "A" * 4 + "B" * 61 + "IDENTIFY")
    assert source[line.span.sequence] == "SEQNUM"
    assert source[line.span.indicator] == "*"
    assert source[line.span.body] == "A" * 4 + "B" * 61
    assert source[line.span.identification] == "IDENTIFY"


def test_sequence_area_garbage_is_ignored() -> None:
    source, lines = load("NC114M.CBL")
    assert source[lines.line(487).span.sequence] == "*/+(>'"
    assert lines.line(487).kind is CobolLineKind.BLANK


def test_option_markers_included() -> None:
    source, lines = load("NC101A.CBL")
    assert lines.line(327).kind is CobolLineKind.OTHER
    assert source[lines.line(327).span.indicator] == "S"
    assert source[lines.line(327).span.body].strip() == "EXIT PROGRAM."


@pytest.mark.parametrize("path", NC_FILES, ids=lambda path: path.name)
def test_corpus_spans_cover_lines(path: Path) -> None:
    source, lines = load(path.name)
    assert len(lines) == source.line_count
    for line in lines:
        # As áreas se concatenam exatamente na linha crua.
        areas = ("sequence", "indicator", "body", "identification")
        assert "".join(source[getattr(line.span, area)] for area in areas) == source[line.span.full]
        assert source.line_col(line.span.body.start) == (
            line.number,
            min(8, len(line.span.full) + 1),
        )
