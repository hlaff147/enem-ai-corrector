"""Testes unitários de configuração, schemas Pydantic e todas as ferramentas determinísticas."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from pydantic import ValidationError

from enem_corretor.config import _bool, _float, _int, carregar_config
from enem_corretor.eval.metricas import (
    bootstrap_ic95,
    concordancia_adjacente,
    concordancia_exata,
    detectar_vazamento,
    jaccard,
    mae,
    qwk,
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
