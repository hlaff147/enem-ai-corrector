"""Testes de integração ponta a ponta:
- Orquestrador `CorretorEnemAgent` no `InMemoryRunner` (paralelo e sequencial)
- Recuperação de falhas de agentes individuais (re-tentativas)
- Persistência em JSONL (`data/execucoes/historico.jsonl`)
- Interface de linha de comando (`enem-corretor` / `main`)
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest
from google.adk.runners import InMemoryRunner
from google.genai import types

from enem_corretor import corrigir_redacao, corrigir_redacao_async, main
from enem_corretor.agents.orquestrador import criar_corretor_agent
from enem_corretor.config import carregar_config
from enem_corretor.eval.run_eval import avaliar_dataset_async, carregar_dataset_jsonl, main_eval
from enem_corretor.schemas.entrada import EntradaRedacao
from tests.conftest import FakeEnemLlm


@pytest.mark.asyncio
async def test_integracao_pipeline_paralelo_e_persistencia_jsonl(tmp_path, redacao_completa):
    cfg = replace(
        carregar_config(),
        paralelo=True,
        salvar_execucoes=True,
        dir_execucoes=tmp_path,
    )
    entrada = EntradaRedacao(
        tema="Desafios para a valorização de comunidades e povos tradicionais no Brasil",
        redacao=redacao_completa,
    )
    av, relatorio = await corrigir_redacao_async(
        entrada, cfg=cfg, modelo_override=FakeEnemLlm()
    )
    assert not av.anulada
    assert av.nota_total == 920
    assert av.feedback is not None
    assert "920 / 1000" in relatorio
    assert "Desvios identificados" in relatorio
    assert "Repertórios avaliados" in relatorio
    assert "Elementos da proposta de intervenção" in relatorio

    historico = tmp_path / "historico.jsonl"
    assert historico.exists()
    linhas = historico.read_text(encoding="utf-8").strip().splitlines()
    assert len(linhas) == 1
    salvo = json.loads(linhas[0])
    assert salvo["nota_total"] == 920


@pytest.mark.asyncio
async def test_integracao_modo_sequencial_e_retry_competencia(tmp_path, redacao_completa):
    """Testa `paralelo=False` (modo Ollama) + recuperação quando C3 falha na 1ª tentativa."""
    cfg = replace(
        carregar_config(),
        paralelo=False,
        tentativas_competencia=2,
        salvar_execucoes=False,
        dir_execucoes=tmp_path,
    )
    fake = FakeEnemLlm(falhar_schemas={"AvaliacaoC3": 1})
    agente = criar_corretor_agent(cfg=cfg, modelo_override=fake)
    runner = InMemoryRunner(agent=agente, app_name="teste_seq")
    sessao = await runner.session_service.create_session(
        app_name="teste_seq", user_id="u"
    )
    # Envia via mensagem de texto (sem `entrada` pré-populada no state) para exercitar
    # `_extrair_texto_usuario` + `extrair_entrada_do_texto`
    msg = types.Content(
        role="user",
        parts=[
            types.Part(
                text=f"TEMA: Povos tradicionais\n\nREDAÇÃO:\n{redacao_completa}"
            )
        ],
    )
    async for _ in runner.run_async(user_id="u", session_id=sessao.id, new_message=msg):
        pass

    sessao_final = await runner.session_service.get_session(
        app_name="teste_seq", user_id="u", session_id=sessao.id
    )
    av_final = sessao_final.state["avaliacao_final"]
    assert av_final["competencias"]["C3"]["nota"] == 160
    assert av_final["nota_total"] == 920


@pytest.mark.asyncio
async def test_integracao_anulacao_semantica_llm_e_degradacao_feedback(
    tmp_path, redacao_completa
):
    cfg = replace(carregar_config(), salvar_execucoes=False, dir_execucoes=tmp_path)
    entrada = EntradaRedacao(tema="Tema X", redacao=redacao_completa)

    # 1) Anulação semântica por fuga ao tema detectada pelo `agente_anulacao`
    av_fuga, rel_fuga = await corrigir_redacao_async(
        entrada, cfg=cfg, modelo_override=FakeEnemLlm(anular_por_fuga=True)
    )
    assert av_fuga.anulada is True
    assert av_fuga.nota_total == 0
    assert "fuga_ao_tema" in rel_fuga

    # 2) Teste de anulação determinística (< 8 linhas) para cobrir o curto-circuito no orquestrador
    entrada_curta = EntradaRedacao(
        tema="Tema X",
        redacao="Texto muito curto com apenas duas linhas que deve ser anulado direto.",
    )
    av_curta, rel_curta = await corrigir_redacao_async(
        entrada_curta, cfg=cfg, modelo_override=FakeEnemLlm()
    )
    assert av_curta.anulada is True
    assert av_curta.nota_total == 0
    assert "texto_insuficiente" in rel_curta

    # 3) Teste de tangenciamento no pipeline completo (C2/C3/C5 limitadas a 40)
    av_tang, _ = await corrigir_redacao_async(
        entrada,
        cfg=cfg,
        modelo_override=FakeEnemLlm(tangenciar=True, elementos_c5_validos=3),
    )
    assert av_tang.competencias["C2"].nota == 40
    assert av_tang.competencias["C3"].nota == 40
    assert av_tang.competencias["C5"].nota == 40

    # 4) Falha nos agentes de anulação e de feedback -> pipeline degrada graciosamente
    fake_deg = FakeEnemLlm(falhar_schemas={"ResultadoAnulacao": 5, "Feedback": 5})
    av_deg, _ = await corrigir_redacao_async(
        entrada, cfg=cfg, modelo_override=fake_deg
    )
    assert av_deg.anulada is False
    assert av_deg.nota_total == 920
    assert av_deg.feedback is None


def test_integracao_cli_main_json_txt_e_preanalise(tmp_path, redacao_completa, capsys):
    # 1) `--apenas-preanalise` com arquivo JSON
    arq_json = tmp_path / "entrada.json"
    arq_json.write_text(
        json.dumps(
            {
                "tema": "Povos tradicionais",
                "redacao": redacao_completa,
                "motivadores": ["Texto motivador"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    rc = main(["--arquivo", str(arq_json), "--apenas-preanalise"])
    assert rc == 0
    saida_pre = json.loads(capsys.readouterr().out)
    assert saida_pre["estatisticas"]["paragrafos"] == 4

    # 2) Execução completa via CLI com `--arquivo .txt`, `--saida-json` e `--saida-md`
    arq_txt = tmp_path / "redacao.txt"
    arq_txt.write_text(redacao_completa, encoding="utf-8")
    out_json = tmp_path / "out" / "avaliacao.json"
    out_md = tmp_path / "out" / "relatorio.md"

    def _corrigir_mock(entrada, cfg=None, modelo_override=None):
        cfg_local = replace(carregar_config(), salvar_execucoes=False)
        return corrigir_redacao(entrada, cfg=cfg_local, modelo_override=FakeEnemLlm())

    with patch("enem_corretor.corrigir_redacao", side_effect=_corrigir_mock):
        rc2 = main(
            [
                "--tema",
                "Povos tradicionais",
                "--arquivo",
                str(arq_txt),
                "--saida-json",
                str(out_json),
                "--saida-md",
                str(out_md),
            ]
        )
    assert rc2 == 0
    assert out_json.exists()
    assert out_md.exists()
    dados_salvos = json.loads(out_json.read_text(encoding="utf-8"))
    assert dados_salvos["nota_total"] == 920


@pytest.mark.asyncio
async def test_integracao_runner_eval_stress_dataset(tmp_path):
    cfg = replace(carregar_config(), salvar_execucoes=False, dir_execucoes=tmp_path)
    dataset_path = Path("data/exemplos/stress_set_amostra.jsonl")
    dataset = carregar_dataset_jsonl(dataset_path)
    out_dir = tmp_path / "eval_out"

    resumo = await avaliar_dataset_async(
        dataset, out_dir=out_dir, cfg=cfg, modelo_override=FakeEnemLlm()
    )
    assert resumo["total_redacoes"] == 2
    assert resumo["falsos_positivos_anulacao"] == 0
    assert resumo["competencias"]["TOTAL"]["exata"] == 1.0
    assert (out_dir / "results.jsonl").exists()
    assert (out_dir / "report.md").exists()


def test_integracao_cli_main_eval(tmp_path):
    dataset_path = Path("data/exemplos/stress_set_amostra.jsonl")

    async def _fake_corrigir_async(ent, cfg=None, modelo_override=None):
        return await corrigir_redacao_async(
            ent,
            cfg=replace(carregar_config(), salvar_execucoes=False),
            modelo_override=FakeEnemLlm(),
        )

    with patch(
        "enem_corretor.eval.run_eval.corrigir_redacao_async",
        new=_fake_corrigir_async,
    ):
        rc = main_eval(["--dataset", str(dataset_path), "--out", str(tmp_path / "cli_eval")])
        assert rc == 0
