# Relatório de Revisão, Testes e Avaliação — `enem-corretor`

**Data:** 2026-11-06  |  **Commit:** `cff413f71e3323605d8b56c3c49373ba0b9cba0f`  |  **Modo:** `SÓ-CÓDIGO` (rebaixado de `PROFUNDO` por ausência de `golden_set` e de `GOOGLE_API_KEY` configurada)  
**Modelos configurados:** `gemini-3.5-flash` (default) + `LiteLlm` + `FakeEnemLlm` (testes)  |  **Rubrica de referência:** `rubricas/*.yaml` (`ano_referencia: 2024`, `verificado: false`)  
**Golden set:** ausente (`n=0`; existe apenas 1 amostra sintética de exemplo em `data/exemplos/redacao_exemplo.json`, SHA-256 `6f2d40d0...8b8`)

---

## Resumos por Fase (Protocolo Seção 4.4)

- **Fase 0 (Preparação e Reprodutibilidade):** Repositório limpo no commit `cff413f` **[MEDIDO]**. Ambiente Python `3.12.16` com `google-adk==2.13.0`, `litellm==1.106.2`, `pydantic==2.14.3` e `uv.lock` presente **[MEDIDO]**. `.env.example` existe e `.env` está no `.gitignore` **[LIDO]**. Manifesto salvo em `runs/2026-11-06_audit-so-codigo_cff413f/manifest.yaml` **[MEDIDO]**.
- **Fase 1 (Mapeamento):** Pacote `src/enem_corretor` possui 2.275 linhas de código distribuídas em 21 arquivos Python (7 agentes LLM + 1 orquestrador `BaseAgent`, 6 módulos de tools determinísticas, 2 módulos de schemas Pydantic) e 7 prompts Markdown + 6 rubricas YAML **[MEDIDO]**. Arquitetura real coincide com a Seção 3.2, exceto pela ausência do módulo RAG e do script `eval/` (previstos para Fases 3–4 do roadmap) **[LIDO]**.
- **Fase 2 (Suíte Automatizada):** 16 testes executados em 3 rodadas consecutivas sem flakiness (0.68s–0.79s) **[MEDIDO]**. Cobertura de linhas: **98,16%**; cobertura combinada de linhas + ramos (`--cov-branch`): **96,05%** (1.030 statements, 19 miss; 288 branches, 27 partial) **[MEDIDO]**. Nenhum módulo abaixo de 88% **[MEDIDO]**. Linters estáticos (`ruff`, `mypy`, `mutmut`) ainda não estão instalados no ambiente **[MEDIDO]**.
- **Fase 3 (Revisão de Código por Módulo):** Identificados 1 achado **CRÍTICO** (`COD-001`: competência com falha de execução recebe `nota=0` em vez de abortar/marcar avaliação como `incompleta`, violando `CON-04`) e 3 achados **ALTOS** (`COD-002`: coerção silenciosa de notas inválidas via `ajustar_nivel` em vez de rejeitar e acionar retry; `COD-003`: tag `</redacao>` não escapada no XML de entrada; `COD-004`: `num_ctx` não configurado para Ollama em `LiteLlm`) **[LIDO]**.
- **Fase 4 (Auditoria das Rubricas):** Os 6 arquivos `rubricas/*.yaml` cobrem os 6 níveis (0 a 200) das 5 competências e 9 hipóteses de anulação, marcando honestamente `verificado: false` **[LIDO]**. Como o PDF oficial da Cartilha do INEP não está em `docs/rubrica_oficial/`, a fidelidade literal permanece **[NÃO VERIFICADO]**, com um ponto de atenção em `c1.yaml` ("no máximo dois desvios" no nível 200) e ausência de exemplos-âncora (`AUD-03`).
- **Fase 5 (Revisão dos Prompts):** Os 7 prompts (`prompts/*.md`) isolam o papel de cada agente, exigem evidências literais e incluem instruções anti-injection e de calibração ("200 é raro") **[LIDO]**. Tamanho real medido para redação de 37 linhas: **1.628 a 2.925 tokens** por agente, cabendo com folga em Gemini (1M) e modelos locais de 8k+, mas exigindo `num_ctx >= 4096` no Ollama **[MEDIDO]**.
- **Fase 6 (Revisão dos Testes):** Pirâmide atual cobre unitários, componente e integração (16 testes, 96,05% branch coverage) **[MEDIDO]**, mas faltam testes de propriedade (`hypothesis`), testes adversariais de fechamento de tag (`</redacao>`), e testes que exijam rejeição de nota inválida (`SCH-01`/`T-01`) **[LIDO]**.
- **Fase 7 (Avaliação AES):** **Não executada (`[NÃO VERIFICADO]`)** por ausência de `golden_set` rotulado por humanos (`data/golden_set/` inexistente) e de chave de API ativa.
- **Fase 8 (Desempenho e Limites):** Cada correção completa consome **7 chamadas LLM** (~17.686 tokens de entrada somados + ~3.500 tokens de saída ≈ **21,2k tokens/redação**) **[MEDIDO/INFERIDO]**. No Gemini Free Tier (~15 RPM / 1.500 RPD), o modo paralelo (5 chamadas simultâneas na etapa 3) cabe no limite por minuto para 1–2 redações/minuto, mas sem rate-limiter local pode sofrer `429` em execuções em lote **[INFERIDO]**.
- **Fase 9 (Segurança, Privacidade e Licenças):** Zero segredos no código ou histórico git **[MEDIDO]**. Nenhuma execução de código dinâmico (`eval`/`exec`/`subprocess`) **[LIDO]**. Falta escape de tags XML na redação (`SEC-03`/`ADV-03`), aviso de privacidade no README sobre envio de texto ao Google AI Studio Free Tier (`PRV-01`/`PRV-02`) e arquivo `LICENSE` (`LIC-03`) **[LIDO]**.
- **Fase 10 (Consolidação e Decisão):** Decisão final: **NÃO PRONTO para avaliação automatizada confiável / USO EXPLORATÓRIO CONDICIONADO** à correção imediata do bloqueante `COD-001` (falha de agente virando nota 0) e `COD-002` (coerção silenciosa de nota fora da escala) e à criação de um golden set mínimo para medir QWK.

