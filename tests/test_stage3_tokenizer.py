"""Testes do estágio 3 tokenizer."""

from pathlib import Path

import pytest

from cobolinho.stage3_tokenizer import CobolToken, CobolTokens
from cobolinho.stage3_tokenizer import CobolTokenKind as K

from .utils import CORPUS_CCVS85_NC_FILES, CORPUS_DIR, make_tokens


def kinds_values(tokens: CobolTokens) -> list[tuple[K, str]]:
    return [(t.kind, t.value) for t in tokens]


def find_token(tokens: CobolTokens, text: str) -> CobolToken:
    return next(t for t in tokens if t.text == text)


def is_in_picture(tokens: CobolTokens, index: int) -> bool:
    """Indica se o token `index` faz parte de uma cadeia de PICTURE (sem modo PICTURE ainda)."""
    # Uma cadeia de PICTURE é uma sequência de tokens contíguos, sem espaços entre eles
    while index > 0 and tokens[index - 1].end == tokens[index].start:
        index -= 1
    previous = [t.value for t in tokens.tokens[max(index - 2, 0) : index]]
    return previous[-1:] in (["PIC"], ["PICTURE"]) or previous in (["PIC", "IS"], ["PICTURE", "IS"])


# Testes específicos
# ------------------


def test_words() -> None:
    tokens = make_tokens("000000     move Contador-1 TO XXXXX055 100-INICIO.")
    assert kinds_values(tokens) == [
        (K.RESERVED_WORD, "MOVE"),
        (K.USER_WORD, "CONTADOR-1"),
        (K.RESERVED_WORD, "TO"),
        (K.USER_WORD, "XXXXX055"),
        (K.USER_WORD, "100-INICIO"),
        (K.PERIOD, "."),
    ]
    assert tokens[1].text == "Contador-1"
    assert tokens.diagnostics == []


def test_word_too_long() -> None:
    word = "A" * 31
    tokens = make_tokens(f"000000     MOVE {word} TO B.")
    assert tokens[1].kind is K.USER_WORD
    (diagnostic,) = tokens.diagnostics
    assert (
        diagnostic.format(tokens.source)
        == f"t:1:17: erro: palavra com mais de 30 caracteres: {word}"
    )


@pytest.mark.parametrize("text", ["-A", "A-", "A.B", "A$B", "1.2.3", "1.A", "+.A", "==", "A/AA"])
def test_invalid_strings(text: str) -> None:
    tokens = make_tokens(f"000000     MOVE {text} Y.")
    assert tokens[1].kind is K.INVALID
    assert tokens[1].text == text
    (diagnostic,) = tokens.diagnostics
    assert diagnostic.message == f"cadeia de caracteres inválida: {text}"


def test_numeric_literals() -> None:
    tokens = make_tokens("000000     COMPUTE X = -999.777 + .5 * +12 - 1.")
    assert kinds_values(tokens)[2:] == [
        (K.OPERATOR, "="),
        (K.NUMERIC_LITERAL, "-999.777"),
        (K.OPERATOR, "+"),
        (K.NUMERIC_LITERAL, ".5"),
        (K.OPERATOR, "*"),
        (K.NUMERIC_LITERAL, "+12"),
        (K.OPERATOR, "-"),
        (K.NUMERIC_LITERAL, "1"),
        (K.PERIOD, "."),
    ]
    assert tokens.diagnostics == []


def test_numeric_literal_too_long() -> None:
    tokens = make_tokens(f"000000     MOVE {'1' * 18}.{'1'} TO X.")
    (diagnostic,) = tokens.diagnostics
    assert diagnostic.message.startswith("literal numérico com mais de 18 dígitos")


def test_digit_only_procedure_names_nc107a() -> None:
    tokens = make_tokens(CORPUS_DIR / "ccvs85/NC107A.CBL")
    token = find_token(tokens, "0000000000000000000000001")
    assert token.kind is K.NUMERIC_LITERAL
    assert tokens.format_location(token) == "NC107A.CBL:1949:8"
    assert tokens.diagnostics == [d for d in tokens.diagnostics if "inválida" in d.message]


def test_decimal_point_is_comma_nc107a() -> None:
    tokens = make_tokens(CORPUS_DIR / "ccvs85/NC107A.CBL")
    token = find_token(tokens, "211113411,114311112")
    assert token.kind is K.NUMERIC_LITERAL

    # Vírgula seguida de espaço continua sendo separador
    tokens = make_tokens("""\
000000     DECIMAL-POINT IS COMMA.
000000     MOVE 1,5 TO X, Y.""")
    assert kinds_values(tokens)[5:] == [
        (K.NUMERIC_LITERAL, "1,5"),
        (K.RESERVED_WORD, "TO"),
        (K.USER_WORD, "X"),
        (K.COMMA, ","),
        (K.USER_WORD, "Y"),
        (K.PERIOD, "."),
    ]


def test_separators() -> None:
    tokens = make_tokens("""\
000000     ADD A, B; C TO D(1, 2) E(I:2).
000000     F.""")
    assert [t.kind for t in tokens] == [
        K.RESERVED_WORD,
        K.USER_WORD,
        K.COMMA,
        K.USER_WORD,
        K.SEMICOLON,
        K.USER_WORD,
        K.RESERVED_WORD,
        K.USER_WORD,
        K.LEFT_PAREN,
        K.NUMERIC_LITERAL,
        K.COMMA,
        K.NUMERIC_LITERAL,
        K.RIGHT_PAREN,
        K.USER_WORD,
        K.LEFT_PAREN,
        K.USER_WORD,
        K.COLON,
        K.NUMERIC_LITERAL,
        K.RIGHT_PAREN,
        K.PERIOD,
        K.USER_WORD,
        K.PERIOD,
    ]


