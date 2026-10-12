# Convenções do código

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