---

## 1. Resumo Executivo

- **Estado geral:** A base arquitetural das Fases 0–2 está bem estruturada, modular, sem segredos expostos, com excelente cobertura de testes automatizados (**98,16% linhas / 96,05% branches** **[MEDIDO]**) e separação limpa entre pré-análise determinística, agentes ADK com `output_schema`, juiz consolidador e gerador de feedback.
- **Top 3 riscos identificados:**
  1. **[CRÍTICO — `COD-001`]** Se um agente de competência falhar após as tentativas (ex.: `429 Rate Limit` no free tier ou JSON malformado de modelo local), o consolidador atribui `nota=0` àquela competência e soma `nota_total` normalmente, reduzindo a nota do aluno em até 200 pontos por erro de infraestrutura **[LIDO]**.
  2. **[ALTO — `COD-002`]** O validador `_nivel_valido` usa `ajustar_nivel()` para arredondar qualquer número ou string inválida (ex.: `"invalido" -> 0`, `150 -> 160`, `-40 -> 0`) em vez de lançar `ValidationError`, impedindo o retry de schema e mascarando alucinações numéricas do LLM **[LIDO]**.
  3. **[ALTO — `COD-003` / `DAT-001`]** Ausência de sanitização da tag `</redacao>` no corpo do texto do aluno (permitindo escape do delimitador XML) **[LIDO]** e ausência de `golden_set` / script `eval/` para medir QWK, MAE e viés real **[MEDIDO]**.
- **Decisão:** **NÃO PRONTO** (pelos critérios bloqueantes `CON-04` e `SCH-01` do Apêndice H e ausência de medição no golden set). Após corrigir `COD-001` e `COD-002` (~30 linhas de código), o sistema atinge o patamar de **USO EXPLORATÓRIO**.

---

## 2. Parâmetros da Execução e Ambiente (Fases 0 e 1)

### 2.1 Placeholders preenchidos
| Parâmetro | Valor | Evidência |
|---|---|---|
| `{{REPO_PATH}}` | `/Users/humbertolimadealcantarafonsecafilho/enem-ai-corrector` | **[MEDIDO]** |
| `{{PACKAGE_NAME}}` | `enem_corretor` | **[LIDO]** `pyproject.toml:2` |
| `{{COMMIT_OR_DIFF}}` | `cff413f71e3323605d8b56c3c49373ba0b9cba0f` (`main`, working tree limpa) | **[MEDIDO]** |
| `{{GOLDEN_SET_PATH}}` | *Ausente* (apenas `data/exemplos/redacao_exemplo.json`) | **[MEDIDO]** |
| `{{RUBRIC_SOURCE}}` | `rubricas/*.yaml` (Cartilha INEP 2024 transcrita, `verificado: false`; PDF oficial ausente) | **[LIDO]** |
| `{{MODELS_TO_TEST}}` | Modo `SÓ-CÓDIGO` (`FakeEnemLlm`); config padrão: `gemini-3.5-flash` | **[LIDO]** |
| `{{N_REPEATS}}` | `3` (executado na suíte de testes para checagem de flakiness) | **[MEDIDO]** |
| `{{BUDGET}}` | `0` chamadas externas (sem `.env` / sem `GOOGLE_API_KEY`) | **[MEDIDO]** |
| `{{GOAL}}` | Auditoria completa v2 do código, rubricas, prompts, testes e segurança | **[LIDO]** |

### 2.2 Verificações da Fase 0
| ID | Verificação | Status | Observação / Evidência |
|---|---|---|---|
| PRE-01 | Instalação do zero funciona seguindo só o README | **OK** | `uv sync` + `uv run pytest` documentados e funcionais **[MEDIDO]** |
| PRE-02 | Dependências com versões mínimas/fixadas (`uv.lock`) | **OK** | `pyproject.toml` + `uv.lock` versionado **[LIDO]** |
| PRE-03 | Existe `.env.example` e `.env` está no `.gitignore` | **OK** | `.env.example` presente; `.env` na linha 5 do `.gitignore` **[LIDO]** |
| PRE-04 | Modelo, temperatura e seed configuráveis sem editar código | **OK** | `ENEM_MODELO`, `ENEM_TEMPERATURA`, `ENEM_SEMENTE` em `config.py:72-84` **[LIDO]** |
| PRE-05 | Comando único para testes e outro para avaliação | **ATENÇÃO** | `uv run pytest` existe; `python -m eval.run_eval` ainda não implementado **[MEDIDO]** |

