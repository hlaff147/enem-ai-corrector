"""Testes unitários para os novos coordenadores da hierarquia de agentes (`EligibilityCoordinator`,
`CompetencyPanelCoordinator`, `FeedbackCoordinator` e propriedades do `CorretorEnemAgent`)."""

from __future__ import annotations

import dataclasses
from unittest.mock import AsyncMock, MagicMock

import pytest
from google.adk.events import Event

from enem_corretor.agents.anulacao import EligibilityCoordinator
from enem_corretor.agents.competencias import CompetencyPanelCoordinator
from enem_corretor.agents.feedback import FeedbackCoordinator
from enem_corretor.agents.orquestrador import criar_corretor_agent
from enem_corretor.config import carregar_config
from enem_corretor.schemas.saida import Feedback, ResultadoAnulacao
from enem_corretor.state_keys import StateKeys


@pytest.mark.asyncio
async def test_eligibility_coordinator():
    mock_agente = MagicMock()
    coord = EligibilityCoordinator(agente_anulacao=mock_agente)

    # Gate 1 Determinístico
    assert coord.verificar_anulacao_deterministica({}) == []
    assert coord.verificar_anulacao_deterministica(
        {StateKeys.PREANALISE: {"motivos_anulacao_deterministicos": ["texto_insuficiente"]}}
    ) == ["texto_insuficiente"]

    # Gate 2 Semântico
    assert coord.verificar_anulacao_semantica({}) is False
    res = ResultadoAnulacao(
        analise="ok",
        anular=True,
        motivos=[{"motivo": "fuga_ao_tema", "evidencia": "nenhuma abordagem do tema"}],
    )
    assert coord.verificar_anulacao_semantica({StateKeys.ANULACAO_LLM: res}) is True

    # Execução assíncrona da triagem
    async def _mock_run(ctx):
        yield Event(author="mock_anulacao", invocation_id="inv-1")

    mock_agente.run_async = _mock_run
    ctx = MagicMock()
    events = [ev async for ev in coord.executar_triagem_semantica(ctx)]
    assert len(events) == 1
    assert events[0].author == "mock_anulacao"


@pytest.mark.asyncio
async def test_competency_panel_coordinator():
    base_cfg = carregar_config()
    cfg_seq = dataclasses.replace(base_cfg, paralelo=False)
    panel_seq = CompetencyPanelCoordinator(cfg=cfg_seq)
    subs_seq = panel_seq.obter_sub_agentes()
    assert len(subs_seq) == 5

    cfg_par = dataclasses.replace(base_cfg, paralelo=True)
    panel_par = CompetencyPanelCoordinator(cfg=cfg_par)
    subs_par = panel_par.obter_sub_agentes()
    assert len(subs_par) == 1
    assert subs_par[0].name == "avaliadores_competencias"

    # Simular execução com estado já preenchido (nenhum retry necessário)
    ctx = MagicMock()
    ctx.session.state = {
        "avaliacao_c1": {"nota": 160},
        "avaliacao_c2": {"nota": 200},
        "avaliacao_c3": {"nota": 160},
        "avaliacao_c4": {"nota": 200},
        "avaliacao_c5": {"nota": 200},
    }
    events = [ev async for ev in panel_seq.executar_painel_async(ctx)]
    assert len(events) == 0


@pytest.mark.asyncio
async def test_feedback_coordinator():
    mock_agente = MagicMock()
    coord = FeedbackCoordinator(agente_feedback=mock_agente)

    assert coord.extrair_feedback({}) is None
    fb = Feedback(
        resumo="Muito bom",
        pontos_fortes=["Excelente repertório"],
        prioridades=[],
        reescritas=[],
        checklist_proxima_redacao=[],
    )
    assert coord.extrair_feedback({StateKeys.FEEDBACK: fb}) == fb

    # Execução assíncrona tratada
    async def _mock_run(ctx):
        yield Event(author="mock_feedback", invocation_id="inv-2")

    mock_agente.run_async = _mock_run
    ctx = MagicMock()
    events = [ev async for ev in coord.executar_feedback_async(ctx)]
    assert len(events) == 1
    assert events[0].author == "mock_feedback"


def test_corretor_agent_properties_backward_compatibility():
    base_cfg = carregar_config()
    cfg = dataclasses.replace(base_cfg, paralelo=True)
    agente = criar_corretor_agent(cfg=cfg)
    assert agente._agente_anulacao is not None
    assert len(agente._agentes_comp) == 5
    assert agente._parallel_comp is not None
    assert agente._agente_feedback is not None
