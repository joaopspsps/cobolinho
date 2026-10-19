"""Diagnósticos (erros e avisos) emitidos pelos estágios do pipeline."""

import enum
from dataclasses import dataclass

from .stage0_source import CobolSource, Span


class DiagnosticSeverity(enum.Enum):
    """Gravidade de um diagnóstico."""

    ERROR = "erro"
    WARNING = "aviso"


@dataclass(slots=True, frozen=True)
class Diagnostic:
    """Mensagem associada a um span do texto cru."""

    severity: DiagnosticSeverity
    message: str
    span: Span

    def format(self, source: CobolSource) -> str:
        """Formata como `nome:linha:coluna: gravidade: mensagem`."""
        return f"{source.format_location(self.span.start)}: {self.severity.value}: {self.message}"
