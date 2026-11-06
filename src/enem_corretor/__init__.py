"""CLI e pacote principal do Corretor de Redação ENEM com Google ADK."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .agent import corrigir_redacao, corrigir_redacao_async, root_agent
from .agents.consolidador import formatar_relatorio_markdown
from .agents.preanalise import executar_preanalise
from .config import Config, carregar_config
from .schemas.entrada import EntradaRedacao
from .schemas.saida import AvaliacaoFinal

__all__ = [
    "AvaliacaoFinal",
    "Config",
    "EntradaRedacao",
    "carregar_config",
    "corrigir_redacao",
    "corrigir_redacao_async",
    "executar_preanalise",
    "formatar_relatorio_markdown",
    "main",
    "root_agent",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="enem-corretor",
        description="Corretor local de redações do ENEM com Google ADK.",
    )
    parser.add_argument(
        "--tema",
        type=str,
        help="Frase-tema da proposta de redação.",
    )
    parser.add_argument(
        "--arquivo",
        type=Path,
        help="Arquivo .txt (texto da redação) ou .json ({tema, redacao, motivadores}).",
    )
    parser.add_argument(
        "--texto",
        type=str,
        help="Texto da redação diretamente na linha de comando.",
    )
    parser.add_argument(
        "--modelo",
        type=str,
        default=None,
        help="Sobrescreve o modelo (ex.: gemini-3.5-flash ou ollama_chat/qwen2.5:7b).",
    )
    parser.add_argument(
        "--apenas-preanalise",
        action="store_true",
        help="Executa somente a pré-análise determinística (sem chamar LLM).",
    )
    parser.add_argument(
        "--saida-json",
        type=Path,
        default=None,
        help="Salva a saída estruturada completa (`AvaliacaoFinal`) neste caminho JSON.",
    )
    parser.add_argument(
        "--saida-md",
        type=Path,
        default=None,
        help="Salva o relatório em Markdown neste caminho.",
    )

    args = parser.parse_args(argv)

    motivadores: list[str] = []
    titulo: str | None = None
    tema = args.tema or ""
    redacao = args.texto or ""

    if args.arquivo:
        conteudo = args.arquivo.read_text(encoding="utf-8")
        if args.arquivo.suffix.lower() == ".json":
            dados = json.loads(conteudo)
            tema = tema or dados.get("tema", "")
            redacao = redacao or dados.get("redacao") or dados.get("texto") or ""
            motivadores = list(dados.get("motivadores") or [])
            titulo = dados.get("titulo")
        else:
            redacao = conteudo

    if not redacao and not sys.stdin.isatty():
        redacao = sys.stdin.read()

    if not redacao.strip():
        parser.error("Informe uma redação via --arquivo, --texto ou stdin.")

    entrada = EntradaRedacao(
        tema=tema or "(tema não informado)",
        redacao=redacao,
        motivadores=motivadores,
        titulo=titulo,
    )

    if args.apenas_preanalise:
        pre = executar_preanalise(entrada)
        pre_limpo = {
            k: v
            for k, v in pre.items()
            if k not in {"redacao_normalizada", "redacao_numerada"}
        }
        print(json.dumps(pre_limpo, ensure_ascii=False, indent=2))
        return 0

    avaliacao, relatorio = corrigir_redacao(
        entrada, modelo_override=args.modelo
    )
    print(relatorio)

    if args.saida_json:
        args.saida_json.parent.mkdir(parents=True, exist_ok=True)
        args.saida_json.write_text(
            json.dumps(avaliacao.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    if args.saida_md:
        args.saida_md.parent.mkdir(parents=True, exist_ok=True)
        args.saida_md.write_text(relatorio, encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
