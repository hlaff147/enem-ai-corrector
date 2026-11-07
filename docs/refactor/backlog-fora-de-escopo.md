# Backlog Fora de Escopo da Refatoração de Agentes

> **Regra de Ouro da Refatoração:** Refatorar é alterar a estrutura interna sem alterar o comportamento observável. Oportunidades de novas funcionalidades, melhorias de prompts ou novos modelos identificadas durante o trabalho são catalogadas aqui para implementação futura.

---

## Itens Registrados

| ID | Área / Módulo | Descrição da Oportunidade | Prioridade Futura | Justificativa de Exclusão da Refatoração Atual |
|---|---|---|---|---|
| **OPO-01** | `tools/gramatica.py` | Expansão das heurísticas de detecção gramatical offline (mais regras de crase, concordância nominal e regência verbal sem depender de servidor LanguageTool externo). | Média | Mudança de comportamento e acurácia de C1; deve ser testada e calibrada separadamente. |
| **OPO-02** | `prompts/` | Refinamento dos prompts com técnica de Few-Shot exemplificando desvios de C1 e repertório produtivo de C2. | Alta | Afeta a distribuição de notas do modelo; requer re-avaliação do golden set de redações nota 1000. |
| **OPO-03** | `vectorstore` | Integração com banco vetorial (RAG) de repertórios socioculturais catalogados (pensadores, alusões históricas, legislação) para suporte a C2/C3. | Baixa | Funcionalidade nova; excede o escopo da organização de agentes e sub-agentes. |
| **OPO-04** | OCR / Imagens | Extração de texto a partir de fotos de espelhos de redação manuscrita via multimodalidade. | Baixa | Feature planejada para fase futura do produto (v2). |
| **OPO-05** | UI / Dashboard | Interface web interativa em FastAPI / Streamlit / React com histórico e gráficos de radar de competências para o estudante. | Média | Pertence à camada de apresentação/produto. |
| **OPO-06** | `rubricas/` | Atualização anual automatizada dos parâmetros da Cartilha do Participante quando o INEP publicar novas diretrizes. | Média | Manutenção periódica de conteúdo oficial. |
