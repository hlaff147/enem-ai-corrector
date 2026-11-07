"""Catálogo formal de chaves e helpers tipados de acesso ao Session State do Google ADK."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from .schemas.entrada import EntradaRedacao
from .schemas.saida import AvaliacaoFinal, Feedback, ResultadoAnulacao


class StateKeys(StrEnum):
    """Identificadores canônicos das chaves do Session State."""

    ENTRADA = "entrada"
    PREANALISE = "preanalise"
    ANULACAO_LLM = "anulacao_llm"
    AVALIACAO_C1 = "avaliacao_c1"
    AVALIACAO_C2 = "avaliacao_c2"
    AVALIACAO_C3 = "avaliacao_c3"
    AVALIACAO_C4 = "avaliacao_c4"
    AVALIACAO_C5 = "avaliacao_c5"
    AVALIACAO_CONSOLIDADA = "avaliacao_consolidada"
    FEEDBACK = "feedback"
    AVALIACAO_FINAL = "avaliacao_final"
    RELATORIO_MARKDOWN = "relatorio_markdown"


def chave_competencia(competencia: str) -> str:
    """Retorna o identificador no session state correspondente a uma competência (`c1`..`c5`)."""
    return f"avaliacao_{competencia.strip().lower()}"


def chaves_reset() -> dict[str, None]:
    """Retorna o delta para limpar saídas de execuções anteriores na mesma sessão."""
    return {
        StateKeys.ANULACAO_LLM: None,
        StateKeys.AVALIACAO_C1: None,
        StateKeys.AVALIACAO_C2: None,
        StateKeys.AVALIACAO_C3: None,
        StateKeys.AVALIACAO_C4: None,
        StateKeys.AVALIACAO_C5: None,
        StateKeys.AVALIACAO_CONSOLIDADA: None,
        StateKeys.FEEDBACK: None,
        StateKeys.AVALIACAO_FINAL: None,
        StateKeys.RELATORIO_MARKDOWN: None,
    }


def obter_entrada(state: dict[str, Any]) -> EntradaRedacao | None:
    """Extrai e valida a `EntradaRedacao` do session state, se presente."""
    raw = state.get(StateKeys.ENTRADA)
    if isinstance(raw, EntradaRedacao):
        return raw
    if isinstance(raw, dict) and raw.get("redacao"):
        try:
            return EntradaRedacao.model_validate(raw)
        except Exception:
            return None
    return None


def obter_preanalise(state: dict[str, Any]) -> dict[str, Any]:
    """Retorna o dicionário de métricas determinísticas da pré-análise."""
    raw = state.get(StateKeys.PREANALISE)
    return raw if isinstance(raw, dict) else {}


def obter_resultado_anulacao(state: dict[str, Any]) -> ResultadoAnulacao | None:
    """Retorna o resultado tipado do agente de anulação, se presente."""
    raw = state.get(StateKeys.ANULACAO_LLM)
    if isinstance(raw, ResultadoAnulacao):
        return raw
    if isinstance(raw, dict) and "anular" in raw:
        try:
            return ResultadoAnulacao.model_validate(raw)
        except Exception:
            return None
    return None


def obter_avaliacao_competencia(state: dict[str, Any], competencia: str) -> dict[str, Any] | None:
    """Retorna o payload bruto gravado pelo avaliador da competência especificada."""
    raw = state.get(chave_competencia(competencia))
    return raw if isinstance(raw, dict) and "nota" in raw else None


def obter_avaliacao_consolidada(state: dict[str, Any]) -> dict[str, Any] | None:
    """Retorna o payload consolidado pelo juiz determinístico."""
    raw = state.get(StateKeys.AVALIACAO_CONSOLIDADA)
    return raw if isinstance(raw, dict) else None


def obter_feedback(state: dict[str, Any]) -> Feedback | None:
    """Retorna o feedback pedagógico validado, se presente."""
    raw = state.get(StateKeys.FEEDBACK)
    if isinstance(raw, Feedback):
        return raw
    if isinstance(raw, dict):
        try:
            return Feedback.model_validate(raw)
        except Exception:
            return None
    return None


def obter_avaliacao_final(state: dict[str, Any]) -> AvaliacaoFinal | None:
    """Retorna a `AvaliacaoFinal` estruturada e validada."""
    raw = state.get(StateKeys.AVALIACAO_FINAL)
    if isinstance(raw, AvaliacaoFinal):
        return raw
    if isinstance(raw, dict) and "nota_total" in raw:
        try:
            return AvaliacaoFinal.model_validate(raw)
        except Exception:
            return None
    return None


def obter_relatorio_markdown(state: dict[str, Any]) -> str:
    """Retorna a string formatada em Markdown do relatório final."""
    return str(state.get(StateKeys.RELATORIO_MARKDOWN) or "")
