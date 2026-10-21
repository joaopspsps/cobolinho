# `cobolinho`

O Cobolinho é um analisador léxico de programas COBOL-85 em formato fixo (área
de sequência, indicador, A, B e identificação). Ele é construído como um
pipeline de estágios que levam o programa COBOL cru até os tokens. A saída de
cada estágio é consumida pelo próximo:

- Estágio 0 `raw` (saída `CobolRawSource`): texto cru do programa COBOL, sem
  modificação nenhuma.
- Estágio 1 `lines` (saída `CobolLines`): sequência de linhas físicas
  classificadas pelo indicador, com recortes das áreas.
- Estágio 2 `norm` (saída `CobolNormSource`): texto normalizado apenas para o
  corpo do programa, com continuações de linha colapsadas em linhas lógicas, e
  linhas de comentário descartadas.
- Estágio 3 `tokens` (saída `CobolTokens`): sequência de tokens, com o tipo,
  valor e posição de cada token.

## Como rodar

Este projeto usa `uv` para gerenciamento de pacotes e versões.

Rode o programa com o seguinte comando:

``` sh
uv run cobolinho --help
```

## Testes automatizados

Há testes para cada estágio do pipeline e para a CLI. Alguns testes usam
programas pequenos, específicos a uma funcionalidade, enquanto que outros são
aplicados de forma geral sobre o corpus de teste padrão, que é o conjunto de
programas COBOL do módulo NC da suíte de teste *COBOL Compiler Validation
System* (CCVS85), versão 4.2. Esses programas foram obtidos do diretório `src`
do repositório
[z390development/nistcobol85](https://github.com/z390development/nistcobol85), e
copiados ao diretório `cbl` deste repositório sem modificação. A suíte contém 14
módulos que abrangem os principais recursos do COBOL-85:

| Prefixo | Arquivos | Descrição                                                 |
|:--------|:---------|:----------------------------------------------------------|
| NC      | 95       | Recursos centrais da linguagem (núcleo)                   |
| IF      | 45       | Funções intrínsecas                                       |
| SQ      | 85       | Arquivos sequenciais                                      |
| IX      | 42       | Arquivos indexados ISAM/VSAM                              |
| RL      | 35       | Arquivos de registros relativos                           |
| IC      | 47       | Instruções CALL, CANCEL e programas aninhados (IPC)       |
| ST      | 40       | Instruções SORT e MERGE                                   |
| DB      | 15       | Recursos de debug                                         |
| SG      | 13       | Segmentação por overlay                                   |
| SM      | 17       | Instruções COPY e REPLACING (manipulação de código fonte) |
| CM      | 9        | Módulo de comunicação                                     |
| RW      | 6        | Geração de relatórios                                     |
| OB      | 9        | Elementos obsoletos                                       |
| EX      | 1        | Programa de controle da suíte de testes (EXEC85)          |
| K       | 49       | Copybooks (não são programas)                             |
| ALT     | 2        | Copybooks para uso pelo programa EXEC85                   |
|         | 2        | Arquivos de dados para uso com o módulo NC                |

Para deixar claro, o corpus de teste se limitou aos programas do módulo NC;
outros módulos estão fora do escopo do Cobolinho, e foram usados apenas para
exploração.

Detalhes sobre o formato dos arquivos:

- Programas COBOL têm extensão `.CBL`, copybooks `.CPY`, e arquivos de dados
  `.DAT`.
- Todos os arquivos têm exatamente 80 colunas, justificadas com espaços à
  direita.
- Programas podem ter indicadores não padrão como `Y`, `P`, `C`, `S` e `X`; eles
  são lidos por EXEC85.
- A área de sequência pode ter lixo; por exemplo, NC114M tem `ABCDEF`, `*/+(>'`
  e outros valores entre as linhas 486 e 491.
- Palavras `XXXXX0nn` são placeholders preenchidos pelo programa EXEC85.
