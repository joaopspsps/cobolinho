# Arquitetura do projeto

## Estágios

O programa COBOL passa por estágios de processamento que utilizam a saída dos
estágios anteriores. Módulos de estágios têm nome de arquivo
`stage{n}_{nome_estagio}.py` para deixar a ordenação explícita.

Restrições:

- Módulos de estágio não devem importar de estágios subsequentes, mas podem
  importar de estágios anteriores.
