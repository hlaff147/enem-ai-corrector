"""Verificação gramatical/ortográfica para apoio à Competência 1:
1. Heurísticas determinísticas rápidas em português (vícios comuns em redações).
2. Integração opcional com API compatível com LanguageTool (pública ou local).
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass
class AlertaGramatical:
    trecho: str
    tipo: str
    sugestao: str
    mensagem: str
    fonte: str = "heuristica"

    def to_dict(self) -> dict:
        return asdict(self)


_REGRAS_HEURISTICAS: list[tuple[str, str, str, str]] = [
    (
        r"\bhaviam\s+(?:muitos|muitas|poucos|poucas|vários|várias|diversos|diversas|inúmeros|inúmeras|problemas|casos|pessoas|fatores)\b",
        "concordancia_verbal",
        "havia",
        "O verbo 'haver' no sentido de existir é impessoal e permanece no singular ('havia').",
    ),
    (
        r"\bfazem\s+\d+\s+(?:anos|meses|dias|séculos|décadas)\b",
        "concordancia_verbal",
        "faz ...",
        "O verbo 'fazer' indicando tempo decorrido é impessoal e fica no singular ('faz').",
    ),
    (
        r"\ba\s+nível\s+de\b",
        "escolha_vocabular",
        "em âmbito / no plano de",
        "A locução 'a nível de' não é aceita na norma-padrão; prefira 'em âmbito' ou 'no que tange a'.",
    ),
    (
        r"\b(?:à|às)\s+(?:partir|fazer|ser|ter|ver|mostrar|garantir|promover|criar|combater|reduzir|resolver)\b",
        "crase",
        "a + verbo (sem crase)",
        "Não ocorre crase antes de verbo no infinitivo.",
    ),
    (
        r"\b(?:à|às)\s+(?:um|uma|uns|umas|isso|esse|este|esta|esses|essas|algum|alguma|todos|todas|cada|quem|ninguém)\b",
        "crase",
        "a (sem crase)",
        "Não ocorre crase antes de artigos indefinidos ou pronomes que não admitem artigo 'a'.",
    ),
    (
        r"\b(?:pra|pro|pras|pros|tá|né|tipo\s+assim|aí\s+que)\b",
        "registro_informal",
        "para / está / etc.",
        "Marca de oralidade/registro informal inadequada à dissertação do ENEM.",
    ),
    (
        r"\batravés\s+d[eo]s?\s+(?:governo|estado|ministério|escola|mídia|lei|campanha|investimento|políticas|medidas|ações)\b",
        "escolha_vocabular",
        "por meio de / por intermédio de",
        "Para indicar instrumento/agente de ação, a norma culta prefere 'por meio de' em vez de 'através de'.",
    ),
    (
        r"\bonde\s+o\s+mesmo\b|\ba\s+mesma\s+(?:deve|pode|precisa|fez)\b",
        "referenciacao",
        "pronome pessoal ou demonstrativo adequado",
        "O uso de 'o mesmo / a mesma' como pronome substantivo é condenado pela norma-padrão.",
    ),
]


def verificar_heuristicas(texto: str) -> list[AlertaGramatical]:
    alertas: list[AlertaGramatical] = []
    for padrao, tipo, sugestao, mensagem in _REGRAS_HEURISTICAS:
        for m in re.finditer(padrao, texto, flags=re.IGNORECASE):
            alertas.append(
                AlertaGramatical(
                    trecho=m.group(0),
                    tipo=tipo,
                    sugestao=sugestao,
                    mensagem=mensagem,
                    fonte="heuristica",
                )
            )
    return alertas


def consultar_languagetool(
    texto: str, url: str = "https://api.languagetool.org/v2/check", timeout: float = 8.0
) -> list[AlertaGramatical]:
    """Consulta opcional à API HTTP do LanguageTool (pública ou servidor local)."""
    try:
        resp = httpx.post(
            url,
            data={"text": texto, "language": "pt-BR"},
            timeout=timeout,
        )
        resp.raise_for_status()
        dados = resp.json()
    except Exception as exc:
        logger.warning("LanguageTool indisponível (%s); seguindo sem ele.", exc)
        return []

    alertas: list[AlertaGramatical] = []
    for match in dados.get("matches", [])[:25]:
        offset = match.get("offset", 0)
        length = match.get("length", 0)
        trecho = texto[offset : offset + length]
        replacements = [r.get("value", "") for r in match.get("replacements", [])[:3]]
        rule = match.get("rule", {})
        alertas.append(
            AlertaGramatical(
                trecho=trecho,
                tipo=rule.get("issueType", "gramatica"),
                sugestao=", ".join(r for r in replacements if r),
                mensagem=match.get("message", ""),
                fonte="languagetool",
            )
        )
    return alertas


def verificar_gramatica(
    texto: str,
    usar_languagetool: bool = False,
    languagetool_url: str = "https://api.languagetool.org/v2/check",
) -> list[dict]:
    alertas = verificar_heuristicas(texto)
    if usar_languagetool:
        alertas.extend(consultar_languagetool(texto, url=languagetool_url))
    return [a.to_dict() for a in alertas]
