# 04 — Plano de Migração Incremental (Step-by-Step)

> **Data:** 2026-11-07  
> **Estratégia:** Strangler Fig com passos atômicos. Cada passo é commitável, não quebra a suíte existente (`pytest`), mantém cobertura ≥ 90% e possui critério de rollback imediato.

---

## 1. Princípios de Execução

1. **Testes sempre verdes:** Ao final de cada passo, `pytest --cov=enem_corretor --cov-branch` deve passar com 100% de sucesso e cobertura ≥ 90%.
2. **Interface externa imutável:** Nenhuma assinatura de `root_agent`, `corrigir_redacao`, `corrigir_redacao_async` ou `criar_corretor_agent` pode sofrer breaking changes.
3. **Rollback atômico:** Se um passo introduzir falha ou regressão insolúvel, ele é revertido imediatamente via `git checkout` antes de qualquer outra modificação.

---

## 2. Roteiro Passo a Passo

```mermaid
flowchart LR
    P0["Passo 0: state_keys.py"] --> P1["Passo 1: Intake & State"]
    P1 --> P2["Passo 2: EligibilityCoordinator"]
    P2 --> P3["Passo 3: CompetencyPanel"]
    P3 --> P4["Passo 4: Consolidador State"]
    P4 --> P5["Passo 5: Feedback Isolado"]
    P5 --> P6["Passo 6: Orquestrador Limpo"]
    P6 --> P7["Passo 7: Verificação & Regressão"]
```

---

### Passo 0: Criação do Catálogo de Estado (`state_keys.py`)
- **Objetivo:** Estabelecer a fonte única da verdade para nomes de chaves e helpers de acesso tipado.
- **Arquivos Criados/Modificados:**
  - `src/enem_corretor/state_keys.py` (novo)
  - `tests/unit/test_unit_state_keys.py` (novo)
- **Verificação:** Executar `pytest tests/unit/test_unit_state_keys.py`.
- **Critério de Aceitação:** Cobertura de 100% no novo módulo; zero strings mágicas necessárias.
- **Critério de Rollback:** Remover os arquivos criados.

---

### Passo 1: Migração do Intake, Pré-análise e Callbacks para `StateKeys`
- **Objetivo:** Adotar `StateKeys` em `preanalise.py` e `comum.py` (`callback_contexto_redacao` e `montar_xml_entrada`).
- **Arquivos Modificados:**
  - `src/enem_corretor/agents/preanalise.py`
  - `src/enem_corretor/agents/comum.py`
- **Verificação:** Executar `pytest tests/unit/`.
- **Critério de Aceitação:** Suíte unitária 100% verde; isolamento de XML preservado contra prompt injection (`ADV-03`).
- **Critério de Rollback:** Reverter alterações em `preanalise.py` e `comum.py`.

---

### Passo 2: Isolamento da Elegibilidade e Curto-Circuito (`EligibilityCoordinator`)
- **Objetivo:** Encapsular a triagem em duas fases (Gate 1 determinístico e Gate 2 semântico com `agente_anulacao`) em um coordenador coeso com contrato explícito.
- **Arquivos Criados/Modificados:**
  - `src/enem_corretor/agents/anulacao.py` (ou `elegibilidade.py`)
  - `tests/unit/test_unit_anulacao.py`
- **Verificação:** Executar `pytest tests/unit/`.
- **Critério de Aceitação:** Curto-circuito confirmado com 0 chamadas para textos inválidos e 1 chamada para fuga ao tema.
- **Critério de Rollback:** Reverter commits do Passo 2.

---

### Passo 3: Criação do Painel de Especialistas (`CompetencyPanelCoordinator`)
- **Objetivo:** Reorganizar a avaliação C1 a C5 em um painel coordenado que gerencie:
  1. Concorrência controlada (compatível com a API do ADK 2.13.0).
  2. Validação individual do schema de cada competência.
  3. Loop de retentativa isolado apenas para competências que falharem.
- **Arquivos Criados/Modificados:**
  - `src/enem_corretor/agents/competencias.py`
  - `tests/unit/test_unit_competencias.py`
- **Verificação:** Executar `pytest tests/unit/` e `tests/component/`.
- **Critério de Aceitação:** Falha em uma competência dispara retry sem reexecutar as demais que tiveram sucesso.
- **Critério de Rollback:** Reverter commits do Passo 3.

---

### Passo 4: Atualização do Consolidador para Consumir o Contrato Tipado
- **Objetivo:** Fazer `consolidar_avaliacao` ler o estado através de `StateKeys` e helpers tipados, aplicando as regras de teto (R-01 a R-07) e validação literal de evidências (R-08).
- **Arquivos Modificados:**
  - `src/enem_corretor/agents/consolidador.py`
  - `tests/component/test_component_consolidador_preanalise.py`
- **Verificação:** Executar `pytest tests/component/`.
- **Critério de Aceitação:** Todos os testes de regras de teto e validação de evidências aprovados.
- **Critério de Rollback:** Reverter alterações em `consolidador.py`.

---

### Passo 5: Modularização do Agente de Feedback
- **Objetivo:** Garantir que `agente_feedback` opere exclusivamente com base no payload da avaliação consolidada, com proteção contra feedback em redações anuladas.
- **Arquivos Modificados:**
  - `src/enem_corretor/agents/feedback.py`
- **Verificação:** Executar `pytest tests/`.
- **Critério de Aceitação:** Sub-agente gera schema `Feedback` estrito e não executa em redações com nota zero.
- **Critério de Rollback:** Reverter alterações em `feedback.py`.

---

### Passo 6: Refatoração do Orquestrador Raiz (`CorretorEnemAgent`)
- **Objetivo:** Limpar a classe `CorretorEnemAgent` em `orquestrador.py`, reduzindo sua complexidade ciclomática ao compor os coordenadores e passos das fases anteriores.
- **Arquivos Modificados:**
  - `src/enem_corretor/agents/orquestrador.py`
  - `src/enem_corretor/agent.py`
- **Verificação:** Executar `pytest tests/integration/`.
- **Critério de Aceitação:** O orquestrador atua como fachada limpa; código reduzido e altamente legível; testes de integração 100% verdes.
- **Critério de Rollback:** Reverter alterações em `orquestrador.py`.

---

### Passo 7: Validação Completa, Testes de Regressão e Benchmark AES
- **Objetivo:** Rodar a suíte completa de testes unitários, de componentes e de integração, gerando o relatório final de cobertura e comparando com o baseline.
- **Comandos de Verificação:**
  1. `pytest --cov=enem_corretor --cov-branch --cov-report=term-missing` (cobertura ≥ 90%)
  2. `enem-corretor-eval --dataset data/exemplos/stress_set_amostra.jsonl --out runs/baseline_refactor_pos`
- **Critério de Aceitação:**
  - 100% dos testes passando.
  - Cobertura de código ≥ 90% (mantendo o patamar de ~96%).
  - Orçamento de chamadas e latência cumpridos.
  - Zero quebras de retrocompatibilidade.

---

## 3. Ponto de Parada Obrigatório

> [!IMPORTANT]
> A execução da **Etapa B (Passos 0 a 7)** só começará após a revisão e a **aprovação explícita** do usuário sobre esta proposta arquitetural e o plano de migração.
