"""Utilidades compartilhadas entre os testes."""

from pathlib import Path
from typing import Any

from cobolinho.stage0_raw import CobolRawSource
from cobolinho.stage1_lines import CobolLines
from cobolinho.stage2_norm import CobolNormSource
from cobolinho.stage3_tokens import CobolTokens

CORPUS_DIR = Path(__file__).parent.parent / "cbl"
CORPUS_NC_FILES = sorted((CORPUS_DIR).glob("NC*.CBL"))


def make_lines(text_or_path: str | Path) -> CobolLines:
    if isinstance(text_or_path, Path):
        name = text_or_path.name
        text = text_or_path.read_text(newline="")
    else:
        name = "t"
        text = text_or_path
    return CobolLines.from_raw(CobolRawSource(name, text))


def make_norm(text_or_path: str | Path, **kwargs: Any) -> CobolNormSource:
    return CobolNormSource.from_lines(make_lines(text_or_path), **kwargs)


def make_tokens(text_or_path: str | Path, **kwargs_norm: Any) -> CobolTokens:
    return CobolTokens.from_norm(make_norm(text_or_path, **kwargs_norm))
