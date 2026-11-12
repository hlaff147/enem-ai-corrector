"""Métricas de Automated Essay Scoring (AES), Machine Learning e Ciência de Dados:
- QWK (Quadratic Weighted Kappa — calculado em Python puro, sem depender de scikit-learn)
- Regressão e Correlação: MAE, RMSE, Viés médio, R², Pearson (r) e Spearman (ρ)
- Classificação Binária (Elegibilidade/Anulação): Matriz de Confusão, Acurácia,
  Acurácia Balanceada, Precisão, Recall, F1-Score, F-beta (F0.5) e MCC
- Classificação Multiclasse/Ordinal (C1–C5): Macro-F1, Weighted-F1, métricas por nível
  (0..200) e Matriz de Confusão 6x6
- Qualidade Intrínseca de Agentes LLM: Taxa de Grounding (Faithfulness), Taxa de
  Alucinação de Evidências e Alinhamento Pedagógico do Agente de Feedback
- Intervalos de confiança de 95% via Bootstrap e Percentis de Latência
- Verificação de vazamento (leakage) por shingles de k palavras (Jaccard).
"""

from __future__ import annotations

import math
import random
from typing import Any, Callable, Sequence

from ..tools.evidencias import validar_trecho
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


# ---------------------------------------------------------------------------
# Classificação Binária (Elegibilidade / Anulação)
# ---------------------------------------------------------------------------


def matriz_confusao_binaria(
    y_true: Sequence[bool], y_pred: Sequence[bool]
) -> dict[str, int]:
    """Calcula a matriz de confusão binária (`tp`, `fp`, `tn`, `fn`)."""
    tp = fp = tn = fn = 0
    for yt, yp in zip(y_true, y_pred):
        bt, bp = bool(yt), bool(yp)
        if bt and bp:
            tp += 1
        elif not bt and bp:
            fp += 1
        elif not bt and not bp:
            tn += 1
        else:
            fn += 1
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn}


def acuracia(y_true: Sequence[Any], y_pred: Sequence[Any]) -> float:
    """Proporção de predições exatamente iguais aos rótulos verdadeiros."""
    if len(y_true) != len(y_pred) or not y_true:
        return float("nan")
    return round(sum(1 for t, p in zip(y_true, y_pred) if t == p) / len(y_true), 4)


def acuracia_balanceada(
    y_true: Sequence[bool], y_pred: Sequence[bool]
) -> float:
    """Média entre Sensibilidade (TPR) e Especificidade (TNR).
    Se apenas uma classe estiver presente em `y_true`, retorna a acurácia padrão."""
    if len(y_true) != len(y_pred) or not y_true:
        return float("nan")
    mc = matriz_confusao_binaria(y_true, y_pred)
    pos = mc["tp"] + mc["fn"]
    neg = mc["tn"] + mc["fp"]
    if pos == 0 or neg == 0:
        return acuracia([bool(x) for x in y_true], [bool(x) for x in y_pred])
    tpr = mc["tp"] / pos
    tnr = mc["tn"] / neg
    return round((tpr + tnr) / 2.0, 4)


