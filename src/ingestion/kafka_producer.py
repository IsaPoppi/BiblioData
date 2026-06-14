"""
Producer de eventos de acesso (Ingestao - origem streaming).

Gera eventos JSON (busca, clique, visualizacao) e os publica. Em producao
publica em um topico Kafka (Redpanda via docker-compose); sem Kafka, escreve
em uma fila baseada em arquivo (data/stream_queue/) que o consumer le -- mesma
semantica de produtor/consumidor desacoplados, sem exigir infra.
"""
from __future__ import annotations

import json
import random
import time
import uuid
from datetime import datetime

from config import settings
from src.monitoring.logger import get_logger

log = get_logger("ingestao.producer")
random.seed(settings.SEED)

TIPOS = ["busca", "clique", "visualizacao"]


def _evento() -> dict:
    return {
        "id_evento": uuid.uuid4().hex,
        "id_usuario": random.randint(1, settings.N_USUARIOS),
        "tipo_evento": random.choice(TIPOS),
        "id_livro": random.randint(1, settings.N_LIVROS),
        "timestamp_evento": datetime.now().isoformat(timespec="seconds"),
    }


def _producer_kafka():
    from kafka import KafkaProducer

    return KafkaProducer(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )


def _produzir_arquivo(n: int) -> int:
    from datetime import datetime as _dt
    arquivo = settings.STREAM_QUEUE / f"acessos_{_dt.now():%Y%m%d_%H%M%S}.jsonl"
    log.info("Publicando %d eventos na fila em arquivo -> %s", n, arquivo.name)
    with open(arquivo, "w", encoding="utf-8") as f:
        for _ in range(n):
            f.write(json.dumps(_evento(), ensure_ascii=False) + "\n")
    return n


def produzir(n: int | None = None) -> int:
    n = n or settings.N_EVENTOS_STREAM

    if settings.STREAM_BACKEND == "kafka":
        try:
            log.info("Publicando %d eventos no topico Kafka '%s'", n, settings.KAFKA_TOPIC)
            producer = _producer_kafka()
            for _ in range(n):
                producer.send(settings.KAFKA_TOPIC, _evento())
            producer.flush()
            return n
        except Exception as exc:
            # Broker indisponivel -> degrada para fila em arquivo (resiliencia)
            log.warning("Kafka indisponivel (%s). Caindo para fila em arquivo.",
                        type(exc).__name__)
            return _produzir_arquivo(n)

    return _produzir_arquivo(n)


if __name__ == "__main__":
    produzir()
