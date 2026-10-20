import pytest

from cobolinho.stage0_raw import CobolRawSource, Position, Span


class TestAbcdef:
    raw = CobolRawSource("t", "ab\ncd\r\nef\n\n")

    def test_line_count(self) -> None:
        assert self.raw.line_count == 4

    @pytest.mark.parametrize(
        "number,start,end,text,follow",
        (
            (1, 0, 2, "ab", "\n"),  # Caso comum
            (2, 3, 5, "cd", "\r"),  # Exclui `\r`
            (3, 7, 9, "ef", "\n"),  # Sem `\n` final
            (4, 10, 10, "", "\n"),  # Linha vazia
        ),
    )
    def test_line_spans(self, number: int, start: int, end: int, text: str, follow: str) -> None:
        span = self.raw.get_line_span(number)
        assert span == Span(start, end)
        assert self.raw.slice(span) == text
        assert self.raw.text[span.end] == follow

    @pytest.mark.parametrize("offset,line,col", ((0, 1, 1), (4, 2, 2), (7, 3, 1), (9, 3, 3)))
    def test_to_position_and_format_location(self, offset: int, line: int, col: int) -> None:
        assert self.raw.to_position(offset) == Position(line, col)
        assert self.raw.format_location(offset) == f"t:{line}:{col}"


def test_trailing_newline_does_not_add_line() -> None:
    assert CobolRawSource("t", "a\n").line_count == 1
    assert CobolRawSource("t", "a\n\n").line_count == 2
    assert CobolRawSource("t", "").line_count == 0
