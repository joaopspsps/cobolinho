"""Tokenizer: divide o texto normalizado em tokens (palavras, literais, separadores)."""

import enum
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Self

from .diagnostics import Diagnostic, DiagnosticSeverity
from .reserved_words import COBOL_RESERVED_WORDS
from .stage0_source import CobolSource, Span
from .stage2_normalized import COBOL_QUOTES, CobolNormalizedSource

COBOL_OPERATORS = {"+", "-", "*", "/", "**", "=", "<", ">", ">=", "<="}
"""Operadores aritméticos e relacionais."""

COBOL_MAX_WORD_LENGTH = 30
"""Limite de caracteres em uma palavra (especificação da linguagem)."""

COBOL_MAX_NUMERIC_DIGITS = 18
"""Limite de dígitos em um literal numérico."""

COBOL_MAX_ALPHANUMERIC_LENGTH = 160
"""Limite de caracteres em um literal alfanumérico."""

COBOL_SPACES = " \n"
"""Caracteres de espaço no texto normalizado (o newline separa linhas lógicas)."""


class CobolTokenKind(enum.Enum):
    """Tipo de token do COBOL."""

    RESERVED_WORD = enum.auto()
    USER_WORD = enum.auto()
    NUMERIC_LITERAL = enum.auto()
    ALPHANUMERIC_LITERAL = enum.auto()
    OPERATOR = enum.auto()
    PERIOD = enum.auto()
    COMMA = enum.auto()
    SEMICOLON = enum.auto()
    COLON = enum.auto()
    LEFT_PAREN = enum.auto()
    RIGHT_PAREN = enum.auto()
    INVALID = enum.auto()
    """Cadeia de caracteres que não forma nenhum token válido (sempre com diagnóstico)."""


@dataclass(slots=True, frozen=True)
class CobolToken:
    """Token com intervalo semiaberto `[start, end)` em offsets do texto normalizado."""

    kind: CobolTokenKind
    """Tipo do token."""
    start: int
    """Offset do primeiro caractere do token no texto normalizado."""
    end: int
    """Offset do último caractere do token no texto normalizado."""
    value: str
    """Valor do token: palavras em maiúsculas; literais alfanuméricos sem aspas e desescapados."""
    text: str
    """Texto do token como aparece no texto normalizado."""


@dataclass(slots=True, frozen=True)
class CobolTokens:
    """Tokens do texto normalizado."""

    normalized: CobolNormalizedSource = field(repr=False, compare=False)
    tokens: list[CobolToken]
    diagnostics: list[Diagnostic]

    @classmethod
    def from_normalized(cls, normalized: CobolNormalizedSource) -> Self:
        """Divide o texto de `normalized` em tokens."""
        scanner = _Scanner(normalized)
        scanner.scan()
        return cls(normalized, scanner.tokens, scanner.diagnostics)

    @property
    def source(self) -> CobolSource:
        """Atalho para `normalized.source`."""
        return self.normalized.source

    def to_raw_spans(self, token: CobolToken) -> list[Span]:
        """Spans crus do token (vários se ele for continuado em mais de uma linha física)."""
        return self.normalized.map.to_raw_spans(token.start, token.end)

    def to_raw_line_cols(self, token: CobolToken) -> tuple[tuple[int, int], tuple[int, int]]:
        """`(linha, coluna)` crus do início e fim do token."""
        return self.normalized.to_raw_line_col(token.start), self.normalized.to_raw_line_col(
            token.end
        )

    def format_location(self, token: CobolToken) -> str:
        """Formata o início do token como `nome:linha:coluna` crus."""
        return self.normalized.format_location(token.start)

    def __len__(self) -> int:
        return len(self.tokens)

    def __iter__(self) -> Iterator[CobolToken]:
        return iter(self.tokens)

    def __getitem__(self, index: int) -> CobolToken:
        return self.tokens[index]


# Código privado
# --------------


_RE_NUMERIC = {
    ".": re.compile(r"[+-]?([0-9]*\.)?[0-9]+"),
    ",": re.compile(r"[+-]?([0-9]*,)?[0-9]+"),
}
"""Literal numérico por caractere de ponto decimal; o ponto não pode ser o último caractere."""

_DECIMAL_POINT_IS_COMMA = (["DECIMAL-POINT", "IS", "COMMA"], ["DECIMAL-POINT", "COMMA"])
"""Cláusula `DECIMAL-POINT IS COMMA` (com `IS` opcional) do parágrafo `SPECIAL-NAMES`."""

_RE_INTEGER = re.compile(r"[0-9]+")
"""Inteiro sem sinal (literal numérico ou nome de parágrafo/seção só com dígitos)."""

_RE_WORD = re.compile(r"[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?")
"""Palavra COBOL: letras, dígitos e hífens, sem hífen no início ou no fim."""

_PUNCTUATION_KINDS = {
    ".": CobolTokenKind.PERIOD,
    ",": CobolTokenKind.COMMA,
    ";": CobolTokenKind.SEMICOLON,
}
"""Separadores que só valem como tal quando seguidos de espaço (ou do fim do texto)."""

_DELIMITER_KINDS = {
    ":": CobolTokenKind.COLON,
    "(": CobolTokenKind.LEFT_PAREN,
    ")": CobolTokenKind.RIGHT_PAREN,
}
"""Separadores que valem em qualquer posição."""


