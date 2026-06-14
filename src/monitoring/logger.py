"""
Logging estruturado do pipeline (camada de Monitoramento).

Cada execucao recebe um run_id e escreve em logs/pipeline.log e no console.
Mensagens carregam o estagio e o run_id para rastreabilidade.
"""
from __future__ import annotations

import logging
import sys
import uuid
from datetime import datetime

from config import settings

_LOG_FILE = settings.LOGS / "pipeline.log"


def novo_run_id() -> str:
    """Gera um identificador unico e legivel para a execucao."""
    return datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6]


def get_logger(estagio: str, run_id: str | None = None) -> logging.Logger:
    logger = logging.getLogger(f"bibliodata.{estagio}")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)-28s | %(message)s",
        datefmt="%H:%M:%S",
    )

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    fh = logging.FileHandler(_LOG_FILE, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    logger.propagate = False
    return logger
