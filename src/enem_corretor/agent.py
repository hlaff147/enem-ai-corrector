"""Ponto de entrada do agente para o Google ADK (`adk web src` / `adk run src/enem_corretor`)
e funções programáticas (`corrigir_redacao` / `corrigir_redacao_async`)."""

from __future__ import annotations

import asyncio
from typing import Any

from google.adk.models.base_llm import BaseLlm
from google.adk.runners import InMemoryRunner
from google.genai import types

from .agents.orquestrador import criar_corretor_agent
from .config import Config, carregar_config
from .schemas.entrada import EntradaRedacao
from .schemas.saida import AvaliacaoFinal
from .state_keys import (
    StateKeys,
    obter_avaliacao_final,
    obter_relatorio_markdown,
)

# Variável descoberta automaticamente pelo CLI do ADK (`adk web` / `adk run`)
root_agent = criar_corretor_agent()


async def corrigir_redacao_async(
    entrada: EntradaRedacao,
    cfg: Config | None = None,
    modelo_override: BaseLlm | str | None = None,
) -> tuple[AvaliacaoFinal, str]:
    """Executa o pipeline completo sobre `entrada` e retorna `(AvaliacaoFinal, relatorio_markdown)`."""
    cfg = cfg or carregar_config()
    agente = criar_corretor_agent(cfg=cfg, modelo_override=modelo_override)
    runner = InMemoryRunner(agent=agente, app_name="enem_corretor")
    sessao = await runner.session_service.create_session(
        app_name="enem_corretor",
        user_id="estudante",
        state={StateKeys.ENTRADA: entrada.model_dump()},
    )
    msg = types.Content(
        role="user",
        parts=[
            types.Part(
                text=f"TEMA: {entrada.tema}\n\nREDAÇÃO:\n{entrada.redacao}"
            )
        ],
    )
    async for _ in runner.run_async(
        user_id="estudante", session_id=sessao.id, new_message=msg
    ):
        pass

    sessao_final = await runner.session_service.get_session(
        app_name="enem_corretor", user_id="estudante", session_id=sessao.id
    )
    state: dict[str, Any] = sessao_final.state if sessao_final else {}
    avaliacao = obter_avaliacao_final(state)
    if avaliacao is None:
        avaliacao = AvaliacaoFinal.model_validate(state.get(StateKeys.AVALIACAO_FINAL, {}))
    relatorio = obter_relatorio_markdown(state)
    return avaliacao, relatorio


def corrigir_redacao(
    entrada: EntradaRedacao,
    cfg: Config | None = None,
    modelo_override: BaseLlm | str | None = None,
) -> tuple[AvaliacaoFinal, str]:
    """Versão síncrona de `corrigir_redacao_async`."""
    return asyncio.run(
        corrigir_redacao_async(entrada, cfg=cfg, modelo_override=modelo_override)
    )
