# Corretor de Redação ENEM com Google ADK

Corretor local de redações do ENEM nas **5 competências oficiais (C1 a C5)** construído sobre o **Google ADK (Agent Development Kit)**, schemas estruturados em **Pydantic v2**, ferramentas determinísticas de pré-análise/validação e suporte nativo tanto ao **Gemini Free Tier (Google AI Studio)** quanto a modelos locais via **Ollama / LiteLLM**.

> [!IMPORTANT]
> Este sistema é uma ferramenta de estudo e apoio pedagógico; não substitui corretores humanos nem garante a nota oficial atribuída pelo INEP. As rubricas em `rubricas/*.yaml` trazem `verificado: false` até que você as confira com a Cartilha do Participante do ano vigente.

---

## 1. Visão Geral da Arquitetura

O sistema combina **etapas determinísticas em Python** (para tarefas em que LLMs puros costumam falhar, como contagem exata de linhas, sobreposição de $n$-gramas com textos motivadores, catálogo de conectivos, regras de teto entre competências e verificação literal de citações) com **agentes especializados no Google ADK** (`LlmAgent` e `ParallelAgent`), coordenados pelo orquestrador customizado `CorretorEnemAgent` (`BaseAgent`).

```mermaid
flowchart TD
    U(["Entrada do Usuário (Tema + Redação + Motivadores)"]) --> E["Parser de Entrada (JSON / Marcadores / Texto)"]
    E --> P["[1] Pré-análise Determinística (agents/preanalise.py)"]

    subgraph Tools["Ferramentas Determinísticas (tools/)"]
        T1["texto.py: Parágrafos, Períodos e Linhas Estimadas"]
        T2["copia.py: Detecção de Cópia por 7-gramas"]
        T3["conectivos.py: Conectivos Intra/Interparágrafos e Repetições"]
        T4["gramatica.py: Heurísticas PT-BR + LanguageTool opcional"]
    end

    P <--> Tools
    P --> D1{"Anulação Determinística? (< 8 linhas / em branco / cópia massiva)"}
    D1 -- "Sim (Curto-circuito)" --> Z["Consolidador: Nota 0 + Motivo"]

    D1 -- "Não" --> A2["[2] Agente de Anulação Semântica (agente_anulacao / ResultadoAnulacao)"]
    A2 --> D2{"Anular por Fuga / Tipo Textual / Impropérios / Identificação?"}
    D2 -- "Sim (Curto-circuito)" --> Z

    D2 -- "Não" --> PARALLEL["[3] Avaliação por Competência (ParallelAgent ou Sequencial c/ Retry)"]

    subgraph Comp["Agentes Especialistas (agents/competencias.py)"]
        C1["agente_c1: Norma-padrão e Sintaxe (AvaliacaoC1)"]
        C2["agente_c2: Tema, Tipo e Repertório (AvaliacaoC2)"]
        C3["agente_c3: Projeto de Texto e Argumentos (AvaliacaoC3)"]
        C4["agente_c4: Coesão e Conectivos (AvaliacaoC4)"]
        C5["agente_c5: Proposta (5 Elementos + DH) (AvaliacaoC5)"]
    end

    PARALLEL --> C1 & C2 & C3 & C4 & C5
    C1 & C2 & C3 & C4 & C5 --> J["[4] Consolidador / Juiz Determinístico (agents/consolidador.py)"]

    EV["evidencias.py: Validação Literal/Aproximada de Trechos"] --> J

    J --> FB["[5] Agente de Feedback Pedagógico (agente_feedback / Feedback)"]
    Z --> OUT["[6] Saída Final (AvaliacaoFinal JSON + Relatório Markdown + JSONL)"]
    FB --> OUT
```

---

## 2. Diagrama de Sequência de Execução

O diagrama abaixo detalha o ciclo de vida de uma correção no `InMemoryRunner` / `adk web`, incluindo o isolamento de contexto via `before_model_callback` (proteção contra *prompt injection* usando delimitadores XML `<tema>`, `<motivadores>`, `<preanalise>` e `<redacao>`).

