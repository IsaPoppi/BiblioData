"""
Monitor de saúde do BiblioData (CLI).

Responde "como sei se está tudo funcionando?" e "e se parar?": executa o
health check, imprime um relatório com semáforo (OK / ALERTA / CRÍTICO) e
encerra com código de saída != 0 quando há problema — o que permite agendá-lo
(Agendador de Tarefas / cron) para alertar automaticamente.

Uso:
    python monitorar.py                # verifica e imprime o status
    python monitorar.py --recuperar    # se o banco Gold estiver fora, reconstrói

Código de saída: 0 = OK, 1 = alerta, 2 = crítico (útil para automação).
"""
from __future__ import annotations

import argparse
import sys

from src.monitoring import health

_SIMBOLO = {"ok": "🟢 OK     ", "alerta": "🟡 ALERTA ", "critico": "🔴 CRÍTICO"}
_COD = {"ok": 0, "alerta": 1, "critico": 2}


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor de saúde do BiblioData")
    parser.add_argument("--recuperar", action="store_true",
                        help="se o banco Gold estiver indisponível, reconstrói a partir da Silver")
    args = parser.parse_args()

    rel = health.verificar()

    print("=" * 60)
    print(f"SAÚDE DO SISTEMA — {rel['ts']}  |  GERAL: {_SIMBOLO[rel['status_geral']].strip()}")
    print("=" * 60)
    for item in rel["itens"]:
        print(f"  {_SIMBOLO[item['status']]}  {item['nome']:<18} {item['detalhe']}")
    print("=" * 60)

    if args.recuperar and rel["status_geral"] != "ok":
        print("\nTentando recovery...")
        if health.recuperar():
            print("Recovery concluído. Verificando novamente:\n")
            rel = health.verificar()
            for item in rel["itens"]:
                print(f"  {_SIMBOLO[item['status']]}  {item['nome']:<18} {item['detalhe']}")

    return _COD.get(rel["status_geral"], 2)


if __name__ == "__main__":
    sys.exit(main())
