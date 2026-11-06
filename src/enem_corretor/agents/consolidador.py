"""Etapa 4 — Consolidador / Juiz determinístico.

Aplica regras de teto entre competências (ex.: tangenciamento em C2 limita C2/C3/C5
a 40; contagem objetiva dos 5 elementos em C5; violação aos DH zera C5; cópia de
motivadores limita C2 a 80), valida as evidências literais contra o texto da redação
e formata o relatório final em Markdown.
"""

from __future__ import annotations

from typing import Any

from ..config import Config, carregar_config
from ..schemas.saida import (
    COMPETENCIAS,
    AvaliacaoFinal,
    Feedback,
    ResultadoCompetencia,
    ajustar_nivel,
)
from ..tools.evidencias import validar_evidencias_competencia
from ..tools.rubricas import carregar_rubrica

ELEMENTOS_C5_CANONICOS = {"agente", "acao", "meio", "finalidade", "detalhamento"}


def _normalizar_nome_elemento(nome: str) -> str:
    n = (nome or "").strip().lower()
    for a, b in (("ç", "c"), ("ã", "a"), ("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o")):
        n = n.replace(a, b)
    if "agente" in n:
        return "agente"
    if "acao" in n:
        return "acao"
    if "meio" in n or "modo" in n:
        return "meio"
    if "finalidade" in n or "efeito" in n:
        return "finalidade"
    if "detalha" in n:
        return "detalhamento"
    return n


