"""Fixtures compartilhadas para as suítes de testes unitários, de componente e de integração."""

from __future__ import annotations

import json
from typing import Any

import pytest
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types

REDACAO_COMPLETA = (
    'Na obra "Os Sertões", Euclides da Cunha retrata a marginalização das populações '
    "do interior brasileiro. Fora da ficção, essa invisibilidade perdura na atualidade, "
    "haja vista os entraves para valorizar as comunidades e os povos tradicionais no Brasil. "
    "Nesse contexto, tanto a negligência estatal quanto o desconhecimento social agravam o problema.\n\n"
    "Em primeira análise, a atuação insuficiente do Poder Público fragiliza a sobrevivência "
    "dos povos originários e quilombolas. Embora a Constituição Federal de 1988 assegure a "
    "proteção territorial, a fiscalização precária impede que esse direito se concretize.\n\n"
    "Ademais, a formação educacional eurocêntrica alimenta o preconceito contra os saberes "
    "tradicionais. Consequentemente, a sociedade deixa de reconhecer que indígenas e ribeirinhos "
    "são fundamentais para a conservação da biodiversidade nacional.\n\n"
    "Portanto, cabe ao Ministério dos Povos Indígenas, em parceria com o Ministério da Educação, "
    "ampliar a fiscalização das terras demarcadas e criar projetos pedagógicos interculturais nas "
    "escolas, por meio de verbas públicas e oficinas com lideranças locais, a fim de garantir a "
    "cidadania plena dessas populações."
)


