# 03 — Contrato Formal do Session State

> **Data:** 2026-11-07  
> **Escopo:** Especificação formal do Session State no Google ADK, eliminação de strings mágicas, catálogo de chaves tipadas, schemas de payload e matriz de controle de acesso (leitura/escrita).

---

## 1. Princípios do Contrato de Estado

1. **Catálogo Único Tipado:** Toda chave usada no `ctx.session.state` deve ser declarada como uma constante no módulo `src/enem_corretor/state_keys.py`. O uso de literais de string inline (`"avaliacao_c1"`, `"entrada"`) é estritamente proibido.
2. **Schema Pydantic por Chave:** O payload associado a cada chave possui um schema de validação explícito. O produtor deve garantir que o valor gravado seja válido contra o schema.
3. **Imutabilidade e Idempotência:** Uma etapa que conclui sua execução não deve ter seu payload sobrescrito por etapas subsequentes. No início de cada ciclo, as chaves de saída são explicitamente limpas.
4. **Princípio do Menor Privilégio (Context Isolation):** Sub-agentes não devem ter visibilidade indiscriminada do estado global. O `before_model_callback` filtra e formata estritamente as chaves necessárias para cada agente.

---

## 2. Catálogo de Chaves (`StateKeys`)

Módulo proposto: `src/enem_corretor/state_keys.py`

```python
from __future__ import annotations
from enum import StrEnum

class StateKeys(StrEnum):
    """Catálogo central de chaves do Session State do Corretor ENEM."""
    ENTRADA = "entrada"
    PREANALISE = "preanalise"
    ANULACAO_LLM = "anulacao_llm"
    AVALIACAO_C1 = "avaliacao_c1"
    AVALIACAO_C2 = "avaliacao_c2"
    AVALIACAO_C3 = "avaliacao_c3"
    AVALIACAO_C4 = "avaliacao_c4"
    AVALIACAO_C5 = "avaliacao_c5"
    AVALIACAO_CONSOLIDADA = "avaliacao_consolidada"
    FEEDBACK = "feedback"
    AVALIACAO_FINAL = "avaliacao_final"
    RELATORIO_MARKDOWN = "relatorio_markdown"
```

---

## 3. Matriz de Produtores, Consumidores e Permissões

| Chave de Estado | Tipo do Payload / Schema | Produtor Responsável | Consumidores Autorizados | Momento do Ciclo |
|---|---|---|---|---|
| `StateKeys.ENTRADA` | `EntradaRedacao` (`dict`) | Runner / `IntakeOrchestrator` | `executar_preanalise`, `before_model_callback`, `ConsolidationJudge` | Inicialização / Input |
| `StateKeys.PREANALISE` | `dict` com métricas determinísticas | `executar_preanalise` | Gate de Anulação, `before_model_callback`, `ConsolidationJudge` | Fase 1 (Pré-análise) |
| `StateKeys.ANULACAO_LLM` | `ResultadoAnulacao` (`dict`) | `agente_anulacao` | Gate de Anulação Semântica, `ConsolidationJudge` | Fase 2 (Elegibilidade) |
| `StateKeys.AVALIACAO_C1` | `ResultadoC1` (`dict`) | `agente_c1` | `CompetencyPanel`, `ConsolidationJudge` | Fase 3 (Competências) |
| `StateKeys.AVALIACAO_C2` | `ResultadoC2` (`dict`) | `agente_c2` | `CompetencyPanel`, `ConsolidationJudge` | Fase 3 (Competências) |
| `StateKeys.AVALIACAO_C3` | `ResultadoC3` (`dict`) | `agente_c3` | `CompetencyPanel`, `ConsolidationJudge` | Fase 3 (Competências) |
| `StateKeys.AVALIACAO_C4` | `ResultadoC4` (`dict`) | `agente_c4` | `CompetencyPanel`, `ConsolidationJudge` | Fase 3 (Competências) |
| `StateKeys.AVALIACAO_C5` | `ResultadoC5` (`dict`) | `agente_c5` | `CompetencyPanel`, `ConsolidationJudge` | Fase 3 (Competências) |
| `StateKeys.AVALIACAO_CONSOLIDADA` | `dict` (notas + alertas + tetos) | `ConsolidationJudge` | `before_model_callback` (Feedback), `Finalizer` | Fase 4 (Consolidação) |
| `StateKeys.FEEDBACK` | `Feedback` (`dict`) | `agente_feedback` | `Finalizer` | Fase 5 (Feedback) |
| `StateKeys.AVALIACAO_FINAL` | `AvaliacaoFinal` (`dict`) | `Finalizer` / Orquestrador | Runner externo, API de saída, histórico | Fase 6 (Finalização) |
| `StateKeys.RELATORIO_MARKDOWN` | `str` | `Finalizer` / Orquestrador | Evento de saída ao usuário (CLI / Web) | Fase 6 (Finalização) |

---

## 4. Ciclo de Vida e Limpeza do Estado

No início da execução de cada redação (`_run_async_impl`), o orquestrador emite um evento de reset para garantir que execuções subsequentes na mesma sessão não reutilizem dados corrompidos ou obsoletos:

```python
RESET_STATE_DELTA: dict[str, None] = {
    StateKeys.ANULACAO_LLM: None,
    StateKeys.AVALIACAO_C1: None,
    StateKeys.AVALIACAO_C2: None,
    StateKeys.AVALIACAO_C3: None,
    StateKeys.AVALIACAO_C4: None,
    StateKeys.AVALIACAO_C5: None,
    StateKeys.AVALIACAO_CONSOLIDADA: None,
    StateKeys.FEEDBACK: None,
    StateKeys.AVALIACAO_FINAL: None,
    StateKeys.RELATORIO_MARKDOWN: None,
}
```

---

## 5. Função de Acesso Seguro (State Helpers)

Para evitar acessos manuais via dicionário fraco, o módulo `state_keys.py` fornecerá helpers tipados:

```python
def obter_entrada(state: dict[str, Any]) -> EntradaRedacao | None: ...
def obter_preanalise(state: dict[str, Any]) -> dict[str, Any]: ...
def obter_resultado_anulacao(state: dict[str, Any]) -> ResultadoAnulacao | None: ...
def obter_avaliacao_competencia(state: dict[str, Any], comp: str) -> dict[str, Any] | None: ...
def obter_avaliacao_final(state: dict[str, Any]) -> AvaliacaoFinal | None: ...
```

Essas funções garantem validação centralizada e mensagens de erro legíveis caso alguma chave esteja ausente ou corrompida.
