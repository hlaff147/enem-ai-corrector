"""Métricas de Automated Essay Scoring (AES) conforme o Apêndice B do protocolo:
- QWK (Quadratic Weighted Kappa — calculado em Python puro, sem depender de scikit-learn)
- MAE, RMSE, Viés médio
- Concordância exata e adjacente (±40 pontos)
- Intervalos de confiança de 95% via Bootstrap
- Verificação de vazamento (leakage) por shingles de k palavras (Jaccard).
"""

from __future__ import annotations

import math
import random
from typing import Callable, Sequence

from ..tools.texto import normalizar_texto


def qwk(
    y_true: Sequence[int | float],
    y_pred: Sequence[int | float],
    min_rating: int = 0,
    max_rating: int = 200,
    step: int = 40,
) -> float:
    """Calcula o Quadratic Weighted Kappa (Cohen's kappa com pesos quadráticos)."""
    if len(y_true) != len(y_pred) or not y_true:
        return float("nan")
    if len(set(y_true)) < 2 and len(set(y_pred)) < 2:
        return float("nan")

    niveis = list(range(min_rating, max_rating + 1, step))
    k = len(niveis)
    if k < 2:
        return float("nan")

    def _idx(v: float) -> int:
        pos = round((float(v) - min_rating) / step)
        return max(0, min(k - 1, int(pos)))

    conf = [[0.0] * k for _ in range(k)]
    hist_true = [0.0] * k
    hist_pred = [0.0] * k
    n = float(len(y_true))

    for yt, yp in zip(y_true, y_pred):
        i, j = _idx(yt), _idx(yp)
        conf[i][j] += 1.0
        hist_true[i] += 1.0
        hist_pred[j] += 1.0

    num = 0.0
    den = 0.0
    denom_peso = float((k - 1) ** 2)
    for i in range(k):
        for j in range(k):
            peso = ((i - j) ** 2) / denom_peso
            esperado = (hist_true[i] * hist_pred[j]) / n
            num += peso * conf[i][j]
            den += peso * esperado

    if den == 0.0:
        return float("nan")
    return round(1.0 - (num / den), 4)


def mae(y_true: Sequence[int | float], y_pred: Sequence[int | float]) -> float:
    if not y_true:
        return float("nan")
    return round(sum(abs(float(p) - float(t)) for t, p in zip(y_true, y_pred)) / len(y_true), 2)


def rmse(y_true: Sequence[int | float], y_pred: Sequence[int | float]) -> float:
    if not y_true:
        return float("nan")
    mse = sum((float(p) - float(t)) ** 2 for t, p in zip(y_true, y_pred)) / len(y_true)
    return round(math.sqrt(mse), 2)


def vies_medio(y_true: Sequence[int | float], y_pred: Sequence[int | float]) -> float:
    """Média de `(predito - humano)`: positivo = infla; negativo = deflaciona."""
    if not y_true:
        return float("nan")
    return round(sum(float(p) - float(t) for t, p in zip(y_true, y_pred)) / len(y_true), 2)


def concordancia_exata(y_true: Sequence[int | float], y_pred: Sequence[int | float]) -> float:
    if not y_true:
        return float("nan")
    return round(sum(1 for t, p in zip(y_true, y_pred) if float(t) == float(p)) / len(y_true), 4)


def concordancia_adjacente(
    y_true: Sequence[int | float], y_pred: Sequence[int | float], tolerancia: float = 40.0
) -> float:
    if not y_true:
        return float("nan")
    return round(
        sum(1 for t, p in zip(y_true, y_pred) if abs(float(p) - float(t)) <= tolerancia)
        / len(y_true),
        4,
    )


def bootstrap_ic95(
    metric_fn: Callable[[Sequence[float], Sequence[float]], float],
    y_true: Sequence[int | float],
    y_pred: Sequence[int | float],
    n_boot: int = 500,
    seed: int = 42,
) -> tuple[float, float, float]:
    """Retorna `(media, limite_inferior_2.5%, limite_superior_97.5%)` via bootstrap."""
    n = len(y_true)
    if n == 0:
        return (float("nan"), float("nan"), float("nan"))
    rng = random.Random(seed)
    valores: list[float] = []
    for _ in range(n_boot):
        indices = [rng.randrange(n) for _ in range(n)]
        amostra_t = [float(y_true[i]) for i in indices]
        amostra_p = [float(y_pred[i]) for i in indices]
        val = metric_fn(amostra_t, amostra_p)
        if not math.isnan(val):
            valores.append(val)
    if not valores:
        return (float("nan"), float("nan"), float("nan"))
    valores.sort()
    lo = valores[max(0, int(0.025 * len(valores)))]
    hi = valores[min(len(valores) - 1, int(0.975 * len(valores)))]
    media = sum(valores) / len(valores)
    return (round(media, 4), round(lo, 4), round(hi, 4))


def shingles(texto: str, k: int = 8) -> set[str]:
    tokens = normalizar_texto(texto).lower().split()
    if len(tokens) < k:
        return {" ".join(tokens)} if tokens else set()
    return {" ".join(tokens[i : i + k]) for i in range(len(tokens) - k + 1)}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def detectar_vazamento(
    golden: dict[str, str], outros: dict[str, str], limiar: float = 0.6, k: int = 8
) -> list[tuple[str, str, float]]:
    """Retorna pares `(id_golden, id_outro, jaccard)` com sobreposição >= `limiar`."""
    g_map = {gid: shingles(txt, k=k) for gid, txt in golden.items()}
    o_map = {oid: shingles(txt, k=k) for oid, txt in outros.items()}
    suspeitos: list[tuple[str, str, float]] = []
    for gid, gs in g_map.items():
        for oid, os_ in o_map.items():
            sim = jaccard(gs, os_)
            if sim >= limiar:
                suspeitos.append((gid, oid, round(sim, 3)))
    return suspeitos
