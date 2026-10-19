"""Camada do arquivo-fonte cru: offsets, spans e localização linha/coluna."""

import bisect
from dataclasses import dataclass, field


@dataclass(slots=True, frozen=True, order=True)
class Span:
    """Intervalo semiaberto `[start, end)` de offsets."""

    start: int
    end: int

    def __post_init__(self) -> None:
        if not 0 <= self.start <= self.end:
            e = ValueError(f"span inválido: {self.start}..{self.end}")
            raise e

    def __len__(self) -> int:
        return self.end - self.start


@dataclass(slots=True, frozen=True)
class CobolSource:
    """Arquivo-fonte COBOL cru com lista de inícios de linha.

    Linhas são separadas apenas por `\\n`; um `\\r` imediatamente antes do `\\n` (ou no fim do
    arquivo) é tratado como parte do terminador.
    """

    name: str
    """Nome do arquivo ou fonte."""

    text: str
    """Conteúdo do arquivo."""

    _line_starts: list[int] = field(init=False, repr=False, compare=False)
    """Offsets do primeiro caractere de cada linha."""

    def __post_init__(self) -> None:
        """Inicializa `_line_starts`."""
        starts = [0]
        starts.extend(i + 1 for i, c in enumerate(self.text) if c == "\n")

        if len(starts) > 1 and starts[-1] == len(self.text):
            # O texto termina em `\n` e não há linha vazia extra após ele; remove índice
            # inválido
            starts.pop()

        # Usa essa sintaxe porque self é "read-only" dentro de post_init, se não o linter reclama
        object.__setattr__(self, "_line_starts", starts)

    @property
    def line_count(self) -> int:
        """Número de linhas (0 para arquivo vazio)."""
        return 0 if not self.text else len(self._line_starts)

    def get_line_span(self, number: int) -> Span:
        """Obtém o span da linha `number` (começando em 1), sem o terminador de linha.

        Essa função é a base de toda a localização nos próximos estágios, então estes pontos
        são importantes:
        - Para a linha 1, `span.start` aponta para o primeiro caractere do texto (offset
          0). Para uma linha no meio do texto, `span.start` aponta para o primeiro caractere da
          linha atual após o `\\n` da linha anterior.
        - Para uma linha no meio do texto, `span.end` aponta para o próximo `\\n` ou `\\r` (no caso
          de `\\r\\n`) após o começo da linha. Para a última linha, `span.end` pode apontar ao
          próximo offset depois do último caractere válido (EOF, igual a `len(text)`), ou a um
          `\\r`.
        - Se a linha é vazia, `span.start == span.end`.
        """
        if not 1 <= number <= self.line_count:
            e = IndexError(f"linha fora do arquivo: {number}")
            raise e

        start = self._line_starts[number - 1]
        end = self.text.find("\n", start)
        if end == -1:
            end = len(self.text)
        if end > start and self.text[end - 1] == "\r":
            end -= 1

        return Span(start, end)

    def to_line_col(self, offset: int) -> tuple[int, int]:
        """Converte offset cru em `(linha, coluna)`, ambos começando em 1."""
        if not 0 <= offset <= len(self.text):
            e = IndexError(f"offset fora do arquivo: {offset}")
            raise e

        index = bisect.bisect_right(self._line_starts, offset) - 1
        return index + 1, offset - self._line_starts[index] + 1

    def format_location(self, offset: int) -> str:
        """Formata offset como `nome:linha:coluna`."""
        line, col = self.to_line_col(offset)
        return f"{self.name}:{line}:{col}"

    def slice(self, span: Span) -> str:
        """Obtém uma porção do texto cru com um span."""
        return self.text[span.start : span.end]
