"""Plugin de telemetria, rastreamento de tokens e latência para o ecossistema Google ADK."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.plugins.base_plugin import BasePlugin

logger = logging.getLogger(__name__)


@dataclass
class MetricasAgente:
    nome: str
    tempo_execucao_s: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    chamadas_llm: int = 0


@dataclass
class RelatorioTelemetria:
    tempo_total_s: float = 0.0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    agentes: dict[str, MetricasAgente] = field(default_factory=dict)

    def para_dict(self) -> dict[str, Any]:
        return {
            "tempo_total_s": round(self.tempo_total_s, 4),
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_tokens,
            "agentes": {
                nome: {
                    "tempo_execucao_s": round(m.tempo_execucao_s, 4),
                    "prompt_tokens": m.prompt_tokens,
                    "completion_tokens": m.completion_tokens,
                    "total_tokens": m.total_tokens,
                    "chamadas_llm": m.chamadas_llm,
                }
                for nome, m in self.agentes.items()
            },
        }


class EnemTelemetryPlugin(BasePlugin):
    """Plugin do ADK que rastreia latência de agentes e consumo de tokens por LLM."""

    def __init__(self, name: str = "enem_telemetry") -> None:
        super().__init__(name=name)
        self._tempos_inicio_agente: dict[str, float] = {}
        self._metricas: dict[str, MetricasAgente] = {}
        self._tempo_inicio_run: float | None = None
        self._tempo_fim_run: float | None = None

    def _obter_ou_criar_metricas(self, nome_agente: str) -> MetricasAgente:
        if nome_agente not in self._metricas:
            self._metricas[nome_agente] = MetricasAgente(nome=nome_agente)
        return self._metricas[nome_agente]

    async def before_run_callback(self, *args: Any, **kwargs: Any) -> None:
        self._tempo_inicio_run = time.perf_counter()

    async def after_run_callback(self, *args: Any, **kwargs: Any) -> None:
        self._tempo_fim_run = time.perf_counter()

    async def before_agent_callback(
        self, agent: Any, callback_context: CallbackContext
    ) -> None:
        nome_agente = getattr(agent, "name", str(agent))
        self._tempos_inicio_agente[nome_agente] = time.perf_counter()
        self._obter_ou_criar_metricas(nome_agente)

    async def after_agent_callback(
        self, agent: Any, callback_context: CallbackContext
    ) -> None:
        nome_agente = getattr(agent, "name", str(agent))
        t_inicio = self._tempos_inicio_agente.pop(nome_agente, None)
        if t_inicio is not None:
            duracao = time.perf_counter() - t_inicio
            m = self._obter_ou_criar_metricas(nome_agente)
            m.tempo_execucao_s += duracao

    async def after_model_callback(
        self,
        *args: Any,
        callback_context: CallbackContext | None = None,
        llm_response: LlmResponse | None = None,
        **kwargs: Any,
    ) -> LlmResponse | None:
        ctx = callback_context or (args[0] if len(args) > 0 else None)
        resp = llm_response or (args[1] if len(args) > 1 else None)
        nome_agente = "desconhecido"
        if ctx is not None:
            raw_agent_name = getattr(ctx, "agent_name", None)
            if isinstance(raw_agent_name, str) and raw_agent_name:
                nome_agente = raw_agent_name
            else:
                ag = getattr(ctx, "agent", None)
                nome_agente = getattr(ag, "name", None) or "desconhecido"
                if not isinstance(nome_agente, str):
                    nome_agente = str(nome_agente)

        m = self._obter_ou_criar_metricas(nome_agente)
        m.chamadas_llm += 1

        usage = getattr(resp, "usage_metadata", None)
        if usage:
            prompt_t = getattr(usage, "prompt_token_count", 0) or 0
            comp_t = getattr(usage, "candidates_token_count", 0) or 0
            total_t = getattr(usage, "total_token_count", 0) or (prompt_t + comp_t)
            m.prompt_tokens += prompt_t
            m.completion_tokens += comp_t
            m.total_tokens += total_t

        return None

    def relatorio(self) -> RelatorioTelemetria:
        """Gera o consolidado de telemetria coletado pelo plugin."""
        tempo_total = 0.0
        if self._tempo_inicio_run is not None:
            t_fim = self._tempo_fim_run or time.perf_counter()
            tempo_total = max(0.0, t_fim - self._tempo_inicio_run)

        total_prompt = sum(m.prompt_tokens for m in self._metricas.values())
        total_comp = sum(m.completion_tokens for m in self._metricas.values())
        total_tok = sum(m.total_tokens for m in self._metricas.values())

        return RelatorioTelemetria(
            tempo_total_s=tempo_total,
            total_prompt_tokens=total_prompt,
            total_completion_tokens=total_comp,
            total_tokens=total_tok,
            agentes=dict(self._metricas),
        )
