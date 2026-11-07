"""Agente orquestrador customizado (`BaseAgent`) do pipeline de correção ENEM.

Hierarquia de Agentes e Coordenadores:
  [1] Intake & Pré-análise determinística (`executar_preanalise`)
  [2] `EligibilityCoordinator`:
        - Gate 1 Determinístico (linhas < 7, em branco, cópia) -> Curto-circuito nota 0
        - Gate 2 Semântico (`agente_anulacao`) -> Curto-circuito nota 0
  [3] `CompetencyPanelCoordinator`:
        - Avaliação C1 a C5 concorrente ou sequencial
        - Retentativa individual isolada por competência
  [4] Juiz Consolidador determinístico (`consolidar_avaliacao`)
  [5] `FeedbackCoordinator`:
        - Agente de feedback pedagógico condicionado às notas consolidadas
  [6] Finalizador:
        - Relatório final em Markdown, schema `AvaliacaoFinal` e persistência opcional.
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncGenerator

from google.adk.agents import BaseAgent, LlmAgent, ParallelAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.adk.models.base_llm import BaseLlm
from google.genai import types
from pydantic import PrivateAttr

from ..config import Config, carregar_config
from ..schemas.entrada import EntradaRedacao
from ..schemas.saida import AvaliacaoFinal, Feedback
from ..state_keys import (
    StateKeys,
    chaves_reset,
    obter_entrada,
    obter_preanalise,
)
from .anulacao import EligibilityCoordinator, criar_agente_anulacao
from .competencias import CompetencyPanelCoordinator, criar_agentes_competencias
from .consolidador import consolidar_avaliacao, formatar_relatorio_markdown
from .feedback import FeedbackCoordinator, criar_agente_feedback
from .preanalise import executar_preanalise, extrair_entrada_do_texto

logger = logging.getLogger(__name__)


def _extrair_texto_usuario(ctx: InvocationContext) -> str:
    if ctx.user_content and ctx.user_content.parts:
        textos = [p.text for p in ctx.user_content.parts if p.text]
        if textos:
            return "\n".join(textos)
    for ev in reversed(ctx.session.events):
        if ev.author == "user" and ev.content and ev.content.parts:
            textos = [p.text for p in ev.content.parts if p.text]
            if textos:
                return "\n".join(textos)
    return ""


def _salvar_execucao_jsonl(cfg: Config, registro: dict[str, Any]) -> None:
    if not cfg.salvar_execucoes:
        return
    try:
        cfg.dir_execucoes.mkdir(parents=True, exist_ok=True)
        arquivo = cfg.dir_execucoes / "historico.jsonl"
        with arquivo.open("a", encoding="utf-8") as f:
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("Não foi possível salvar execução em JSONL: %s", exc)


class CorretorEnemAgent(BaseAgent):
    """Orquestrador multi-agente de correção de redações do ENEM."""

    _cfg: Config = PrivateAttr()
    _coordenador_elegibilidade: EligibilityCoordinator = PrivateAttr()
    _painel_competencias: CompetencyPanelCoordinator = PrivateAttr()
    _coordenador_feedback: FeedbackCoordinator = PrivateAttr()

    def __init__(
        self,
        name: str = "corretor_enem",
        cfg: Config | None = None,
        modelo_override: BaseLlm | str | None = None,
    ) -> None:
        cfg_resolvida = cfg or carregar_config()
        coordenador_elegibilidade = EligibilityCoordinator(
            cfg=cfg_resolvida, modelo_override=modelo_override
        )
        painel_competencias = CompetencyPanelCoordinator(
            cfg=cfg_resolvida, modelo_override=modelo_override
        )
        coordenador_feedback = FeedbackCoordinator(
            cfg=cfg_resolvida, modelo_override=modelo_override
        )

        sub_agents: list[BaseAgent] = [
            coordenador_elegibilidade.agente_anulacao,
            *painel_competencias.obter_sub_agentes(),
            coordenador_feedback.agente_feedback,
        ]

        super().__init__(
            name=name,
            description="Corretor multi-agente de redações do ENEM nas 5 competências oficiais.",
            sub_agents=sub_agents,
        )
        self._cfg = cfg_resolvida
        self._coordenador_elegibilidade = coordenador_elegibilidade
        self._painel_competencias = painel_competencias
        self._coordenador_feedback = coordenador_feedback

    @property
    def _agente_anulacao(self) -> LlmAgent:
        return self._coordenador_elegibilidade.agente_anulacao

    @property
    def _agentes_comp(self) -> dict[str, LlmAgent]:
        return self._painel_competencias.agentes_comp

    @property
    def _parallel_comp(self) -> ParallelAgent | None:
        return self._painel_competencias.parallel_comp

    @property
    def _agente_feedback(self) -> LlmAgent:
        return self._coordenador_feedback.agente_feedback

    def _encerrar_com_avaliacao(
        self, ctx: InvocationContext, final: AvaliacaoFinal
    ) -> Event:
        """Monta o evento final de resposta e persiste histórico."""
        relatorio = formatar_relatorio_markdown(final)
        _salvar_execucao_jsonl(self._cfg, final.model_dump())
        return Event(
            author=self.name,
            invocation_id=ctx.invocation_id,
            content=types.Content(
                role="model", parts=[types.Part(text=relatorio)]
            ),
            actions=EventActions(
                state_delta={
                    StateKeys.AVALIACAO_FINAL: final.model_dump(),
                    StateKeys.RELATORIO_MARKDOWN: relatorio,
                }
            ),
        )

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        # 1. Entrada e Pré-análise determinística
        entrada = obter_entrada(ctx.session.state)
        if entrada is None:
            texto_msg = _extrair_texto_usuario(ctx)
            entrada = extrair_entrada_do_texto(texto_msg)

        preanalise = executar_preanalise(entrada, self._cfg)
        yield Event(
            author=self.name,
            invocation_id=ctx.invocation_id,
            actions=EventActions(
                state_delta={
                    **chaves_reset(),
                    StateKeys.ENTRADA: entrada.model_dump(),
                    StateKeys.PREANALISE: preanalise,
                }
            ),
        )

        # 2. Gate 1: Anulação determinística (curto-circuito sem chamadas de LLM)
        if self._coordenador_elegibilidade.verificar_anulacao_deterministica(ctx.session.state):
            final = consolidar_avaliacao(ctx.session.state, self._cfg)
            yield self._encerrar_com_avaliacao(ctx, final)
            return

        # 3. Gate 2: Triagem semântica de anulação via sub-agente LLM
        async for ev in self._coordenador_elegibilidade.executar_triagem_semantica(ctx):
            yield ev

        if self._coordenador_elegibilidade.verificar_anulacao_semantica(ctx.session.state):
            final = consolidar_avaliacao(ctx.session.state, self._cfg)
            yield self._encerrar_com_avaliacao(ctx, final)
            return

        # 4. Avaliação por competência (C1–C5) via painel especialista
        async for ev in self._painel_competencias.executar_painel_async(ctx):
            yield ev

        # 5. Consolidação determinística (regras de teto + validação de evidências literais)
        parcial = consolidar_avaliacao(ctx.session.state, self._cfg)
        yield Event(
            author=self.name,
            invocation_id=ctx.invocation_id,
            actions=EventActions(
                state_delta={
                    StateKeys.AVALIACAO_CONSOLIDADA: {
                        "nota_total": parcial.nota_total,
                        "competencias": {
                            k: v.model_dump(exclude={"evidencias_validadas"})
                            for k, v in parcial.competencias.items()
                        },
                        "alertas": parcial.alertas,
                    }
                }
            ),
        )

        # 6. Agente de Feedback pedagógico
        async for ev in self._coordenador_feedback.executar_feedback_async(ctx):
            yield ev

        feedback = self._coordenador_feedback.extrair_feedback(ctx.session.state)
        if feedback is not None:
            parcial.feedback = feedback

        # 7. Finalização e relatório
        yield self._encerrar_com_avaliacao(ctx, parcial)


def criar_corretor_agent(
    cfg: Config | None = None,
    modelo_override: BaseLlm | str | None = None,
) -> CorretorEnemAgent:
    return CorretorEnemAgent(cfg=cfg, modelo_override=modelo_override)
