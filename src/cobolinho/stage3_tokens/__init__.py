"""Tokens: palavras, literais, separadores."""

import enum
import functools
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Self

from cobolinho.diagnostics import Diagnostic, DiagnosticSeverity
from cobolinho.stage0_raw import CobolRawSource, Position, Span
from cobolinho.stage2_norm import COBOL_QUOTES, CobolNormSource
from cobolinho.stage3_tokens.reserved_words import COBOL_RESERVED_WORDS

COBOL_OPERATORS = {"+", "-", "*", "/", "**", "=", "<", ">", ">=", "<="}
"""Operadores aritméticos e relacionais."""

COBOL_MAX_WORD_LENGTH = 30
"""Limite de caracteres em uma palavra (especificação da linguagem)."""

COBOL_MAX_NUMERIC_DIGITS = 18
"""Limite de dígitos em um literal numérico."""

COBOL_MAX_ALPHANUMERIC_LENGTH = 160
"""Limite de caracteres em um literal alfanumérico."""

COBOL_MAX_PICTURE_LENGTH = 30
"""Limite de caracteres em uma cadeia de PICTURE."""

COBOL_SPACES = " \n"
"""Caracteres de espaço no texto normalizado (o newline separa linhas lógicas)."""


class CobolTokenKind(enum.Enum):
    """Tipo de token COBOL."""

    RESERVED_WORD = enum.auto()
    USER_WORD = enum.auto()
    NUMERIC_LITERAL = enum.auto()
    ALPHANUMERIC_LITERAL = enum.auto()
    PICTURE_STRING = enum.auto()
    """Cadeia de caracteres da cláusula `PIC/PICTURE [IS]`."""
    OPERATOR = enum.auto()
    PERIOD = enum.auto()
    COMMA = enum.auto()
    SEMICOLON = enum.auto()
    COLON = enum.auto()
    LEFT_PAREN = enum.auto()
    RIGHT_PAREN = enum.auto()
    COMMENT_ENTRY = enum.auto()
    """Comentário dos parágrafos opcionais da `IDENTIFICATION DIVISION` (`AUTHOR.` etc.)."""
    INVALID = enum.auto()
    """Cadeia de caracteres que não forma nenhum token válido (sempre com diagnóstico)."""


@dataclass(slots=True, frozen=True)
class CobolToken:
    """Token do texto normalizado."""

    kind: CobolTokenKind
    """Tipo do token."""
    span: Span
    """Span do token no texto normalizado."""
    value: str
    """Valor do token: palavras e cadeias de PICTURE em maiúsculas; literais alfanuméricos sem
    aspas e desescapados; comentários como no texto (podem ocupar várias linhas lógicas)."""
    text: str
    """Texto do token como aparece no texto normalizado."""


@dataclass(slots=True, frozen=True)
class CobolTokens:
    """Tokens do texto normalizado."""

    norm: CobolNormSource = field(repr=False, compare=False)
    tokens: list[CobolToken]
    diagnostics: list[Diagnostic]

    @classmethod
    def from_norm(cls, norm: CobolNormSource) -> Self:
        """Divide o texto normalizado em tokens."""
        scanner = _Scanner(norm)
        scanner.scan()
        return cls(norm, scanner.tokens, scanner.diagnostics)

    @property
    def raw(self) -> CobolRawSource:
        """Atalho para o texto cru."""
        return self.norm.raw

    def to_raw_spans(self, token: CobolToken) -> list[Span]:
        """Spans crus do token (vários se ele for continuado em mais de uma linha física)."""
        return self.norm.to_raw_spans(token.span)

    def to_raw_position(self, token: CobolToken) -> Position:
        """Posição crua do início do token."""
        return self.norm.to_raw_position(token.span.start)

    def format_location(self, token: CobolToken) -> str:
        """Formata o início do token como `nome:linha:coluna` crus."""
        return self.norm.format_location(token.span.start)

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

_CURRENCY_SIGN = (
    ["CURRENCY", "SIGN", "IS"],
    ["CURRENCY", "SIGN"],
    ["CURRENCY", "IS"],
    ["CURRENCY"],
)
"""Cláusula `CURRENCY [SIGN] [IS]` (seguida de literal) do parágrafo `SPECIAL-NAMES`."""