```mermaid
sequenceDiagram
    autonumber
    actor Aluno as Estudante (CLI ou adk web)
    participant Orq as CorretorEnemAgent
    participant Pre as PreAnalise e Tools
    participant Anul as AgenteAnulacao
    participant Comp as ParallelAgent (C1 a C5)
    participant Cons as Consolidador e Evidencias
    participant Feed as AgenteFeedback

    Aluno->>Orq: Envia Tema + Redação (+ Motivadores)
    Orq->>Pre: executar_preanalise(entrada)
    Pre-->>Orq: Estatísticas, linhas, cópia, coesão, alertas C1
    Orq->>Orq: Grava entrada e preanalise no Session State

    alt Anulação Determinística (menos de 8 linhas ou cópia massiva)
        Orq->>Cons: consolidar_avaliacao(state)
        Cons-->>Aluno: Nota 0 + Relatório de Anulação
    else Aprovado na Triagem Determinística
        Orq->>Anul: run_async(ctx) via XML isolado no callback
        Anul-->>Orq: ResultadoAnulacao (anulacao_llm)

        alt Anulação Semântica (fuga ao tema, tipo textual, etc.)
            Orq->>Cons: consolidar_avaliacao(state)
            Cons-->>Aluno: Nota 0 + Relatório de Anulação
        else Redação Conformante
            Orq->>Comp: Dispara agente_c1 a agente_c5 em paralelo
            Comp-->>Orq: Grava avaliacao_c1 a avaliacao_c5 no State
            opt Alguma competência falhou (rate limit ou JSON inválido)
                Orq->>Comp: Re-executa individualmente a competência faltante
            end
            Orq->>Cons: consolidar_avaliacao(state)
            Cons->>Cons: Aplica tetos (tangenciamento, cópia, C5 elementos, DH)
            Cons->>Cons: Valida se trechos citados existem na redação
            Cons-->>Orq: AvaliacaoFinal parcial + avaliacao_consolidada
            Orq->>Feed: run_async(ctx) com avaliacao_consolidada
            Feed-->>Orq: Feedback (prioridades, reescritas, checklist)
            Orq->>Orq: Salva execução em data/execucoes/historico.jsonl
            Orq-->>Aluno: Relatório Markdown + AvaliacaoFinal (JSON)
        end
    end
```

---

## 3. Regras de Consolidação e Tetos de Nota (Etapa 4)

Mesmo com prompts calibrados, LLMs podem divergir entre o diagnóstico textual e a nota atribuída. O módulo `agents/consolidador.py` aplica deterministicamente as travas oficiais da matriz do ENEM:

```mermaid
flowchart LR
    subgraph C2_Rules["Regras da Competência 2"]
        R1["tangenciamento == true"] --> T1["Teto C2 <= 40"]
        R2["copia_motivadores >= 20%"] --> T2["Teto C2 <= 80"]
        R3["tipo_textual_adequado == false"] --> T3["Teto C2 <= 40"]
    end

    subgraph Cross_Rules["Impacto Cruzado (C2 -> C3 e C5)"]
        T1 --> TC3["Teto C3 <= 40"]
        T1 --> TC5["Teto C5 <= 40"]
    end

    subgraph C5_Rules["Regras da Competência 5"]
        DH["respeita_direitos_humanos == false"] --> Z5["C5 = 0"]
        NP["proposta_presente == false"] --> Z5
        EL["Contagem de Elementos Válidos (agente, acao, meio, finalidade, detalhamento)"] --> N5["Nota C5 = 40 x N_válidos"]
        NA["articulada_a_discussao == false"] --> T80["Teto C5 <= 80"]
    end
```

---

## 4. Estrutura do Repositório e Módulos

```mermaid
graph LR
    subgraph Repo["enem-ai-corrector/"]
        RUB["rubricas/ (c1..c5.yaml, anulacao.yaml)"]
        PRM["prompts/ (c1..c5.md, anulacao.md, feedback.md)"]
        SRC["src/enem_corretor/"]
        TST["tests/ (unit, component, integration)"]
    end

    subgraph Pacote["src/enem_corretor/"]
        CFG["config.py"]
        SCH["schemas/ (entrada.py, saida.py)"]
        TLS["tools/ (texto, copia, conectivos, gramatica, evidencias, rubricas)"]
        AGS["agents/ (preanalise, anulacao, competencias, consolidador, feedback, orquestrador)"]
        ENT["agent.py e __init__.py (root_agent + CLI enem-corretor)"]
    end

    RUB --> TLS
    PRM --> TLS
    CFG --> AGS
    SCH --> AGS
    TLS --> AGS
    AGS --> ENT
```

