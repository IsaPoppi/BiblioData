"""
Ingestao batch (CSV -> Bronze).

Le os CSVs de data/raw/, valida contra os contratos, registra metricas e
linhagem, e grava na Bronze como Parquet (ou CSV no fallback) com colunas de
controle. A Bronze e IMUTAVEL: nenhum dado e limpo aqui -- so anexado.

Esta funcao e chamada pelo orquestrador, que trata retries e quality gates.
"""
from __future__ import annotations

import time

import pandas as pd

from config.data_contracts import DATASETS_BATCH
from config import settings
from src import storage
from src.governance import lineage
from src.monitoring.logger import get_logger
from src.monitoring.metrics import RunMetrics
from src.quality import checks

log = get_logger("ingestao.batch")


def ingerir(metrics: RunMetrics | None = None) -> dict[str, int]:
    t0 = time.time()
    contagem = {}
    refs: dict[str, pd.DataFrame] = {}

    # Primeiro carrega as referencias (usuarios/livros) para checagem de FK
    for nome in DATASETS_BATCH:
        df = pd.read_csv(settings.RAW / f"{nome}.csv")
        refs[nome] = df

    total_invalidos = 0
    for nome in DATASETS_BATCH:
        df = refs[nome]
        rel = checks.validar(df, nome, refs=refs)
        log.info(
            "Bronze/%s: %d linhas | qualidade %.2f%% | %d invalidos",
            nome, len(df), rel.taxa_aprovacao * 100, len(rel.indices_invalidos),
        )
        total_invalidos += len(rel.indices_invalidos)

        storage.escrever_bronze(df, nome, fonte=f"raw/{nome}.csv")
        lineage.registrar(f"raw/{nome}", f"bronze/{nome}", "ingestao_batch", len(df))
        contagem[nome] = len(df)

    if metrics:
        total = sum(contagem.values())
        metrics.registrar_estagio(
            "ingestao_batch",
            linhas_entrada=total,
            linhas_saida=total,
            duracao_seg=time.time() - t0,
            extra={"invalidos_detectados": total_invalidos},
        )
        metrics.checar_deriva_volume("ingestao_batch", sum(contagem.values()))

    return contagem


if __name__ == "__main__":
    ingerir()
