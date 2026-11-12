"""Runner de avaliação em lote (`python -m enem_corretor.eval` ou `enem-corretor-eval`)
sobre arquivos JSONL no formato do Apêndice F.1, gerando `results.jsonl`, `metrics.json` e `report.md`."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import time
from pathlib import Path
from typing import Any

from google.adk.models.base_llm import BaseLlm

from ..agent import corrigir_redacao_async
from ..config import Config, carregar_config
from ..schemas.entrada import EntradaRedacao
from ..schemas.saida import COMPETENCIAS, NIVEIS
from .metricas import (
    acuracia,
    acuracia_balanceada,
    avaliar_qualidade_feedback,
    bootstrap_ic95,
    concordancia_adjacente,
    concordancia_exata,
    correlacao_pearson,
    correlacao_spearman,
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
    vies_medio,
)


def _sanitizar_para_json(obj: Any) -> Any:
    """Converte `NaN`/`Inf` em `None` recursivamente para serialização JSON estrita."""
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: _sanitizar_para_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitizar_para_json(v) for v in obj]
    return obj


def carregar_dataset_jsonl(caminho: Path) -> list[dict[str, Any]]:
    itens: list[dict[str, Any]] = []
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha:
            itens.append(json.loads(linha))
    return itens


async def avaliar_dataset_async(
    dataset: list[dict[str, Any]],
    out_dir: Path,
    cfg: Config | None = None,
    modelo_override: BaseLlm | str | None = None,
) -> dict[str, Any]:
    cfg = cfg or carregar_config()
    out_dir.mkdir(parents=True, exist_ok=True)
    arq_resultados = out_dir / "results.jsonl"

    registros: list[dict[str, Any]] = []
    with arq_resultados.open("w", encoding="utf-8") as f_out:
        for item in dataset:
            essay_id = item.get("essay_id", "sem-id")
            entrada = EntradaRedacao(
                tema=item.get("tema", "(tema não informado)"),
                redacao=item.get("texto") or item.get("redacao") or "",
                motivadores=list(item.get("motivadores") or []),
            )
            t0 = time.perf_counter()
            av, _ = await corrigir_redacao_async(
                entrada, cfg=cfg, modelo_override=modelo_override
            )
            latencia_ms = round((time.perf_counter() - t0) * 1000)

            evid_counts = {"exata": 0, "aproximada": 0, "nao_encontrada": 0}
            evid_por_agente: dict[str, dict[str, int]] = {}
            for comp_nome, rc in av.competencias.items():
                cont_comp = {"exata": 0, "aproximada": 0, "nao_encontrada": 0}
                for ev in rc.evidencias_validadas:
                    evid_counts[ev.status] = evid_counts.get(ev.status, 0) + 1
                    cont_comp[ev.status] = cont_comp.get(ev.status, 0) + 1
                evid_por_agente[comp_nome] = cont_comp

            notas_modelo = {
                c.lower(): (
                    av.competencias[c].nota_modelo if c in av.competencias else None
                )
                for c in COMPETENCIAS
            }
            total_modelo = (
                None
                if av.incompleta
                or any(notas_modelo[c.lower()] is None for c in COMPETENCIAS)
                else sum(int(notas_modelo[c.lower()] or 0) for c in COMPETENCIAS)
            )
            notas_modelo["total"] = total_modelo

            intervencoes = {
                c.lower(): bool(av.competencias[c].ajustes)
                for c in COMPETENCIAS
                if c in av.competencias and not av.anulada
            }

            notas_finais_comp = {
                c: (av.competencias[c].nota if c in av.competencias else None)
                for c in COMPETENCIAS
            }
            qualidade_fb = avaliar_qualidade_feedback(
                av.feedback, entrada.redacao, notas_finais_comp
            )

            reg = {
                "essay_id": essay_id,
                "esperado": {
                    "anulada": item.get("anulada", False),
                    "motivo_anulacao": item.get("motivo_anulacao"),
                    "c1": item.get("c1"),
                    "c2": item.get("c2"),
                    "c3": item.get("c3"),
                    "c4": item.get("c4"),
                    "c5": item.get("c5"),
                    "total": item.get("total"),
                },
                "obtido": {
                    "anulada": av.anulada,
                    "incompleta": av.incompleta,
                    "motivos_anulacao": list(av.motivos_anulacao),
                    "c1": av.competencias["C1"].nota if "C1" in av.competencias else None,
                    "c2": av.competencias["C2"].nota if "C2" in av.competencias else None,
                    "c3": av.competencias["C3"].nota if "C3" in av.competencias else None,
                    "c4": av.competencias["C4"].nota if "C4" in av.competencias else None,
                    "c5": av.competencias["C5"].nota if "C5" in av.competencias else None,
                    "total": av.nota_total,
                },
                "obtido_modelo": notas_modelo,
                "intervencoes_consolidador": intervencoes,
                "evidencias": evid_counts,
                "evidencias_por_agente": evid_por_agente,
                "qualidade_feedback": qualidade_fb,
                "latencia_ms": latencia_ms,
            }
            registros.append(reg)
            f_out.write(json.dumps(_sanitizar_para_json(reg), ensure_ascii=False) + "\n")

    resumo = calcular_resumo_metricas(registros)
    _salvar_artefatos_resumo(resumo, len(registros), out_dir)
    return resumo


def _salvar_artefatos_resumo(
    resumo: dict[str, Any], n_total: int, out_dir: Path
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    relatorio_md = formatar_relatorio_eval(resumo, n_total)
    (out_dir / "report.md").write_text(relatorio_md, encoding="utf-8")
    (out_dir / "metrics.json").write_text(
        json.dumps(_sanitizar_para_json(resumo), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def recalcular_de_resultados(
    arq_resultados: Path, out_dir: Path | None = None
) -> dict[str, Any]:
    """Recalcula todas as métricas de ML/DS a partir de um `results.jsonl` existente."""
    registros = carregar_dataset_jsonl(arq_resultados)
    destino = out_dir or arq_resultados.parent
    resumo = calcular_resumo_metricas(registros)
    _salvar_artefatos_resumo(resumo, len(registros), destino)
    return resumo


def _subtrair_seguro(a: float, b: float) -> float:
    if math.isnan(a) or math.isnan(b):
        return float("nan")
    return round(a - b, 4)


def calcular_resumo_metricas(registros: list[dict[str, Any]]) -> dict[str, Any]:
    metricas_comp: dict[str, dict[str, Any]] = {}
    ablation_comp: dict[str, dict[str, Any]] = {}
    todas_classes_total = tuple(range(0, 1001, 40))

    for comp in [*[c.lower() for c in COMPETENCIAS], "total"]:
        pares = [
            (float(r["esperado"][comp]), float(r["obtido"][comp]))
            for r in registros
            if r.get("esperado", {}).get(comp) is not None
            and r.get("obtido", {}).get(comp) is not None
        ]
        if not pares:
            continue
        yt = [p[0] for p in pares]
        yp = [p[1] for p in pares]
        max_r = 1000 if comp == "total" else 200
        step_r = 40
        tol_adj = 80.0 if comp == "total" else 40.0
        classes_alvo = todas_classes_total if comp == "total" else NIVEIS

        _, qwk_lo, qwk_hi = bootstrap_ic95(
            lambda a, b, mr=max_r, sr=step_r: qwk(a, b, 0, mr, sr),
            yt,
            yp,
            n_boot=200,
        )
        mc_info = metricas_multiclasse(yt, yp, classes=classes_alvo)
        qwk_final = qwk(yt, yp, 0, max_r, step_r)
        mae_final = mae(yt, yp)

        dados_dim: dict[str, Any] = {
            "n": len(pares),
            "qwk": qwk_final,
            "qwk_ic95": [qwk_lo, qwk_hi],
            "mae": mae_final,
            "rmse": rmse(yt, yp),
            "vies": vies_medio(yt, yp),
            "exata": concordancia_exata(yt, yp),
            "adjacente": concordancia_adjacente(yt, yp, tolerancia=tol_adj),
            "macro_precisao": mc_info["macro_precisao"],
            "macro_recall": mc_info["macro_recall"],
            "macro_f1": mc_info["macro_f1"],
            "weighted_f1": mc_info["weighted_f1"],
            "pearson_r": correlacao_pearson(yt, yp),
            "spearman_rho": correlacao_spearman(yt, yp),
            "r2": r2_score(yt, yp),
        }
        if comp != "total":
            dados_dim["por_nivel"] = mc_info["por_nivel"]
            dados_dim["matriz_confusao"] = mc_info["matriz_confusao"]

        metricas_comp[comp.upper()] = dados_dim

        # Ablation: Agente LLM puro (`obtido_modelo`) vs. Pós-Consolidador (`obtido`)
        pares_mod = [
            (
                float(r["esperado"][comp]),
                float(r["obtido_modelo"][comp]),
                float(r["obtido"][comp]),
            )
            for r in registros
            if r.get("esperado", {}).get(comp) is not None
            and (r.get("obtido_modelo") or {}).get(comp) is not None
            and r.get("obtido", {}).get(comp) is not None
        ]
        if pares_mod:
            yt_m = [p[0] for p in pares_mod]
            yp_m = [p[1] for p in pares_mod]
            yp_f = [p[2] for p in pares_mod]
            qwk_mod = qwk(yt_m, yp_m, 0, max_r, step_r)
            mae_mod = mae(yt_m, yp_m)
            mf1_mod = metricas_multiclasse(yt_m, yp_m, classes=classes_alvo)["macro_f1"]

            intervencoes_n = sum(1 for _, m_val, f_val in pares_mod if m_val != f_val)
            if comp != "total":
                intervencoes_explicitas = sum(
                    1
                    for r in registros
                    if (r.get("intervencoes_consolidador") or {}).get(comp, False)
                )
                intervencoes_n = max(intervencoes_n, intervencoes_explicitas)

            ablation_comp[comp.upper()] = {
                "n": len(pares_mod),
                "qwk_modelo": qwk_mod,
                "qwk_pos_consolidador": qwk_final,
                "delta_qwk": _subtrair_seguro(qwk_final, qwk_mod),
                "mae_modelo": mae_mod,
                "mae_pos_consolidador": mae_final,
                "delta_mae": _subtrair_seguro(mae_final, mae_mod),
                "macro_f1_modelo": mf1_mod,
                "macro_f1_pos_consolidador": mc_info["macro_f1"],
                "delta_macro_f1": _subtrair_seguro(mc_info["macro_f1"], mf1_mod),
                "taxa_intervencao": round(intervencoes_n / len(pares_mod), 4),
            }

    # Classificação Binária de Anulação / Elegibilidade
    y_true_anul = [bool(r.get("esperado", {}).get("anulada", False)) for r in registros]
    y_pred_anul = [bool(r.get("obtido", {}).get("anulada", False)) for r in registros]
    mc_anul = matriz_confusao_binaria(y_true_anul, y_pred_anul)
    prf_anul = precisao_recall_fbeta(y_true_anul, y_pred_anul, beta=0.5)

    # Acurácia do motivo de anulação (quando esperado tem `motivo_anulacao` e obtido tem `motivos_anulacao`)
    motivos_avaliaveis = [
        (
            str(r["esperado"]["motivo_anulacao"]).strip().lower(),
            [str(m).lower() for m in (r.get("obtido", {}).get("motivos_anulacao") or [])],
        )
        for r in registros
        if r.get("esperado", {}).get("motivo_anulacao")
        and "motivos_anulacao" in (r.get("obtido") or {})
    ]
    acuracia_motivo = (
        round(
            sum(
                1
                for esp_m, obt_ms in motivos_avaliaveis
                if any(esp_m in m for m in obt_ms)
            )
            / len(motivos_avaliaveis),
            4,
        )
        if motivos_avaliaveis
        else float("nan")
    )

    metricas_anulacao = {
        **mc_anul,
        "acuracia": acuracia(y_true_anul, y_pred_anul),
        "acuracia_balanceada": acuracia_balanceada(y_true_anul, y_pred_anul),
        "precisao": prf_anul["precisao"],
        "recall": prf_anul["recall"],
        "f1": prf_anul["f1"],
        "f05": prf_anul["f_beta"],
        "mcc": mcc_binario(y_true_anul, y_pred_anul),
        "acuracia_motivo": acuracia_motivo,
    }

    # Qualidade Intrínseca de Agentes, Grounding e Telemetria de Latência
    n_reg = len(registros)
    incompletas = sum(
        1 for r in registros if bool(r.get("obtido", {}).get("incompleta", False))
    )
    taxa_completude = round((n_reg - incompletas) / n_reg, 4) if n_reg > 0 else float("nan")

    latencias = [
        float(r["latencia_ms"])
        for r in registros
        if r.get("latencia_ms") is not None
    ]
    latencia_media = round(sum(latencias) / len(latencias), 2) if latencias else float("nan")

    soma_evid = {"exata": 0, "aproximada": 0, "nao_encontrada": 0}
    soma_evid_agente: dict[str, dict[str, int]] = {
        c: {"exata": 0, "aproximada": 0, "nao_encontrada": 0} for c in COMPETENCIAS
    }
    for r in registros:
        ev = r.get("evidencias") or {}
        for k in soma_evid:
            soma_evid[k] += int(ev.get(k, 0))
        ev_ag = r.get("evidencias_por_agente") or {}
        for c in COMPETENCIAS:
            if c in ev_ag and isinstance(ev_ag[c], dict):
                for k in soma_evid_agente[c]:
                    soma_evid_agente[c][k] += int(ev_ag[c].get(k, 0))

    grounding_por_agente = {
        c: metricas_grounding_evidencias(soma_evid_agente[c])
        for c in COMPETENCIAS
        if sum(soma_evid_agente[c].values()) > 0
    }

    # Consolidação de métricas do `agente_feedback`
    nao_anuladas = [
        r for r in registros if not bool(r.get("obtido", {}).get("anulada", False))
    ]
    fbs = [
        r["qualidade_feedback"]
        for r in nao_anuladas
        if isinstance(r.get("qualidade_feedback"), dict)
    ]
    fb_presentes = [f for f in fbs if f.get("presente")]
    tot_reesc = sum(int(f.get("total_reescritas", 0)) for f in fb_presentes)
    anc_reesc = sum(int(f.get("reescritas_ancoradas", 0)) for f in fb_presentes)
    tot_prio = sum(int(f.get("total_prioridades", 0)) for f in fb_presentes)
    ali_prio = sum(int(f.get("prioridades_alinhadas", 0)) for f in fb_presentes)

    qualidade_agentes = {
        "taxa_completude": taxa_completude,
        "incompletas": incompletas,
        "latencia_media_ms": latencia_media,
        "latencia_p50_ms": percentil(latencias, 50),
        "latencia_p90_ms": percentil(latencias, 90),
        "latencia_p95_ms": percentil(latencias, 95),
        "grounding_geral": metricas_grounding_evidencias(soma_evid),
        "grounding_por_agente": grounding_por_agente,
        "feedback": {
            "taxa_presenca": (
                round(len(fb_presentes) / len(fbs), 4) if fbs else float("nan")
            ),
            "taxa_grounding_reescritas": (
                round(anc_reesc / tot_reesc, 4) if tot_reesc > 0 else float("nan")
            ),
            "alinhamento_prioridades": (
                round(ali_prio / tot_prio, 4) if tot_prio > 0 else float("nan")
            ),
        },
    }

    return {
        "total_redacoes": len(registros),
        "falsos_positivos_anulacao": mc_anul["fp"],
        "falsos_negativos_anulacao": mc_anul["fn"],
        "anulacao": metricas_anulacao,
        "competencias": metricas_comp,
        "ablation_consolidador": ablation_comp,
        "qualidade_agentes": qualidade_agentes,
    }


def formatar_relatorio_eval(resumo: dict[str, Any], n_total: int) -> str:
    anul = resumo.get("anulacao") or {}
    qual = resumo.get("qualidade_agentes") or {}
    grd = qual.get("grounding_geral") or {}
    fb = qual.get("feedback") or {}

    linhas = [
        "# Relatório de Avaliação AES & Machine Learning (Golden / Stress Set)",
        "",
        f"- **Redações avaliadas:** {n_total}",
        f"- **Taxa de completude (SLA dos agentes):** {qual.get('taxa_completude', 'nan')}",
        f"- **Falsos positivos de anulação:** {resumo.get('falsos_positivos_anulacao', 0)}",
        f"- **Falsos negativos de anulação:** {resumo.get('falsos_negativos_anulacao', 0)}",
        "",
        "## 1. Elegibilidade e Anulação (`EligibilityCoordinator` — Classificação Binária)",
        "",
        "| TP | FP | TN | FN | Acurácia | Acurácia Bal. | Precisão | Recall | F1-Score | F0.5-Score | MCC | Acurácia Motivo |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        (
            f"| {anul.get('tp', 0)} | {anul.get('fp', 0)} | {anul.get('tn', 0)} | {anul.get('fn', 0)} | "
            f"{anul.get('acuracia', 'nan')} | {anul.get('acuracia_balanceada', 'nan')} | "
            f"{anul.get('precisao', 'nan')} | {anul.get('recall', 'nan')} | "
            f"{anul.get('f1', 'nan')} | {anul.get('f05', 'nan')} | "
            f"{anul.get('mcc', 'nan')} | {anul.get('acuracia_motivo', 'nan')} |"
        ),
        "",
        "## 2. Desempenho por Competência e Nota Total (`CompetencyPanelCoordinator`)",
        "",
        "| Dimensão | N | QWK [IC95%] | MAE | RMSE | Viés | Exata (Acc) | Adjacente | Macro-F1 | Weighted-F1 | Pearson (r) | Spearman (ρ) | R² |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for chave, m in resumo.get("competencias", {}).items():
        ic = m.get("qwk_ic95", [float("nan"), float("nan")])
        linhas.append(
            f"| **{chave}** | {m['n']} | {m['qwk']} [{ic[0]}, {ic[1]}] | "
            f"{m['mae']} | {m['rmse']} | {m['vies']} | {m['exata']} | {m['adjacente']} | "
            f"{m.get('macro_f1', 'nan')} | {m.get('weighted_f1', 'nan')} | "
            f"{m.get('pearson_r', 'nan')} | {m.get('spearman_rho', 'nan')} | {m.get('r2', 'nan')} |"
        )

    ablation = resumo.get("ablation_consolidador") or {}
    if ablation:
        linhas.extend(
            [
                "",
                "## 3. Estudo de Ablação: Agente LLM Puro vs. Juiz Consolidador (`consolidador.py`)",
                "",
                "| Dimensão | QWK Agente | QWK Final | Δ QWK | MAE Agente | MAE Final | Δ MAE | Macro-F1 Agente | Macro-F1 Final | Taxa Intervenção |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for chave, ab in ablation.items():
            linhas.append(
                f"| **{chave}** | {ab['qwk_modelo']} | {ab['qwk_pos_consolidador']} | {ab['delta_qwk']} | "
                f"{ab['mae_modelo']} | {ab['mae_pos_consolidador']} | {ab['delta_mae']} | "
                f"{ab['macro_f1_modelo']} | {ab['macro_f1_pos_consolidador']} | {ab['taxa_intervencao']} |"
            )

    linhas.extend(
        [
            "",
            "## 4. Qualidade Intrínseca, Grounding (Alucinação) e Agente de Feedback",
            "",
            f"- **Evidências avaliadas (C1–C5):** {grd.get('total_evidencias', 0)} "
            f"(Grounding total: `{grd.get('taxa_grounding_total', 'nan')}` | "
            f"Grounding exato: `{grd.get('taxa_grounding_exato', 'nan')}` | "
            f"Taxa de alucinação: `{grd.get('taxa_alucinacao', 'nan')}`)",
            f"- **Agente de Feedback (`agente_feedback`):** "
            f"Presença: `{fb.get('taxa_presenca', 'nan')}` | "
            f"Grounding de reescritas: `{fb.get('taxa_grounding_reescritas', 'nan')}` | "
            f"Alinhamento pedagógico de prioridades: `{fb.get('alinhamento_prioridades', 'nan')}`",
            f"- **Telemetria de Latência (ms):** "
            f"Média: `{qual.get('latencia_media_ms', 'nan')}` | "
            f"P50: `{qual.get('latencia_p50_ms', 'nan')}` | "
            f"P90: `{qual.get('latencia_p90_ms', 'nan')}` | "
            f"P95: `{qual.get('latencia_p95_ms', 'nan')}`",
        ]
    )

    grd_ag = qual.get("grounding_por_agente") or {}
    if grd_ag:
        linhas.extend(
            [
                "",
                "### Grounding e Taxa de Alucinação por Agente Especialista",
                "",
                "| Agente | Total Evidências | Grounding Exato | Grounding Total | Taxa de Alucinação |",
                "|---|---:|---:|---:|---:|",
            ]
        )
        for comp, g in grd_ag.items():
            linhas.append(
                f"| **agente_{comp.lower()}** | {g['total_evidencias']} | "
                f"{g['taxa_grounding_exato']} | {g['taxa_grounding_total']} | {g['taxa_alucinacao']} |"
            )

    return "\n".join(linhas) + "\n"


def main_eval(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="enem-corretor-eval",
        description="Avalia o corretor em um dataset JSONL (golden/stress) e calcula métricas de AES e ML/DS.",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=None,
        help="Arquivo .jsonl de entrada com redações para executar no pipeline.",
    )
    parser.add_argument(
        "--recalcular-de",
        type=Path,
        default=None,
        help="Recalcula métricas e relatório a partir de um results.jsonl existente sem chamar o LLM.",
    )
    parser.add_argument("--out", type=Path, required=True, help="Diretório de saída.")
    parser.add_argument("--modelo", type=str, default=None, help="Override opcional de modelo.")
    args = parser.parse_args(argv)

    if args.recalcular_de is not None:
        recalcular_de_resultados(args.recalcular_de, args.out)
        print((args.out / "report.md").read_text(encoding="utf-8"))
        return 0

    if args.dataset is None:
        parser.error("Informe `--dataset <arquivo.jsonl>` ou `--recalcular-de <results.jsonl>`.")

    dataset = carregar_dataset_jsonl(args.dataset)
    asyncio.run(avaliar_dataset_async(dataset, args.out, modelo_override=args.modelo))
    print((args.out / "report.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main_eval())
