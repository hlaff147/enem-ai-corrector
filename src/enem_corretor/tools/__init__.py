from .conectivos import AnaliseCoesao, analisar_coesao
from .copia import ResultadoCopia, detectar_copia_motivadores
from .evidencias import validar_evidencias_competencia, validar_trecho
from .gramatica import AlertaGramatical, verificar_gramatica, verificar_heuristicas
from .rubricas import carregar_prompt, carregar_rubrica, rubrica_como_texto
from .texto import (
    EstatisticasTexto,
    analisar_texto,
    estimar_linhas,
    normalizar_texto,
    numerar_paragrafos,
    palavras,
    separar_paragrafos,
    separar_periodos,
)

__all__ = [
    "AlertaGramatical",
    "AnaliseCoesao",
    "EstatisticasTexto",
    "ResultadoCopia",
    "analisar_coesao",
    "analisar_texto",
    "carregar_prompt",
    "carregar_rubrica",
    "detectar_copia_motivadores",
    "estimar_linhas",
    "normalizar_texto",
    "numerar_paragrafos",
    "palavras",
    "rubrica_como_texto",
    "separar_paragrafos",
    "separar_periodos",
    "validar_evidencias_competencia",
    "validar_trecho",
    "verificar_gramatica",
    "verificar_heuristicas",
]
