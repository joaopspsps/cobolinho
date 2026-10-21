"""Testes da interface com a linha de comando."""

import pytest

from cobolinho.__main__ import dump_norm, dump_tokens
from cobolinho.stage0_raw import CobolRawSource


def test_dump_tokens_without_diagnostics(capsys: pytest.CaptureFixture[str]) -> None:
    raw = CobolRawSource("t", "000000     STOP RUN.\n")
    assert dump_tokens(raw, include_debug=False, include_other=True) == 0
    assert capsys.readouterr().err == ""


def test_dump_tokens_stage3_diagnostic(capsys: pytest.CaptureFixture[str]) -> None:
    raw = CobolRawSource("t", "000000     COMPUTE X=A+B.\n")
    assert dump_tokens(raw, include_debug=False, include_other=True) == 1
    assert "cadeia de caracteres inválida" in capsys.readouterr().err


def test_dump_tokens_stage2_diagnostic(capsys: pytest.CaptureFixture[str]) -> None:
    # Só o estágio 2 emite diagnóstico, mas o código de saída deve refletir isso
    raw = CobolRawSource("t", '000000-    "ABC".\n')
    assert dump_tokens(raw, include_debug=False, include_other=True) == 1
    assert "linha de continuação sem linha de código anterior" in capsys.readouterr().err


def test_dump_norm_stage2_diagnostic(capsys: pytest.CaptureFixture[str]) -> None:
    raw = CobolRawSource("t", '000000-    "ABC".\n')
    assert dump_norm(raw, include_debug=False, include_other=True) == 1
    assert "linha de continuação sem linha de código anterior" in capsys.readouterr().err
