"""Validação pós-modelo de que os trechos citados como evidência realmente
existem no texto da redação (mitigação contra alucinação de evidências)."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from ..schemas.saida import ValidacaoEvidencia


def _simplificar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip(" \"'“”‘’.,;:!?()[]")


def validar_trecho(trecho: str, redacao: str) -> ValidacaoEvidencia:
    """Verifica se `trecho` ocorre de forma exata ou aproximada em `redacao`."""
    limpo = (trecho or "").strip()
    if not limpo:
        return ValidacaoEvidencia(trecho=trecho, status="nao_encontrada")

    if limpo in redacao or limpo.lower() in redacao.lower():
        return ValidacaoEvidencia(trecho=trecho, status="exata")

    alvo = _simplificar(limpo)
    base = _simplificar(redacao)
    if not alvo:
        return ValidacaoEvidencia(trecho=trecho, status="nao_encontrada")

    if alvo in base:
        return ValidacaoEvidencia(trecho=trecho, status="exata")

    # Reticências ("inicio ... fim"): valida se ambas as pontas existem na redação
    if "..." in alvo or "…" in limpo:
        partes = [p.strip() for p in re.split(r"\.{3}|…", alvo) if len(p.strip()) >= 6]
        if partes and all(p in base for p in partes):
            return ValidacaoEvidencia(trecho=trecho, status="aproximada")

    # Janela deslizante para similaridade aproximada (>= 0.82)
    tam = len(alvo)
    if tam >= 8 and len(base) >= tam:
        passo = max(1, tam // 5)
        melhor = 0.0
        for i in range(0, len(base) - tam + 1, passo):
            janela = base[i : i + tam]
            ratio = SequenceMatcher(None, alvo, janela).ratio()
            if ratio > melhor:
                melhor = ratio
                if melhor >= 0.85:
                    return ValidacaoEvidencia(trecho=trecho, status="aproximada")
        if melhor >= 0.80:
            return ValidacaoEvidencia(trecho=trecho, status="aproximada")

    return ValidacaoEvidencia(trecho=trecho, status="nao_encontrada")


def validar_evidencias_competencia(avaliacao_dict: dict, redacao: str) -> list[ValidacaoEvidencia]:
    """Extrai todos os trechos citados em uma avaliação de competência e os valida."""
    trechos: list[str] = []
    for item in avaliacao_dict.get("evidencias", []) or []:
        if isinstance(item, dict) and item.get("trecho"):
            trechos.append(item["trecho"])
    for chave in ("desvios", "repertorios", "argumentos", "inadequacoes", "elementos"):
        for item in avaliacao_dict.get(chave, []) or []:
            if isinstance(item, dict) and item.get("trecho"):
                trechos.append(item["trecho"])

    vistos: set[str] = set()
    resultado: list[ValidacaoEvidencia] = []
    for t in trechos:
        if t not in vistos:
            vistos.add(t)
            resultado.append(validar_trecho(t, redacao))
    return resultado
