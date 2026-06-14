"""
Consumer de eventos de acesso (Ingestao - origem streaming -> Bronze).

Consome os eventos publicados pelo producer e os grava na camada Bronze como
uma tabela de eventos (Parquet/CSV). Em producao consome de um topico Kafka;
no fallback, le e consolida os arquivos JSONL da fila em arquivo.

Os eventos seguem o mesmo fluxo Silver/Gold do caminho batch depois.
"""
from __future__ import annotations

import json
import time

import pandas as pd

from config import settings
from src import storage
from src.governance import lineage
from src.monitoring.logger import get_logger
from src.monitoring.metrics import RunMetrics
from src.quality import checks

log = get_logger("ingestao.consumer")


def _consumir_kafka(timeout_ms: int = 3000) -> list[dict]:
    from kafka import KafkaConsumer

    consumer = KafkaConsumer(
        settings.KAFKA_TOPIC,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP,
        auto_offset_reset="earliest",
        consumer_timeout_ms=timeout_ms,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        group_id="bibliodata-consumer",
    )
    return [msg.value for msg in consumer]


def _consumir_fila_arquivo() -> list[dict]:
    eventos = []
    arquivos = sorted(settings.STREAM_QUEUE.glob("acessos_*.jsonl"))
    consumidos = settings.STREAM_QUEUE / "_consumidos"
    consumidos.mkdir(exist_ok=True)
    for arq in arquivos:
        with open(arq, encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if linha:
                    eventos.append(json.loads(linha))
        # arquiva o arquivo ja lido -> evita reconsumir/inflar a contagem
        import shutil
        shutil.move(str(arq), str(consumidos / arq.name))
    return eventos


def consumir(metrics: RunMetrics | None = None) -> int:
    t0 = time.time()
    if settings.STREAM_BACKEND == "kafka":
        try:
            log.info("Consumindo eventos do topico Kafka '%s'", settings.KAFKA_TOPIC)
            eventos = _consumir_kafka()
        except Exception as exc:
            log.warning("Kafka indisponivel (%s). Lendo da fila em arquivo.",
                        type(exc).__name__)
            eventos = _consumir_fila_arquivo()
    else:
        log.info("Consumindo eventos da fila em arquivo")
        eventos = _consumir_fila_arquivo()

    if not eventos:
        log.warning("Nenhum evento de acesso para consumir")
        if metrics:
            metrics.registrar_estagio("ingestao_stream", 0, 0, time.time() - t0)
        return 0

    df = pd.DataFrame(eventos)
    rel = checks.validar(df, "acessos")
    log.info(
        "Bronze/acessos: %d eventos | qualidade %.2f%%",
        len(df), rel.taxa_aprovacao * 100,
    )

    storage.escrever_bronze(df, "acessos", fonte=settings.STREAM_BACKEND)
    lineage.registrar("stream/acessos", "bronze/acessos", "kafka_consumer", len(df))

    if metrics:
        metrics.registrar_estagio(
            "ingestao_stream",
            linhas_entrada=len(df),
            linhas_saida=len(df),
            duracao_seg=time.time() - t0,
            taxa_qualidade=round(rel.taxa_aprovacao, 4),
        )
    return len(df)


if __name__ == "__main__":
    consumir()
