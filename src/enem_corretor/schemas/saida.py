"""Schemas Pydantic das saídas dos agentes (usados como `output_schema`) e do
resultado final consolidado.

Observação: os campos de análise/raciocínio vêm ANTES da nota em cada schema,
para que o modelo "pense" (checklist → nível → nota) antes de decidir a nota.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

NIVEIS = (0, 40, 80, 120, 160, 200)
COMPETENCIAS = ("C1", "C2", "C3", "C4", "C5")
Competencia = Literal["C1", "C2", "C3", "C4", "C5"]

_DESC_NOTA = "Nota da competência. Use SOMENTE um destes valores: 0, 40, 80, 120, 160, 200."


def ajustar_nivel(valor: int | float | str) -> int:
    """Aproxima qualquer número para o nível válido mais próximo (0–200, passo 40)."""
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return 0
    numero = max(0.0, min(200.0, numero))
    return min(NIVEIS, key=lambda nivel: (abs(nivel - numero), nivel))


# ---------------------------------------------------------------------------
# Blocos comuns
# ---------------------------------------------------------------------------


class Evidencia(BaseModel):
    trecho: str = Field(description="Trecho LITERAL copiado da redação, sem alterações.")
    comentario: str = Field(description="Por que este trecho sustenta a avaliação.")


class _AvaliacaoBase(BaseModel):
    analise: str = Field(
        description=(
            "Raciocínio estruturado: percorra o checklist da competência e compare"
            " com os descritores dos níveis antes de decidir a nota."
        )
    )
    nota: int = Field(description=_DESC_NOTA)
    justificativa: str = Field(
        description="Justificativa final da nota, citando o descritor do nível escolhido."
    )
    evidencias: list[Evidencia] = Field(
        default_factory=list,
        description="Trechos literais da redação que sustentam a nota (2 a 5).",
    )
    pontos_fortes: list[str] = Field(default_factory=list)
    pontos_fracos: list[str] = Field(default_factory=list)

    @field_validator("nota", mode="before")
    @classmethod
    def _nivel_valido(cls, valor: int) -> int:
        return ajustar_nivel(valor)


# ---------------------------------------------------------------------------
# Saídas por competência
# ---------------------------------------------------------------------------


class Desvio(BaseModel):
    trecho: str = Field(description="Trecho LITERAL da redação que contém o desvio.")
    tipo: str = Field(
        description=(
            "Tipo do desvio: ortografia, acentuacao, pontuacao, concordancia_verbal,"
            " concordancia_nominal, regencia, crase, colocacao_pronominal, paralelismo,"
            " registro_informal, escolha_vocabular, estrutura_sintatica,"
            " maiusculas_minusculas ou outro."
        )
    )
    correcao: str = Field(description="Como o trecho ficaria corrigido.")
    explicacao: str = Field(description="Regra gramatical envolvida, em uma frase.")


class AvaliacaoC1(_AvaliacaoBase):
    estrutura_sintatica: str = Field(
        description="Qualidade da estrutura sintática: excelente, boa, regular, deficitaria ou precaria."
    )
    desvios: list[Desvio] = Field(
        default_factory=list, description="Todos os desvios encontrados (um item por ocorrência)."
    )


class Repertorio(BaseModel):
    trecho: str = Field(description="Trecho LITERAL onde o repertório aparece.")
    descricao: str = Field(description="Qual é o repertório (autor, lei, dado, obra, fato...).")
    legitimado: bool = Field(description="É conhecimento verificável e correto?")
    pertinente: bool = Field(description="Relaciona-se ao TEMA (não só ao assunto)?")
    produtivo: bool = Field(description="Está articulado à argumentação (não é só citado)?")
    observacao: str = Field(default="", description="Ex.: imprecisão factual, uso decorado.")


class AvaliacaoC2(_AvaliacaoBase):
    abordagem_tema: str = Field(
        description="'completa', 'tangenciamento' ou 'fuga'. Explique o recorte do tema."
    )
    tangenciamento: bool = Field(description="True se o texto apenas tangencia o tema.")
    tipo_textual_adequado: bool = Field(
        description="False se houver traços constantes de outros tipos textuais."
    )
    tem_introducao: bool
    tem_desenvolvimento: bool
    tem_conclusao: bool
    partes_embrionarias: list[str] = Field(
        default_factory=list, description="Partes presentes mas pouco desenvolvidas."
    )
    copia_motivadores: bool = Field(
        description="True se há cópia de trechos dos textos motivadores."
    )
    repertorios: list[Repertorio] = Field(default_factory=list)


class Argumento(BaseModel):
    trecho: str = Field(description="Trecho LITERAL que enuncia o argumento.")
    desenvolvido: bool = Field(description="O argumento é explicado/fundamentado ou apenas enunciado?")
    comentario: str


class AvaliacaoC3(_AvaliacaoBase):
    tese: str = Field(description="A tese identificada (paráfrase curta) ou '' se ausente.")
    projeto_de_texto: str = Field(description="Avaliação do planejamento e da progressão do texto.")
    argumentos: list[Argumento] = Field(default_factory=list)
    contradicoes: list[str] = Field(default_factory=list)
    autoria: str = Field(description="'autoria', 'indicios_de_autoria' ou 'sem_autoria' + comentário.")


class AvaliacaoC4(_AvaliacaoBase):
    conectivos_interparagrafos: list[str] = Field(
        default_factory=list, description="Conectivos que ligam parágrafos, na ordem."
    )
    diversidade_recursos: str = Field(
        description="'diversificado', 'pouco_diversificado' ou 'limitado'."
    )
    inadequacoes: list[Evidencia] = Field(
        default_factory=list,
        description="Usos inadequados de conectivos/referenciação (trecho literal + explicação).",
    )
    repeticoes: list[str] = Field(
        default_factory=list, description="Palavras/expressões repetidas excessivamente."
    )


ElementoProposta = Literal["agente", "acao", "meio", "finalidade", "detalhamento"]


class ElementoIntervencao(BaseModel):
    elemento: str = Field(
        description="Um de: agente, acao, meio, finalidade, detalhamento."
    )
    trecho: str = Field(description="Trecho LITERAL da redação que contém o elemento.")
    valido: bool = Field(description="False se o elemento for genérico/vago demais.")
    comentario: str = ""


class AvaliacaoC5(_AvaliacaoBase):
    proposta_presente: bool
    elementos: list[ElementoIntervencao] = Field(
        default_factory=list,
        description="Elementos da proposta MAIS completa (um item por elemento).",
    )
    articulada_a_discussao: bool = Field(
        description="A proposta decorre dos problemas discutidos no desenvolvimento?"
    )
    relacionada_ao_tema: bool = Field(
        description="False se a proposta se relaciona apenas ao assunto geral."
    )
    respeita_direitos_humanos: bool


SCHEMAS_COMPETENCIA: dict[str, type[_AvaliacaoBase]] = {
    "C1": AvaliacaoC1,
    "C2": AvaliacaoC2,
    "C3": AvaliacaoC3,
    "C4": AvaliacaoC4,
    "C5": AvaliacaoC5,
}


# ---------------------------------------------------------------------------
# Anulação
# ---------------------------------------------------------------------------


class MotivoAnulacao(BaseModel):
    motivo: str = Field(
        description=(
            "Um de: fuga_ao_tema, tipo_textual, parte_desconectada, improperios,"
            " identificacao, lingua_estrangeira."
        )
    )
    evidencia: str = Field(description="Trecho literal ou descrição objetiva.")
    confianca: str = Field(description="'alta', 'media' ou 'baixa'.")


class ResultadoAnulacao(BaseModel):
    analise: str = Field(description="Verificação item a item dos motivos de anulação.")
    anular: bool = Field(description="True SOMENTE se houver motivo inequívoco.")
    motivos: list[MotivoAnulacao] = Field(default_factory=list)
    alertas: list[str] = Field(
        default_factory=list, description="Situações duvidosas que não justificam anular."
    )


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------


class Prioridade(BaseModel):
    competencia: str = Field(description="C1, C2, C3, C4 ou C5.")
    problema: str
    como_melhorar: str


class Reescrita(BaseModel):
    competencia: str
    trecho_original: str = Field(description="Trecho LITERAL da redação.")
    sugestao: str = Field(description="Versão reescrita do trecho.")
    explicacao: str


class Feedback(BaseModel):
    resumo: str = Field(description="Parágrafo curto com a visão geral do desempenho.")
    pontos_fortes: list[str] = Field(default_factory=list)
    prioridades: list[Prioridade] = Field(
        default_factory=list, description="Até 5 melhorias, da mais para a menos impactante."
    )
    reescritas: list[Reescrita] = Field(
        default_factory=list, description="2 a 4 exemplos de reescrita de trechos."
    )
    checklist_proxima_redacao: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Resultado final consolidado (montado em Python, não pelo LLM)
# ---------------------------------------------------------------------------


class ValidacaoEvidencia(BaseModel):
    trecho: str
    status: Literal["exata", "aproximada", "nao_encontrada"]


class ResultadoCompetencia(BaseModel):
    competencia: Competencia
    nota: int
    nota_modelo: int | None = Field(description="Nota original dada pelo agente LLM.")
    ajustes: list[str] = Field(default_factory=list, description="Regras aplicadas pelo consolidador.")
    justificativa: str = ""
    avaliacao: dict | None = Field(default=None, description="Saída completa do agente.")
    evidencias_validadas: list[ValidacaoEvidencia] = Field(default_factory=list)


class AvaliacaoFinal(BaseModel):
    tema: str
    anulada: bool
    motivos_anulacao: list[str] = Field(default_factory=list)
    competencias: dict[str, ResultadoCompetencia] = Field(default_factory=dict)
    nota_total: int
    alertas: list[str] = Field(default_factory=list)
    preanalise: dict = Field(default_factory=dict)
    feedback: Feedback | None = None
    modelo: str = ""
    rubrica_ano_referencia: int | None = None
    rubrica_verificada: bool = False
    gerado_em: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
