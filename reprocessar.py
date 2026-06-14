"""
Reprocessamento da quarentena (retroalimentacao de qualidade).

Fecha o ciclo: registros reprovados na Silver vao para a quarentena com o
motivo anotado; este script permite triar e REINTEGRAR ao pipeline os que
voltarem a ser validos (apos correcao externa ou ajuste de regra).

Fluxo:
    1. le os arquivos de quarentena de um dataset;
    2. revalida contra os contratos atuais (usando a Bronze como referencia
       de integridade);
    3. os que agora passam sao ANEXADOS a Bronze (que e append-only) e serao
       promovidos a Silver/Gold na proxima execucao do pipeline;
    4. os que ainda falham voltam para uma nova quarentena;
    5. os arquivos ja triados sao movidos para quarantine/_processadas/.

Uso:
    python reprocessar.py listar
    python reprocessar.py <dataset>     # ex.: python reprocessar.py usuarios
"""
from __future__ import annotations

import argparse
import shutil
from collections import defaultdict

import pandas as pd

from config import settings
from config.data_contracts import CONTRATOS, DATASETS_BATCH
from src import storage
from src.monitoring.logger import get_logger
from src.quality import checks

log = get_logger("reprocessar")

_PROCESSADAS = settings.QUARANTINE / "_processadas"


def _arquivos_por_dataset() -> dict[str, list]:
    grupos = defaultdict(list)
    for arq in settings.QUARANTINE.glob("*"):
        if arq.is_dir():
            continue
        for ds in CONTRATOS:
            if arq.name.startswith(ds + "_"):
                grupos[ds].append(arq)
                break
    return grupos


def listar() -> None:
    grupos = _arquivos_por_dataset()
    if not grupos:
        log.info("Quarentena vazia. Nada a reprocessar.")
        return
    log.info("Conteudo da quarentena:")
    for ds, arquivos in grupos.items():
        total = 0
        motivos = set()
        for arq in arquivos:
            df = pd.read_csv(arq) if arq.suffix == ".csv" else pd.read_parquet(arq)
            total += len(df)
            if "_motivo_quarentena" in df.columns:
                motivos.update(df["_motivo_quarentena"].unique().tolist())
        log.info("  %-14s %d registros em %d arquivo(s) | motivos: %s",
                 ds, total, len(arquivos), ", ".join(motivos))


def reprocessar(dataset: str) -> None:
    if dataset not in CONTRATOS:
        log.error("Dataset desconhecido: %s", dataset)
        return

    arquivos = _arquivos_por_dataset().get(dataset, [])
    if not arquivos:
        log.info("Nenhum registro em quarentena para '%s'.", dataset)
        return

    # carrega e junta os registros em quarentena
    partes = [pd.read_csv(a) if a.suffix == ".csv" else pd.read_parquet(a) for a in arquivos]
    df = pd.concat(partes, ignore_index=True)
    df = df.drop(columns=[c for c in df.columns if c.startswith("_")], errors="ignore")
    log.info("Reprocessando %d registros de '%s'", len(df), dataset)

    # referencias atuais da Bronze para checagem de FK
    refs = {n: storage.ler("bronze", n) for n in DATASETS_BATCH if storage.existe("bronze", n)}

    rel = checks.validar(df, dataset, refs=refs)
    validos = df.drop(index=list(rel.indices_invalidos))
    invalidos = df.loc[sorted(rel.indices_invalidos)]

    # reintegra os validos a Bronze (append-only)
    if len(validos):
        if storage.existe("bronze", dataset):
            base = storage.ler("bronze", dataset)
            base = base.drop(columns=[c for c in base.columns if c.startswith("_")], errors="ignore")
            combinado = pd.concat([base, validos], ignore_index=True).drop_duplicates()
        else:
            combinado = validos
        storage.escrever_bronze(combinado, dataset, fonte="reprocessamento")
        log.info("Reintegrados %d registros a bronze/%s (serao promovidos no proximo run)",
                 len(validos), dataset)
    else:
        log.info("Nenhum registro recuperavel desta vez.")

    # os que ainda falham voltam para a quarentena
    if len(invalidos):
        caminho = storage.quarentena(invalidos, dataset, motivo="ainda_invalido_apos_reprocessamento")
        log.warning("%d registros continuam invalidos -> %s", len(invalidos), caminho.name)

    # move os arquivos ja triados para nao reprocessar de novo
    _PROCESSADAS.mkdir(exist_ok=True)
    for arq in arquivos:
        shutil.move(str(arq), str(_PROCESSADAS / arq.name))
    log.info("Arquivos triados movidos para %s", _PROCESSADAS.name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reprocessamento da quarentena")
    parser.add_argument("alvo", help="'listar' ou o nome do dataset (ex.: usuarios)")
    args = parser.parse_args()
    if args.alvo == "listar":
        listar()
    else:
        reprocessar(args.alvo)
