"""Testes unitários para o catálogo de chaves e helpers de session state (`state_keys.py`)."""

from __future__ import annotations

import pytest

from enem_corretor.schemas.entrada import EntradaRedacao
from enem_corretor.schemas.saida import (
    AvaliacaoFinal,
    Feedback,
    MotivoAnulacao,
    Prioridade,
    Reescrita,
    ResultadoAnulacao,
)
from enem_corretor.state_keys import (
    StateKeys,
    chave_competencia,
    chaves_reset,
    obter_avaliacao_competencia,
    obter_avaliacao_consolidada,
    obter_avaliacao_final,
    obter_entrada,
    obter_feedback,
    obter_preanalise,
    obter_relatorio_markdown,
    obter_resultado_anulacao,
)


def test_state_keys_enum_values():
    assert StateKeys.ENTRADA == "entrada"
    assert StateKeys.PREANALISE == "preanalise"
    assert StateKeys.ANULACAO_LLM == "anulacao_llm"
    assert StateKeys.AVALIACAO_C1 == "avaliacao_c1"
    assert StateKeys.AVALIACAO_C5 == "avaliacao_c5"
    assert StateKeys.AVALIACAO_CONSOLIDADA == "avaliacao_consolidada"
    assert StateKeys.FEEDBACK == "feedback"
    assert StateKeys.AVALIACAO_FINAL == "avaliacao_final"
    assert StateKeys.RELATORIO_MARKDOWN == "relatorio_markdown"


def test_chave_competencia():
    assert chave_competencia("C1") == "avaliacao_c1"
    assert chave_competencia("c5") == "avaliacao_c5"
    assert chave_competencia(" C3 ") == "avaliacao_c3"


def test_chaves_reset():
    reset = chaves_reset()
    assert isinstance(reset, dict)
    assert reset[StateKeys.AVALIACAO_C1] is None
    assert reset[StateKeys.FEEDBACK] is None
    assert reset[StateKeys.AVALIACAO_FINAL] is None
    assert StateKeys.ENTRADA not in reset


def test_obter_entrada():
    assert obter_entrada({}) is None
    assert obter_entrada({"entrada": "invalido"}) is None
    ent = EntradaRedacao(tema="Tema Teste", redacao="Texto de teste longo o suficiente.")
    assert obter_entrada({"entrada": ent}) == ent
    res_dump = obter_entrada({"entrada": ent.model_dump()})
    assert res_dump is not None and res_dump.tema == "Tema Teste"
    assert obter_entrada({"entrada": {"invalido": True}}) is None


def test_obter_preanalise():
    assert obter_preanalise({}) == {}
    assert obter_preanalise({"preanalise": {"palavras": 100}}) == {"palavras": 100}
    assert obter_preanalise({"preanalise": "nao_dict"}) == {}


def test_obter_resultado_anulacao():
    assert obter_resultado_anulacao({}) is None
    res = ResultadoAnulacao(
        analise="Texto não abordou o tema.",
        anular=True,
        motivos=[MotivoAnulacao(motivo="fuga_ao_tema", evidencia="Nenhuma menção ao tema")],
    )
    assert obter_resultado_anulacao({"anulacao_llm": res}) == res
    res_dict = obter_resultado_anulacao({"anulacao_llm": res.model_dump()})
    assert res_dict is not None and res_dict.anular is True
    assert obter_resultado_anulacao({"anulacao_llm": {"anular": "invalido"}}) is None


def test_obter_avaliacao_competencia():
    assert obter_avaliacao_competencia({}, "C1") is None
    assert obter_avaliacao_competencia({"avaliacao_c1": "invalido"}, "C1") is None
    assert obter_avaliacao_competencia({"avaliacao_c1": {"nota": 160}}, "C1") == {"nota": 160}


def test_obter_avaliacao_consolidada():
    assert obter_avaliacao_consolidada({}) is None
    assert obter_avaliacao_consolidada({"avaliacao_consolidada": {"nota_total": 800}}) == {"nota_total": 800}
    assert obter_avaliacao_consolidada({"avaliacao_consolidada": "invalido"}) is None


def test_obter_feedback():
    assert obter_feedback({}) is None
    fb = Feedback(
        resumo="Texto muito bem estruturado com repertório consistente.",
        pontos_fortes=["Excelente repertório sociocultural"],
        prioridades=[Prioridade(competencia="C1", problema="Crase incorreta", como_melhorar="Revisar crase")],
        reescritas=[
            Reescrita(
                competencia="C1",
                trecho_original="Devido a falta",
                sugestao="Devido à falta",
                explicacao="Exige crase feminina",
            )
        ],
        checklist_proxima_redacao=["Revisar uso de crase"],
    )
    assert obter_feedback({"feedback": fb}) == fb
    res_fb = obter_feedback({"feedback": fb.model_dump()})
    assert res_fb is not None and res_fb.pontos_fortes == ["Excelente repertório sociocultural"]
    assert obter_feedback({"feedback": {"resumo": 12345, "pontos_fortes": "invalido"}}) is None


def test_obter_avaliacao_final():
    assert obter_avaliacao_final({}) is None
    av = AvaliacaoFinal(
        tema="Tema",
        anulada=False,
        competencias={},
        nota_total=0,
    )
    assert obter_avaliacao_final({"avaliacao_final": av}) == av
    res_av = obter_avaliacao_final({"avaliacao_final": av.model_dump()})
    assert res_av is not None and res_av.tema == "Tema"
    assert obter_avaliacao_final({"avaliacao_final": {"nota_total": "invalido"}}) is None


def test_obter_relatorio_markdown():
    assert obter_relatorio_markdown({}) == ""
    assert obter_relatorio_markdown({"relatorio_markdown": "# Relatório"}) == "# Relatório"