def consolidar_avaliacao(
    state: dict[str, Any], cfg: Config | None = None
) -> AvaliacaoFinal:
    cfg = cfg or carregar_config()
    entrada = state.get("entrada", {})
    preanalise = state.get("preanalise", {})
    redacao_original = preanalise.get("redacao_normalizada") or entrada.get("redacao", "")
    rubrica_c1 = carregar_rubrica("c1")

    motivos_det: list[str] = list(preanalise.get("motivos_anulacao_deterministicos") or [])
    anulacao_llm: dict[str, Any] = state.get("anulacao_llm") or {}
    motivos_llm: list[str] = []
    if anulacao_llm.get("anular"):
        for m in anulacao_llm.get("motivos") or []:
            if isinstance(m, dict):
                motivos_llm.append(f"{m.get('motivo')}: {m.get('evidencia')}")
            else:
                motivos_llm.append(str(m))

    motivos_anulacao = motivos_det + motivos_llm
    anulada = bool(motivos_anulacao)

    alertas: list[str] = list(preanalise.get("alertas_preanalise") or [])
    for al in anulacao_llm.get("alertas") or []:
        if al not in alertas:
            alertas.append(al)

    if not rubrica_c1.get("verificado", False):
        alertas.append(
            "Rubricas ainda estão com `verificado: false` (ano de referência: "
            f"{rubrica_c1.get('ano_referencia')}). Confira com a Cartilha oficial do INEP."
        )

    # Caso anulada: todas as competências recebem 0
    if anulada:
        comps_anuladas = {
            c: ResultadoCompetencia(
                competencia=c,  # type: ignore[arg-type]
                nota=0,
                nota_modelo=0,
                ajustes=["Redação anulada (nota 0 em todas as competências)."],
                justificativa="Redação anulada: " + "; ".join(motivos_anulacao),
            )
            for c in COMPETENCIAS
        }
        return AvaliacaoFinal(
            tema=entrada.get("tema", ""),
            anulada=True,
            motivos_anulacao=motivos_anulacao,
            competencias=comps_anuladas,
            nota_total=0,
            alertas=alertas,
            preanalise={
                k: v
                for k, v in preanalise.items()
                if k not in {"redacao_numerada", "redacao_normalizada", "paragrafos"}
            },
            modelo=cfg.modelo,
            rubrica_ano_referencia=rubrica_c1.get("ano_referencia"),
            rubrica_verificada=bool(rubrica_c1.get("verificado", False)),
        )

    av_c2: dict[str, Any] = state.get("avaliacao_c2") or {}
    tangenciamento = bool(
        av_c2.get("tangenciamento")
        or str(av_c2.get("abordagem_tema", "")).strip().lower() == "tangenciamento"
    )
    copia_prop = (
        (preanalise.get("copia_motivadores") or {}).get("proporcao_copiada", 0.0) or 0.0
    )

    resultados: dict[str, ResultadoCompetencia] = {}

    for comp in COMPETENCIAS:
        chave = f"avaliacao_{comp.lower()}"
        dados_comp: dict[str, Any] | None = state.get(chave)
        if not dados_comp or not isinstance(dados_comp, dict):
            alertas.append(f"Agente {comp} não retornou avaliação estruturada válida.")
            resultados[comp] = ResultadoCompetencia(
                competencia=comp,  # type: ignore[arg-type]
                nota=0,
                nota_modelo=None,
                ajustes=["Falha na execução do agente da competência."],
                justificativa="Avaliação indisponível.",
            )
            continue

        nota_modelo = ajustar_nivel(dados_comp.get("nota", 0))
        nota_final = nota_modelo
        ajustes: list[str] = []

        # Regras específicas por competência
        if comp == "C2":
            if tangenciamento and nota_final > 40:
                nota_final = 40
                ajustes.append("Teto de tangenciamento aplicado: C2 limitada a 40 pontos.")
            if (dados_comp.get("copia_motivadores") or copia_prop >= 0.20) and nota_final > 80:
                nota_final = 80
                ajustes.append("Cópia de trechos dos textos motivadores: C2 limitada a 80 pontos.")
            if not dados_comp.get("tipo_textual_adequado", True) and nota_final > 40:
                nota_final = 40
                ajustes.append("Predomínio/traços constantes de outro tipo textual: C2 limitada a 40.")

        elif comp == "C3":
            if tangenciamento and nota_final > 40:
                nota_final = 40
                ajustes.append("Teto de tangenciamento (detectado em C2): C3 limitada a 40 pontos.")

        elif comp == "C5":
            if not dados_comp.get("respeita_direitos_humanos", True):
                if nota_final != 0:
                    ajustes.append("Violação aos Direitos Humanos: C5 zerada (0 pontos).")
                nota_final = 0
            elif not dados_comp.get("proposta_presente", True) or not dados_comp.get(
                "relacionada_ao_tema", True
            ):
                if not dados_comp.get("proposta_presente", True):
                    nota_final = 0
                    ajustes.append("Ausência de proposta de intervenção: C5 = 0.")
                elif nota_final > 40:
                    nota_final = 40
                    ajustes.append("Proposta relacionada apenas ao assunto: C5 limitada a 40.")
            else:
                elementos = dados_comp.get("elementos") or []
                validos = {
                    _normalizar_nome_elemento(el.get("elemento", ""))
                    for el in elementos
                    if isinstance(el, dict) and el.get("valido")
                } & ELEMENTOS_C5_CANONICOS
                nota_por_elementos = min(200, len(validos) * 40)
                if elementos and nota_por_elementos != nota_final:
                    ajustes.append(
                        f"Contagem objetiva de elementos válidos em C5 ({len(validos)}/5: "
                        f"{', '.join(sorted(validos)) or 'nenhum'}) → {nota_por_elementos} pontos "
                        f"(nota original do agente: {nota_final})."
                    )
                    nota_final = nota_por_elementos
                if not dados_comp.get("articulada_a_discussao", True) and nota_final > 80:
                    nota_final = 80
                    ajustes.append(
                        "Proposta não articulada à discussão desenvolvida no texto: C5 limitada a 80."
                    )
                if tangenciamento and nota_final > 40:
                    nota_final = 40
                    ajustes.append(
                        "Teto de tangenciamento (detectado em C2): C5 limitada a 40 pontos."
                    )

        evidencias_val = validar_evidencias_competencia(dados_comp, redacao_original)
        nao_enc = [ev.trecho for ev in evidencias_val if ev.status == "nao_encontrada"]
        if nao_enc:
            alertas.append(
                f"{comp}: {len(nao_enc)} trecho(s) citado(s) pelo modelo não foram encontrados "
                "literalmente na redação."
            )

        resultados[comp] = ResultadoCompetencia(
            competencia=comp,  # type: ignore[arg-type]
            nota=nota_final,
            nota_modelo=nota_modelo,
            ajustes=ajustes,
            justificativa=dados_comp.get("justificativa", ""),
            avaliacao=dados_comp,
            evidencias_validadas=evidencias_val,
        )

    nota_total = sum(r.nota for r in resultados.values())
    fb_raw = state.get("feedback")
    feedback = Feedback.model_validate(fb_raw) if isinstance(fb_raw, dict) else None

    return AvaliacaoFinal(
        tema=entrada.get("tema", ""),
        anulada=False,
        motivos_anulacao=[],
        competencias=resultados,
        nota_total=nota_total,
        alertas=alertas,
        preanalise={
            k: v
            for k, v in preanalise.items()
            if k not in {"redacao_numerada", "redacao_normalizada", "paragrafos"}
        },
        feedback=feedback,
        modelo=cfg.modelo,
        rubrica_ano_referencia=rubrica_c1.get("ano_referencia"),
        rubrica_verificada=bool(rubrica_c1.get("verificado", False)),
    )


