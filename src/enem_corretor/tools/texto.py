"""Funções determinísticas de análise de texto: normalização, parágrafos,
contagem de linhas/palavras/períodos e heurísticas simples."""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import asdict, dataclass, field

_STOPWORDS_PT = {
    "a", "o", "as", "os", "de", "da", "do", "das", "dos", "e", "é", "em", "no",
    "na", "nos", "nas", "um", "uma", "que", "para", "por", "com", "não", "se",
    "ao", "aos", "à", "às", "como", "mais", "mas", "ou", "sua", "seu", "suas",
    "seus", "isso", "essa", "esse", "esta", "este", "pela", "pelo", "pelas",
    "pelos", "são", "também", "ser", "foi", "há", "entre", "sobre", "quando",
    "muito", "já", "sem", "mesmo", "nem", "assim", "ainda", "onde", "lhe",
}
_STOPWORDS_EN = {
    "the", "and", "of", "to", "is", "in", "that", "it", "for", "on", "with",
    "as", "are", "this", "be", "by", "not", "or", "from", "at", "which",
}
_STOPWORDS_ES = {
    "el", "la", "los", "las", "y", "es", "en", "que", "del", "por", "con",
    "para", "una", "uno", "pero", "muy", "también", "está", "son", "sus",
}


def normalizar_texto(texto: str) -> str:
    """Normaliza quebras de linha, espaços, caracteres invisíveis de largura zero e sinais tipográficos."""
    texto = unicodedata.normalize("NFC", texto or "")
    texto = re.sub(r"[\u200b-\u200d\ufeff]", "", texto)
    for orig, dest in (
        ("“", '"'),
        ("”", '"'),
        ("‘", "'"),
        ("’", "'"),
        ("–", "-"),
        ("—", "-"),
    ):
        texto = texto.replace(orig, dest)
    texto = texto.replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ")
    texto = re.sub(r"[ \u00a0]+", " ", texto)
    texto = "\n".join(linha.strip() for linha in texto.split("\n"))
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def separar_paragrafos(texto: str) -> list[str]:
    """Separa parágrafos por linha em branco; se não houver, por quebra simples."""
    texto = normalizar_texto(texto)
    if not texto:
        return []
    if "\n\n" in texto:
        blocos = texto.split("\n\n")
        return [" ".join(b.split("\n")).strip() for b in blocos if b.strip()]
    return [linha for linha in texto.split("\n") if linha.strip()]


def palavras(texto: str) -> list[str]:
    return re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ]+(?:-[A-Za-zÀ-ÖØ-öø-ÿ]+)*", texto)


def separar_periodos(texto: str) -> list[str]:
    partes = re.split(r"(?<=[.!?…])\s+", normalizar_texto(texto).replace("\n", " "))
    return [p.strip() for p in partes if palavras(p)]


def estimar_linhas(paragrafos: list[str], caracteres_por_linha: int) -> int:
    """Estima as linhas manuscritas: cada parágrafo começa em linha nova e ocupa
    ceil(caracteres / caracteres_por_linha) linhas (+ recuo de ~3 caracteres)."""
    return sum(
        max(1, math.ceil((len(p) + 3) / caracteres_por_linha)) for p in paragrafos if p
    )


def proporcao_idiomas(texto: str) -> dict[str, float]:
    tokens = [t.lower() for t in palavras(texto)]
    if not tokens:
        return {"pt": 0.0, "en": 0.0, "es": 0.0}
    total = len(tokens)
    return {
        "pt": sum(t in _STOPWORDS_PT for t in tokens) / total,
        "en": sum(t in _STOPWORDS_EN for t in tokens) / total,
        "es": sum(t in _STOPWORDS_ES for t in tokens) / total,
    }


_PADROES_IDENTIFICACAO = [
    (r"\b(?:meu nome é|me chamo|assinado|att\.?|atenciosamente)\b", "possível assinatura/identificação"),
    (r"[\w.+-]+@[\w-]+\.[\w.]+", "e-mail"),
    (r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b", "possível CPF"),
    (r"(?:^|\n)\s*(?:nome|aluno|aluna|candidato|candidata)\s*:", "campo de nome"),
]


def sinais_identificacao(texto: str) -> list[str]:
    achados = []
    for padrao, rotulo in _PADROES_IDENTIFICACAO:
        if m := re.search(padrao, texto, flags=re.IGNORECASE):
            achados.append(f"{rotulo}: '{m.group(0).strip()}'")
    return achados


@dataclass
class EstatisticasTexto:
    caracteres: int
    palavras: int
    paragrafos: int
    periodos: int
    linhas_estimadas: int
    media_palavras_por_periodo: float
    periodos_longos: list[str] = field(default_factory=list)
    """Períodos com mais de 60 palavras (risco de truncamento/estrutura falha)."""
    tamanho_paragrafos: list[int] = field(default_factory=list)
    """Número de palavras de cada parágrafo."""
    idioma: dict[str, float] = field(default_factory=dict)
    sinais_identificacao: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def analisar_texto(texto: str, caracteres_por_linha: int = 70) -> EstatisticasTexto:
    texto = normalizar_texto(texto)
    pars = separar_paragrafos(texto)
    pers = separar_periodos(texto)
    n_palavras = len(palavras(texto))
    return EstatisticasTexto(
        caracteres=len(texto),
        palavras=n_palavras,
        paragrafos=len(pars),
        periodos=len(pers),
        linhas_estimadas=estimar_linhas(pars, caracteres_por_linha),
        media_palavras_por_periodo=round(n_palavras / len(pers), 1) if pers else 0.0,
        periodos_longos=[p for p in pers if len(palavras(p)) > 60],
        tamanho_paragrafos=[len(palavras(p)) for p in pars],
        idioma={k: round(v, 3) for k, v in proporcao_idiomas(texto).items()},
        sinais_identificacao=sinais_identificacao(texto),
    )


def numerar_paragrafos(paragrafos: list[str]) -> str:
    """Formata os parágrafos como [§1] ..., para que os agentes possam referenciá-los."""
    return "\n\n".join(f"[§{i}] {p}" for i, p in enumerate(paragrafos, start=1))
