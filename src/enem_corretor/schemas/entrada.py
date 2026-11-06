"""Modelo de entrada do corretor."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class EntradaRedacao(BaseModel):
    """Dados enviados pelo usuário para correção."""

    tema: str = Field(description="Frase-tema da proposta de redação.")
    redacao: str = Field(description="Texto da redação (digitado).")
    motivadores: list[str] = Field(
        default_factory=list, description="Textos motivadores da coletânea (opcional)."
    )
    titulo: str | None = Field(default=None, description="Título (opcional no ENEM).")

    @field_validator("tema", "redacao")
    @classmethod
    def _nao_vazio(cls, valor: str) -> str:
        return valor.strip()
