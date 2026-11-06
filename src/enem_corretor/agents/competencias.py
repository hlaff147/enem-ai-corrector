"""Etapa 3 — Agentes avaliadores das 5 competências do ENEM (C1 a C5)."""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.models.base_llm import BaseLlm

from ..config import Config, carregar_config
from ..schemas.saida import COMPETENCIAS, SCHEMAS_COMPETENCIA
from .comum import (
    callback_contexto_redacao,
    construir_generate_config,
    construir_modelo,
    instrucao_com_rubrica,
)

DESCRICOES_COMPETENCIA: dict[str, str] = {
    "C1": "Avalia a Competência 1 (domínio da modalidade escrita formal da língua portuguesa).",
    "C2": "Avalia a Competência 2 (compreensão do tema, estrutura dissertativo-argumentativa e repertório).",
    "C3": "Avalia a Competência 3 (projeto de texto, seleção e desenvolvimento de argumentos).",
    "C4": "Avalia a Competência 4 (mecanismos linguísticos de coesão e articulação argumentativa).",
    "C5": "Avalia a Competência 5 (proposta de intervenção com 5 elementos e respeito aos direitos humanos).",
}


def criar_agente_competencia(
    competencia: str,
    cfg: Config | None = None,
    modelo_override: BaseLlm | str | None = None,
) -> LlmAgent:
    comp = competencia.upper()
    if comp not in SCHEMAS_COMPETENCIA:
        raise ValueError(f"Competência inválida: {competencia}")

    cfg = cfg or carregar_config()
    codigo_lower = comp.lower()
    return LlmAgent(
        name=f"agente_{codigo_lower}",
        description=DESCRICOES_COMPETENCIA[comp],
        model=construir_modelo(cfg, modelo_override),
        instruction=instrucao_com_rubrica(codigo_lower, codigo_lower),
        generate_content_config=construir_generate_config(cfg),
        output_schema=SCHEMAS_COMPETENCIA[comp],
        output_key=f"avaliacao_{codigo_lower}",
        include_contents="none",
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
        before_model_callback=callback_contexto_redacao(incluir_avaliacao=False),
    )


def criar_agentes_competencias(
    cfg: Config | None = None,
    modelo_override: BaseLlm | str | None = None,
) -> dict[str, LlmAgent]:
    return {
        comp: criar_agente_competencia(comp, cfg=cfg, modelo_override=modelo_override)
        for comp in COMPETENCIAS
    }
