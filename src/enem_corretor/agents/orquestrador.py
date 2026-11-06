"""Agente orquestrador customizado (`BaseAgent`) do pipeline de correção ENEM.

Fluxo:
  [1] Pré-análise determinística (linhas, parágrafos, cópia, coesão, heurísticas C1)
  [2] Triagem de anulação (determinística + `agente_anulacao`)
        └─ se anular → encerra imediatamente com nota 0 + motivo
  [3] Avaliação C1–C5 (via `ParallelAgent` se `cfg.paralelo=True` ou sequencial,
      com re-tentativa individual caso alguma competência falhe)
  [4] Consolidador determinístico (regras de teto entre competências + validação
      de evidências literais)
  [5] `agente_feedback` (plano de melhoria, reescritas e checklist)
  [6] Relatório final em Markdown + `avaliacao_final` estruturada no session state
      + persistência opcional em JSONL (`data/execucoes/historico.jsonl`).
"""

from __future__ import annotations

import json
import logging
import warnings
from typing import Any, AsyncGenerator

from google.adk.agents import BaseAgent, LlmAgent, ParallelAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.adk.models.base_llm import BaseLlm
from google.adk.utils.context_utils import Aclosing
from google.genai import types
from pydantic import PrivateAttr

from ..config import Config, carregar_config
from ..schemas.entrada import EntradaRedacao
from ..schemas.saida import COMPETENCIAS, Feedback
from .anulacao import criar_agente_anulacao
from .competencias import criar_agentes_competencias
from .consolidador import consolidar_avaliacao, formatar_relatorio_markdown
from .feedback import criar_agente_feedback
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
    _agente_anulacao: LlmAgent = PrivateAttr()
    _agentes_comp: dict[str, LlmAgent] = PrivateAttr()
    _parallel_comp: ParallelAgent | None = PrivateAttr(default=None)
    _agente_feedback: LlmAgent = PrivateAttr()

    def __init__(
        self,
        name: str = "corretor_enem",
        cfg: Config | None = None,
        modelo_override: BaseLlm | str | None = None,
    ) -> None:
        cfg_resolvida = cfg or carregar_config()
        ag_anulacao = criar_agente_anulacao(cfg_resolvida, modelo_override)
        ags_comp = criar_agentes_competencias(cfg_resolvida, modelo_override)
        ag_feedback = criar_agente_feedback(cfg_resolvida, modelo_override)

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=DeprecationWarning)
            par_comp = (
                ParallelAgent(
                    name="avaliadores_competencias",
                    description="Avalia C1 a C5 em paralelo.",
                    sub_agents=list(ags_comp.values()),
                )
                if cfg_resolvida.paralelo
                else None
            )

        sub_agents: list[BaseAgent] = [ag_anulacao]
        if par_comp is not None:
            sub_agents.append(par_comp)
        else:
            sub_agents.extend(ags_comp.values())
        sub_agents.append(ag_feedback)

        super().__init__(
            name=name,
            description="Corretor multi-agente de redações do ENEM nas 5 competências oficiais.",
            sub_agents=sub_agents,
        )
        self._cfg = cfg_resolvida
        self._agente_anulacao = ag_anulacao
        self._agentes_comp = ags_comp
        self._parallel_comp = par_comp
        self._agente_feedback = ag_feedback

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        # 1. Entrada e Pré-análise determinística
        entrada_state = ctx.session.state.get("entrada")
        if isinstance(entrada_state, dict) and entrada_state.get("redacao"):
            entrada = EntradaRedacao.model_validate(entrada_state)
        else:
            texto_msg = _extrair_texto_usuario(ctx)
            entrada = extrair_entrada_do_texto(texto_msg)

        preanalise = executar_preanalise(entrada, self._cfg)
        limpar_chaves = {
            "anulacao_llm": None,
            "avaliacao_c1": None,
            "avaliacao_c2": None,
            "avaliacao_c3": None,
            "avaliacao_c4": None,
            "avaliacao_c5": None,
            "avaliacao_consolidada": None,
            "feedback": None,
            "avaliacao_final": None,
            "relatorio_markdown": None,
        }
        yield Event(
            author=self.name,
            invocation_id=ctx.invocation_id,
            actions=EventActions(
                state_delta={
                    **limpar_chaves,
                    "entrada": entrada.model_dump(),
                    "preanalise": preanalise,
                }
            ),
        )

        # 2. Anulação determinística (curto-circuito sem gastar chamadas de LLM)
        if preanalise["motivos_anulacao_deterministicos"]:
            final = consolidar_avaliacao(ctx.session.state, self._cfg)
            relatorio = formatar_relatorio_markdown(final)
            _salvar_execucao_jsonl(self._cfg, final.model_dump())
            yield Event(
                author=self.name,
                invocation_id=ctx.invocation_id,
                content=types.Content(
                    role="model", parts=[types.Part(text=relatorio)]
                ),
                actions=EventActions(
                    state_delta={
                        "avaliacao_final": final.model_dump(),
                        "relatorio_markdown": relatorio,
                    }
                ),
            )
            return

        # 3. Triagem semântica de anulação via LLM
        try:
            async with Aclosing(self._agente_anulacao.run_async(ctx)) as agen:
                async for ev in agen:
                    yield ev
        except Exception as exc:
            logger.warning("Falha no agente de anulação (%s); prosseguindo.", exc)

        anulacao_llm = ctx.session.state.get("anulacao_llm") or {}
        if isinstance(anulacao_llm, dict) and anulacao_llm.get("anular"):
            final = consolidar_avaliacao(ctx.session.state, self._cfg)
            relatorio = formatar_relatorio_markdown(final)
            _salvar_execucao_jsonl(self._cfg, final.model_dump())
            yield Event(
                author=self.name,
                invocation_id=ctx.invocation_id,
                content=types.Content(
                    role="model", parts=[types.Part(text=relatorio)]
                ),
                actions=EventActions(
                    state_delta={
                        "avaliacao_final": final.model_dump(),
                        "relatorio_markdown": relatorio,
                    }
                ),
            )
            return

        # 4. Avaliação por competência (C1–C5) em paralelo ou sequencial + fallback
        if self._parallel_comp is not None:
            try:
                async with Aclosing(self._parallel_comp.run_async(ctx)) as agen:
                    async for ev in agen:
                        yield ev
            except Exception as exc:
                logger.warning(
                    "Falha parcial na execução paralela (%s); re-tentando competências faltantes.",
                    exc,
                )

        # Re-executa individualmente qualquer competência que não tenha gravado saída válida
        for comp in COMPETENCIAS:
            chave = f"avaliacao_{comp.lower()}"
            ag = self._agentes_comp[comp]
            for tentativa in range(self._cfg.tentativas_competencia):
                valor = ctx.session.state.get(chave)
                if isinstance(valor, dict) and "nota" in valor:
                    break
                try:
                    async with Aclosing(ag.run_async(ctx)) as agen:
                        async for ev in agen:
                            yield ev
                except Exception as exc:
                    logger.warning(
                        "Tentativa %d falhou para %s: %s", tentativa + 1, comp, exc
                    )

        # 5. Consolidação determinística (regras de teto + validação de evidências)
        parcial = consolidar_avaliacao(ctx.session.state, self._cfg)
        yield Event(
            author=self.name,
            invocation_id=ctx.invocation_id,
            actions=EventActions(
                state_delta={
                    "avaliacao_consolidada": {
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
        try:
            async with Aclosing(self._agente_feedback.run_async(ctx)) as agen:
                async for ev in agen:
                    yield ev
        except Exception as exc:
            logger.warning("Falha no agente de feedback (%s); mantendo relatório sem feedback.", exc)

        fb_raw = ctx.session.state.get("feedback")
        if isinstance(fb_raw, dict):
            try:
                parcial.feedback = Feedback.model_validate(fb_raw)
            except Exception as exc:
                logger.warning("Feedback inválido ignorado: %s", exc)

        relatorio = formatar_relatorio_markdown(parcial)
        _salvar_execucao_jsonl(self._cfg, parcial.model_dump())

        yield Event(
            author=self.name,
            invocation_id=ctx.invocation_id,
            content=types.Content(
                role="model", parts=[types.Part(text=relatorio)]
            ),
            actions=EventActions(
                state_delta={
                    "avaliacao_final": parcial.model_dump(),
                    "relatorio_markdown": relatorio,
                }
            ),
        )


def criar_corretor_agent(
    cfg: Config | None = None,
    modelo_override: BaseLlm | str | None = None,
) -> CorretorEnemAgent:
    return CorretorEnemAgent(cfg=cfg, modelo_override=modelo_override)
