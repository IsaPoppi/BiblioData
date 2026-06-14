"""
Configuracoes centrais do BiblioData.

Toda a stack e parametrizada aqui. O ponto-chave de engenharia: cada backend
"de producao" tem um fallback automatico para que o pipeline rode em qualquer
maquina, mesmo sem pyarrow/duckdb/kafka instalados. Isso e proposital -- faz
parte de NAO depender apenas do "caminho feliz".

Ordem de prioridade da configuracao:
    1. Variavel de ambiente (.env / export)
    2. Auto-deteccao (a lib esta instalada? o servico esta no ar?)
    3. Fallback seguro (CSV / SQLite / fila em arquivo)
"""
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Caminhos
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
BRONZE = DATA / "bronze"
SILVER = DATA / "silver"
GOLD = DATA / "gold"
QUARANTINE = DATA / "quarantine"
STREAM_QUEUE = DATA / "stream_queue"
CATALOG = ROOT / "catalog"
LOGS = ROOT / "logs"

for _p in (RAW, BRONZE, SILVER, GOLD, QUARANTINE, STREAM_QUEUE, CATALOG, LOGS):
    _p.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Reprodutibilidade
# ---------------------------------------------------------------------------
SEED = int(os.getenv("BIBLIODATA_SEED", "42"))

# Volumes sinteticos (sobrescritiveis para testes rapidos)
N_USUARIOS = int(os.getenv("N_USUARIOS", "10000"))
N_LIVROS = int(os.getenv("N_LIVROS", "5000"))
N_EMPRESTIMOS = int(os.getenv("N_EMPRESTIMOS", "20000"))
N_AVALIACOES = int(os.getenv("N_AVALIACOES", "4000"))
N_EVENTOS_STREAM = int(os.getenv("N_EVENTOS_STREAM", "2000"))


# ---------------------------------------------------------------------------
# Deteccao de backends (producao -> fallback)
# ---------------------------------------------------------------------------
def _lib_disponivel(nome: str) -> bool:
    import importlib.util

    return importlib.util.find_spec(nome) is not None


# Formato de armazenamento das camadas Bronze/Silver
# parquet (producao, precisa de pyarrow) | csv (fallback)
_fmt_env = os.getenv("STORAGE_FORMAT")
if _fmt_env:
    STORAGE_FORMAT = _fmt_env
elif _lib_disponivel("pyarrow") or _lib_disponivel("fastparquet"):
    STORAGE_FORMAT = "parquet"
else:
    STORAGE_FORMAT = "csv"

# Engine analitico da camada Gold
# duckdb (producao) | sqlite (fallback/local/testes)
_engine_env = os.getenv("GOLD_ENGINE", "sqlite").lower()

if _engine_env not in {"duckdb", "sqlite"}:
    raise ValueError(
        f"GOLD_ENGINE invalido: {_engine_env}. Use 'duckdb' ou 'sqlite'."
    )

GOLD_ENGINE = _engine_env

GOLD_DUCKDB = GOLD / "bibliodata.duckdb"
GOLD_SQLITE = GOLD / "bibliodata.sqlite"

# Backend de streaming
# kafka (producao, Redpanda via docker-compose) | file (fallback sem infra)
# Importante: NAO selecionamos kafka so porque a lib esta instalada -- ela vem
# no requirements.txt e estaria sempre presente. So usamos kafka quando o
# usuario opta explicitamente (STREAM_BACKEND=kafka), tipicamente apos subir o
# docker-compose. Mesmo assim, o producer/consumer caem para arquivo se o
# broker nao responder (ver kafka_producer.py / kafka_consumer.py).
STREAM_BACKEND = os.getenv("STREAM_BACKEND", "file")

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "acessos")

# ---------------------------------------------------------------------------
# Portoes de qualidade (Quality Gates) -- alimentam as retroalimentacoes
# ---------------------------------------------------------------------------
# Taxa minima de registros aprovados para uma camada ser promovida.
# Abaixo disso o pipeline ALERTA e interrompe a propagacao downstream.
QUALITY_GATE_MIN_PASS_RATE = float(os.getenv("QUALITY_GATE_MIN_PASS_RATE", "0.95"))

# Deriva de volume: variacao aceitavel de contagem de linhas vs. execucao anterior
VOLUME_DRIFT_TOLERANCE = float(os.getenv("VOLUME_DRIFT_TOLERANCE", "0.50"))

# ---------------------------------------------------------------------------
# Orquestracao
# ---------------------------------------------------------------------------
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "2"))
RETRY_BACKOFF_SEG = float(os.getenv("RETRY_BACKOFF_SEG", "1.0"))


def resumo() -> dict:
    """Snapshot da configuracao efetiva -- usado em logs e no catalogo."""
    return {
        "storage_format": STORAGE_FORMAT,
        "gold_engine": GOLD_ENGINE,
        "stream_backend": STREAM_BACKEND,
        "seed": SEED,
        "quality_gate_min_pass_rate": QUALITY_GATE_MIN_PASS_RATE,
        "max_retries": MAX_RETRIES,
    }
