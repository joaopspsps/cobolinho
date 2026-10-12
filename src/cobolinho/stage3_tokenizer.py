import enum
from dataclasses import dataclass

# Palavras reservadas do COBOL. Têm precedência sobre palavras definidas pelo usuário.
RESERVED_WORDS = {
    "ACCEPT",
    "DATA",
    "DISPLAY",
    "DIVISION",
    "ELSE",
    "END-IF",
    "ENVIRONMENT",
    "IDENTIFICATION",
    "IF",
    "MOVE",
    "PERFORM",
    "PIC",
    "PICTURE",
    "PROCEDURE",
    "RUN",
    "SECTION",
    "STOP",
    # ...
}


class TokenKind(enum.Enum):
    """Tipo de token do COBOL."""

    RESERVED_WORD = enum.auto()
    USER_WORD = enum.auto()
    # ...


@dataclass(slots=True, frozen=True)
class Token:
    kind: TokenKind
    value: str
    start: int
    end: int
