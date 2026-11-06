"""Etapa 2 — Agente LLM de conformidade / detecção de anulação."""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.models.base_llm import BaseLlm

from ..config import Config, carregar_config
from ..schemas.saida import ResultadoAnulacao
from .comum import (
    callback_contexto_redacao,
    construir_generate_config,
    construir_modelo,
    instrucao_com_rubrica,
)


def criar_agente_anulacao(
    cfg: Config | None = None, modelo_override: BaseLlm | str | None = None
) -> LlmAgent:
    cfg = cfg or carregar_config()
    return LlmAgent(
        name="agente_anulacao",
        description="Verifica motivos semânticos de anulação (fuga ao tema, tipo textual, impropérios, identificação).",
        model=construir_modelo(cfg, modelo_override),
        instruction=instrucao_com_rubrica("anulacao", "anulacao"),
        generate_content_config=construir_generate_config(cfg),
        output_schema=ResultadoAnulacao,
        output_key="anulacao_llm",
        include_contents="none",
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
        before_model_callback=callback_contexto_redacao(incluir_avaliacao=False),
    )
