"""
Orquestrador do pipeline BiblioData.

Encadeia as tarefas do ciclo de vida com:
    - dependencias explicitas (mini-DAG sequencial)
    - RETRIES com backoff (nao depende do caminho feliz)
    - QUALITY GATE: interrompe a promocao para Gold se a qualidade reprovar
    - coleta de metricas e geracao de catalogo/linhagem ao final
    - relatorio de saude impresso no console

Optou-se por um orquestrador proprio e leve no lugar do Airflow (ver README,
secao de mudancas as-built). A interface e a mesma de um agendador: tarefas,
dependencias, retries e observabilidade.

Uso:
    python pipeline.py            # executa o pipeline completo
    python pipeline.py --no-gen   # reaproveita os CSVs ja gerados
"""
from __future__ import annotations

import argparse
import sys
import time

from config import settings
from src.governance import catalog
from src.monitoring.logger import get_logger, novo_run_id
from src.monitoring.metrics import RunMetrics

log = get_logger("orquestrador")


def _executar_com_retry(nome: str, func, run_metrics: RunMetrics, **kwargs):
    """Executa uma tarefa com ate MAX_RETRIES tentativas e backoff."""
    tentativa = 0
    while True:
        try:
            return func(**kwargs)
        except Exception as exc:
            tentativa += 1
            if tentativa > settings.MAX_RETRIES:
                run_metrics.alerta("CRITICAL", f"Tarefa '{nome}' falhou apos "
                                   f"{settings.MAX_RETRIES} retries: {exc}")
                raise
            espera = settings.RETRY_BACKOFF_SEG * tentativa
            log.warning("Tarefa '%s' falhou (tentativa %d): %s | retry em %.1fs",
                        nome, tentativa, exc, espera)
            run_metrics.alerta("WARN", f"Retry de '{nome}' (tentativa {tentativa})")
            time.sleep(espera)


def rodar(gerar: bool = True) -> dict:
    run_id = novo_run_id()
    metrics = RunMetrics(run_id)
    log.info("=" * 64)
    log.info("INICIANDO PIPELINE | run_id=%s", run_id)
    log.info("Config: %s", settings.resumo())
    log.info("=" * 64)

    # imports tardios para o logger configurar primeiro
    from src.ingestion import gerar_dados, ingestao_batch, kafka_consumer, kafka_producer
    from src.transform import transformar_gold, transformar_silver

    try:
        # 1. Geracao de dados sinteticos (origem)
        if gerar:
            _executar_com_retry("gerar_dados", gerar_dados.main, metrics)
            _executar_com_retry("kafka_producer", kafka_producer.produzir, metrics)

        # 2. Ingestao batch + streaming -> Bronze
        _executar_com_retry("ingestao_batch", ingestao_batch.ingerir, metrics, metrics=metrics)
        _executar_com_retry("ingestao_stream", kafka_consumer.consumir, metrics, metrics=metrics)

        # 3. Transformacao Silver (limpeza + quarentena + LGPD + quality gate)
        res_silver = _executar_com_retry(
            "transformar_silver", transformar_silver.transformar, metrics, metrics=metrics
        )

        # ---- RETROALIMENTACAO: quality gate decide a promocao ----
        if not res_silver["quality_gate_ok"]:
            log.error("QUALITY GATE REPROVADO -> Gold NAO sera atualizada.")
            metrics.finalizar(status="bloqueado_quality_gate")
            _gerar_governanca(metrics)
            _relatorio_saude(metrics)
            return {"status": "bloqueado_quality_gate", "run_id": run_id}

        # 4. Transformacao Gold (agregacoes para consumo)
        _executar_com_retry(
            "transformar_gold", transformar_gold.transformar, metrics, metrics=metrics
        )

        # 5. Governanca: catalogo + linhagem
        _gerar_governanca(metrics)

        registro = metrics.finalizar(status="sucesso")
        _relatorio_saude(metrics)
        return {"status": "sucesso", "run_id": run_id, "metricas": registro}

    except Exception as exc:
        log.exception("Pipeline interrompido: %s", exc)
        metrics.finalizar(status="falha")
        _relatorio_saude(metrics)
        return {"status": "falha", "run_id": run_id, "erro": str(exc)}


def _gerar_governanca(metrics: RunMetrics) -> None:
    t0 = time.time()
    profile = catalog.gerar_catalogo()
    catalog.gerar_catalogo_dados()  # catálogo de dados (tipo, descrição, setor)
    if profile.get("deriva_schema"):
        for aviso in profile["deriva_schema"]:
            metrics.alerta("WARN", f"Deriva de schema: {aviso}")
    metrics.registrar_estagio("governanca_catalogo", duracao_seg=time.time() - t0)
    log.info("Catalogo e linhagem atualizados em catalog/")


def _relatorio_saude(metrics: RunMetrics) -> None:
    log.info("=" * 64)
    log.info("RELATORIO DE SAUDE | run_id=%s | status=%s", metrics.run_id, metrics.status)
    for estagio, m in metrics.estagios.items():
        tq = m.get("taxa_qualidade")
        tq_str = f" | qualidade {tq:.2%}" if tq is not None else ""
        quar = f" | quarentena {m['quarentena']}" if m.get("quarentena") else ""
        log.info("  %-22s in=%-7d out=%-7d %.2fs%s%s",
                 estagio, m["linhas_entrada"], m["linhas_saida"],
                 m["duracao_seg"], tq_str, quar)
    if metrics.alertas:
        log.info("  ALERTAS:")
        for a in metrics.alertas:
            log.info("    [%s] %s", a["severidade"], a["mensagem"])
    log.info("=" * 64)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline BiblioData")
    parser.add_argument("--no-gen", action="store_true",
                        help="reaproveita dados ja gerados (nao chama Faker)")
    args = parser.parse_args()
    resultado = rodar(gerar=not args.no_gen)
    sys.exit(0 if resultado["status"] in ("sucesso", "bloqueado_quality_gate") else 1)
