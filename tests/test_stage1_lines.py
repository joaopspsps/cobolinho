from pathlib import Path

import pytest

from cobolinho.stage0_source import CobolSource
from cobolinho.stage1_lines import CobolLineKind, CobolLines

CORPUS_DIR = Path(__file__).parent.parent / "cbl" / "ccvs85"
CORPUS_NC_FILES = sorted(CORPUS_DIR.glob("NC*.CBL"))


def load(name: str) -> CobolLines:
    text = (CORPUS_DIR / name).read_text(newline="")
    source = CobolSource(name, text)
    return CobolLines.from_source(source)


def make(text: str) -> CobolLines:
    source = CobolSource("t", text)
    return CobolLines.from_source(source)


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
def test_classify_indicator(indicator: str, kind: CobolLineKind) -> None:
    lines = make(f"000100{indicator}    MOVE A TO B.")
    line = lines.get_line(1)
    assert line.kind is kind
    assert lines.source[line.span.indicator] == indicator


def test_classify_blank_and_short_lines() -> None:
    lines = make("000100 \n0001\n\n" + " " * 80)
    assert [x.kind for x in lines] == [CobolLineKind.BLANK] * 4
    short = lines.get_line(1)
    assert lines.source[short.span.indicator] == " "
    assert (
        len(lines.source[short.span.body]) == 0
        and len(lines.source[short.span.identification]) == 0
    )


def test_column_spans() -> None:
    lines = make("SEQNUM" + "*" + "A" * 4 + "B" * 61 + "IDENTIFY")
    line = lines.get_line(1)
    assert lines.source[line.span.sequence] == "SEQNUM"
    assert lines.source[line.span.indicator] == "*"
    assert lines.source[line.span.body] == "A" * 4 + "B" * 61
    assert lines.source[line.span.identification] == "IDENTIFY"


def test_sequence_area_garbage_is_ignored() -> None:
    lines = load("NC114M.CBL")
    assert lines.source[lines.get_line(487).span.sequence] == "*/+(>'"
    assert lines.get_line(487).kind is CobolLineKind.BLANK


def test_classify_option_markers() -> None:
    lines = load("NC101A.CBL")
    assert lines.get_line(327).kind is CobolLineKind.OTHER
    assert lines.source[lines.get_line(327).span.indicator] == "S"
    assert lines.source[lines.get_line(327).span.body].strip() == "EXIT PROGRAM."


@pytest.mark.parametrize("path", CORPUS_NC_FILES, ids=lambda path: path.name)
def test_corpus_spans_cover_lines(path: Path) -> None:
    lines = load(path.name)
    assert len(lines) == lines.source.line_count
    for line in lines:
        # As áreas se concatenam exatamente na linha crua.
        areas = ("sequence", "indicator", "body", "identification")
        assert (
            "".join(lines.source[getattr(line.span, area)] for area in areas)
            == lines.source[line.span.full]
        )
        assert lines.source.to_line_col(line.span.body.start) == (
            line.number,
            min(8, len(line.span.full) + 1),
        )
