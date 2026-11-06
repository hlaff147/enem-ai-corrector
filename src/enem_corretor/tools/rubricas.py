"""Carregamento das rubricas YAML e dos arquivos de prompt."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from ..config import carregar_config


@lru_cache(maxsize=16)
def carregar_rubrica(nome: str) -> dict[str, Any]:
    """Carrega `rubricas/{nome}.yaml` (ex.: 'c1', 'c2', ..., 'anulacao')."""
    cfg = carregar_config()
    caminho: Path = cfg.dir_rubricas / f"{nome.lower()}.yaml"
    with caminho.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=16)
def rubrica_como_texto(nome: str) -> str:
    cfg = carregar_config()
    caminho: Path = cfg.dir_rubricas / f"{nome.lower()}.yaml"
    return caminho.read_text(encoding="utf-8")


@lru_cache(maxsize=16)
def carregar_prompt(nome: str) -> str:
    """Carrega `prompts/{nome}.md`."""
    cfg = carregar_config()
    caminho: Path = cfg.dir_prompts / f"{nome.lower()}.md"
    return caminho.read_text(encoding="utf-8")
