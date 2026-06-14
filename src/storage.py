"""
Abstracao de armazenamento do Data Lake (camadas medalhao).

Le e escreve tabelas nas camadas raw/bronze/silver/gold sem que o resto do
codigo precise saber o formato fisico. Em producao usa Parquet (pyarrow);
sem pyarrow, cai automaticamente para CSV -- as transformacoes nao mudam.

Ao escrever na Bronze, adiciona colunas de controle (data de ingestao e fonte),
preservando a regra de ouro do medalhao: a Bronze e imutavel e auditavel.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from config import settings

_LAYER_DIR = {
    "raw": settings.RAW,
    "bronze": settings.BRONZE,
    "silver": settings.SILVER,
    "gold": settings.GOLD,
    "quarantine": settings.QUARANTINE,
}


def _caminho(layer: str, nome: str) -> Path:
    ext = "parquet" if settings.STORAGE_FORMAT == "parquet" else "csv"
    return _LAYER_DIR[layer] / f"{nome}.{ext}"


def escrever(df: pd.DataFrame, layer: str, nome: str) -> Path:
    caminho = _caminho(layer, nome)
    if settings.STORAGE_FORMAT == "parquet":
        df.to_parquet(caminho, index=False)
    else:
        df.to_csv(caminho, index=False)
    return caminho


def escrever_bronze(df: pd.DataFrame, nome: str, fonte: str) -> Path:
    """Grava na Bronze adicionando metadados de ingestao (controle/auditoria)."""
    df = df.copy()
    df["_data_ingestao"] = datetime.now().isoformat(timespec="seconds")
    df["_fonte"] = fonte
    return escrever(df, "bronze", nome)


def ler(layer: str, nome: str) -> pd.DataFrame:
    caminho = _caminho(layer, nome)
    if not caminho.exists():
        raise FileNotFoundError(f"Tabela ausente: {layer}/{nome} ({caminho})")
    if settings.STORAGE_FORMAT == "parquet":
        return pd.read_parquet(caminho)
    return pd.read_csv(caminho)


def existe(layer: str, nome: str) -> bool:
    return _caminho(layer, nome).exists()


def quarentena(df: pd.DataFrame, nome: str, motivo: str) -> Path:
    """Desvia registros reprovados para a quarentena, anotando o motivo.

    Retroalimentacao: nada e descartado silenciosamente. Os registros ficam
    disponiveis para inspecao e reprocessamento a partir da Bronze.
    """
    df = df.copy()
    df["_motivo_quarentena"] = motivo
    df["_data_quarentena"] = datetime.now().isoformat(timespec="seconds")
    caminho = _caminho("quarantine", f"{nome}_{datetime.now():%Y%m%d_%H%M%S}")
    if settings.STORAGE_FORMAT == "parquet":
        df.to_parquet(caminho, index=False)
    else:
        df.to_csv(caminho, index=False)
    return caminho
