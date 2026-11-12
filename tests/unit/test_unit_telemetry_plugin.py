"""Testes unitários do plugin de telemetria e rastreamento de tokens."""

import asyncio
from unittest.mock import MagicMock

import pytest
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from enem_corretor.plugins.telemetria import EnemTelemetryPlugin


@pytest.mark.asyncio
async def test_enem_telemetry_plugin_ciclo_completo():
    plugin = EnemTelemetryPlugin()

    await plugin.before_run_callback()

    # Agente 1 (ex: agente_c1)
    agente_mock = MagicMock()
    agente_mock.name = "agente_c1"
    ctx_mock = MagicMock(spec=CallbackContext)
    ctx_mock.agent = agente_mock

    await plugin.before_agent_callback(agente_mock, ctx_mock)
    await asyncio.sleep(0.01)

    usage = types.GenerateContentResponseUsageMetadata(
        prompt_token_count=120,
        candidates_token_count=80,
        total_token_count=200,
    )
    resp = LlmResponse(
        content=types.Content(role="model", parts=[types.Part(text="{}")]),
        usage_metadata=usage,
    )

    await plugin.after_model_callback(ctx_mock, resp)
    await plugin.after_agent_callback(agente_mock, ctx_mock)

    await plugin.after_run_callback()

    rel = plugin.relatorio()
    assert rel.tempo_total_s > 0
    assert rel.total_prompt_tokens == 120
    assert rel.total_completion_tokens == 80
    assert rel.total_tokens == 200

    d = rel.para_dict()
    assert "agente_c1" in d["agentes"]
    assert d["agentes"]["agente_c1"]["chamadas_llm"] == 1
    assert d["agentes"]["agente_c1"]["prompt_tokens"] == 120


@pytest.mark.asyncio
async def test_enem_telemetry_plugin_sem_usage_metadata():
    plugin = EnemTelemetryPlugin()
    agente_mock = MagicMock()
    agente_mock.name = "agente_feedback"
    ctx_mock = MagicMock(spec=CallbackContext)
    ctx_mock.agent = agente_mock

    await plugin.before_agent_callback(agente_mock, ctx_mock)
    resp_sem_usage = LlmResponse(
        content=types.Content(role="model", parts=[types.Part(text="{}")])
    )
    await plugin.after_model_callback(ctx_mock, resp_sem_usage)
    await plugin.after_agent_callback(agente_mock, ctx_mock)

    rel = plugin.relatorio()
    assert rel.agentes["agente_feedback"].chamadas_llm == 1
    assert rel.agentes["agente_feedback"].total_tokens == 0
