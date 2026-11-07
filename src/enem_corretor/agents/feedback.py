"""Etapa 5 — Agente de Feedback Pedagógico e Reescrita e Coordenador de Feedback."""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator

from google.adk.agents import BaseAgent, LlmAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.adk.models.base_llm import BaseLlm
from google.adk.utils.context_utils import Aclosing

from ..config import Config, carregar_config
from ..schemas.saida import Feedback
from ..state_keys import StateKeys, obter_feedback
from .comum import (
    callback_contexto_redacao,
    construir_generate_config,
    construir_modelo,
    instrucao_com_rubrica,
)

logger = logging.getLogger(__name__)


def criar_agente_feedback(
    cfg: Config | None = None, modelo_override: BaseLlm | str | None = None
) -> LlmAgent:
    cfg = cfg or carregar_config()
    return LlmAgent(
        name="agente_feedback",
        description="Gera feedback acionável, prioridades de melhoria, exemplos de reescrita e checklist.",
        model=construir_modelo(cfg, modelo_override),
        instruction=instrucao_com_rubrica("feedback", None),
        generate_content_config=construir_generate_config(cfg),
        output_schema=Feedback,
        output_key=StateKeys.FEEDBACK,
        include_contents="none",
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
        before_model_callback=callback_contexto_redacao(incluir_avaliacao=True),
    )


class FeedbackCoordinator:
    """Coordenador da geração de feedback pedagógico condicionado às notas consolidadas."""

    def __init__(
        self,
        agente_feedback: LlmAgent | None = None,
        cfg: Config | None = None,
        modelo_override: BaseLlm | str | None = None,
    ) -> None:
        self.cfg = cfg or carregar_config()
        self.agente_feedback = agente_feedback or criar_agente_feedback(
            self.cfg, modelo_override=modelo_override
        )

    async def executar_feedback_async(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        """Invoca o agente de feedback isolado e trata falhas graciosamente."""
        try:
            async with Aclosing(self.agente_feedback.run_async(ctx)) as agen:
                async for ev in agen:
                    yield ev
        except Exception as exc:
            logger.warning("Falha na geração do feedback pedagógico: %s", exc)

    def extrair_feedback(self, state: dict[str, Any]) -> Feedback | None:
        """Extrai e valida o feedback registrado no session state."""
        return obter_feedback(state)
