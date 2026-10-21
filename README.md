# `cobolinho`

Analisador léxico de programas COBOL-85 em formato fixo (área de sequência,
indicador, A, B e identificação).

## Como rodar

Este projeto usa `uv` para gerenciamento de pacotes e versões.

Rode o programa com o seguinte comando:

``` sh
uv run cobolinho -h
```

## Programas COBOL para teste

O diretório `cbl` contém os programas COBOL da suíte de teste *COBOL Compiler
Validation System* versão 4.2. Eles foram obtidos do diretório `src` do
repositório <https://github.com/z390development/nistcobol85>

São 14 módulos que abrangem os principais recursos do COBOL-85:

| Prefixo | Arquivos | Descrição |
|:--|:--|:--|
| NC | 97 | Recursos centrais da linguagem (núcleo) |
| IF | 45 | Funções intrínsecas (ANSI X3.23b-1993) |
| SQ | 86 | Arquivos sequenciais |
| IX | 42 | Arquivos indexados ISAM/VSAM |
| RL | 35 | Arquivos de registros relativos |
| IC | 35 | Instruções CALL, CANCEL e programas aninhados (IPC) |
| ST | 40 | Instruções SORT e MERGE |
| DB | 15 | Recursos de debug |
| SG | 13 | Segmentação por overlay |
| SM | 17 | Instruções COPY e REPLACING (manipulação de código fonte) |
| CM | 9 | Módulo de comunicação |
| RW | 6 | Geração de relatórios |
| OB | 9 | Elementos obsoletos |
| EX | 1 | Programa de controle da suíte de testes (EXEC85) |
| K | 49 | Copybooks (não são programas) |
| ALT | 2 | Copybooks para uso pelo programa EXEC85 |
| | 2 | Arquivos de dados para uso com o módulo NC |

Detalhes sobre o formato dos arquivos:

- Programas COBOL têm extensão `.CBL`, copybooks `.CPY`, e arquivos de dados
  `.DAT`.
- Todos os arquivos têm exatamente 80 colunas, justificadas com espaços à
  direita.
- Programas podem ter indicadores não-padrão como `S` e `Y`; eles são lidos por
  EXEC85.
- Área de sequência pode ter lixo; por exemplo, NC114M tem `ABCDEF`, `*/+(>'` e
  outros valores entre as linhas 486 e 491.
- Palavras `XXXXX0nn` são placeholders preenchidos pelo programa EXEC85.
- Entradas `AUTHOR.`, `DATE-WRITTEN.` etc. são comentários que extendem até a
  próxima linha
