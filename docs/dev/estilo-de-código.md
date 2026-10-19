# Estilo de código

Convenções opinionadas sobre práticas que tornam o código mais legível,
eficiente ou fácil de manter.

## Nomenclatura de identificadores (variáveis, funções, classes)

### Funções começam com verbo

Funções e métodos são nomeados pelo que fazem: `group_lines`, `find_segment`,
`add_raw`. Verbos descritivos enriquecem a documentação de uma função.
Propriedades e campos são lidos como dados (substantivos): `norm_length`,
`source`, `is_comment_like`.

Prefixos idiomáticos do Python são exceções, por exemplo:

- `from_*`: para classmethods (`from_source`, `from_lines`).
- `to_*`: conversões (`to_raw_offset`, `to_raw_spans`).
- `iter_*`: função com yield (`iter_logical_lines`).
- `is_*`, `has_*`, `starts_*`: predicados (`starts_in_area_a`).

Funções podem ter prefixos compartilhados antes dos verbos, como em C
(`pthread_mutex_lock`, `pthread_mutex_unlock`). Um exemplo no projeto é
`parser_init`.

Ruim:

``` py
def newline_offset(source, line): ...
```

Bom:

``` py
def find_newline_offset(source, line): ...
```

### Nomes relacionados compartilham o prefixo

A parte comum vem primeiro e o que distingue os nomes vem depois. Assim, os
nomes ficam agrupados na leitura, alinhados, e melhor encontrados no
autocomplete ou grep.

Ruim:

``` py
start_norm, end_norm, start_raw, end_raw
lstrip, rstrip
```

Bom:

``` py
norm_start, norm_end, raw_start, raw_end
strip_start, strip_end
```

### Tamanho proporcional ao escopo

> Use descriptive names for globals, short names for locals.
>
> --- Kernighan & Pike, The Practice of Programming

O nome deve ser tão curto quanto possível sem perder clareza, e o tamanho
aceitável cresce com o escopo. Nomes de uma letra só servem para escopos
minúsculos (`i` num loop de uma linha, `c` para um caractere, `e` para uma
exceção). Nomes que atravessam funções ou módulos precisam dizer o que são, mas
sem repetir o que o contexto (classe, módulo, tipo) já diz.

Ruim:

``` py
offset_of_character_in_normalized_source
```

Bom:

``` py
norm_start  # dentro de Segment, "do segmento" é implícito
```

### Referências

- [Swift API Design
  Guidelines](https://www.swift.org/documentation/api-design-guidelines)
- Kerninghan & Pike, *The Practice of Programming*, capítulo 1.
- Steve McConnell, *Code Complete*, capítulos 7 e 11.
- [Andrew Gerrand, *What's in a name*](https://go.dev/talks/2014/names.slide)

## Levantamento de exceções

Sempre salve a exceção em uma variável antes de levantá-la, para que o traceback
não mostre a exceção duas vezes repetidas.

Ruim:

``` py
raise ValueError()
```

Bom:

``` py
e = ValueError()
raise e
```
