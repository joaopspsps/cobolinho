"""Utilidades compartilhadas entre os testes."""

from pathlib import Path
from typing import Any

from cobolinho.stage0_source import CobolSource
from cobolinho.stage1_lines import CobolLines
from cobolinho.stage2_normalized import CobolNormalizedSource
from cobolinho.stage3_tokenizer import CobolTokens

CORPUS_DIR = Path(__file__).parent.parent / "cbl"
CORPUS_CCVS85_NC_FILES = sorted((CORPUS_DIR).glob("ccvs85/NC*.CBL"))


def make_lines(text_or_path: str | Path) -> CobolLines:
    if isinstance(text_or_path, Path):
        name = text_or_path.name
        text = text_or_path.read_text(newline="")
    else:
        name = "t"
        text = text_or_path
    return CobolLines.from_source(CobolSource(name, text))


def make_norm(text_or_path: str | Path, **kwargs: Any) -> CobolNormalizedSource:
    return CobolNormalizedSource.from_lines(make_lines(text_or_path), **kwargs)


def make_tokens(text_or_path: str | Path, **kwargs_norm: Any) -> CobolTokens:
    return CobolTokens.from_normalized(make_norm(text_or_path, **kwargs_norm))
