# 00 — Baseline Obrigatório Pré-Refatoração

> **Data de Medição:** 2026-11-07  
> **Repositório:** `enem-ai-corrector` (`enem_corretor`)  
> **Objetivo:** Estabelecer a linha de base empírica e reproduzível (testes, cobertura, métricas AES, orçamento de chamadas e latência) antes do início da refatoração da hierarquia de agentes e sub-agentes.

---

## 1. Identificação do Ambiente e Versões

| Parâmetro | Valor Registrado | Evidência / Comando |
|---|---|---|
| **Git Commit** | `a110591bf84d910a33b946c413fb31b4de57c9a4` | `git log -1 --format="%H"` |
| **Data do Commit** | `2026-11-07 00:27:07 -0300` | `git log -1 --format="%ci"` |
| **Branch** | `main` (working tree limpo) | `git status` |
| **Python** | `3.12.16` | `python --version` |
| **Sistema Operacional** | `macOS` (Darwin arm64) | `uname -sm` |
| **google-adk** | `2.13.0` | `pip show google-adk` |
| **litellm** | `1.81.3` | `pip show litellm` |
| **pydantic** | `2.12.5` | `pip show pydantic` |
| **pytest / pytest-cov** | `pytest 9.2.0` / `pytest-cov 7.1.0` | `pytest --version` |

---

## 2. Execução da Suíte de Testes e Cobertura

### 2.1 Comando de Execução
```bash
.venv/bin/pytest --cov=enem_corretor --cov-branch --cov-report=term-missing
```

### 2.2 Resumo dos Resultados
- **Total de testes:** 19
- **Aprovados:** 19 (100%)
- **Falhas / Erros:** 0
- **Tempo de execução:** ~2.52 segundos

### 2.3 Relatório Detalhado de Cobertura de Código

| Módulo | Stmts | Miss | Branch | BrPart | Cobertura (%) |
|---|---:|---:|---:|---:|---:|
| `src/enem_corretor/__init__.py` | 56 | 3 | 16 | 6 | 88% |
| `src/enem_corretor/agent.py` | 26 | 0 | 2 | 0 | **100%** |
| `src/enem_corretor/agents/__init__.py` | 7 | 0 | 0 | 0 | **100%** |
| `src/enem_corretor/agents/anulacao.py` | 9 | 0 | 0 | 0 | **100%** |
| `src/enem_corretor/agents/competencias.py` | 16 | 0 | 2 | 0 | **100%** |
| `src/enem_corretor/agents/comum.py` | 68 | 0 | 14 | 1 | **99%** |
| `src/enem_corretor/agents/consolidador.py` | 187 | 2 | 110 | 12 | **95%** |
| `src/enem_corretor/agents/feedback.py` | 9 | 0 | 0 | 0 | **100%** |
| `src/enem_corretor/agents/orquestrador.py` | 134 | 12 | 38 | 2 | **88%** |
| `src/enem_corretor/agents/preanalise.py` | 56 | 0 | 22 | 1 | **99%** |
| `src/enem_corretor/config.py` | 49 | 0 | 2 | 0 | **100%** |
| `src/enem_corretor/eval/__init__.py` | 3 | 0 | 0 | 0 | **100%** |
| `src/enem_corretor/eval/metricas.py` | 98 | 3 | 42 | 3 | **96%** |
| `src/enem_corretor/eval/run_eval.py` | 78 | 2 | 18 | 3 | **95%** |
| `src/enem_corretor/schemas/__init__.py` | 3 | 0 | 0 | 0 | **100%** |
| `src/enem_corretor/schemas/entrada.py` | 11 | 0 | 0 | 0 | **100%** |
| `src/enem_corretor/schemas/saida.py` | 144 | 0 | 4 | 0 | **100%** |
| `src/enem_corretor/tools/__init__.py` | 7 | 0 | 0 | 0 | **100%** |
| `src/enem_corretor/tools/conectivos.py` | 50 | 0 | 16 | 0 | **100%** |
| `src/enem_corretor/tools/copia.py` | 39 | 0 | 16 | 0 | **100%** |
| `src/enem_corretor/tools/evidencias.py` | 59 | 2 | 38 | 6 | **92%** |
| `src/enem_corretor/tools/gramatica.py` | 44 | 0 | 8 | 0 | **100%** |
| `src/enem_corretor/tools/rubricas.py` | 22 | 0 | 0 | 0 | **100%** |
| `src/enem_corretor/tools/texto.py` | 70 | 0 | 12 | 0 | **100%** |
| **TOTAL GERAL** | **1245** | **24** | **360** | **34** | **96.01%** |

