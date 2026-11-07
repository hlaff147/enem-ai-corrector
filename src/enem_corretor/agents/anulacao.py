"""Etapa 2 — Agente LLM de conformidade / detecção de anulação e Coordenador de Elegibilidade."""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator

from google.adk.agents import BaseAgent, LlmAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.adk.models.base_llm import BaseLlm
from google.adk.utils.context_utils import Aclosing

from ..config import Config, carregar_config
from ..schemas.saida import ResultadoAnulacao
from ..state_keys import StateKeys, obter_preanalise, obter_resultado_anulacao
from .comum import (
    callback_contexto_redacao,
    construir_generate_config,
    construir_modelo,
    instrucao_com_rubrica,
)

logger = logging.getLogger(__name__)


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
        output_key=StateKeys.ANULACAO_LLM,
        include_contents="none",
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
        before_model_callback=callback_contexto_redacao(incluir_avaliacao=False),
    )


class EligibilityCoordinator:
    """Coordenador do processo de triagem e elegibilidade (Gate 1 Determinístico e Gate 2 Semântico)."""

    def __init__(
        self,
        agente_anulacao: LlmAgent | None = None,
        cfg: Config | None = None,
        modelo_override: BaseLlm | str | None = None,
    ) -> None:
        self.cfg = cfg or carregar_config()
        self.agente_anulacao = agente_anulacao or criar_agente_anulacao(
            self.cfg, modelo_override=modelo_override
        )

    def verificar_anulacao_deterministica(self, state: dict[str, Any]) -> list[str]:
        """Gate 1: Retorna lista de motivos determinísticos de anulação, se houver."""
        pre = obter_preanalise(state)
        return list(pre.get("motivos_anulacao_deterministicos") or [])

    async def executar_triagem_semantica(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        """Gate 2: Executa o agente LLM de anulação semântica se a redação passar pelo Gate 1."""
        try:
            async with Aclosing(self.agente_anulacao.run_async(ctx)) as agen:
                async for ev in agen:
                    yield ev
        except Exception as exc:
            logger.warning("Falha na execução do agente de anulação semântica: %s", exc)

    def verificar_anulacao_semantica(self, state: dict[str, Any]) -> bool:
        """Verifica se o agente semântico confirmou anulação."""
        res = obter_resultado_anulacao(state)
        return bool(res and res.anular)
