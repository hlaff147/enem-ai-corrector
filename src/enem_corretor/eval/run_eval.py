"""Runner de avaliação em lote (`python -m enem_corretor.eval` ou `enem-corretor-eval`)
sobre arquivos JSONL no formato do Apêndice F.1, gerando `results.jsonl` e `report.md`."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import Any

from google.adk.models.base_llm import BaseLlm

from ..agent import corrigir_redacao_async
from ..config import Config, carregar_config
from ..schemas.entrada import EntradaRedacao
from ..schemas.saida import COMPETENCIAS
from .metricas import (
    bootstrap_ic95,
    concordancia_adjacente,
    concordancia_exata,
    mae,
    qwk,
    rmse,
    vies_medio,
)


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
            for rc in av.competencias.values():
                for ev in rc.evidencias_validadas:
                    evid_counts[ev.status] = evid_counts.get(ev.status, 0) + 1

            reg = {
                "essay_id": essay_id,
                "esperado": {
                    "anulada": item.get("anulada", False),
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
                    "c1": av.competencias["C1"].nota if "C1" in av.competencias else None,
                    "c2": av.competencias["C2"].nota if "C2" in av.competencias else None,
                    "c3": av.competencias["C3"].nota if "C3" in av.competencias else None,
                    "c4": av.competencias["C4"].nota if "C4" in av.competencias else None,
                    "c5": av.competencias["C5"].nota if "C5" in av.competencias else None,
                    "total": av.nota_total,
                },
                "evidencias": evid_counts,
                "latencia_ms": latencia_ms,
            }
            registros.append(reg)
            f_out.write(json.dumps(reg, ensure_ascii=False) + "\n")

    resumo = calcular_resumo_metricas(registros)
    relatorio_md = formatar_relatorio_eval(resumo, len(registros))
    (out_dir / "report.md").write_text(relatorio_md, encoding="utf-8")
    return resumo


def calcular_resumo_metricas(registros: list[dict[str, Any]]) -> dict[str, Any]:
    metricas_comp: dict[str, dict[str, Any]] = {}
    for comp in [*[c.lower() for c in COMPETENCIAS], "total"]:
        pares = [
            (float(r["esperado"][comp]), float(r["obtido"][comp]))
            for r in registros
            if r["esperado"].get(comp) is not None and r["obtido"].get(comp) is not None
        ]
        if not pares:
            continue
        yt = [p[0] for p in pares]
        yp = [p[1] for p in pares]
        max_r = 1000 if comp == "total" else 200
        step_r = 40
        tol_adj = 80.0 if comp == "total" else 40.0
        _, qwk_lo, qwk_hi = bootstrap_ic95(
            lambda a, b: qwk(a, b, 0, max_r, step_r), yt, yp, n_boot=200
        )
        metricas_comp[comp.upper()] = {
            "n": len(pares),
            "qwk": qwk(yt, yp, 0, max_r, step_r),
            "qwk_ic95": [qwk_lo, qwk_hi],
            "mae": mae(yt, yp),
            "rmse": rmse(yt, yp),
            "vies": vies_medio(yt, yp),
            "exata": concordancia_exata(yt, yp),
            "adjacente": concordancia_adjacente(yt, yp, tolerancia=tol_adj),
        }

    anul_pares = [
        (bool(r["esperado"]["anulada"]), bool(r["obtido"]["anulada"])) for r in registros
    ]
    fp_anulacao = sum(1 for esp, obt in anul_pares if not esp and obt)
    fn_anulacao = sum(1 for esp, obt in anul_pares if esp and not obt)

    return {
        "total_redacoes": len(registros),
        "falsos_positivos_anulacao": fp_anulacao,
        "falsos_negativos_anulacao": fn_anulacao,
        "competencias": metricas_comp,
    }


def formatar_relatorio_eval(resumo: dict[str, Any], n_total: int) -> str:
    linhas = [
        "# Relatório de Avaliação AES (Golden / Stress Set)",
        "",
        f"- **Redações avaliadas:** {n_total}",
        f"- **Falsos positivos de anulação:** {resumo['falsos_positivos_anulacao']}",
        f"- **Falsos negativos de anulação:** {resumo['falsos_negativos_anulacao']}",
        "",
        "| Dimensão | N | QWK [IC95%] | MAE | RMSE | Viés | Exata | Adjacente |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for chave, m in resumo.get("competencias", {}).items():
        ic = m["qwk_ic95"]
        linhas.append(
            f"| **{chave}** | {m['n']} | {m['qwk']} [{ic[0]}, {ic[1]}] | "
            f"{m['mae']} | {m['rmse']} | {m['vies']} | {m['exata']} | {m['adjacente']} |"
        )
    return "\n".join(linhas) + "\n"


def main_eval(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="enem-corretor-eval",
        description="Avalia o corretor em um dataset JSONL (golden/stress) e calcula QWK/MAE/viés.",
    )
    parser.add_argument("--dataset", type=Path, required=True, help="Arquivo .jsonl de entrada.")
    parser.add_argument("--out", type=Path, required=True, help="Diretório de saída.")
    parser.add_argument("--modelo", type=str, default=None, help="Override opcional de modelo.")
    args = parser.parse_args(argv)

    dataset = carregar_dataset_jsonl(args.dataset)
    asyncio.run(avaliar_dataset_async(dataset, args.out, modelo_override=args.modelo))
    print((args.out / "report.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main_eval())