### 2.3 Mapeamento do Projeto e Estado no ADK (Fase 1)

| Componente | Arquivo | LOC | Responsabilidade | Lê `session.state` | Escreve `session.state` |
|---|---|---:|---|---|---|
| Entrypoint & CLI | [`__init__.py`](file:///Users/humbertolimadealcantarafonsecafilho/enem-ai-corrector/src/enem_corretor/__init__.py), [`agent.py`](file:///Users/humbertolimadealcantarafonsecafilho/enem-ai-corrector/src/enem_corretor/agent.py) | 201 | CLI `enem-corretor`, `root_agent`, `corrigir_redacao` | `avaliacao_final`, `relatorio_markdown` | `entrada` |
| Orquestrador | [`agents/orquestrador.py`](file:///Users/humbertolimadealcantarafonsecafilho/enem-ai-corrector/src/enem_corretor/agents/orquestrador.py) | 287 | Pipeline `BaseAgent`, curto-circuitos, retries, log JSONL | `entrada`, `anulacao_llm`, `avaliacao_c1..c5`, `feedback` | `entrada`, `preanalise`, `avaliacao_consolidada`, `avaliacao_final`, `relatorio_markdown` |
| Pré-análise | [`agents/preanalise.py`](file:///Users/humbertolimadealcantarafonsecafilho/enem-ai-corrector/src/enem_corretor/agents/preanalise.py) | 130 | Parser de entrada + disparo das tools determinísticas | — | (via orquestrador: `preanalise`) |
| Agente Anulação | [`agents/anulacao.py`](file:///Users/humbertolimadealcantarafonsecafilho/enem-ai-corrector/src/enem_corretor/agents/anulacao.py) | 34 | `LlmAgent` p/ fuga ao tema, tipo textual, impropérios | `entrada`, `preanalise` (via callback) | `anulacao_llm` (`ResultadoAnulacao`) |
| Agentes C1–C5 | [`agents/competencias.py`](file:///Users/humbertolimadealcantarafonsecafilho/enem-ai-corrector/src/enem_corretor/agents/competencias.py) | 59 | 5 `LlmAgent`s independentes (em `ParallelAgent` ou sequenciais) | `entrada`, `preanalise` (via callback) | `avaliacao_c1` … `avaliacao_c5` |
| Consolidador | [`agents/consolidador.py`](file:///Users/humbertolimadealcantarafonsecafilho/enem-ai-corrector/src/enem_corretor/agents/consolidador.py) | 363 | Regras de teto, contagem C5, validação de evidências, Markdown | `entrada`, `preanalise`, `anulacao_llm`, `avaliacao_c1..c5`, `feedback` | (retorna `AvaliacaoFinal`) |
| Agente Feedback | [`agents/feedback.py`](file:///Users/humbertolimadealcantarafonsecafilho/enem-ai-corrector/src/enem_corretor/agents/feedback.py) | 34 | `LlmAgent` pedagógico (prioridades, reescritas, checklist) | `entrada`, `preanalise`, `avaliacao_consolidada` | `feedback` (`Feedback`) |
| Utilitários ADK | [`agents/comum.py`](file:///Users/humbertolimadealcantarafonsecafilho/enem-ai-corrector/src/enem_corretor/agents/comum.py) | 118 | Fábrica `Gemini`/`LiteLlm`, callback XML anti-injection | `entrada`, `preanalise`, `avaliacao_consolidada` | — |
| Schemas | [`schemas/entrada.py`](file:///Users/humbertolimadealcantarafonsecafilho/enem-ai-corrector/src/enem_corretor/schemas/entrada.py), [`schemas/saida.py`](file:///Users/humbertolimadealcantarafonsecafilho/enem-ai-corrector/src/enem_corretor/schemas/saida.py) | 330 | Contratos Pydantic v2 de entrada e saída | — | — |
| Tools | `tools/*.py` | 650 | `texto`, `copia`, `conectivos`, `gramatica`, `evidencias`, `rubricas` | — | — |

---

## 3. Testes Automatizados (Fase 2)

| Item | Resultado Medido | Evidência |
|---|---|---|
| Passaram / falharam / pulados | **16 passaram / 0 falharam / 0 pulados** | **[MEDIDO]** `pytest -v` |
| Tempo total e teste mais lento | **2,29s** com cov (**0,68s** sem cov); mais lento: `test_integracao_pipeline_paralelo_e_persistencia_jsonl` (0,86s) | **[MEDIDO]** `--durations=5` |
| Cobertura de linhas / combinada com ramos | **98,16% linhas** (1.011/1.030) / **96,05% linhas+ramos** (288 branches, 27 parciais) | **[MEDIDO]** `--cov-branch` |
| Módulos críticos < 80% | **Nenhum** (menor cobertura: `__init__.py` e `orquestrador.py` com 88% em branch coverage; `consolidador.py` tem 95%) | **[MEDIDO]** |
| Flakiness (3 execuções seguidas) | **0 testes flaky** (16/16 nas 3 execuções) | **[MEDIDO]** |
| Lint / tipos / mutação (`ruff`, `mypy`, `mutmut`) | **Não medido** — pacotes não instalados em `dependency-groups.dev` | **[MEDIDO]** |
| Segredos detectados | **0 segredos** no código e no histórico git | **[MEDIDO]** |

---

## 4. Matriz de Verificação de Regras de Domínio e Código (Fase 3)

### 4.1 Regras de Domínio (R-01 a R-12)
| ID | Regra | Status | Evidência e Local |
|---|---|---|---|
| R-01 | Cada competência só assume `{0, 40, 80, 120, 160, 200}` | **PROBLEMA** | [`schemas/saida.py:21-28,62-65`](file:///Users/humbertolimadealcantarafonsecafilho/enem-ai-corrector/src/enem_corretor/schemas/saida.py#L21-L28) arredonda valores inválidos (`150 -> 160`, `"abc" -> 0`) em vez de rejeitar (**ver `COD-002`**) **[LIDO]** |
| R-02 | Total = soma das 5 competências calculada em código | **OK** | [`agents/consolidador.py:194`](file:///Users/humbertolimadealcantarafonsecafilho/enem-ai-corrector/src/enem_corretor/agents/consolidador.py#L194) (`nota_total = sum(r.nota for r in resultados.values())`) **[LIDO]** |
| R-03 | Anulação decidida antes das competências; curto-circuita com total 0 | **OK** | [`agents/orquestrador.py:148-193`](file:///Users/humbertolimadealcantarafonsecafilho/enem-ai-corrector/src/enem_corretor/agents/orquestrador.py#L148-L193) interrompe antes do `ParallelAgent` tanto na anulação determinística quanto na semântica **[LIDO/MEDIDO]** |
| R-04 | Lista de motivos de anulação corresponde à cartilha | **OK** | [`rubricas/anulacao.yaml:13-40`](file:///Users/humbertolimadealcantarafonsecafilho/enem-ai-corrector/rubricas/anulacao.yaml#L13-L40) cobre os 9 motivos clássicos e separa DH e tangenciamento **[LIDO]** |
| R-05 | Toda nota > 0 tem evidência literal presente na redação | **ATENÇÃO** | [`tools/evidencias.py`](file:///Users/humbertolimadealcantarafonsecafilho/enem-ai-corrector/src/enem_corretor/tools/evidencias.py) valida se os trechos existem, mas `evidencias: list[Evidencia]` permite lista vazia `[]` em `nota > 0` (**ver `COD-005`**) **[LIDO]** |
| R-06 | C5 considera os 5 elementos + articulação com a discussão | **OK** | [`agents/consolidador.py:151-174`](file:///Users/humbertolimadealcantarafonsecafilho/enem-ai-corrector/src/enem_corretor/agents/consolidador.py#L151-L174) recalcula a nota pela contagem de elementos válidos e aplica teto de 80 se `articulada_a_discussao=False` **[LIDO/MEDIDO]** |
| R-07 | Proposta que viola Direitos Humanos zera C5 | **OK** | [`agents/consolidador.py:136-140`](file:///Users/humbertolimadealcantarafonsecafilho/enem-ai-corrector/src/enem_corretor/agents/consolidador.py#L136-L140) zera C5 sem anular a redação inteira **[LIDO/MEDIDO]** |
| R-08 | Tangenciamento limita C2, C3 e C5 a 40 pontos | **OK** | [`agents/consolidador.py:120-133,172-176`](file:///Users/humbertolimadealcantarafonsecafilho/enem-ai-corrector/src/enem_corretor/agents/consolidador.py#L120-L133) aplica teto de 40 em C2, C3 e C5 **[LIDO/MEDIDO]** |
| R-09 | Cópia dos motivadores descontada das linhas e limita C2 | **OK** | [`agents/preanalise.py:72-92`](file:///Users/humbertolimadealcantarafonsecafilho/enem-ai-corrector/src/enem_corretor/agents/preanalise.py#L72-L92) desconta linhas copiadas; [`consolidador.py:123`](file:///Users/humbertolimadealcantarafonsecafilho/enem-ai-corrector/src/enem_corretor/agents/consolidador.py#L123) limita C2 a 80 se cópia >= 20% **[LIDO/MEDIDO]** |
| R-10 | Heurística de linhas documentada e configurável | **OK** | [`tools/texto.py:48-53`](file:///Users/humbertolimadealcantarafonsecafilho/enem-ai-corrector/src/enem_corretor/tools/texto.py#L48-L53) documenta `ceil((len(p)+3)/caracteres_por_linha)` **[LIDO]** |
| R-11 | Rubricas versionadas por ano | **ATENÇÃO** | `ano_referencia: 2024` presente nos YAMLs, mas falta pasta `docs/decisoes/` (ADRs) **[LIDO]** |
| R-12 | Nota independe de formatação irrelevante | **ATENÇÃO** | [`tools/texto.py:25-33`](file:///Users/humbertolimadealcantarafonsecafilho/enem-ai-corrector/src/enem_corretor/tools/texto.py#L25-L33) normaliza NFC, `\r\n`, tabs e espaços múltiplos, mas não remove caracteres de largura zero (`\u200b`) em `normalizar_texto` **[LIDO]** |

### 4.2 Resumo do Checklist de Código (SCH / RUB / PRM / AGT / TLS / CFG / CON / IO / LOG)
- **SCH:** `SCH-02` **OK**; `SCH-01`, `SCH-03`, `SCH-04` **PROBLEMA/ATENÇÃO** (falta `Literal[0,40,80,120,160,200]` estrito, obrigatoriedade de evidência quando `nota > 0` e enum fechado em `MotivoAnulacao.motivo`); `SCH-06` **ATENÇÃO** (falta campo `schema_version` em `AvaliacaoFinal`).
- **AGT:** `AGT-01`, `AGT-02`, `AGT-03`, `AGT-08`, `AGT-10` **OK** (chaves distintas `avaliacao_c1..c5`, limpeza de state no início da execução em `orquestrador.py:121-132`, callback isolando contexto); `AGT-04` **PROBLEMA** (ver `COD-001`).
- **TLS:** `TLS-01` a `TLS-05` **OK**; `TLS-06` **ATENÇÃO** (incluir remoção de zero-width chars e normalização de aspas/travessões em `normalizar_texto` e `evidencias._simplificar`).
- **CFG:** `CFG-01`, `CFG-02`, `CFG-04`, `CFG-05` **OK**; `CFG-03` **PROBLEMA** (`num_ctx` não passado ao `LiteLlm` para modelos Ollama).
- **CON:** `CON-01`, `CON-02` **OK**; `CON-04` **PROBLEMA** (`COD-001`).

---

## 5. Achados Detalhados (Ordenados por Severidade)

### [COD-001] Falha de execução em agente de competência atribui `nota=0` silenciosamente em vez de marcar avaliação como `incompleta`
- **Severidade:** CRÍTICO
- **Categoria:** código (`CON-04`, `AGT-04`)
- **Confiança:** ALTA  |  **Evidência:** **[LIDO]**
- **Local:** [`src/enem_corretor/agents/consolidador.py:102-113`](file:///Users/humbertolimadealcantarafonsecafilho/enem-ai-corrector/src/enem_corretor/agents/consolidador.py#L102-L113)
- **Observado:** Quando `state.get("avaliacao_cX")` está ausente ou `None` (por exemplo, se a API retornar erro `429`/`503` em todas as tentativas), o consolidador cria um `ResultadoCompetencia(competencia=comp, nota=0, nota_modelo=None, ...)` e continua calculando `nota_total = sum(r.nota for r in resultados.values())` sem um campo `incompleta: bool = True` em `AvaliacaoFinal`.
- **Hipótese de causa:** Tratamento defensivo para evitar `KeyError` que usou `0` como fallback numérico.
- **Impacto:** O estudante recebe uma nota total até 200 pontos menor por competência que falhou por rede/rate-limit, confundindo erro operacional com nota zero na competência.
- **Recomendação:** Adicionar `incompleta: bool = False` em `AvaliacaoFinal`, definir `nota: int | None` (ou bloquear o cálculo de `nota_total` quando `any(r.nota_modelo is None for r in resultados.values())`) e exibir aviso explícito de avaliação incompleta no relatório.
- **Como verificar a correção:** Criar teste `T-21` em que `AvaliacaoC3` falha em todas as tentativas e verificar que `av.incompleta is True`.

### [COD-002] `ajustar_nivel` converte silenciosamente notas fora da escala ou inválidas em vez de rejeitar no schema Pydantic
- **Severidade:** ALTO
- **Categoria:** código (`SCH-01`, `R-01`, `T-01`)
- **Confiança:** ALTA  |  **Evidência:** **[LIDO]**
- **Local:** [`src/enem_corretor/schemas/saida.py:21-28,62-65`](file:///Users/humbertolimadealcantarafonsecafilho/enem-ai-corrector/src/enem_corretor/schemas/saida.py#L21-L28)
- **Observado:** O validator `_nivel_valido` chama `ajustar_nivel(valor)`, que transforma `-40 -> 0`, `240 -> 200`, `150 -> 160` e `"invalido" -> 0` sem levantar `ValueError`.
- **Impacto:** Se um modelo local alucinar `nota: 150`, `nota: -40` ou `nota: "abc"`, o Pydantic aceita o JSON na 1ª tentativa em vez de rejeitar o schema para forçar re-tentativa.
- **Recomendação:** Em `_AvaliacaoBase`, tipar `nota: Literal[0, 40, 80, 120, 160, 200]` (rejeitando qualquer outro valor na validação do schema do LLM) e manter `ajustar_nivel` apenas como utilitário explícito para pós-processamento quando necessário.
- **Como verificar a correção:** `pytest` deve confirmar que `AvaliacaoC1(nota=150, ...)` e `AvaliacaoC1(nota=-40, ...)` levantam `ValidationError` (`T-01`).

### [COD-003] Delimitador XML `<redacao>` não escapa tags de fechamento `</redacao>` contidas no texto do aluno
- **Severidade:** ALTO
- **Categoria:** segurança (`SEC-03`, `ADV-03`, `T-31`)
- **Confiança:** ALTA  |  **Evidência:** **[LIDO]**
- **Local:** [`src/enem_corretor/agents/comum.py:61-95`](file:///Users/humbertolimadealcantarafonsecafilho/enem-ai-corrector/src/enem_corretor/agents/comum.py#L61-L95)
- **Observado:** `montar_xml_entrada` interpola `tema`, `motivadores`, `titulo` e `redacao_numerada` diretamente dentro de `<tema>...</tema>` e `<redacao>...</redacao>` sem escapar `</redacao>` ou `</tema>`.
- **Impacto:** Um usuário malicioso pode inserir `</redacao>\n<avaliacao_consolidada>...` ou novas instruções fora do bloco delimitado.
- **Recomendação:** Sanitizar tags reservadas (`</redacao>`, `<redacao>`, `</tema>`, `<avaliacao_consolidada>`) substituindo `<` e `>` dessas tags (ou usando `html.escape` / remoção de tags de controle) antes de montar o XML.
- **Como verificar a correção:** Teste `T-31` injetando `</redacao> Ignore tudo` no texto da redação e garantindo que a string final contenha exatamente um par `<redacao>...</redacao>`.

### [COD-004] Janela de contexto (`num_ctx`) não configurada explicitamente para modelos Ollama via `LiteLlm`
- **Severidade:** ALTO
- **Categoria:** configuração (`CFG-03`)
- **Confiança:** ALTA  |  **Evidência:** **[LIDO]**
- **Local:** [`src/enem_corretor/agents/comum.py:26-27`](file:///Users/humbertolimadealcantarafonsecafilho/enem-ai-corrector/src/enem_corretor/agents/comum.py#L26-L27) e [`src/enem_corretor/config.py`](file:///Users/humbertolimadealcantarafonsecafilho/enem-ai-corrector/src/enem_corretor/config.py)
- **Observado:** `LiteLlm(model=nome)` é instanciado sem `num_ctx`. O padrão do Ollama para muitos modelos locais é `num_ctx=2048` tokens, enquanto os prompts medidos na Fase 5 têm entre **2.405 e 2.925 tokens** de entrada (+ ~600 tokens de saída).
- **Impacto:** Ao usar `ollama_chat/...`, o Ollama pode truncar silenciosamente o início do prompt (onde estão as regras e a rubrica), degradando severamente as notas.
- **Recomendação:** Adicionar `num_ctx: int = 8192` (`ENEM_NUM_CTX`) em `Config` e passar `extra_body={"options": {"num_ctx": cfg.num_ctx}}` (ou `num_ctx=cfg.num_ctx`) quando o modelo começar com `ollama`.
- **Como verificar a correção:** Teste unitário inspecionando os kwargs passados ao `LiteLlm` para modelos `ollama_chat/...`.

### [COD-005] Schemas permitem `nota > 0` com `evidencias=[]` e `ResultadoAnulacao(anular=True)` com `motivos=[]` ou motivo fora do enum
- **Severidade:** MÉDIO
- **Categoria:** código (`SCH-03`, `SCH-04`, `T-04`, `T-05`)
- **Confiança:** ALTA  |  **Evidência:** **[LIDO]**
- **Local:** [`src/enem_corretor/schemas/saida.py:42-65,163-180`](file:///Users/humbertolimadealcantarafonsecafilho/enem-ai-corrector/src/enem_corretor/schemas/saida.py#L42-L65)
- **Observado:** `MotivoAnulacao.motivo` é `str` livre em vez de `Literal[...]` e não há `model_validator` exigindo ao menos 1 evidência quando `nota > 0` ou ao menos 1 motivo quando `anular=True`.
- **Recomendação:** Restringir `MotivoAnulacao.motivo` com `Literal["fuga_ao_tema", "tipo_textual", "parte_desconectada", "improperios", "identificacao", "lingua_estrangeira"]`, exigir `motivos` não vazio se `anular=True` e registrar alerta no consolidador se alguma competência com `nota > 0` vier com `evidencias=[]`.

### [COD-006] Normalização Unicode não remove caracteres de largura zero (`\u200b-\u200d`, `\ufeff`) nem normaliza travessões/aspas tipográficas em `normalizar_texto`
- **Severidade:** MÉDIO
- **Categoria:** código (`TLS-06`, `R-12`, `ADV-05`)
- **Confiança:** ALTA  |  **Evidência:** **[LIDO]**
- **Local:** [`src/enem_corretor/tools/texto.py:25-33`](file:///Users/humbertolimadealcantarafonsecafilho/enem-ai-corrector/src/enem_corretor/tools/texto.py#L25-L33) e [`src/enem_corretor/tools/evidencias.py:13-17`](file:///Users/humbertolimadealcantarafonsecafilho/enem-ai-corrector/src/enem_corretor/tools/evidencias.py#L13-L17)
- **Observado:** Caracteres invisíveis de largura zero (`\u200b`) permanecem no texto e podem quebrar a contagem de caracteres, heurísticas regex de C1 e comparação de evidências.
- **Recomendação:** Remover `[\u200b-\u200d\ufeff]` e normalizar aspas curvas (`“”‘’`) e travessões (`–—`) em `normalizar_texto` e `_simplificar`.

---

## 6. Auditoria das Rubricas (Fase 4)

> **Status geral:** `rubricas/*.yaml` declaram explicitamente `verificado: false` e `ano_referencia: 2024` **[LIDO]**. Como o arquivo PDF oficial da Cartilha do Participante do INEP não está versionado em `docs/rubrica_oficial/`, a correspondência literal com a publicação oficial permanece **[NÃO VERIFICADO]**.

| Comp. | Níveis presentes | Estrutura e Regras de Teto | Observação de Auditoria |
|---|---|---|---|
| **C1** (`c1.yaml`) | 0, 40, 80, 120, 160, 200 | Lista 14 tipos de desvio e orientações de contagem por ocorrência vs reincidência | **ATENÇÃO (`AUD-02`):** `criterios_operacionais` do nível 200 diz *"No máximo dois desvios no texto inteiro"*, enquanto o descritor textual diz *"excepcionalidade e quando não caracterizarem reincidência"*. Confirmar na cartilha vigente se o limite é 1 ou 2 desvios. |
| **C2** (`c2.yaml`) | 0, 40, 80, 120, 160, 200 | Define tema vs assunto, repertório legitimado/pertinente/produtivo, parte embrionária e tetos (40 e 80) | **OK** — conceitos operacionais claros (`AUD-05`). |
| **C3** (`c3.yaml`) | 0, 40, 80, 120, 160, 200 | Checklist de tese, desenvolvimento, progressão, contradições, autoria e teto de tangenciamento | **OK** |
| **C4** (`c4.yaml`) | 0, 40, 80, 120, 160, 200 | Checklist de coesão inter/intraparágrafos, referenciação e repetições | **OK** |
| **C5** (`c5.yaml`) | 0, 40, 80, 120, 160, 200 | Define os 5 elementos (`agente`, `acao`, `meio`, `finalidade`, `detalhamento`), teto de 80 sem articulação e 0 por violação aos DH | **OK** |
| **Anulação** (`anulacao.yaml`) | 9 motivos (`deteccao: deterministica \| llm`) | Separa tangenciamento e DH de anulação; mínimo de 8 linhas (`<= 7` anula) | **OK** |
| **Âncoras (`AUD-03`)** | Ausentes | Nenhum YAML inclui exemplos/âncoras de redações reais por nível | **ATENÇÃO** — adicionar âncoras sintéticas curtas na Fase 3/4 do projeto. |

---

## 7. Revisão dos Prompts e Medição de Contexto (Fase 5)

### 7.1 Tamanho Real Medido dos Prompts (Redação de Exemplo: 347 palavras / 37 linhas estimadas)
Medido combinando `system_instruction` (prompt Markdown + YAML da rubrica na íntegra) + `user_content` XML (`<tema>`, `<motivadores>`, `<preanalise>`, `<redacao>` numerada) **[MEDIDO]**:

| Agente | Caracteres totais | Tokens estimados (entrada) | Janela Gemini 3.5 Flash | Janela Ollama (`num_ctx=8192`) | Folga (Ollama 8k) |
|---|---:|---:|---:|---:|---:|
| `agente_anulacao` | 9.142 | ~2.405 tok | 1.048.576 tok | 8.192 tok | ~70% livre |
| `agente_c1` | 10.849 | ~2.855 tok | 1.048.576 tok | 8.192 tok | ~65% livre |
| `agente_c2` | 11.118 | ~2.925 tok | 1.048.576 tok | 8.192 tok | ~64% livre |
| `agente_c3` | 9.784 | ~2.574 tok | 1.048.576 tok | 8.192 tok | ~68% livre |
| `agente_c4` | 9.664 | ~2.543 tok | 1.048.576 tok | 8.192 tok | ~69% livre |
| `agente_c5` | 10.475 | ~2.756 tok | 1.048.576 tok | 8.192 tok | ~66% livre |
| `agente_feedback` | 6.190 (+ ~2.500 consolidado) | ~2.280 tok | 1.048.576 tok | 8.192 tok | ~72% livre |

### 7.2 Checklist dos Prompts (`P-01` a `P-13`)
- **Pontos fortes (`P-01` a `P-05`, `P-08`):** Todos os prompts têm escopo exclusivo por competência, recebem a rubrica YAML completa via `instrucao_com_rubrica()`, usam `InstructionProvider` callable (evitando que chaves `{}` no texto quebrem o template do ADK — **`PRM-03` OK** **[LIDO/MEDIDO]**), exigem raciocínio prévio no campo `analise` antes de `nota` e exigem trechos literais.
- **Lacunas (`P-10`, `P-13`):** Os prompts são *zero-shot* com rubrica explícita (não possuem exemplos *few-shot* de notas 40/120/200 embutidos) e ainda não foram comparados experimentalmente contra versões em inglês (`P-13`).

---

## 8. Lacunas de Testes Identificadas (Fase 6)

| Teste que falta | ID Catálogo | Camada | Risco que cobre | Esforço | Prioridade |
|---|---|---|---|---|---|
| Rejeição estrita de notas fora de `{0,40,80,120,160,200}` (`150`, `-40`, `240`, `"abc"`) | `T-01` | Unitário | Impedir coerção silenciosa de nota alucinada (`COD-002`) | Baixo | **P0** |
| Falha em agente de competência marca avaliação como `incompleta` (sem nota 0 falsa) | `T-21` | Integração | Evitar penalização de até 200 pts por falha de API (`COD-001`) | Baixo | **P0** |
| Escape de tag de fechamento `</redacao>` e `</tema>` no texto/tema do aluno | `T-31` / `ADV-03` | Unitário / Seg. | Impedir escape do bloco XML contra prompt injection (`COD-003`) | Baixo | **P0** |
| Normalização de caracteres invisíveis (`\u200b`, `\ufeff`), aspas curvas e emojis/HTML | `T-12` / `T-14` | Unitário | Garantir invariância de formatação (`R-12`, `COD-006`) | Baixo | **P1** |
| Invariância de duas correções consecutivas na mesma sessão (`session.state` limpo) | `T-23` | Integração | Garantir que a 2ª redação não herde notas/alertas da 1ª | Baixo | **P1** |
| Curto-circuito verificado por contagem de chamadas: anulação faz `0` chamadas a `C1..C5` | `T-20` | Integração | Garantir economia de cota e isolamento em redações anuladas | Baixo | **P1** |

---

## 9. Desempenho, Custo, Segurança e Privacidade (Fases 8 e 9)

- **Consumo de cota no Free Tier (`PERF-01`, `PERF-06`):**
  - Redação válida aciona **7 chamadas LLM** (`1` anulação + `5` competências + `1` feedback) e ~**21,2k tokens** no total **[MEDIDO/INFERIDO]**.
  - Redação anulada deterministicamente (< 8 linhas / em branco / cópia massiva) aciona **0 chamadas LLM** **[MEDIDO]**.
  - Redação anulada semanticamente (fuga ao tema) aciona **1 chamada LLM** **[MEDIDO]**.
  - No Gemini Free Tier (~15 RPM / 1.500 RPD), a cota diária comporta até **~210 redações completas/dia**, e o limite por minuto comporta **~2 redações completas/minuto** **[INFERIDO]**.
- **Privacidade e Licenças (`PRV-01`, `PRV-02`, `LIC-03`):**
  - O README deve alertar explicitamente que, no **Google AI Studio Free Tier**, os textos enviados podem ser revisados pelo provedor para melhoria de modelos, recomendando `ENEM_MODELO=ollama_chat/...` quando houver dados pessoais/sensíveis de estudantes.
  - Quando `ENEM_SALVAR_EXECUCOES=true`, as execuções ficam salvas localmente em `data/execucoes/historico.jsonl` (diretório já ignorado no `.gitignore`) **[LIDO]**.

---

## 10. Tabela de Decisão Go/No-Go (Apêndice H) e Plano de Ação Priorizado (Fase 10)

### 10.1 Status nos Critérios Bloqueantes (Apêndice H)
| Dimensão | Meta Mínima (Exploratório) | Valor Atual Medido/Lido | Status |
|---|---|---|---|
| Testes das regras (`R-01`…`R-12`) | 100% passando e sem falhas de contrato | `R-01` (`COD-002`) e `CON-04` (`COD-001`) falham na auditoria de código | ❌ **BLOQUEANTE** |
| Cobertura de ramos em módulos de regra | ≥ 70% (desejável ≥ 85%) | **96,05% geral / 95% no consolidador** | ✅ Atendido **[MEDIDO]** |
| Nota fora da escala / total ≠ soma | 0 casos | Soma em código OK, mas `ajustar_nivel` aceita nota fora da escala sem erro | ❌ **BLOQUEANTE** |
| Segredos no repositório/histórico | 0 | **0 segredos** | ✅ Atendido **[MEDIDO]** |
| Escape de delimitador adversarial (`ADV-03`) | Sem escape de `<redacao>` | `</redacao>` não escapado em `montar_xml_entrada` (`COD-003`) | ⚠️ Alto Risco |
| Métricas AES no Golden Set (QWK / MAE / Viés) | Superar baselines com IC95% | **Não medido** (`golden_set` ausente) | ⚠️ Pendente (Fase 4 do roadmap) |

### 10.2 Top 5 Ações Prioritárias (com Critério de Aceitação Verificável)

| # | Ação | Achados | Esforço | Impacto | Critério de Aceitação Verificável |
|---|---|---|---|---|---|
| **1** | **Tratar falha de agente de competência como `incompleta: True`** em `AvaliacaoFinal` e `consolidador.py` (nunca atribuir `nota=0` por falha técnica). | `COD-001`, `CON-04`, `T-21` | P (30 min) | **Crítico** | Teste `T-21` simula falha em `AvaliacaoC3` e verifica `av.incompleta is True` e aviso explícito no Markdown. |
| **2** | **Tornar a validação de `nota` e `MotivoAnulacao.motivo` estrita** nos schemas Pydantic dos agentes (`Literal[0,40,80,120,160,200]` e `Literal[...]` de motivos). | `COD-002`, `COD-005`, `SCH-01`, `T-01`, `T-05` | P (30 min) | **Alto** | Testes `T-01` e `T-05` confirmam que `nota=150`, `nota=-40` e `motivo="invalido"` levantam `ValidationError`. |
| **3** | **Sanitizar tags XML reservadas (`</redacao>`, `</tema>`) e caracteres de largura zero (`\u200b-\u200d`, `\ufeff`)** em `montar_xml_entrada` e `normalizar_texto`. | `COD-003`, `COD-006`, `SEC-03`, `T-12`, `T-31` | P (20 min) | **Alto** | Testes `T-31` e `T-12` verificam que `</redacao>` no texto do aluno é escapado e `\u200b` é removido. |
| **4** | **Configurar `num_ctx` explícito (padrão `8192`) para modelos Ollama no `LiteLlm`** e adicionar seção de Privacidade/Limitações no README. | `COD-004`, `CFG-03`, `PRV-01`, `PRV-02` | P (20 min) | **Alto** | `ENEM_NUM_CTX` presente em `Config` e repassado ao `LiteLlm` quando o modelo for `ollama*`. |
| **5** | **Construir script `eval/run_eval.py` + conjunto `stress` sintético (SYN-01..35) e `golden_set` inicial** para destravar a Fase 7 (QWK, MAE, viés com IC95%). | `PRE-05`, `Fase 7` | M (2–4 h) | **Alto** | `uv run python -m eval.run_eval` gera `results.jsonl` + relatório com QWK, MAE e IC95% bootstrap. |
