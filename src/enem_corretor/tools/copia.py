"""Detecção de cópia dos textos motivadores por sobreposição de n-gramas."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field


def _tokens(texto: str) -> list[str]:
    texto = unicodedata.normalize("NFKD", texto.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9]+", texto)


@dataclass
class ResultadoCopia:
    proporcao_copiada: float
    """Fração das palavras da redação cobertas por n-gramas copiados."""
    palavras_copiadas: int
    trechos_copiados: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def detectar_copia_motivadores(
    texto: str, motivadores: list[str], n: int = 7
) -> ResultadoCopia:
    """Marca como copiada toda sequência de `n` palavras consecutivas da redação
    que também aparece em algum texto motivador.

    n=7 evita falsos positivos com expressões comuns ("de acordo com o", etc.).
    """
    tokens = _tokens(texto)
    if len(tokens) < n or not motivadores:
        return ResultadoCopia(0.0, 0)

    ngramas_motivadores: set[tuple[str, ...]] = set()
    for motivador in motivadores:
        t = _tokens(motivador)
        ngramas_motivadores.update(tuple(t[i : i + n]) for i in range(len(t) - n + 1))

    copiado = [False] * len(tokens)
    for i in range(len(tokens) - n + 1):
        if tuple(tokens[i : i + n]) in ngramas_motivadores:
            for j in range(i, i + n):
                copiado[j] = True

    trechos: list[str] = []
    inicio = None
    for i, flag in enumerate(copiado + [False]):
        if flag and inicio is None:
            inicio = i
        elif not flag and inicio is not None:
            trechos.append(" ".join(tokens[inicio:i]))
            inicio = None

    total = sum(copiado)
    return ResultadoCopia(
        proporcao_copiada=round(total / len(tokens), 3),
        palavras_copiadas=total,
        trechos_copiados=trechos,
    )
