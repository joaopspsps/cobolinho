# Escolhas de projeto

Escolhas que foram sendo tomadas acerca da arquitetura, organização e filosofia
do projeto.

## Estágios

O programa COBOL passa por estágios de processamento que utilizam a saída dos
estágios anteriores. Estágios são pacotes `stage{n}_{nome}`, com o número para
deixar a ordenação explícita.

Restrição: módulos de estágio não devem importar de estágios subsequentes, mas
podem importar de estágios anteriores.

### Saídas dos estágios

As saídas são incrementais: a estrutura de saída de cada estágio guarda uma
referência à saída do estágio anterior, de modo que qualquer saída é
autossuficiente (por exemplo, para formatar localizações `nome:linha:coluna`).

- Cada estágio tem um único construtor, que recebe apenas a saída do estágio
  anterior (mais opções): `CobolLines.from_raw(raw)`,
  `CobolNormSource.from_lines(lines)`, etc. Encadear estágios é tarefa do código
  de orquestração, não dos estágios.
- Referências para estágios anteriores usam `field(repr=False, compare=False)`.
- Atalhos para estágios mais antigos podem ser expostos como `@property` (por
  exemplo, `CobolNormSource.raw` é `self.lines.raw`).
- Estruturas auxiliares (como `CobolNormSegment`) são dados puros, sem
  referência ao texto cru; métodos que precisam dele ficam na saída do estágio.
- A saída de um estágio segue o padrão "referência ao estágio anterior + dados
  próprios" (por exemplo, `CobolLines` tem `raw` + `lines`, e `CobolNormSource`
  tem `lines` + `text` + `segments` + `diagnostics`), sem objetos intermediários
  que só repassam chamadas.