- **Meta de cobertura do projeto:** ≥ 90.00%
- **Status atual:** Superada com folga (**96.01%** combinado).

---

## 3. Orçamento e Perfil de Chamadas ao LLM

O pipeline atual possui três perfis de execução com respeito ao consumo de chamadas de LLM:

| Cenário de Execução | Agentes Acionados | Chamadas LLM (Mínimo / Normal) | Chamadas LLM (Pior Caso c/ Retries) | Observação |
|---|---|---:|---:|---|
| **1. Anulação Determinística** (texto < 7 linhas, folha em branco, cópia massiva) | Apenas pré-análise e consolidador | **0 chamadas** | **0 chamadas** | Curto-circuito imediato sem gastar cota de API |
| **2. Anulação Semântica** (fuga total ao tema, não atendimento ao tipo textual) | `agente_anulacao` detecta anulação | **1 chamada** | **1 chamada** | Curto-circuito após etapa de conformidade |
| **3. Fluxo Completo Normal** (redação válida) | `agente_anulacao` + `C1` a `C5` + `agente_feedback` | **7 chamadas** | **12 chamadas** | 1 (anulação) + 5 (competências) + 1 (feedback); até 2 tentativas por competência em caso de falha |

---

## 4. Avaliação em Dataset de Amostra / Stress Set

Executado via CLI de avaliação:
```bash
.venv/bin/enem-corretor-eval --dataset data/exemplos/stress_set_amostra.jsonl --out runs/baseline_refactor
```

### Resultados Obtidos
1. **Redação SYN-03 (Texto insuficiente, < 7 linhas):**
   - **Latência:** 2 ms
   - **Chamadas LLM:** 0
   - **Classificação:** Anulada com motivo `texto_insuficiente`
   - **Notas:** C1=0, C2=0, C3=0, C4=0, C5=0, Total=0
   - **Concordância com rótulo humano/esperado:** 100% exata
2. **Redação SYN-01 (Redação completa dissertativa-argumentativa):**
   - **Comportamento em ambiente sandbox sem chave de API externa:**
     - Falha de conexão/chave tratada graciosamente com log de warning.
     - Sistema não quebrou por exceção não tratada (`fail-safe`).
     - Estrutura de consolidação gerou relatório parcial sem crash.

---

## 5. Critérios de Não-Regressão para a Refatoração

Durante e após a refatoração, as seguintes garantias devem ser preservadas:
1. **Suíte de testes:** 100% dos testes devem continuar passando (mínimo 19 testes).
2. **Cobertura de código:** Cobertura combinada (linhas + ramos) deve permanecer ≥ 90% (meta: manter no patamar de ~96%).
3. **Orçamento de chamadas:**
   - 0 chamadas para anulação determinística.
   - 1 chamada para anulação semântica.
   - ≤ 7 chamadas no caminho feliz completo.
4. **Interface pública:** `root_agent`, `corrigir_redacao`, `corrigir_redacao_async`, `criar_corretor_agent` e CLI devem manter assinaturas idênticas.
5. **Regras de domínio (R-01 a R-12):** Nenhuma regra de teto, penalidade ou evidência pode ser afrouxada ou alterada.
