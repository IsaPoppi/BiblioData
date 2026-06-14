"""
Agendador do pipeline BiblioData (camada de Orquestracao).

Demonstra o AGENDAMENTO das tarefas (alem do encadeamento feito em
pipeline.py). Atende ao item da avaliacao: "como as tarefas sao agendadas".

Em producao pode usar APScheduler (suporta expressoes cron); sem APScheduler
instalado, usa um laco simples baseado na biblioteca padrao -- zero dependencia.

Uso:
    python agendador.py --once                 # roda uma vez e sai
    python agendador.py --intervalo 3600       # roda a cada 1 hora
    python agendador.py --cron "0 3 * * *"     # 03:00 todo dia (precisa APScheduler)

Alternativa nativa do Windows: Agendador de Tarefas executando
    do projeto, o python .venv/Scripts/python.exe com pipeline.py.
No Linux/Mac, um cron equivalente:
    0 3 * * * /caminho/.venv/bin/python /caminho/pipeline.py
"""
from __future__ import annotations

import argparse
import time

import pipeline
from src.monitoring.logger import get_logger

log = get_logger("agendador")


def _rodar_uma_vez():
    log.info("Disparo agendado do pipeline")
    resultado = pipeline.rodar(gerar=True)
    log.info("Execucao concluida: status=%s", resultado["status"])
    return resultado


def _loop_intervalo(intervalo_seg: int):
    log.info("Agendador ativo: a cada %d segundos (Ctrl+C para parar)", intervalo_seg)
    while True:
        _rodar_uma_vez()
        log.info("Aguardando %d s ate o proximo disparo...", intervalo_seg)
        time.sleep(intervalo_seg)


def _loop_cron(expr: str):
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        log.error("Modo --cron exige APScheduler. Instale com: pip install apscheduler")
        log.error("Como alternativa, use --intervalo (sem dependencias).")
        return
    sched = BlockingScheduler()
    sched.add_job(_rodar_uma_vez, CronTrigger.from_crontab(expr))
    log.info("Agendador cron ativo: '%s' (Ctrl+C para parar)", expr)
    try:
        sched.start()
    except KeyboardInterrupt:
        log.info("Agendador encerrado.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agendador do pipeline BiblioData")
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--once", action="store_true", help="executa uma vez e sai")
    grupo.add_argument("--intervalo", type=int, metavar="SEG",
                       help="executa em laco a cada SEG segundos")
    grupo.add_argument("--cron", type=str, metavar="EXPR",
                       help="agenda por expressao cron (requer APScheduler)")
    args = parser.parse_args()

    try:
        if args.cron:
            _loop_cron(args.cron)
        elif args.intervalo:
            _loop_intervalo(args.intervalo)
        else:
            _rodar_uma_vez()  # --once e o padrao
    except KeyboardInterrupt:
        log.info("Agendador interrompido pelo usuario.")
