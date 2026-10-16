from cobolinho.stage0_source import CobolSource, Span


def test_get_line_span_and_to_line_col() -> None:
    source = CobolSource("t", "ab\ncd\r\nef")
    assert source.line_count == 3
    assert source.get_line_span(1) == Span(0, 2)
    assert source.get_line_span(2) == Span(3, 5)  # `\r` excluído
    assert source.get_line_span(3) == Span(7, 9)  # sem `\n` final
    assert source.to_line_col(0) == (1, 1)
    assert source.to_line_col(4) == (2, 2)
    assert source.to_line_col(7) == (3, 1)
    assert source.to_line_col(9) == (3, 3)  # EOF
    assert source.format_location(4) == "t:2:2"


def test_trailing_newline_does_not_add_line() -> None:
    assert CobolSource("t", "a\n").line_count == 1
    assert CobolSource("t", "a\n\n").line_count == 2
    assert CobolSource("t", "").line_count == 0
