"""Testes do estágio 1 lines."""

from pathlib import Path

import pytest

from cobolinho.stage1_lines import CobolLineKind

from .utils import CORPUS_CCVS85_NC_FILES, make_lines

# Testes específicos
# ------------------


class TestClassifyIndicatorKind:
    params = (
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
    )

    @pytest.mark.parametrize(
        "indicator,kind",
        params,
        ids=(f'"{indicator}" -> {kind.name}' for indicator, kind in params),
    )
    def test(self, indicator: str, kind: CobolLineKind) -> None:
        lines = make_lines(f"000100{indicator}    MOVE A TO B.")
        line = lines.get_line(1)
        assert line.kind is kind
        assert lines.source.slice(line.span.indicator) == indicator


def test_classify_blank_and_short_lines() -> None:
    lines = make_lines("000100 \n0001\n\n" + " " * 80)
    assert [x.kind for x in lines] == [CobolLineKind.BLANK] * 4
    short = lines.get_line(1)
    assert lines.source.slice(short.span.indicator) == " "
    assert (
        len(lines.source.slice(short.span.body)) == 0
        and len(lines.source.slice(short.span.identification)) == 0
    )


def test_area_spans() -> None:
    body = "A" * 4 + "B" * 61
    lines = make_lines("SEQUEN" + "*" + body + "IDENTIFI")
    line = lines.get_line(1)
    assert lines.source.slice(line.span.sequence) == "SEQUEN"
    assert lines.source.slice(line.span.indicator) == "*"
    assert lines.source.slice(line.span.body) == body
    assert lines.source.slice(line.span.identification) == "IDENTIFI"


# NC114M:486-491
@pytest.mark.parametrize("sequence", ("ABCDEF", "*/+(>'", "999-99", "Z=.,;<", ")14$ X", "  23 4"))
def test_ignore_sequence_area_garbage(sequence: str) -> None:
    lines = make_lines(sequence + " " * 74)
    line = lines.get_line(1)
    assert lines.source.slice(line.span.sequence) == sequence
    assert line.kind is CobolLineKind.BLANK


# Testes gerais sobre o corpus
# ----------------------------


@pytest.mark.parametrize("path", CORPUS_CCVS85_NC_FILES, ids=lambda path: path.name)
def test_corpus_spans_cover_lines(path: Path) -> None:
    lines = make_lines(path)

    assert len(lines) == lines.source.line_count
    for line in lines:
        # As áreas se concatenam exatamente na linha crua
        areas = ("sequence", "indicator", "body", "identification")
        assert "".join(
            lines.source.slice(getattr(line.span, area)) for area in areas
        ) == lines.source.slice(line.span.full)
        assert lines.source.to_line_col(line.span.body.start) == (
            line.number,
            min(8, len(line.span.full) + 1),
        )
