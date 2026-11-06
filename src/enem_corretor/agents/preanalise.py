"""Etapa 1 — Pré-análise determinística e parsing da entrada do usuário."""

from __future__ import annotations

import json
import re
from typing import Any

from ..config import Config, carregar_config
from ..schemas.entrada import EntradaRedacao
from ..tools.conectivos import analisar_coesao
from ..tools.copia import detectar_copia_motivadores
from ..tools.gramatica import verificar_gramatica
from ..tools.texto import (
    analisar_texto,
    estimar_linhas,
    normalizar_texto,
    numerar_paragrafos,
    separar_paragrafos,
)


def extrair_entrada_do_texto(mensagem: str) -> EntradaRedacao:
    """Aceita entrada em JSON (`{"tema": ..., "redacao": ...}`), tags/marcadores
    (`TEMA: ... REDAÇÃO: ...`) ou texto puro (usa tema genérico com alerta)."""
    texto = (mensagem or "").strip()
    if not texto:
        return EntradaRedacao(tema="(não informado)", redacao="")

    # 1. JSON direto
    if texto.startswith("{"):
        try:
            dados = json.loads(texto)
            if isinstance(dados, dict) and ("redacao" in dados or "texto" in dados):
                return EntradaRedacao(
                    tema=str(dados.get("tema") or "(tema não informado)"),
                    redacao=str(dados.get("redacao") or dados.get("texto") or ""),
                    motivadores=list(dados.get("motivadores") or []),
                    titulo=dados.get("titulo"),
                )
        except json.JSONDecodeError:
            pass

    # 2. Formato "TEMA: ...\nREDAÇÃO: ..." (ou "Tema: ...\nTexto: ...")
    padrao = re.compile(
        r"^\s*tema\s*:\s*(?P<tema>.+?)\n+\s*(?:reda[cç][aã]o|texto)\s*:\s*(?P<redacao>[\s\S]+)$",
        flags=re.IGNORECASE,
    )
    m = padrao.match(texto)
    if m:
        return EntradaRedacao(
            tema=m.group("tema").strip(),
            redacao=m.group("redacao").strip(),
        )

    # 3. Texto puro → primeira linha curta como tema se vier precedida de "Tema"
    linhas = texto.splitlines()
    if len(linhas) >= 3 and len(linhas[0]) < 160 and "tema" in linhas[0].lower():
        tema = re.sub(r"^\s*tema\s*[:\-–]?\s*", "", linhas[0], flags=re.IGNORECASE).strip()
        corpo = "\n".join(linhas[1:]).strip()
        return EntradaRedacao(tema=tema or "(tema não informado)", redacao=corpo)

    return EntradaRedacao(tema="(tema não informado pelo usuário)", redacao=texto)


def executar_preanalise(entrada: EntradaRedacao, cfg: Config | None = None) -> dict[str, Any]:
    """Executa todas as ferramentas determinísticas sobre a redação."""
    cfg = cfg or carregar_config()
    redacao_norm = normalizar_texto(entrada.redacao)
    paragrafos = separar_paragrafos(redacao_norm)
    stats = analisar_texto(redacao_norm, caracteres_por_linha=cfg.caracteres_por_linha)
    copia = detectar_copia_motivadores(redacao_norm, entrada.motivadores)
    coesao = analisar_coesao(redacao_norm)
    alertas_gramatica = verificar_gramatica(
        redacao_norm,
        usar_languagetool=cfg.languagetool_habilitado,
        languagetool_url=cfg.languagetool_url,
    )

    # Desconta linhas equivalentes aos trechos copiados dos motivadores
    fracao_original = max(0.0, 1.0 - copia.proporcao_copiada)
    linhas_originais_estimadas = max(
        0, round(stats.linhas_estimadas * fracao_original)
    ) if redacao_norm else 0

    motivos_deterministicos: list[str] = []
    alertas_preanalise: list[str] = []

    if not redacao_norm or stats.palavras == 0:
        motivos_deterministicos.append(
            "folha_em_branco: Redação em branco ou sem palavras válidas."
        )
    elif stats.linhas_estimadas < cfg.linhas_minimas:
        motivos_deterministicos.append(
            f"texto_insuficiente: Redação estimada em {stats.linhas_estimadas} linha(s) "
            f"(mínimo exigido: {cfg.linhas_minimas} linhas; textos até 7 linhas são anulados)."
        )
    elif linhas_originais_estimadas < cfg.linhas_minimas and copia.proporcao_copiada >= 0.5:
        motivos_deterministicos.append(
            f"copia_motivadores: {int(copia.proporcao_copiada * 100)}% do texto coincide com os "
            f"textos motivadores, restando ~{linhas_originais_estimadas} linha(s) próprias "
            f"(mínimo: {cfg.linhas_minimas})."
        )

    if stats.linhas_estimadas > cfg.linhas_maximas:
        alertas_preanalise.append(
            f"Texto estimado em {stats.linhas_estimadas} linhas (ultrapassa o limite de "
            f"{cfg.linhas_maximas} linhas da folha oficial)."
        )
    if entrada.tema.startswith("(tema não informado"):
        alertas_preanalise.append(
            "Tema não foi informado separadamente; informe 'TEMA: ...' e 'REDAÇÃO: ...' para avaliação precisa de C2/C3."
        )
    if stats.sinais_identificacao:
        alertas_preanalise.append(
            "Sinais potenciais de identificação detectados: " + "; ".join(stats.sinais_identificacao)
        )

    return {
        "estatisticas": stats.to_dict(),
        "linhas_originais_estimadas": linhas_originais_estimadas,
        "copia_motivadores": copia.to_dict(),
        "coesao": coesao.to_dict(),
        "alertas_gramaticais": alertas_gramatica,
        "motivos_anulacao_deterministicos": motivos_deterministicos,
        "alertas_preanalise": alertas_preanalise,
        "paragrafos": paragrafos,
        "redacao_normalizada": redacao_norm,
        "redacao_numerada": numerar_paragrafos(paragrafos),
    }