def formatar_relatorio_markdown(av: AvaliacaoFinal) -> str:
    """Gera um relatório legível em Markdown a partir de `AvaliacaoFinal`."""
    linhas: list[str] = [
        "# Relatório de Correção — Redação ENEM",
        "",
        f"**Tema:** {av.tema}",
        f"**Nota Total:** **{av.nota_total} / 1000**",
        f"**Modelo:** `{av.modelo}`",
    ]

    est = (av.preanalise or {}).get("estatisticas") or {}
    if est:
        linhas.append(
            f"**Pré-análise:** {est.get('palavras', 0)} palavras | "
            f"{est.get('paragrafos', 0)} parágrafos | "
            f"~{est.get('linhas_estimadas', 0)} linhas estimadas"
        )
    linhas.append("")

    if av.anulada:
        linhas.extend(
            [
                "## ⚠️ Redação Anulada (Nota 0)",
                "",
                "Motivo(s) identificado(s):",
                *[f"- {m}" for m in av.motivos_anulacao],
                "",
            ]
        )
        return "\n".join(linhas)

    linhas.extend(
        [
            "## Quadro de Notas por Competência",
            "",
            "| Competência | Nota Final | Nota Agente | Ajustes de Regra |",
            "|---|---:|---:|---|",
        ]
    )
    for comp in COMPETENCIAS:
        rc = av.competencias.get(comp)
        if not rc:
            continue
        aj = "; ".join(rc.ajustes) if rc.ajustes else "—"
        linhas.append(f"| **{comp}** | **{rc.nota}** | {rc.nota_modelo} | {aj} |")
    linhas.append("")

    linhas.append("## Detalhamento por Competência")
    linhas.append("")
    for comp in COMPETENCIAS:
        rc = av.competencias.get(comp)
        if not rc:
            continue
        linhas.append(f"### {comp} — {rc.nota} pontos")
        if rc.justificativa:
            linhas.append(f"**Justificativa:** {rc.justificativa}")
        dados = rc.avaliacao or {}

        if comp == "C1" and dados.get("desvios"):
            linhas.append("\n**Desvios identificados:**")
            for d in dados["desvios"]:
                linhas.append(
                    f"- `{d.get('trecho')}` → **{d.get('correcao')}** "
                    f"*({d.get('tipo')})*: {d.get('explicacao')}"
                )
        elif comp == "C2" and dados.get("repertorios"):
            linhas.append("\n**Repertórios avaliados:**")
            for r in dados["repertorios"]:
                flags = (
                    f"legitimado={'sim' if r.get('legitimado') else 'não'}, "
                    f"pertinente={'sim' if r.get('pertinente') else 'não'}, "
                    f"produtivo={'sim' if r.get('produtivo') else 'não'}"
                )
                linhas.append(f"- `{r.get('trecho')}` — {r.get('descricao')} ({flags})")
        elif comp == "C5" and dados.get("elementos"):
            linhas.append("\n**Elementos da proposta de intervenção:**")
            for el in dados["elementos"]:
                status = "✅ válido" if el.get("valido") else "❌ inválido/vago"
                linhas.append(
                    f"- **{el.get('elemento')}** ({status}): `{el.get('trecho')}`"
                )

        if dados.get("evidencias"):
            linhas.append("\n**Evidências no texto:**")
            for ev in dados["evidencias"]:
                linhas.append(f'- "{ev.get("trecho")}" — {ev.get("comentario")}')
        linhas.append("")

    if av.feedback:
        fb = av.feedback
        linhas.extend(
            [
                "## Feedback Pedagógico e Plano de Melhoria",
                "",
                fb.resumo,
                "",
            ]
        )
        if fb.pontos_fortes:
            linhas.append("### Pontos Fortes")
            linhas.extend(f"- {pf}" for pf in fb.pontos_fortes)
            linhas.append("")
        if fb.prioridades:
            linhas.append("### Prioridades de Estudo")
            for p in fb.prioridades:
                linhas.append(
                    f"- **[{p.competencia}] {p.problema}** → {p.como_melhorar}"
                )
            linhas.append("")
        if fb.reescritas:
            linhas.append("### Exemplos de Reescrita")
            for r in fb.reescritas:
                linhas.extend(
                    [
                        f"- **[{r.competencia}] Original:** `{r.trecho_original}`",
                        f"  - **Sugestão:** `{r.sugestao}`",
                        f"  - *Por quê:* {r.explicacao}",
                    ]
                )
            linhas.append("")
        if fb.checklist_proxima_redacao:
            linhas.append("### Checklist para a Próxima Redação")
            linhas.extend(f"- [ ] {item}" for item in fb.checklist_proxima_redacao)
            linhas.append("")

    if av.alertas:
        linhas.append("## Alertas do Sistema")
        linhas.extend(f"- {a}" for a in av.alertas)
        linhas.append("")

    return "\n".join(linhas)
