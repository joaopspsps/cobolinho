# Escolhas de projeto

Escolhas que foram sendo tomadas acerca da arquitetura, organização e filosofia
do projeto.

## Estágios

O programa COBOL passa por estágios de processamento que utilizam a saída dos
estágios anteriores. Estágios são pacotes `stage{n}_{nome}`, com o número para
deixar a ordenação explícita.

Restrições:

- Módulos de estágio não devem importar de estágios subsequentes, mas podem
  importar de estágios anteriores.
- Módulos não de estágios (como `cli.py`) não devem importar de módulos de
  estágios, a não ser que seja um módulo helper de orquestração.

### Saídas dos estágios

As saídas são incrementais: a estrutura de saída de cada estágio guarda uma
referência à saída do estágio anterior, de modo que qualquer saída é
autossuficiente (por exemplo, para formatar localizações `nome:linha:coluna`).

- Cada estágio tem um único construtor, que recebe apenas a saída do estágio
  anterior (mais opções): `CobolLines.from_source(source)`,
  `CobolNormSource.from_lines(lines)`, etc. Encadear estágios é tarefa do código
  de orquestração, não dos estágios.
- Referências para estágios anteriores usam `field(repr=False, compare=False)`.
- Atalhos para estágios mais antigos podem ser expostos como `@property` (por
  exemplo, `CobolNormSource.source` é `self.lines.source`).
- Estruturas auxiliares (como `CobolNormSegment`) são dados puros, sem
  referência ao texto cru; métodos que precisam dele ficam na saída do estágio.
- A saída de um estágio segue o padrão "referência ao estágio anterior + dados
  próprios" (por exemplo, `CobolLines` tem `source` + `lines`, e
  `CobolNormSource` tem `lines` + `text` + `segments` + `diagnostics`), sem
  objetos intermediários que só repassam chamadas.
