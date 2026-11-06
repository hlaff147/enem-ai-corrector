"""Detecção determinística de conectivos, operadores argumentativos e repetições lexicais (apoio à C4)."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass, field

from .texto import _STOPWORDS_PT, palavras, separar_paragrafos

CATALOGO_CONECTIVOS: dict[str, list[str]] = {
    "adicao_continuacao": [
        "além disso",
        "ademais",
        "outrossim",
        "somado a isso",
        "soma-se a isso",
        "não obstante",
        "também",
        "paralelamente",
        "em consonância",
    ],
    "oposicao_contraste": [
        "entretanto",
        "no entanto",
        "todavia",
        "contudo",
        "porém",
        "embora",
        "apesar de",
        "apesar disso",
        "em contrapartida",
        "por outro lado",
        "conquanto",
        "malgrado",
    ],
    "causa_explicacao": [
        "visto que",
        "já que",
        "uma vez que",
        "dado que",
        "porquanto",
        "em virtude de",
        "em razão de",
        "devido a",
        "haja vista",
        "porque",
        "pois",
    ],
    "conclusao_consequencia": [
        "portanto",
        "logo",
        "assim",
        "dessa forma",
        "desse modo",
        "dessa maneira",
        "nesse sentido",
        "nesse contexto",
        "nesse viés",
        "sob essa ótica",
        "por conseguinte",
        "em suma",
        "em síntese",
        "diante disso",
        "diante desse cenário",
        "sendo assim",
        "destarte",
        "infere-se",
    ],
    "finalidade": [
        "a fim de",
        "com o intuito de",
        "com o objetivo de",
        "com a finalidade de",
        "para que",
        "visando",
    ],
    "ordenacao_exemplificacao": [
        "em primeiro lugar",
        "em primeira análise",
        "em primeiro plano",
        "primeiramente",
        "a princípio",
        "em segundo lugar",
        "em segunda análise",
        "em segundo plano",
        "por exemplo",
        "a título de exemplo",
        "como exemplo",
    ],
}


@dataclass
class AnaliseCoesao:
    conectivos_por_categoria: dict[str, list[str]] = field(default_factory=dict)
    total_conectivos: int = 0
    conectivos_distintos: int = 0
    inicios_paragrafos: list[str] = field(default_factory=list)
    conectivos_interparagrafos: list[str] = field(default_factory=list)
    conectivos_repetidos: dict[str, int] = field(default_factory=dict)
    palavras_repetidas: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def analisar_coesao(texto: str) -> AnaliseCoesao:
    paragrafos = separar_paragrafos(texto)
    texto_lower = texto.lower()

    encontrados_cat: dict[str, list[str]] = {}
    contagem_conectivos: Counter[str] = Counter()

    for categoria, lista in CATALOGO_CONECTIVOS.items():
        achados = []
        for conectivo in lista:
            padrao = r"\b" + re.escape(conectivo) + r"\b"
            ocorrencias = re.findall(padrao, texto_lower)
            if ocorrencias:
                achados.extend(ocorrencias)
                contagem_conectivos[conectivo] += len(ocorrencias)
        if achados:
            encontrados_cat[categoria] = achados

    inicios: list[str] = []
    interparagrafos: list[str] = []
    todos_conectivos = [
        c for lista in CATALOGO_CONECTIVOS.values() for c in lista
    ]
    todos_conectivos.sort(key=len, reverse=True)

    for idx, p in enumerate(paragrafos):
        primeiras = " ".join(p.split()[:6])
        inicios.append(primeiras)
        if idx >= 1:
            inicio_lower = " ".join(p.split()[:5]).lower()
            for c in todos_conectivos:
                if re.search(r"^\W*\b" + re.escape(c) + r"\b", inicio_lower):
                    interparagrafos.append(c)
                    break

    tokens_conteudo = [
        t.lower()
        for t in palavras(texto)
        if len(t) >= 4 and t.lower() not in _STOPWORDS_PT
    ]
    freq_palavras = Counter(tokens_conteudo)
    repetidas = {pal: qtd for pal, qtd in freq_palavras.most_common(10) if qtd >= 4}
    conectivos_rep = {c: q for c, q in contagem_conectivos.items() if q >= 2}

    return AnaliseCoesao(
        conectivos_por_categoria=encontrados_cat,
        total_conectivos=sum(contagem_conectivos.values()),
        conectivos_distintos=len(contagem_conectivos),
        inicios_paragrafos=inicios,
        conectivos_interparagrafos=interparagrafos,
        conectivos_repetidos=conectivos_rep,
        palavras_repetidas=repetidas,
    )
