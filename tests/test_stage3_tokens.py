"""Testes do estágio 3 tokens."""

from pathlib import Path

import pytest

from cobolinho.stage0_raw import Position
from cobolinho.stage3_tokens import CobolToken, CobolTokens
from cobolinho.stage3_tokens import CobolTokenKind as K

from .utils import CORPUS_DIR, CORPUS_NC_FILES, make_tokens


def kinds_values(tokens: CobolTokens) -> list[tuple[K, str]]:
    return [(t.kind, t.value) for t in tokens]


def find_token(tokens: CobolTokens, text: str) -> CobolToken:
    return next(t for t in tokens if t.text == text)


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
        diagnostic.format(tokens.raw) == f"t:1:17: erro: palavra com mais de 30 caracteres: {word}"
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
    tokens = make_tokens(CORPUS_DIR / "NC107A.CBL")
    token = find_token(tokens, "0000000000000000000000001")
    assert token.kind is K.NUMERIC_LITERAL
    assert tokens.format_location(token) == "NC107A.CBL:1949:8"
    assert tokens.diagnostics == [d for d in tokens.diagnostics if "inválida" in d.message]


def test_decimal_point_is_comma_nc107a() -> None:
    tokens = make_tokens(CORPUS_DIR / "NC107A.CBL")
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
    assert [(t.text, t.kind) for t in tokens] == [
        ("ADD", K.RESERVED_WORD),
        ("A", K.USER_WORD),
        (",", K.COMMA),
        ("B", K.USER_WORD),
        (";", K.SEMICOLON),
        ("C", K.USER_WORD),
        ("TO", K.RESERVED_WORD),
        ("D", K.USER_WORD),
        ("(", K.LEFT_PAREN),
        ("1", K.NUMERIC_LITERAL),
        (",", K.COMMA),
        ("2", K.NUMERIC_LITERAL),
        (")", K.RIGHT_PAREN),
        ("E", K.USER_WORD),
        ("(", K.LEFT_PAREN),
        ("I", K.USER_WORD),
        (":", K.COLON),
        ("2", K.NUMERIC_LITERAL),
        (")", K.RIGHT_PAREN),
        (".", K.PERIOD),
        ("F", K.USER_WORD),
        (".", K.PERIOD),
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
    assert [tokens.raw.slice(s) for s in tokens.to_raw_spans(literal)] == ['"ABC', 'DEF"']
    assert tokens.to_raw_position(tokens[2]) == Position(2, 18)
    assert tokens.diagnostics == []


def test_alphanumeric_literal_160_nc107a() -> None:
    # Esse arquivo tem um literal só com aspas começando nas linhas 115-121
    tokens = make_tokens(CORPUS_DIR / "NC107A.CBL")
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
        diagnostic.format(tokens.raw) == "t:1:17: erro: literal alfanumérico sem aspa de fechamento"
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


def test_empty_text() -> None:
    tokens = make_tokens("")
    assert len(tokens) == 0
    assert tokens.diagnostics == []


def test_digit_only_name_too_long() -> None:
    tokens = make_tokens(f"000000     PERFORM {'1' * 31}.")
    (diagnostic,) = tokens.diagnostics
    assert diagnostic.message == f"literal numérico com mais de 30 dígitos: {'1' * 31}"


def test_picture_strings() -> None:
    tokens = make_tokens("""\
000000 01  A PIC S9(4)V99. 01 B PICTURE IS x(5)BA(10)0X VALUE "X".
000000 01  C PIC IS $$,$$9.99CR; 01 D PIC .9999/99,99. 01 E PIC 9(3)..""")
    pictures = [t for t in tokens if t.kind is K.PICTURE_STRING]
    assert [t.value for t in pictures] == [
        "S9(4)V99",
        "X(5)BA(10)0X",
        "$$,$$9.99CR",
        ".9999/99,99",
        "9(3).",
    ]
    assert pictures[1].text == "x(5)BA(10)0X"
    # `IS` é palavra reservada; pontuação seguida de espaço termina a cadeia
    assert [t.kind for t in tokens if t.value == "IS"] == [K.RESERVED_WORD] * 2
    assert kinds_values(tokens)[-2:] == [(K.PICTURE_STRING, "9(3)."), (K.PERIOD, ".")]
    assert (K.SEMICOLON, ";") in kinds_values(tokens)
    assert tokens.diagnostics == []


def test_picture_missing_string() -> None:
    tokens = make_tokens("000000 01  A PIC. 01 B PIC IS")
    assert kinds_values(tokens) == [
        (K.NUMERIC_LITERAL, "01"),
        (K.USER_WORD, "A"),
        (K.RESERVED_WORD, "PIC"),
        (K.PERIOD, "."),
        (K.NUMERIC_LITERAL, "01"),
        (K.USER_WORD, "B"),
        (K.RESERVED_WORD, "PIC"),
        (K.RESERVED_WORD, "IS"),
    ]


@pytest.mark.parametrize(
    "text", ["X(0)", "X(", "X(A)", "XQ", "(5)X", "X(5)(3)", "CR(2)", "9:9", "IS", '"X"']
)
def test_picture_invalid(text: str) -> None:
    tokens = make_tokens(f"000000 01  A PIC IS {text} VALUE 1.")
    assert tokens[4].kind is K.INVALID
    assert tokens[4].text == text
    assert tokens[5].value == "VALUE"
    (diagnostic,) = tokens.diagnostics
    assert diagnostic.message == f"cadeia de PICTURE inválida: {text}"


def test_picture_too_long() -> None:
    tokens = make_tokens(f"000000 01  A PIC {'X' * 31}.")
    assert tokens[3].kind is K.PICTURE_STRING
    (diagnostic,) = tokens.diagnostics
    assert (
        diagnostic.format(tokens.raw)
        == f"t:1:18: erro: cadeia de PICTURE com mais de 30 caracteres: {'X' * 31}"
    )


def test_picture_currency_sign() -> None:
    tokens = make_tokens("""\
000000 01  A PIC $$9 B PIC W9.
000000     CURRENCY SIGN IS "W".
000000 01  C PIC WW9 D PIC $9.""")
    assert [t.kind for t in tokens if t.value in ("$$9", "W9", "WW9", "$9")] == [
        K.PICTURE_STRING,
        K.INVALID,
        K.PICTURE_STRING,
        K.INVALID,
    ]


@pytest.mark.parametrize(
    ("name", "picture"), [("NC107A.CBL", "W9999"), ("NC108M.CBL", "<(3),<<<.99")]
)
def test_picture_currency_sign_corpus(name: str, picture: str) -> None:
    tokens = make_tokens(CORPUS_DIR / name)
    assert find_token(tokens, picture).kind is K.PICTURE_STRING


@pytest.mark.parametrize(
    "name", ["AUTHOR", "INSTALLATION", "DATE-WRITTEN", "DATE-COMPILED", "SECURITY"]
)
def test_comment_entry(name: str) -> None:
    tokens = make_tokens(f"""\
000000 {name}. A "B' C.
000000     PIC X. 01 ,;
000000*COMENTÁRIO
000000 ENVIRONMENT DIVISION.""")
    assert kinds_values(tokens) == [
        (K.RESERVED_WORD, name),
        (K.PERIOD, "."),
        (K.COMMENT_ENTRY, """A "B' C.\n    PIC X. 01 ,;"""),
        (K.RESERVED_WORD, "ENVIRONMENT"),
        (K.RESERVED_WORD, "DIVISION"),
        (K.PERIOD, "."),
    ]
    entry = tokens[2]
    assert entry.text == entry.value
    assert tokens.to_raw_position(entry) == Position(1, 10 + len(name))
    assert [tokens.raw.slice(s) for s in tokens.to_raw_spans(entry)] == [
        """A "B' C.\n""",
        "    PIC X. 01 ,;",
    ]
    assert tokens.diagnostics == []


def test_comment_entry_next_line() -> None:
    tokens = make_tokens("""\
000000 AUTHOR.
000000     FULANO.
000000 DATE-WRITTEN.""")
    assert kinds_values(tokens) == [
        (K.RESERVED_WORD, "AUTHOR"),
        (K.PERIOD, "."),
        (K.COMMENT_ENTRY, "FULANO."),
        (K.RESERVED_WORD, "DATE-WRITTEN"),
        (K.PERIOD, "."),
    ]


def test_comment_entry_absent() -> None:
    tokens = make_tokens("""\
000000 AUTHOR.
000000 SECURITY.
000000 ENVIRONMENT DIVISION.""")
    assert K.COMMENT_ENTRY not in [t.kind for t in tokens]
    assert len(tokens) == 7


def test_comment_entry_until_end() -> None:
    tokens = make_tokens("000000 SECURITY. NENHUMA")
    assert kinds_values(tokens)[-1] == (K.COMMENT_ENTRY, "NENHUMA")


def test_comment_entry_requires_period() -> None:
    tokens = make_tokens("000000 AUTHOR FULANO.")
    assert kinds_values(tokens) == [
        (K.RESERVED_WORD, "AUTHOR"),
        (K.USER_WORD, "FULANO"),
        (K.PERIOD, "."),
    ]


@pytest.mark.parametrize("name", ["CM101M.CBL", "NC302M.CBL", "NC303M.CBL"])
def test_comment_entry_corpus(name: str) -> None:
    tokens = make_tokens(CORPUS_DIR / name)
    entries = [t for t in tokens if t.kind is K.COMMENT_ENTRY]
    assert entries
    for entry in entries:
        assert tokens.norm.starts_in_area_a(entry.span.end + 1) or entry.span.end == len(
            tokens.norm.text
        )
    assert tokens.diagnostics == []


# Testes gerais sobre o corpus
# ----------------------------


@pytest.mark.parametrize("path", CORPUS_NC_FILES, ids=lambda path: path.name)
def test_corpus_invariant(path: Path) -> None:
    tokens = make_tokens(path)
    norm = tokens.norm

    covered = set()
    for token in tokens:
        assert token.text == norm.slice(token.span)
        covered.update(range(token.span.start, token.span.end))
        # Round-trip: os spans crus juntados reproduzem o token, sem os caracteres sintéticos
        raw = "".join(norm.raw.slice(s) for s in tokens.to_raw_spans(token))
        assert raw == "".join(
            c
            for i, c in enumerate(token.text, start=token.span.start)
            if not norm.find_segment(i).synthetic
        )

    # Os tokens cobrem todo o texto normalizado, exceto espaços
    for i, c in enumerate(norm.text):
        assert i in covered or c in " \n"

    assert not tokens.diagnostics
