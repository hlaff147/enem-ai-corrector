"""Testes unitários de configuração, schemas Pydantic e todas as ferramentas determinísticas."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from pydantic import ValidationError

from enem_corretor.config import _bool, _float, _int, carregar_config
from enem_corretor.eval.metricas import (
    acuracia,
    acuracia_balanceada,
    avaliar_qualidade_feedback,
    bootstrap_ic95,
    concordancia_adjacente,
    concordancia_exata,
    correlacao_pearson,
    correlacao_spearman,
    detectar_vazamento,
    jaccard,
    mae,
    matriz_confusao_binaria,
    mcc_binario,
    metricas_grounding_evidencias,
    metricas_multiclasse,
    percentil,
    precisao_recall_fbeta,
    qwk,
    r2_score,
    rmse,
    shingles,
    vies_medio,
)
from enem_corretor.schemas.entrada import EntradaRedacao
from enem_corretor.schemas.saida import AvaliacaoC1, MotivoAnulacao, ResultadoAnulacao, ajustar_nivel
from enem_corretor.tools.conectivos import analisar_coesao
from enem_corretor.tools.copia import detectar_copia_motivadores
from enem_corretor.tools.evidencias import validar_evidencias_competencia, validar_trecho
from enem_corretor.tools.gramatica import (
    AlertaGramatical,
    consultar_languagetool,
    verificar_gramatica,
    verificar_heuristicas,
)
from enem_corretor.tools.rubricas import carregar_prompt, carregar_rubrica, rubrica_como_texto
from enem_corretor.tools.texto import (
    analisar_texto,
    estimar_linhas,
    numerar_paragrafos,
    proporcao_idiomas,
    separar_paragrafos,
    sinais_identificacao,
)


def test_config_helpers_e_propriedades(monkeypatch):
    monkeypatch.setenv("TEST_BOOL", "sim")
    monkeypatch.setenv("TEST_INT", "12")
    monkeypatch.setenv("TEST_FLOAT", "0.25")
    assert _bool("TEST_BOOL", False) is True
    assert _bool("NAO_EXISTE", True) is True
    assert _int("TEST_INT", 5) == 12
    assert _float("TEST_FLOAT", 0.1) == 0.25

    carregar_config.cache_clear()
    monkeypatch.setenv("ENEM_MODELO", "ollama_chat/qwen2.5:3b")
    monkeypatch.setenv("ENEM_SEMENTE", "42")
    cfg = carregar_config()
    assert cfg.usa_litellm is True
    assert cfg.semente == 42
    carregar_config.cache_clear()


def test_schemas_ajustar_nivel_e_validacao():
    assert ajustar_nivel(200) == 200
    assert ajustar_nivel(155) == 160
    assert ajustar_nivel(130) == 120
    assert ajustar_nivel(-10) == 0
    assert ajustar_nivel(250) == 200
    assert ajustar_nivel("invalido") == 0

    ent = EntradaRedacao(tema="  Tema X  ", redacao="  Texto Y  ")
    assert ent.tema == "Tema X"
    assert ent.redacao == "Texto Y"

    c1 = AvaliacaoC1(
        analise="ok",
        nota=160,
        justificativa="ok",
        estrutura_sintatica="boa",
    )
    assert c1.nota == 160

    # T-01: valores fora de {0,40,80,120,160,200} devem ser rejeitados estritamente
    for valor_invalido in (150, -40, 240, "invalido", True):
        with pytest.raises(ValidationError):
            AvaliacaoC1(
                analise="ok",
                nota=valor_invalido,  # type: ignore[arg-type]
                justificativa="ok",
                estrutura_sintatica="boa",
            )

    # T-05: motivo de anulação fora do enum fechado ou anular=True sem motivos é rejeitado
    with pytest.raises(ValidationError):
        MotivoAnulacao(motivo="motivo_inventado", evidencia="x", confianca="alta")  # type: ignore[arg-type]

    with pytest.raises(ValidationError):
        ResultadoAnulacao(analise="x", anular=True, motivos=[])


def test_texto_paragrafos_idiomas_e_identificacao():
    assert separar_paragrafos("") == []
    # Sem linha dupla -> separa por quebra simples
    pars_simples = separar_paragrafos("Linha um.\nLinha dois.")
    assert len(pars_simples) == 2
    assert estimar_linhas(pars_simples, 70) == 2
    assert "[§1] Linha um." in numerar_paragrafos(pars_simples)

    assert proporcao_idiomas("") == {"pt": 0.0, "en": 0.0, "es": 0.0}

    texto_id = "Finalizo o texto.\nAtenciosamente, João. Email: joao@teste.com CPF 123.456.789-00"
    achados = sinais_identificacao(texto_id)
    assert len(achados) >= 3

    stats = analisar_texto("Frase curta. " + " ".join(["palavra"] * 65) + ".", 70)
    assert len(stats.periodos_longos) == 1


def test_copia_motivadores_casos_borda():
    assert detectar_copia_motivadores("texto curto", ["motivador"]).proporcao_copiada == 0.0
    assert detectar_copia_motivadores("um dois tres quatro cinco seis sete oito", []).palavras_copiadas == 0

    motivador = "Povos e comunidades tradicionais são grupos culturalmente diferenciados no país."
    redacao = "Sabemos que povos e comunidades tradicionais são grupos culturalmente diferenciados no país hoje."
    res = detectar_copia_motivadores(redacao, [motivador], n=7)
    assert res.palavras_copiadas >= 9
    assert res.proporcao_copiada > 0.5


def test_conectivos_e_repeticoes():
    texto = (
        "No Brasil, a educação enfrenta desafios. A educação precisa de reforma.\n\n"
        "Em primeira análise, a educação carece de verba. Além disso, a educação sofre.\n\n"
        "Portanto, além disso, o Estado deve priorizar a educação."
    )
    res = analisar_coesao(texto)
    assert "em primeira análise" in res.conectivos_interparagrafos
    assert "portanto" in res.conectivos_interparagrafos
    assert "além disso" in res.conectivos_repetidos
    assert "educação" in res.palavras_repetidas


def test_gramatica_heuristicas_e_languagetool_mock():
    alerta = AlertaGramatical(trecho="pra", tipo="registro", sugestao="para", mensagem="msg")
    assert alerta.to_dict()["trecho"] == "pra"

    alertas = verificar_heuristicas("Haviam problemas pra resolver à partir de agora a nível de lei.")
    assert len(alertas) >= 4

    # Mock de sucesso do LanguageTool
    fake_resp = MagicMock()
    fake_resp.raise_for_status.return_value = None
    fake_resp.json.return_value = {
        "matches": [
            {
                "offset": 0,
                "length": 6,
                "message": "Erro de concordância",
                "replacements": [{"value": "Havia"}],
                "rule": {"issueType": "grammar"},
            }
        ]
    }
    with patch("enem_corretor.tools.gramatica.httpx.post", return_value=fake_resp):
        lt = consultar_languagetool("Haviam problemas.")
        assert len(lt) == 1
        assert lt[0].fonte == "languagetool"
        todos = verificar_gramatica("Haviam problemas.", usar_languagetool=True)
        assert any(a["fonte"] == "languagetool" for a in todos)

    # Mock de falha de rede do LanguageTool (degradação graciosa)
    with patch("enem_corretor.tools.gramatica.httpx.post", side_effect=RuntimeError("offline")):
        assert consultar_languagetool("Texto qualquer") == []


def test_evidencias_exata_aproximada_e_inexistente():
    redacao = (
        "Embora a Constituição Federal de 1988 assegure a proteção às manifestações "
        "culturais, a demora na demarcação de terras persiste no século XXI."
    )
    assert validar_trecho("", redacao).status == "nao_encontrada"
    assert validar_trecho("...", redacao).status == "nao_encontrada"
    assert validar_trecho("Constituição Federal de 1988", redacao).status == "exata"
    # Diferença apenas de acentuação/pontuação -> exata após simplificação
    assert validar_trecho("Constituicao Federal de 1988!", redacao).status == "exata"
    # Reticências com ambas as pontas presentes
    assert (
        validar_trecho("Embora a Constituição ... demarcação de terras", redacao).status
        == "aproximada"
    )
    # Pequena alteração de 1 letra -> aproximada por SequenceMatcher
    assert (
        validar_trecho("demora na demarcacao de terras persiste no seculo", redacao).status
        in {"exata", "aproximada"}
    )
    assert validar_trecho("trecho totalmente inventado pelo llm", redacao).status == "nao_encontrada"

    av = {
        "evidencias": [{"trecho": "demora na demarcação de terras", "comentario": "ok"}],
        "desvios": [{"trecho": "trecho fantasma", "tipo": "ortografia"}],
    }
    res = validar_evidencias_competencia(av, redacao)
    assert [r.status for r in res] == ["exata", "nao_encontrada"]


def test_rubricas_e_prompts():
    for nome in ("c1", "c2", "c3", "c4", "c5", "anulacao"):
        assert "fonte" in carregar_rubrica(nome)
        assert len(rubrica_como_texto(nome)) > 100
        assert len(carregar_prompt(nome)) > 100
    assert len(carregar_prompt("feedback")) > 100


def test_metricas_aes_qwk_bootstrap_e_vazamento():
    y_true = [80, 120, 160, 200, 120, 40]
    y_pred = [80, 120, 120, 200, 160, 40]

    k = qwk(y_true, y_pred)
    assert 0.7 < k <= 1.0
    assert mae(y_true, y_pred) > 0
    assert rmse(y_true, y_pred) > 0
    assert vies_medio(y_true, y_pred) == 0.0
    assert concordancia_exata(y_true, y_pred) == round(4 / 6, 4)
    assert concordancia_adjacente(y_true, y_pred, 40.0) == 1.0

    media, lo, hi = bootstrap_ic95(qwk, y_true, y_pred, n_boot=100, seed=7)
    assert lo <= media <= hi

    # Casos degenerados
    import math

    assert math.isnan(qwk([], []))
    assert math.isnan(qwk([120, 120], [120, 120]))
    assert math.isnan(mae([], []))
    assert math.isnan(rmse([], []))
    assert math.isnan(vies_medio([], []))
    assert math.isnan(concordancia_exata([], []))
    assert math.isnan(concordancia_adjacente([], []))
    assert math.isnan(bootstrap_ic95(qwk, [], [])[0])

    # Detecção de vazamento por shingles
    golden = {"g1": "um dois tres quatro cinco seis sete oito nove dez"}
    outros = {
        "o_igual": "um dois tres quatro cinco seis sete oito nove dez",
        "o_diferente": "texto totalmente distinto sem palavras em comum aqui agora",
    }
    vazamentos = detectar_vazamento(golden, outros, limiar=0.6, k=5)
    assert len(vazamentos) == 1
    assert vazamentos[0][0] == "g1" and vazamentos[0][1] == "o_igual"
    assert shingles("", k=5) == set()
    assert jaccard(set(), {"a"}) == 0.0


def test_metricas_ml_classificacao_binaria_e_multiclasse():
    import math

    # 1. Classificação binária (Elegibilidade / Anulação)
    yt_bin = [True, True, False, False, False, False]
    yp_bin = [True, False, False, False, True, False]
    mc = matriz_confusao_binaria(yt_bin, yp_bin)
    assert mc == {"tp": 1, "fp": 1, "tn": 3, "fn": 1}

    assert acuracia(yt_bin, yp_bin) == round(4 / 6, 4)
    # TPR = 1/2 = 0.5, TNR = 3/4 = 0.75 -> Bal Acc = 0.625
    assert acuracia_balanceada(yt_bin, yp_bin) == 0.625

    prf = precisao_recall_fbeta(yt_bin, yp_bin, beta=0.5)
    assert prf["precisao"] == 0.5
    assert prf["recall"] == 0.5
    assert prf["f1"] == 0.5
    assert prf["f_beta"] == 0.5
    assert mcc_binario(yt_bin, yp_bin) == 0.25

    # Casos degenerados / uma única classe
    assert math.isnan(acuracia([], []))
    assert math.isnan(acuracia_balanceada([], []))
    assert acuracia_balanceada([False, False], [False, False]) == 1.0
    assert math.isnan(precisao_recall_fbeta([], [])["f1"])
    assert math.isnan(mcc_binario([], []))
    assert mcc_binario([False, False], [False, False]) == 0.0

    # 2. Classificação multiclasse ordinal (0..200)
    yt_mc = [80, 120, 160, 200, 160, 200]
    yp_mc = [80, 120, 120, 200, 160, 200]
    res_mc = metricas_multiclasse(yt_mc, yp_mc)
    assert res_mc["acuracia"] == round(5 / 6, 4)
    assert 0.7 < res_mc["macro_f1"] <= 1.0
    assert 0.8 < res_mc["weighted_f1"] <= 1.0
    assert res_mc["por_nivel"]["200"]["f1"] == 1.0
    assert res_mc["matriz_confusao"]["160"]["120"] == 1
    assert math.isnan(metricas_multiclasse([], [])["macro_f1"])


def test_metricas_ml_correlacao_r2_percentil_e_qualidade_agentes():
    import math

    yt = [80, 120, 160, 160, 200]
    yp = [80, 120, 120, 160, 200]

    r = correlacao_pearson(yt, yp)
    rho = correlacao_spearman(yt, yp)
    r2 = r2_score(yt, yp)
    assert 0.85 < r <= 1.0
    assert 0.85 < rho <= 1.0
    assert 0.65 < r2 <= 1.0

    assert math.isnan(correlacao_pearson([120], [120]))
    assert math.isnan(correlacao_pearson([120, 120], [120, 160]))
    assert math.isnan(correlacao_spearman([120], [120]))
    assert math.isnan(r2_score([120], [120]))
    assert math.isnan(r2_score([120, 120], [120, 160]))

    assert percentil([10, 20, 30, 40, 50], 50) == 30.0
    assert percentil([10, 20, 30, 40], 50) == 25.0
    assert percentil([42], 95) == 42.0
    assert math.isnan(percentil([], 50))

    # Grounding de evidências
    g = metricas_grounding_evidencias({"exata": 3, "aproximada": 1, "nao_encontrada": 1})
    assert g["total_evidencias"] == 5
    assert g["taxa_grounding_exato"] == 0.6
    assert g["taxa_grounding_total"] == 0.8
    assert g["taxa_alucinacao"] == 0.2
    assert math.isnan(metricas_grounding_evidencias({})["taxa_alucinacao"])

    # Qualidade do agente de feedback
    redacao = "A Constituição Federal de 1988 assegura direitos, mas há falhas graves na prática."
    fb = {
        "resumo": "Bom texto.",
        "prioridades": [
            {"competencia": "C1", "problema": "Desvios", "como_melhorar": "Revisar"},
            {"competencia": "C2", "problema": "Nenhum", "como_melhorar": "Manter"},
        ],
        "reescritas": [
            {
                "competencia": "C1",
                "trecho_original": "A Constituição Federal de 1988 assegura direitos",
                "sugestao": "A Carta Magna de 1988 garante direitos",
                "explicacao": "Evita repetição.",
            },
            {
                "competencia": "C3",
                "trecho_original": "trecho inventado que nao existe no texto original",
                "sugestao": "...",
                "explicacao": "...",
            },
        ],
    }
    notas = {"C1": 120, "C2": 200, "C3": 160, "C4": 200, "C5": 200}
    q_fb = avaliar_qualidade_feedback(fb, redacao, notas)
    assert q_fb["presente"] is True
    assert q_fb["taxa_grounding_reescritas"] == 0.5
    # Menor nota é 120 (faixa prioritária <= 160: C1 e C3); das prioridades (C1 e C2), 1/2 está alinhada
    assert q_fb["alinhamento_prioridades"] == 0.5
    assert avaliar_qualidade_feedback(None, redacao, notas)["presente"] is False
