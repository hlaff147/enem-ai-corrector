"""Etapa 3 — Agentes avaliadores das 5 competências do ENEM (C1 a C5) e Painel de Competências."""

from __future__ import annotations

import logging
import warnings
from typing import Any, AsyncGenerator

from google.adk.agents import BaseAgent, LlmAgent, ParallelAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.adk.models.base_llm import BaseLlm
from google.adk.utils.context_utils import Aclosing

from ..config import Config, carregar_config
from ..schemas.saida import COMPETENCIAS, SCHEMAS_COMPETENCIA
from ..state_keys import chave_competencia, obter_avaliacao_competencia
from .comum import (
    callback_contexto_redacao,
    callback_guardrail_nota_competencia,
    construir_generate_config,
    construir_modelo,
    instrucao_com_rubrica,
)

logger = logging.getLogger(__name__)

DESCRICOES_COMPETENCIA: dict[str, str] = {
    "C1": "Avalia a Competência 1 (domínio da modalidade escrita formal da língua portuguesa).",
    "C2": "Avalia a Competência 2 (compreensão do tema, estrutura dissertativo-argumentativa e repertório).",
    "C3": "Avalia a Competência 3 (projeto de texto, seleção e desenvolvimento de argumentos).",
    "C4": "Avalia a Competência 4 (mecanismos linguísticos de coesão e articulação argumentativa).",
    "C5": "Avalia a Competência 5 (proposta de intervenção com 5 elementos e respeito aos direitos humanos).",
}


def criar_agente_competencia(
    competencia: str,
    cfg: Config | None = None,
    modelo_override: BaseLlm | str | None = None,
) -> LlmAgent:
    comp = competencia.upper()
    if comp not in SCHEMAS_COMPETENCIA:
        raise ValueError(f"Competência inválida: {competencia}")

    cfg = cfg or carregar_config()
    codigo_lower = comp.lower()
    return LlmAgent(
        name=f"agente_{codigo_lower}",
        description=DESCRICOES_COMPETENCIA[comp],
        model=construir_modelo(cfg, modelo_override),
        instruction=instrucao_com_rubrica(codigo_lower, codigo_lower),
        generate_content_config=construir_generate_config(cfg),
        output_schema=SCHEMAS_COMPETENCIA[comp],
        output_key=chave_competencia(comp),
        include_contents="none",
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
        before_model_callback=callback_contexto_redacao(
            incluir_avaliacao=False,
            competencia=comp,
            checar_curto_circuito_anulacao=True,
        ),
        after_model_callback=callback_guardrail_nota_competencia(comp),
    )


def criar_agentes_competencias(
    cfg: Config | None = None,
    modelo_override: BaseLlm | str | None = None,
) -> dict[str, LlmAgent]:
    return {
        comp: criar_agente_competencia(comp, cfg=cfg, modelo_override=modelo_override)
        for comp in COMPETENCIAS
    }


class CompetencyPanelCoordinator:
    """Coordenador do painel de especialistas (C1 a C5) com concorrência e retentativa isolada."""

    def __init__(
        self,
        agentes_comp: dict[str, LlmAgent] | None = None,
        cfg: Config | None = None,
        modelo_override: BaseLlm | str | None = None,
    ) -> None:
        self.cfg = cfg or carregar_config()
        self.agentes_comp = agentes_comp or criar_agentes_competencias(
            self.cfg, modelo_override=modelo_override
        )
        self.parallel_comp: ParallelAgent | None = None
        if self.cfg.paralelo:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=DeprecationWarning)
                self.parallel_comp = ParallelAgent(
                    name="avaliadores_competencias",
                    description="Avalia C1 a C5 em paralelo.",
                    sub_agents=list(self.agentes_comp.values()),
                )

    def obter_sub_agentes(self) -> list[BaseAgent]:
        """Retorna a lista de agentes para registro no orquestrador raiz."""
        if self.parallel_comp is not None:
            return [self.parallel_comp]
        return list(self.agentes_comp.values())

    async def executar_painel_async(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        """Executa a avaliação concorrente (se habilitada) e retenta individualmente competências pendentes."""
        # 1. Execução concorrente via ParallelAgent
        if self.parallel_comp is not None:
            try:
                async with Aclosing(self.parallel_comp.run_async(ctx)) as agen:
                    async for ev in agen:
                        yield ev
            except Exception as exc:
                logger.warning(
                    "Falha parcial na execução paralela de competências (%s); re-tentando competências faltantes.",
                    exc,
                )

        # 2. Retentativa individual isolada para qualquer competência com saída ausente ou inválida
        for comp in COMPETENCIAS:
            ag = self.agentes_comp[comp]
            for tentativa in range(self.cfg.tentativas_competencia):
                valor = obter_avaliacao_competencia(ctx.session.state, comp)
                if valor is not None:
                    break
                try:
                    async with Aclosing(ag.run_async(ctx)) as agen:
                        async for ev in agen:
                            yield ev
                except Exception as exc:
                    logger.warning(
                        "Tentativa %d falhou para %s: %s", tentativa + 1, comp, exc
                    )
