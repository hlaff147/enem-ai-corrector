"""Configuração do corretor (lida de variáveis de ambiente / arquivo .env)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

RAIZ_PROJETO = Path(__file__).resolve().parents[2]

load_dotenv(RAIZ_PROJETO / ".env")


def _bool(nome: str, padrao: bool) -> bool:
    valor = os.getenv(nome)
    if valor is None or valor.strip() == "":
        return padrao
    return valor.strip().lower() in {"1", "true", "sim", "yes", "on"}


def _int(nome: str, padrao: int) -> int:
    valor = os.getenv(nome)
    return int(valor) if valor and valor.strip() else padrao


def _float(nome: str, padrao: float) -> float:
    valor = os.getenv(nome)
    return float(valor) if valor and valor.strip() else padrao


@dataclass(frozen=True)
class Config:
    # Modelo -----------------------------------------------------------------
    modelo: str
    """Nome do modelo. Ex.: 'gemini-3.5-flash' (Gemini nativo) ou
    'ollama_chat/qwen2.5:7b', 'openrouter/...', 'groq/...' (via LiteLLM)."""
    temperatura: float
    semente: int | None
    tentativas_modelo: int
    paralelo: bool
    """Rodar os agentes C1–C5 em paralelo (desligue para Ollama/limites de taxa)."""
    tentativas_competencia: int
    """Quantas vezes re-executar um agente de competência que falhou."""

    # Heurísticas de texto ---------------------------------------------------
    caracteres_por_linha: int
    """Heurística para estimar linhas manuscritas a partir de texto digitado."""
    linhas_minimas: int
    linhas_maximas: int

    # Ferramentas externas ---------------------------------------------------
    languagetool_habilitado: bool
    languagetool_url: str

    # Caminhos ---------------------------------------------------------------
    dir_rubricas: Path
    dir_prompts: Path
    dir_execucoes: Path
    salvar_execucoes: bool

    @property
    def usa_litellm(self) -> bool:
        return "/" in self.modelo


@lru_cache(maxsize=1)
def carregar_config() -> Config:
    semente = os.getenv("ENEM_SEMENTE")
    return Config(
        modelo=os.getenv("ENEM_MODELO", "gemini-3.5-flash"),
        temperatura=_float("ENEM_TEMPERATURA", 0.1),
        semente=int(semente) if semente and semente.strip() else None,
        tentativas_modelo=_int("ENEM_TENTATIVAS_MODELO", 4),
        paralelo=_bool("ENEM_PARALELO", True),
        tentativas_competencia=_int("ENEM_TENTATIVAS_COMPETENCIA", 2),
        caracteres_por_linha=_int("ENEM_CARACTERES_POR_LINHA", 70),
        linhas_minimas=_int("ENEM_LINHAS_MINIMAS", 8),
        linhas_maximas=_int("ENEM_LINHAS_MAXIMAS", 30),
        languagetool_habilitado=_bool("LANGUAGETOOL_HABILITADO", False),
        languagetool_url=os.getenv(
            "LANGUAGETOOL_URL", "https://api.languagetool.org/v2/check"
        ),
        dir_rubricas=Path(os.getenv("ENEM_DIR_RUBRICAS", RAIZ_PROJETO / "rubricas")),
        dir_prompts=Path(os.getenv("ENEM_DIR_PROMPTS", RAIZ_PROJETO / "prompts")),
        dir_execucoes=Path(
            os.getenv("ENEM_DIR_EXECUCOES", RAIZ_PROJETO / "data" / "execucoes")
        ),
        salvar_execucoes=_bool("ENEM_SALVAR_EXECUCOES", True),
    )