_PICTURE_CLAUSE = (["PIC", "IS"], ["PICTURE", "IS"], ["PIC"], ["PICTURE"])
"""Palavras que precedem uma cadeia de PICTURE."""

_COMMENT_ENTRY_PARAGRAPHS = {
    "AUTHOR",
    "INSTALLATION",
    "DATE-WRITTEN",
    "DATE-COMPILED",
    "SECURITY",
}
"""Parágrafos da `IDENTIFICATION DIVISION` cujo nome (seguido de ponto) precede um comentário."""

_RE_LINE_START = re.compile(r"\n *")
"""Início de linha lógica até o primeiro caractere não espaço."""

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


@functools.cache
def _compile_picture_regex(currency_sign: str) -> re.Pattern[str]:
    """Cadeia de PICTURE: símbolos, cada um opcionalmente seguido de repetição `(n)`, `n > 0`."""
    symbol = rf"[ABPSVXZ90/,.+*-]|{re.escape(currency_sign)}"
    return re.compile(rf"(CR|DB|({symbol})(\(0*[1-9][0-9]*\))?)+", re.IGNORECASE)


@dataclass(slots=True)
class _Scanner:
    """Estado da varredura do texto normalizado."""

    norm: CobolNormSource
    tokens: list[CobolToken] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    decimal_point: str = "."
    """Ponto decimal dos literais numéricos (`,` após `DECIMAL-POINT IS COMMA`)."""
    currency_sign: str = "$"
    """Símbolo de moeda das cadeias de PICTURE (alterado por `CURRENCY SIGN IS literal`)."""

    # Métodos de scan
    # ---------------

    def scan(self) -> None:
        text = self.norm.text
        i = 0
        while i < len(text):
            c = text[i]
            if c in COBOL_SPACES:
                i += 1
            elif self.is_comment_entry_start(i):
                i = self.scan_comment_entry(i)
            elif self.ends_with_words(*_PICTURE_CLAUSE) and not self.is_punctuation(i):
                i = self.scan_picture(i)
            elif c in COBOL_QUOTES:
                i = self.scan_alphanumeric(i)
            elif c in _DELIMITER_KINDS:
                self.add_token(_DELIMITER_KINDS[c], Span(i, i + 1), c)
                i += 1
            elif self.is_punctuation(i):
                self.add_token(_PUNCTUATION_KINDS[c], Span(i, i + 1), c)
                i += 1
            else:
                i = self.scan_string(i)

    def scan_alphanumeric(self, start: int) -> int:
        """Lê um literal alfanumérico; aspas duplicadas dentro dele são escapes."""
        text = self.norm.text
        quote = text[start]
        line_end = text.find("\n", start)
        if line_end == -1:
            line_end = len(text)

        i = start + 1
        while True:
            close = text.find(quote, i, line_end)
            if close == -1:
                self.add_error(
                    "literal alfanumérico sem aspa de fechamento", Span(start, start + 1)
                )
                end, value = line_end, text[start + 1 : line_end]
                break
            if text.startswith(quote, close + 1):
                i = close + 2
                continue
            end, value = close + 1, text[start + 1 : close]
            break

        value = value.replace(quote * 2, quote)
        if not value:
            self.add_error("literal alfanumérico vazio", Span(start, end))
        elif len(value) > COBOL_MAX_ALPHANUMERIC_LENGTH:
            self.add_error(
                f"literal alfanumérico com mais de {COBOL_MAX_ALPHANUMERIC_LENGTH} caracteres",
                Span(start, end),
            )
        # Aspa logo após outro literal já foi reportada pela verificação de fechamento dele
        if start > 0 and text[start - 1] not in COBOL_SPACES + COBOL_QUOTES + "(":
            self.add_error(
                "literal alfanumérico deve ser precedido de espaço ou (", Span(start, start + 1)
            )
        if end < len(text) and (text[end] in COBOL_QUOTES + "(" or not self.is_separator(end)):
            self.add_error("literal alfanumérico deve ser seguido de separador", Span(end, end + 1))

        if len(value) == 1 and self.ends_with_words(*_CURRENCY_SIGN):
            self.currency_sign = value
        self.add_token(CobolTokenKind.ALPHANUMERIC_LITERAL, Span(start, end), value)
        return end

    def scan_comment_entry(self, start: int) -> int:
        """Lê um comentário até a próxima linha lógica com conteúdo na área A (ou o fim)."""
        text = self.norm.text
        end = len(text)
        for match in _RE_LINE_START.finditer(text, start):
            if self.norm.starts_in_area_a(match.end()):
                end = match.start()
                break
        # Linhas lógicas não terminam com espaços, então o comentário também não
        self.add_token(CobolTokenKind.COMMENT_ENTRY, Span(start, end), text[start:end])
        return end

    def scan_picture(self, start: int) -> int:
        """Lê uma cadeia de PICTURE até um espaço ou separador de pontuação (ponto final etc.)."""
        text = self.norm.text
        end = start + 1
        while end < len(text) and text[end] not in COBOL_SPACES and not self.is_punctuation(end):
            end += 1

        string = text[start:end]
        # `IS` não é uma cadeia de PICTURE válida, então é a palavra opcional de `PIC IS`
        if string.upper() == "IS" and self.ends_with_words(["PIC"], ["PICTURE"]):
            return self.scan_string(start)

        if _compile_picture_regex(self.currency_sign).fullmatch(string):
            kind = CobolTokenKind.PICTURE_STRING
            if len(string) > COBOL_MAX_PICTURE_LENGTH:
                self.add_error(
                    f"cadeia de PICTURE com mais de {COBOL_MAX_PICTURE_LENGTH} caracteres: {string}",
                    Span(start, end),
                )
        else:
            kind = CobolTokenKind.INVALID
            self.add_error(f"cadeia de PICTURE inválida: {string}", Span(start, end))

        self.add_token(kind, Span(start, end), string.upper())
        return end

    def scan_string(self, start: int) -> int:
        """Lê e classifica uma cadeia de caracteres até o próximo separador."""
        end = start + 1
        while not self.is_separator(end):
            end += 1

        string = self.norm.text[start:end]
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
                    f"palavra com mais de {COBOL_MAX_WORD_LENGTH} caracteres: {string}",
                    Span(start, end),
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
                    Span(start, end),
                )
        elif string in COBOL_OPERATORS:
            kind, value = CobolTokenKind.OPERATOR, string
        else:
            kind, value = CobolTokenKind.INVALID, string
            self.add_error(f"cadeia de caracteres inválida: {string}", Span(start, end))

        self.add_token(kind, Span(start, end), value)
        if value == "COMMA" and self.ends_with_words(*_DECIMAL_POINT_IS_COMMA):
            self.decimal_point = ","
        return end

    # Predicados puros
    # ----------------

    def is_followed_by_space(self, offset: int) -> bool:
        """Indica se o offset é o último do texto ou é seguido de espaço."""
        text = self.norm.text
        return offset + 1 >= len(text) or text[offset + 1] in COBOL_SPACES

    def is_punctuation(self, offset: int) -> bool:
        """Indica se o offset contém um separador de pontuação (`.`, `,` ou `;` seguido de espaço)."""
        return self.norm.text[offset] in _PUNCTUATION_KINDS and self.is_followed_by_space(offset)

    def is_separator(self, offset: int) -> bool:
        """Indica se o offset começa um separador (ou é o fim do texto)."""
        text = self.norm.text
        if offset >= len(text):
            return True
        c = text[offset]
        if c in COBOL_SPACES or c in COBOL_QUOTES or c in _DELIMITER_KINDS:
            return True
        return self.is_punctuation(offset)

    def is_comment_entry_start(self, offset: int) -> bool:
        """Indica se o offset começa um comentário: vem depois de `AUTHOR.` etc. e não está na
        área A (senão é o próximo parágrafo, e o comentário está ausente)."""
        if len(self.tokens) < 2:
            return False
        name, period = self.tokens[-2:]
        return (
            period.kind is CobolTokenKind.PERIOD
            and name.kind is CobolTokenKind.RESERVED_WORD
            and name.value in _COMMENT_ENTRY_PARAGRAPHS
            and not self.norm.starts_in_area_a(offset)
        )

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

    def add_token(self, kind: CobolTokenKind, span: Span, value: str) -> None:
        text = self.norm.slice(span)
        token = CobolToken(kind, span, value, text)
        self.tokens.append(token)

    def add_error(self, message: str, span: Span) -> None:
        raw_span = self.norm.to_raw_spans(span)[0]
        diagnostic = Diagnostic(DiagnosticSeverity.ERROR, message, raw_span)
        self.diagnostics.append(diagnostic)