```text
enem-ai-corrector/
├── README.md
├── pyproject.toml
├── .env.example
├── rubricas/
│   ├── c1.yaml … c5.yaml          # Descritores por nível (0..200), orientações e tetos
│   └── anulacao.yaml              # Hipóteses de nota zero (determinísticas e semânticas)
├── prompts/
│   ├── anulacao.md                # Prompt conservador de triagem de conformidade
│   ├── c1.md … c5.md              # Prompts calibrados por competência
│   └── feedback.md                # Prompt pedagógico com reescrita comentada
├── data/
│   └── exemplos/
│       └── redacao_exemplo.json   # Redação completa de exemplo para teste rápido
├── src/
│   └── enem_corretor/
│       ├── __init__.py            # CLI `enem-corretor` e API pública do pacote
│       ├── agent.py               # `root_agent` (ADK) + `corrigir_redacao`
│       ├── config.py              # Configuração via variáveis de ambiente (.env)
│       ├── schemas/
│       │   ├── entrada.py         # `EntradaRedacao`
│       │   └── saida.py           # `AvaliacaoC1`..`C5`, `ResultadoAnulacao`, `Feedback`, `AvaliacaoFinal`
│       ├── tools/
│       │   ├── texto.py           # Normalização, parágrafos, períodos, linhas estimadas
│       │   ├── copia.py           # Detecção de cópia dos motivadores por 7-gramas
│       │   ├── conectivos.py      # Catálogo de conectivos e repetições lexicais
│       │   ├── gramatica.py       # Heurísticas PT-BR + cliente HTTP LanguageTool
│       │   ├── evidencias.py      # Verificação literal/aproximada de trechos citados
│       │   └── rubricas.py        # Loader com cache de YAMLs e prompts Markdown
│       └── agents/
│           ├── comum.py           # Fábrica Gemini/LiteLLM + callbacks XML anti-injection
│           ├── preanalise.py      # Parser de entrada + pré-análise determinística
│           ├── anulacao.py        # `agente_anulacao`
│           ├── competencias.py    # `agente_c1` .. `agente_c5`
│           ├── consolidador.py    # Juiz de tetos, validação de evidências e relatório Markdown
│           ├── feedback.py        # `agente_feedback`
│           └── orquestrador.py    # `CorretorEnemAgent` (BaseAgent)
└── tests/
    ├── conftest.py                # `FakeEnemLlm` e fixtures compartilhadas
    ├── unit/                      # Testes unitários (tools, schemas, config)
    ├── component/                 # Testes de componente (pré-análise, consolidador, fábricas)
    └── integration/               # Testes de integração (pipeline ADK paralelo/sequencial e CLI)
```

---

## 5. Como Configurar e Executar

### 5.1. Instalar dependências e configurar `.env`
```bash
uv sync
cp .env.example .env
```
Edite `.env` e adicione sua chave gratuita do [Google AI Studio](https://aistudio.google.com/):
```env
GOOGLE_API_KEY=sua_chave_aqui
ENEM_MODELO=gemini-3.5-flash
```

Para rodar **100% local com Ollama** via LiteLLM (recomendado desativar o paralelismo em máquinas com 8 GB de RAM):
```env
ENEM_MODELO=ollama_chat/qwen2.5:3b
ENEM_PARALELO=false
```

### 5.2. Uso via linha de comando (`enem-corretor`)

**Somente pré-análise determinística** (instantânea, sem chamadas de LLM):
```bash
uv run enem-corretor --arquivo data/exemplos/redacao_exemplo.json --apenas-preanalise
```

**Correção completa com geração de JSON e relatório Markdown:**
```bash
uv run enem-corretor \
  --arquivo data/exemplos/redacao_exemplo.json \
  --saida-json data/execucoes/ultima_avaliacao.json \
  --saida-md data/execucoes/ultimo_relatorio.md
```

### 5.3. Uso na Interface Web do Google ADK (`adk web`)
```bash
uv run adk web src
```
Selecione o agente **`enem_corretor`** no navegador e envie a redação como JSON ou no formato:
```text
TEMA: Desafios para a valorização de comunidades e povos tradicionais no Brasil

REDAÇÃO:
[cole os parágrafos da sua redação aqui]
```

---

## 6. Testes Automatizados e Cobertura (>= 90%)

A suíte de testes é dividida em **3 camadas** e exige cobertura mínima de **90%** configurada diretamente no `pyproject.toml` (`--cov-fail-under=90`, atingindo **~98% de cobertura total**):

- **Unitários (`tests/unit/`)**: testam isoladamente cada ferramenta determinística (`texto`, `copia`, `conectivos`, `gramatica`, `evidencias`, `rubricas`), os validadores Pydantic e o carregamento de configuração.
- **Componente (`tests/component/`)**: testam os subsistemas de pré-análise, extração de múltiplos formatos de entrada, fábricas de agentes/modelos e todas as regras de teto e formatação do consolidador.
- **Integração (`tests/integration/`)**: testam o pipeline multi-agente ADK ponta a ponta no `InMemoryRunner` (modos paralelo e sequencial, *retry* automático de competência, curto-circuito de anulação, degradação graciosa, persistência JSONL e CLI).

```bash
uv run pytest
```