@pytest.mark.parametrize("op", ["+", "-", "*", "/", "**", "=", "<", ">", ">=", "<="])
def test_operators(op: str) -> None:
    tokens = make_tokens(f"000000     IF A {op} B")
    assert kinds_values(tokens)[2] == (K.OPERATOR, op)


def test_alphanumeric_literals() -> None:
    tokens = make_tokens("""000000     DISPLAY "A ""B"" C" 'D''E' "F'G".""")
    literals = [t for t in tokens if t.kind is K.ALPHANUMERIC_LITERAL]
    assert [t.value for t in literals] == ['A "B" C', "D'E", "F'G"]
    assert [t.text for t in literals] == ['"A ""B"" C"', "'D''E'", '"F\'G"']
    assert tokens[-1].kind is K.PERIOD
    assert tokens.diagnostics == []


def test_alphanumeric_literal_continued() -> None:
    tokens = make_tokens("""\
000000     MOVE "ABC
000000-    "DEF" TO X.""")
    literal = tokens[1]
    assert literal.value == "ABC" + " " * (65 - len('    MOVE "ABC')) + "DEF"
    assert [tokens.source.slice(s) for s in tokens.to_raw_spans(literal)] == ['"ABC', 'DEF"']
    assert tokens.to_raw_line_cols(tokens[2]) == ((2, 18), (2, 20))
    assert tokens.diagnostics == []


def test_alphanumeric_literal_160_nc107a() -> None:
    # Esse arquivo tem um literal só com aspas começando nas linhas 115-121
    tokens = make_tokens(CORPUS_DIR / "ccvs85/NC107A.CBL")
    lengths = {len(t.value) for t in tokens if t.kind is K.ALPHANUMERIC_LITERAL}
    assert max(lengths) == 160


def test_alphanumeric_literal_unterminated() -> None:
    tokens = make_tokens("""\
000000     MOVE "ABC TO X.
000000     STOP RUN.""")

    assert tokens[1].value == "ABC TO X."
    assert tokens[2].value == "STOP"
    (diagnostic,) = tokens.diagnostics
    assert (
        diagnostic.format(tokens.source)
        == "t:1:17: erro: literal alfanumérico sem aspa de fechamento"
    )


def test_alphanumeric_literal_empty_and_too_long() -> None:
    tokens = make_tokens('000000     MOVE "" TO X.')
    assert [d.message for d in tokens.diagnostics] == ["literal alfanumérico vazio"]
    tokens = make_tokens(f"""\
000000     MOVE "{"A" * 50}
000000-    "{"A" * 50}
000000-    "{"A" * 50}" TO X.""")
    assert [d.message for d in tokens.diagnostics] == [
        "literal alfanumérico com mais de 160 caracteres"
    ]


@pytest.mark.parametrize("after", ["X", "(", "'", ".X"])
def test_alphanumeric_literal_not_followed_by_separator(after: str) -> None:
    tokens = make_tokens(f'000000     MOVE "ABC"{after} TO X.')
    messages = [d.message for d in tokens.diagnostics]
    assert messages[0] == "literal alfanumérico deve ser seguido de separador"


@pytest.mark.parametrize("after", [" ", ")", ". ", ", ", "; "])
def test_alphanumeric_literal_followed_by_separator(after: str) -> None:
    tokens = make_tokens(f'000000     MOVE "ABC"{after}TO X.')
    assert tokens.diagnostics == []


def test_empty_source() -> None:
    tokens = make_tokens("")
    assert len(tokens) == 0
    assert tokens.diagnostics == []


def test_digit_only_name_too_long() -> None:
    tokens = make_tokens(f"000000     PERFORM {'1' * 31}.")
    (diagnostic,) = tokens.diagnostics
    assert diagnostic.message == f"literal numérico com mais de 30 dígitos: {'1' * 31}"


# Testes gerais sobre o corpus
# ----------------------------


@pytest.mark.parametrize("path", CORPUS_CCVS85_NC_FILES, ids=lambda path: path.name)
def test_corpus_invariant(path: Path) -> None:
    tokens = make_tokens(path)
    normalized = tokens.normalized

    covered = set()
    for token in tokens:
        assert token.text == normalized.text[token.start : token.end]
        covered.update(range(token.start, token.end))
        # Round-trip: os spans crus juntados reproduzem o token, sem os caracteres sintéticos
        raw = "".join(normalized.source.slice(s) for s in tokens.to_raw_spans(token))
        assert raw == "".join(
            c
            for i, c in enumerate(token.text, start=token.start)
            if not normalized.map.find_segment(i).synthetic
        )

    # Os tokens cobrem todo o texto normalizado, exceto espaços
    for i, c in enumerate(normalized.text):
        assert i in covered or c in " \n"

    # Enquanto não há modo PICTURE, só cadeias de PICTURE são inválidas
    invalid = [i for i, t in enumerate(tokens) if t.kind is K.INVALID]
    assert all(is_in_picture(tokens, i) for i in invalid)
    assert len(tokens.diagnostics) == len(invalid)
