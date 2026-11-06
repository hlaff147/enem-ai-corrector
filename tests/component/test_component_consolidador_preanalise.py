"""Testes de componente: testam isoladamente cada componente do sistema
(pré-análise/parser de entrada, fábrica de agentes/modelos, e todas as regras
de negócio do consolidador e formatador Markdown)."""

from __future__ import annotations

from dataclasses import replace

import pytest
from google.adk.models.lite_llm import LiteLlm

from enem_corretor.agents.competencias import criar_agente_competencia
from enem_corretor.agents.comum import (
    construir_generate_config,
    construir_modelo,
    montar_xml_entrada,
)
from enem_corretor.agents.consolidador import (
    _normalizar_nome_elemento,
    consolidar_avaliacao,
    formatar_relatorio_markdown,
)
from enem_corretor.agents.preanalise import executar_preanalise, extrair_entrada_do_texto
from enem_corretor.config import carregar_config
from enem_corretor.schemas.entrada import EntradaRedacao


def test_extrair_entrada_do_texto_formatos():
    # 1. Vazio
    vazio = extrair_entrada_do_texto("   ")
    assert vazio.redacao == ""

    # 2. JSON válido
    via_json = extrair_entrada_do_texto(
        '{"tema": "Tema JSON", "redacao": "Texto JSON", "motivadores": ["M1"], "titulo": "T"}'
    )
    assert via_json.tema == "Tema JSON"
    assert via_json.redacao == "Texto JSON"
    assert via_json.motivadores == ["M1"]
    assert via_json.titulo == "T"

    # 3. JSON inválido que começa com '{' -> cai no fallback de texto puro
    json_quebrado = extrair_entrada_do_texto("{invalido mas texto de redação")
    assert "invalido" in json_quebrado.redacao

    # 4. Formato "TEMA: ...\nREDAÇÃO: ..."
    via_marcador = extrair_entrada_do_texto("TEMA: Educação digital\n\nREDAÇÃO:\nMeu texto aqui.")
    assert via_marcador.tema == "Educação digital"
    assert via_marcador.redacao == "Meu texto aqui."

    # 5. Primeira linha com "Tema - ..." e múltiplas linhas
    via_primeira_linha = extrair_entrada_do_texto(
        "Tema: Saúde mental\nParágrafo 1.\nParágrafo 2."
    )
    assert via_primeira_linha.tema == "Saúde mental"
    assert "Parágrafo 1." in via_primeira_linha.redacao

    # 6. Texto puro sem tema
    puro = extrair_entrada_do_texto("Apenas o corpo da redação direto.")
    assert puro.tema.startswith("(tema não informado")


def test_executar_preanalise_anulacoes_e_alertas():
    cfg = carregar_config()

    # Folha em branco
    pre_branco = executar_preanalise(EntradaRedacao(tema="T", redacao="   "), cfg)
    assert any("folha_em_branco" in m for m in pre_branco["motivos_anulacao_deterministicos"])

    # Cópia massiva dos motivadores que deixa menos de 8 linhas originais
    motivador_longo = " ".join(
        [f"palavra{i}" for i in range(1, 90)]
    )
    redacao_copiada = motivador_longo + " final curto."
    pre_copia = executar_preanalise(
        EntradaRedacao(tema="T", redacao=redacao_copiada, motivadores=[motivador_longo]),
        cfg,
    )
    assert any("copia_motivadores" in m for m in pre_copia["motivos_anulacao_deterministicos"])

    # Excesso de linhas (> 30) + tema não informado + sinal de identificação
    redacao_longa = "\n\n".join(
        [" ".join(["argumento"] * 120) for _ in range(4)]
    ) + "\nAtenciosamente, Fulano."
    pre_longa = executar_preanalise(
        EntradaRedacao(tema="(tema não informado pelo usuário)", redacao=redacao_longa),
        cfg,
    )
    alertas_txt = " ".join(pre_longa["alertas_preanalise"])
    assert "ultrapassa o limite" in alertas_txt
    assert "Tema não foi informado" in alertas_txt
    assert "identificação" in alertas_txt