@dataclass(slots=True)
class _Scanner:
    """Estado da varredura do texto normalizado."""

    normalized: CobolNormalizedSource
    tokens: list[CobolToken] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    decimal_point: str = "."
    """Ponto decimal dos literais numéricos (`,` após `DECIMAL-POINT IS COMMA`)."""

    # Métodos de scan
    # ---------------

    def scan(self) -> None:
        text = self.normalized.text
        i = 0
        while i < len(text):
            c = text[i]
            if c in COBOL_SPACES:
                i += 1
            elif c in COBOL_QUOTES:
                i = self.scan_alphanumeric(i)
            elif c in _DELIMITER_KINDS:
                self.add_token(_DELIMITER_KINDS[c], i, i + 1, c)
                i += 1
            elif c in _PUNCTUATION_KINDS and self.is_followed_by_space(i):
                self.add_token(_PUNCTUATION_KINDS[c], i, i + 1, c)
                i += 1
            else:
                i = self.scan_string(i)

    def scan_alphanumeric(self, start: int) -> int:
        """Lê um literal alfanumérico; aspas duplicadas dentro dele são escapes."""
        text = self.normalized.text
        quote = text[start]
        line_end = text.find("\n", start)
        if line_end == -1:
            line_end = len(text)

        i = start + 1
        while True:
            close = text.find(quote, i, line_end)
            if close == -1:
                self.add_error("literal alfanumérico sem aspa de fechamento", start, start + 1)
                end, value = line_end, text[start + 1 : line_end]
                break
            if text.startswith(quote, close + 1):
                i = close + 2
                continue
            end, value = close + 1, text[start + 1 : close]
            break

        value = value.replace(quote * 2, quote)
        if not value:
            self.add_error("literal alfanumérico vazio", start, end)
        elif len(value) > COBOL_MAX_ALPHANUMERIC_LENGTH:
            self.add_error(
                f"literal alfanumérico com mais de {COBOL_MAX_ALPHANUMERIC_LENGTH} caracteres",
                start,
                end,
            )
        if end < len(text) and (text[end] in COBOL_QUOTES + "(" or not self.is_separator(end)):
            self.add_error("literal alfanumérico deve ser seguido de separador", end, end + 1)

        self.add_token(CobolTokenKind.ALPHANUMERIC_LITERAL, start, end, value)
        return end

    def scan_string(self, start: int) -> int:
        """Lê e classifica uma cadeia de caracteres até o próximo separador."""
        end = start + 1
        while not self.is_separator(end):
            end += 1

        string = self.normalized.text[start:end]
        is_integer = _RE_INTEGER.fullmatch(string) is not None
        if _RE_WORD.fullmatch(string) and not is_integer:
            value = string.upper()
            kind = (
                CobolTokenKind.RESERVED_WORD
                if value in COBOL_RESERVED_WORDS
                else CobolTokenKind.USER_WORD
            )
            if len(string) > COBOL_MAX_WORD_LENGTH:
                self.add_error(
                    f"palavra com mais de {COBOL_MAX_WORD_LENGTH} caracteres: {string}", start, end
                )
        elif _RE_NUMERIC[self.decimal_point].fullmatch(string):
            kind, value = CobolTokenKind.NUMERIC_LITERAL, string
            # Inteiros sem sinal podem ser nomes de parágrafo/seção (até 30 caracteres); cabe ao
            # parser verificar o limite de dígitos nesse caso
            digits = sum(c in "0123456789" for c in string)
            limit = COBOL_MAX_WORD_LENGTH if is_integer else COBOL_MAX_NUMERIC_DIGITS
            if digits > limit:
                self.add_error(
                    f"literal numérico com mais de {limit} dígitos: {string}",
                    start,
                    end,
                )
        elif string in COBOL_OPERATORS:
            kind, value = CobolTokenKind.OPERATOR, string
        else:
            kind, value = CobolTokenKind.INVALID, string
            self.add_error(f"cadeia de caracteres inválida: {string}", start, end)

        self.add_token(kind, start, end, value)
        if value == "COMMA" and self.ends_with_words(*_DECIMAL_POINT_IS_COMMA):
            self.decimal_point = ","
        return end

    # Predicados puros
    # ----------------

    def is_followed_by_space(self, i: int) -> bool:
        """Indica se o caractere `i` é o último do texto ou é seguido de espaço."""
        text = self.normalized.text
        return i + 1 >= len(text) or text[i + 1] in COBOL_SPACES

    def is_separator(self, i: int) -> bool:
        """Indica se a posição `i` começa um separador (ou é o fim do texto)."""
        text = self.normalized.text
        if i >= len(text):
            return True
        c = text[i]
        if c in COBOL_SPACES or c in COBOL_QUOTES or c in _DELIMITER_KINDS:
            return True
        return c in _PUNCTUATION_KINDS and self.is_followed_by_space(i)

    def ends_with_words(self, *sequences: list[str]) -> bool:
        """Indica se os últimos tokens são as palavras de alguma das sequências dadas."""
        for words in sequences:
            last = self.tokens[-len(words) :]
            if [t.value for t in last] == words and all(
                t.kind in (CobolTokenKind.RESERVED_WORD, CobolTokenKind.USER_WORD) for t in last
            ):
                return True
        return False

    # Helpers com side effects
    # ------------------------

    def add_token(self, kind: CobolTokenKind, start: int, end: int, value: str) -> None:
        self.tokens.append(CobolToken(kind, start, end, value, self.normalized.text[start:end]))

    def add_error(self, message: str, start: int, end: int) -> None:
        span = self.normalized.map.to_raw_spans(start, end)[0]
        self.diagnostics.append(Diagnostic(DiagnosticSeverity.ERROR, message, span))