class FakeEnemLlm(BaseLlm):
    """Modelo ADK determinístico e configurável para testes de componente e integração."""

    model: str = "fake-enem-llm"
    tangenciar: bool = False
    anular_por_fuga: bool = False
    elementos_c5_validos: int = 5
    violar_dh: bool = False
    proposta_presente: bool = True
    relacionada_ao_tema: bool = True
    articulada_a_discussao: bool = True
    tipo_textual_adequado: bool = True
    copia_motivadores_flag: bool = False
    falhar_schemas: dict[str, int] = {}
    """Mapeia nome do schema -> quantas vezes deve levantar exceção antes de responder."""

    async def generate_content_async(self, llm_request, stream=False):
        schema = llm_request.config.response_schema
        nome_schema = getattr(schema, "__name__", "")

        restantes = self.falhar_schemas.get(nome_schema, 0)
        if restantes > 0:
            self.falhar_schemas[nome_schema] = restantes - 1
            raise RuntimeError(f"Falha simulada para {nome_schema}")

        texto_user = llm_request.contents[0].parts[0].text
        assert "<redacao>" in texto_user
        assert "<tema>" in texto_user

        payload = self._montar_payload(nome_schema, texto_user)
        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part(text=json.dumps(payload, ensure_ascii=False))],
            )
        )

    def _montar_payload(self, nome_schema: str, texto_user: str) -> dict[str, Any]:
        if nome_schema == "ResultadoAnulacao":
            return {
                "analise": "Verificação completa.",
                "anular": self.anular_por_fuga,
                "motivos": (
                    [
                        {
                            "motivo": "fuga_ao_tema",
                            "evidencia": "O texto não aborda nem o assunto nem o tema.",
                            "confianca": "alta",
                        }
                    ]
                    if self.anular_por_fuga
                    else []
                ),
                "alertas": ["Alerta semântico de teste"],
            }
        if nome_schema == "AvaliacaoC1":
            return {
                "analise": "Boa estrutura sintática e domínio formal.",
                "nota": 160,
                "justificativa": "Bom domínio da modalidade escrita formal.",
                "evidencias": [
                    {
                        "trecho": "Embora a Constituição Federal de 1988 assegure",
                        "comentario": "Uso correto de subordinação concessiva.",
                    }
                ],
                "pontos_fortes": ["Boa pontuação"],
                "pontos_fracos": [],
                "estrutura_sintatica": "boa",
                "desvios": [
                    {
                        "trecho": "fiscalização precária impede",
                        "tipo": "pontuacao",
                        "correcao": "a fiscalização precária impede",
                        "explicacao": "Exemplo de desvio para relatório.",
                    }
                ],
            }
        if nome_schema == "AvaliacaoC2":
            return {
                "analise": "Análise temática e de repertório.",
                "nota": 200,
                "justificativa": "Repertório produtivo.",
                "evidencias": [
                    {
                        "trecho": 'Na obra "Os Sertões", Euclides da Cunha retrata',
                        "comentario": "Repertório literário produtivo.",
                    }
                ],
                "pontos_fortes": ["Repertório legitimado"],
                "pontos_fracos": [],
                "abordagem_tema": "tangenciamento" if self.tangenciar else "completa",
                "tangenciamento": self.tangenciar,
                "tipo_textual_adequado": self.tipo_textual_adequado,
                "tem_introducao": True,
                "tem_desenvolvimento": True,
                "tem_conclusao": True,
                "partes_embrionarias": [],
                "copia_motivadores": self.copia_motivadores_flag,
                "repertorios": [
                    {
                        "trecho": 'Na obra "Os Sertões", Euclides da Cunha retrata',
                        "descricao": "Os Sertões, de Euclides da Cunha",
                        "legitimado": True,
                        "pertinente": True,
                        "produtivo": True,
                        "observacao": "",
                    }
                ],
            }
        if nome_schema == "AvaliacaoC3":
            return {
                "analise": "Projeto de texto estratégico.",
                "nota": 160,
                "justificativa": "Argumentos bem relacionados em defesa da tese.",
                "evidencias": [
                    {
                        "trecho": "tanto a negligência estatal quanto o desconhecimento social",
                        "comentario": "Tese clara com dois eixos.",
                    }
                ],
                "pontos_fortes": ["Tese explícita"],
                "pontos_fracos": [],
                "tese": "Negligência estatal e desconhecimento social.",
                "projeto_de_texto": "Claro e progressivo.",
                "argumentos": [
                    {
                        "trecho": "atuação insuficiente do Poder Público fragiliza",
                        "desenvolvido": True,
                        "comentario": "Fundamentado com a CF/88.",
                    }
                ],
                "contradicoes": [],
                "autoria": "autoria",
            }
        if nome_schema == "AvaliacaoC4":
            return {
                "analise": "Bom uso de conectivos inter e intraparágrafos.",
                "nota": 200,
                "justificativa": "Repertório diversificado de recursos coesivos.",
                "evidencias": [
                    {
                        "trecho": "Em primeira análise, a atuação insuficiente",
                        "comentario": "Operador interparágrafo adequado.",
                    }
                ],
                "pontos_fortes": ["Conectivos variados"],
                "pontos_fracos": [],
                "conectivos_interparagrafos": ["Em primeira análise", "Ademais", "Portanto"],
                "diversidade_recursos": "diversificado",
                "inadequacoes": [],
                "repeticoes": [],
            }
        if nome_schema == "AvaliacaoC5":
            nomes_el = ["agente", "acao", "meio", "finalidade", "detalhamento"]
            elementos = [
                {
                    "elemento": nome,
                    "trecho": "cabe ao Ministério dos Povos Indígenas",
                    "valido": idx < self.elementos_c5_validos,
                    "comentario": "ok",
                }
                for idx, nome in enumerate(nomes_el)
            ]
            return {
                "analise": "Verificação dos 5 elementos.",
                "nota": 200,
                "justificativa": "Proposta avaliada.",
                "evidencias": [
                    {
                        "trecho": "cabe ao Ministério dos Povos Indígenas",
                        "comentario": "Agente explícito.",
                    }
                ],
                "pontos_fortes": ["Proposta clara"],
                "pontos_fracos": [],
                "proposta_presente": self.proposta_presente,
                "elementos": elementos,
                "articulada_a_discussao": self.articulada_a_discussao,
                "relacionada_ao_tema": self.relacionada_ao_tema,
                "respeita_direitos_humanos": not self.violar_dh,
            }
        if nome_schema == "Feedback":
            assert "<avaliacao_consolidada>" in texto_user
            return {
                "resumo": "Excelente desempenho geral.",
                "pontos_fortes": ["Repertório pertinente e coesão consistente."],
                "prioridades": [
                    {
                        "competencia": "C3",
                        "problema": "Aprofundar exemplo do segundo parágrafo.",
                        "como_melhorar": "Apresentar dado concreto sobre demarcações.",
                    }
                ],
                "reescritas": [
                    {
                        "competencia": "C1",
                        "trecho_original": "fiscalização precária impede",
                        "sugestao": "a precariedade da fiscalização governamental impede",
                        "explicacao": "Maior precisão nominal.",
                    }
                ],
                "checklist_proxima_redacao": ["Revisar os 5 elementos da C5."],
            }
        raise AssertionError(f"Schema inesperado: {nome_schema}")


@pytest.fixture
def redacao_completa() -> str:
    return REDACAO_COMPLETA