def test_fábrica_modelos_e_xml_entrada():
    cfg = replace(carregar_config(), semente=123)
    gen_cfg = construir_generate_config(cfg)
    assert gen_cfg.seed == 123

    mod_lite = construir_modelo(cfg, modelo_override="ollama_chat/qwen2.5:3b")
    assert isinstance(mod_lite, LiteLlm)

    with pytest.raises(ValueError, match="Competência inválida"):
        criar_agente_competencia("C9", cfg=cfg)

    xml = montar_xml_entrada(
        {
            "entrada": {
                "tema": "Tema X",
                "titulo": "Meu Título",
                "motivadores": ["Motivador A"],
                "redacao": "Texto",
            },
            "preanalise": {"redacao_numerada": "[§1] Texto"},
            "avaliacao_consolidada": {"nota_total": 800},
        },
        incluir_avaliacao=True,
    )
    assert "<motivadores>" in xml
    assert "Título: Meu Título" in xml
    assert "<avaliacao_consolidada>" in xml


def test_consolidador_regras_de_teto_e_casos_borda(redacao_completa):
    assert _normalizar_nome_elemento("Modo / Meio de execução") == "meio"
    assert _normalizar_nome_elemento("Efeito esperado") == "finalidade"
    assert _normalizar_nome_elemento("outro") == "outro"

    # 1) Anulação semântica vinda do LLM (com item dict e item string)
    state_anulado = {
        "entrada": {"tema": "Tema", "redacao": redacao_completa},
        "preanalise": {"redacao_normalizada": redacao_completa},
        "anulacao_llm": {
            "anular": True,
            "motivos": [
                {"motivo": "fuga_ao_tema", "evidencia": "fugiu"},
                "improperios: ofensa",
            ],
            "alertas": ["alerta 1"],
        },
    }
    av_anulada = consolidar_avaliacao(state_anulado)
    assert av_anulada.anulada is True
    assert av_anulada.nota_total == 0
    assert len(av_anulada.motivos_anulacao) == 2

    # 2) Competência ausente + C2 com cópia e tipo textual inadequado + C5 violando DH
    state_tetos = {
        "entrada": {"tema": "Tema", "redacao": redacao_completa},
        "preanalise": {
            "redacao_normalizada": redacao_completa,
            "copia_motivadores": {"proporcao_copiada": 0.25},
        },
        "avaliacao_c1": None,  # simula falha do agente C1
        "avaliacao_c2": {
            "analise": "x",
            "nota": 160,
            "justificativa": "x",
            "abordagem_tema": "completa",
            "tangenciamento": False,
            "tipo_textual_adequado": False,
            "tem_introducao": True,
            "tem_desenvolvimento": True,
            "tem_conclusao": True,
            "copia_motivadores": True,
            "evidencias": [{"trecho": "trecho inexistente xyz", "comentario": "c"}],
        },
        "avaliacao_c3": {"analise": "x", "nota": 120, "justificativa": "x"},
        "avaliacao_c4": {"analise": "x", "nota": 120, "justificativa": "x"},
        "avaliacao_c5": {
            "analise": "x",
            "nota": 160,
            "justificativa": "x",
            "proposta_presente": True,
            "relacionada_ao_tema": True,
            "articulada_a_discussao": True,
            "respeita_direitos_humanos": False,
            "elementos": [],
        },
    }
    av = consolidar_avaliacao(state_tetos)
    assert av.competencias["C1"].nota == 0
    assert av.competencias["C2"].nota == 40  # limitada por tipo_textual_adequado=False
    assert av.competencias["C5"].nota == 0   # zerada por violação aos DH
    assert any("não foram encontrados" in a for a in av.alertas)

    # 3) C5 sem proposta, relacionada só ao assunto e não articulada à discussão
    for caso, esperado in [
        ({"proposta_presente": False, "relacionada_ao_tema": True, "articulada_a_discussao": True}, 0),
        ({"proposta_presente": True, "relacionada_ao_tema": False, "articulada_a_discussao": True}, 40),
        (
            {
                "proposta_presente": True,
                "relacionada_ao_tema": True,
                "articulada_a_discussao": False,
                "elementos": [
                    {"elemento": e, "trecho": "cabe ao Ministério", "valido": True}
                    for e in ("agente", "acao", "meio", "finalidade")
                ],
            },
            80,
        ),
    ]:
        state_c5 = {
            **state_tetos,
            "avaliacao_c5": {
                "analise": "x",
                "nota": 160,
                "justificativa": "x",
                "respeita_direitos_humanos": True,
                **caso,
            },
        }
        res_c5 = consolidar_avaliacao(state_c5)
        assert res_c5.competencias["C5"].nota == esperado

    md = formatar_relatorio_markdown(av)
    assert "# Relatório de Correção" in md
    assert "## Alertas do Sistema" in md