def precisao_recall_fbeta(
    y_true: Sequence[bool],
    y_pred: Sequence[bool],
    beta: float = 0.5,
    zero_division: float = 0.0,
) -> dict[str, float]:
    """Calcula Precisão, Recall, F1-Score e F-beta (padrão `beta=0.5` para priorizar Precisão)."""
    if len(y_true) != len(y_pred) or not y_true:
        nan = float("nan")
        return {"precisao": nan, "recall": nan, "f1": nan, "f_beta": nan}

    mc = matriz_confusao_binaria(y_true, y_pred)
    tp, fp, fn = mc["tp"], mc["fp"], mc["fn"]

    precisao = tp / (tp + fp) if (tp + fp) > 0 else zero_division
    recall = tp / (tp + fn) if (tp + fn) > 0 else zero_division
    f1 = (
        (2.0 * precisao * recall) / (precisao + recall)
        if (precisao + recall) > 0
        else zero_division
    )
    beta2 = beta**2
    denom_fb = (beta2 * precisao) + recall
    f_beta = (
        ((1.0 + beta2) * precisao * recall) / denom_fb
        if denom_fb > 0
        else zero_division
    )

    return {
        "precisao": round(precisao, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "f_beta": round(f_beta, 4),
    }


def mcc_binario(y_true: Sequence[bool], y_pred: Sequence[bool]) -> float:
    """Coeficiente de Correlação de Matthews (MCC) para classificação binária [-1, +1]."""
    if len(y_true) != len(y_pred) or not y_true:
        return float("nan")
    mc = matriz_confusao_binaria(y_true, y_pred)
    tp, fp, tn, fn = mc["tp"], mc["fp"], mc["tn"], mc["fn"]
    denom_sq = float((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    if denom_sq <= 0.0:
        return 0.0
    return round(((tp * tn) - (fp * fn)) / math.sqrt(denom_sq), 4)


# ---------------------------------------------------------------------------
# Classificação Multiclasse / Ordinal (Níveis 0, 40, 80, 120, 160, 200)
# ---------------------------------------------------------------------------


def metricas_multiclasse(
    y_true: Sequence[int | float],
    y_pred: Sequence[int | float],
    classes: Sequence[int] = (0, 40, 80, 120, 160, 200),
) -> dict[str, Any]:
    """Calcula Matriz de Confusão, Precisão/Recall/F1 por nível, Macro-F1 e Weighted-F1."""
    if len(y_true) != len(y_pred) or not y_true:
        nan = float("nan")
        return {
            "acuracia": nan,
            "macro_precisao": nan,
            "macro_recall": nan,
            "macro_f1": nan,
            "weighted_f1": nan,
            "por_nivel": {},
            "matriz_confusao": {},
        }

    classes_list = [int(c) for c in classes]

    def _ajustar_classe(v: int | float) -> int:
        val = float(v)
        return min(classes_list, key=lambda c: (abs(c - val), c))

    yt_norm = [_ajustar_classe(v) for v in y_true]
    yp_norm = [_ajustar_classe(v) for v in y_pred]

    matriz: dict[str, dict[str, int]] = {
        str(ct): {str(cp): 0 for cp in classes_list} for ct in classes_list
    }
    for t, p in zip(yt_norm, yp_norm):
        matriz[str(t)][str(p)] += 1

    por_nivel: dict[str, dict[str, float | int]] = {}
    classes_ativas: list[str] = []
    n_total = len(yt_norm)

    for c in classes_list:
        chave = str(c)
        tp = matriz[chave][chave]
        suporte = sum(matriz[chave].values())
        preditos = sum(matriz[ str(r) ][chave] for r in classes_list)

        prec = tp / preditos if preditos > 0 else 0.0
        rec = tp / suporte if suporte > 0 else 0.0
        f1 = (2.0 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0

        por_nivel[chave] = {
            "precisao": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(f1, 4),
            "suporte": suporte,
            "preditos": preditos,
        }
        if suporte > 0 or preditos > 0:
            classes_ativas.append(chave)

    n_ativas = len(classes_ativas) or 1
    macro_prec = sum(float(por_nivel[k]["precisao"]) for k in classes_ativas) / n_ativas
    macro_rec = sum(float(por_nivel[k]["recall"]) for k in classes_ativas) / n_ativas
    macro_f1 = sum(float(por_nivel[k]["f1"]) for k in classes_ativas) / n_ativas
    weighted_f1 = (
        sum(float(por_nivel[str(c)]["f1"]) * int(por_nivel[str(c)]["suporte"]) for c in classes_list)
        / n_total
    )

    return {
        "acuracia": acuracia(yt_norm, yp_norm),
        "macro_precisao": round(macro_prec, 4),
        "macro_recall": round(macro_rec, 4),
        "macro_f1": round(macro_f1, 4),
        "weighted_f1": round(weighted_f1, 4),
        "por_nivel": por_nivel,
        "matriz_confusao": matriz,
    }


# ---------------------------------------------------------------------------
# Correlação, Regressão e Distribuição (Pearson, Spearman, R², Percentis)
# ---------------------------------------------------------------------------


def correlacao_pearson(
    y_true: Sequence[int | float], y_pred: Sequence[int | float]
) -> float:
    """Calcula o coeficiente de correlação linear de Pearson (`r` em [-1, 1])."""
    if len(y_true) != len(y_pred) or len(y_true) < 2:
        return float("nan")
    n = float(len(y_true))
    yt = [float(v) for v in y_true]
    yp = [float(v) for v in y_pred]
    mt = sum(yt) / n
    mp = sum(yp) / n
    cov = sum((t - mt) * (p - mp) for t, p in zip(yt, yp))
    var_t = sum((t - mt) ** 2 for t in yt)
    var_p = sum((p - mp) ** 2 for p in yp)
    if var_t <= 0.0 or var_p <= 0.0:
        return float("nan")
    return round(cov / math.sqrt(var_t * var_p), 4)


def _calcular_postos(valores: Sequence[float]) -> list[float]:
    """Converte uma sequência numérica em postos médios (average ranks para empates)."""
    n = len(valores)
    ordenados = sorted(enumerate(valores), key=lambda par: par[1])
    postos = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and ordenados[j + 1][1] == ordenados[i][1]:
            j += 1
        posto_medio = (i + j + 2) / 2.0
        for k in range(i, j + 1):
            postos[ordenados[k][0]] = posto_medio
        i = j + 1
    return postos


def correlacao_spearman(
    y_true: Sequence[int | float], y_pred: Sequence[int | float]
) -> float:
    """Calcula a correlação de postos de Spearman (`rho` em [-1, 1]) com ajuste de empates."""
    if len(y_true) != len(y_pred) or len(y_true) < 2:
        return float("nan")
    postos_t = _calcular_postos([float(v) for v in y_true])
    postos_p = _calcular_postos([float(v) for v in y_pred])
    return correlacao_pearson(postos_t, postos_p)


def r2_score(
    y_true: Sequence[int | float], y_pred: Sequence[int | float]
) -> float:
    """Calcula o Coeficiente de Determinação (R²)."""
    if len(y_true) != len(y_pred) or len(y_true) < 2:
        return float("nan")
    yt = [float(v) for v in y_true]
    yp = [float(v) for v in y_pred]
    media_t = sum(yt) / len(yt)
    ss_tot = sum((t - media_t) ** 2 for t in yt)
    if ss_tot <= 0.0:
        return float("nan")
    ss_res = sum((t - p) ** 2 for t, p in zip(yt, yp))
    return round(1.0 - (ss_res / ss_tot), 4)


def percentil(valores: Sequence[int | float], p: float) -> float:
    """Calcula o percentil `p` (0 a 100) via interpolação linear."""
    if not valores:
        return float("nan")
    ordenados = sorted(float(v) for v in valores)
    if len(ordenados) == 1:
        return round(ordenados[0], 2)
    p_clamped = max(0.0, min(100.0, float(p)))
    pos = (p_clamped / 100.0) * (len(ordenados) - 1)
    idx_lo = int(math.floor(pos))
    idx_hi = int(math.ceil(pos))
    if idx_lo == idx_hi:
        return round(ordenados[idx_lo], 2)
    frac = pos - idx_lo
    interpolado = ordenados[idx_lo] + frac * (ordenados[idx_hi] - ordenados[idx_lo])
    return round(interpolado, 2)


# ---------------------------------------------------------------------------
# Qualidade Intrínseca de Agentes LLM (Grounding, Alucinação e Feedback)
# ---------------------------------------------------------------------------


def metricas_grounding_evidencias(
    contagens: dict[str, int]
) -> dict[str, float | int]:
    """Calcula taxas de ancoragem textual (grounding) e de alucinação de citações."""
    exata = int(contagens.get("exata", 0))
    aproximada = int(contagens.get("aproximada", 0))
    nao_encontrada = int(contagens.get("nao_encontrada", 0))
    total = exata + aproximada + nao_encontrada
    if total == 0:
        nan = float("nan")
        return {
            "total_evidencias": 0,
            "taxa_grounding_exato": nan,
            "taxa_grounding_total": nan,
            "taxa_alucinacao": nan,
        }
    return {
        "total_evidencias": total,
        "taxa_grounding_exato": round(exata / total, 4),
        "taxa_grounding_total": round((exata + aproximada) / total, 4),
        "taxa_alucinacao": round(nao_encontrada / total, 4),
    }


def avaliar_qualidade_feedback(
    feedback: dict[str, Any] | Any | None,
    redacao: str,
    notas_comp: dict[str, int | None],
) -> dict[str, Any]:
    """Avalia a qualidade intrínseca do `agente_feedback`:
    - `taxa_grounding_reescritas`: proporção de `trecho_original` nas reescritas que
      existem (exata ou aproximadamente) na redação original.
    - `alinhamento_prioridades`: proporção de `prioridades` que apontam para competências
      com defasagem real (nota < 200 e dentro da faixa prioritária de menor nota da redação).
    """
    if feedback is None:
        nan = float("nan")
        return {
            "presente": False,
            "total_reescritas": 0,
            "reescritas_ancoradas": 0,
            "taxa_grounding_reescritas": nan,
            "total_prioridades": 0,
            "prioridades_alinhadas": 0,
            "alinhamento_prioridades": nan,
        }

    fb_dict = (
        feedback.model_dump()
        if hasattr(feedback, "model_dump")
        else (dict(feedback) if isinstance(feedback, dict) else {})
    )

    reescritas = fb_dict.get("reescritas") or []
    ancoradas = 0
    for item in reescritas:
        trecho = item.get("trecho_original", "") if isinstance(item, dict) else ""
        val = validar_trecho(trecho, redacao)
        if val.status in {"exata", "aproximada"}:
            ancoradas += 1

    total_reescritas = len(reescritas)
    taxa_reescritas = (
        round(ancoradas / total_reescritas, 4) if total_reescritas > 0 else float("nan")
    )

    prioridades = fb_dict.get("prioridades") or []
    notas_validas = {
        k.upper(): int(v) for k, v in notas_comp.items() if v is not None
    }
    menor_nota = min(notas_validas.values()) if notas_validas else 200
    # Competências prioritárias: qualquer competência com nota < 200 que esteja até 1 nível (40 pts)
    # acima da menor nota da redação (ou todas se todas tiverem nota 200).
    comps_alvo = {
        comp
        for comp, nota in notas_validas.items()
        if (menor_nota == 200) or (nota < 200 and nota <= menor_nota + 40)
    }

    alinhadas = 0
    for item in prioridades:
        comp_p = (
            str(item.get("competencia", "")).strip().upper()
            if isinstance(item, dict)
            else ""
        )
        if comp_p in comps_alvo:
            alinhadas += 1

    total_prioridades = len(prioridades)
    taxa_alinhamento = (
        round(alinhadas / total_prioridades, 4)
        if total_prioridades > 0
        else float("nan")
    )

    return {
        "presente": True,
        "total_reescritas": total_reescritas,
        "reescritas_ancoradas": ancoradas,
        "taxa_grounding_reescritas": taxa_reescritas,
        "total_prioridades": total_prioridades,
        "prioridades_alinhadas": alinhadas,
        "alinhamento_prioridades": taxa_alinhamento,
    }
