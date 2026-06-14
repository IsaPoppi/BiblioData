"""
Transformacao Silver (Bronze -> Silver).

Le a Bronze, valida com os contratos e SEPARA os registros validos dos
invalidos. Os invalidos vao para a QUARENTENA (retroalimentacao: nada e
descartado em silencio). Os validos sao limpos: remocao de duplicatas,
normalizacao de tipos/datas e aplicacao das politicas de PII (LGPD) antes
de gravar na Silver.

QUALITY GATE: se a taxa de aprovacao de um dataset ficar abaixo do limite
configurado, o estagio sinaliza falha. O orquestrador usa esse sinal para
NAO promover dados ruins para a Gold/consumo.
"""
from __future__ import annotations

import time

import pandas as pd

from config import settings
from config.data_contracts import CONTRATOS, DATASETS_BATCH, DATASETS_STREAM
from src import storage
from src.governance import lineage, privacy
from src.monitoring.logger import get_logger
from src.monitoring.metrics import RunMetrics
from src.quality import checks

log = get_logger("transform.silver")

_COLS_DATA = {
    "usuarios": ["data_cadastro"],
    "emprestimos": ["data_emprestimo", "data_devolucao"],
    "avaliacoes": ["data_avaliacao"],
    "acessos": ["timestamp_evento"],
}


def _limpar(df: pd.DataFrame, dataset: str) -> pd.DataFrame:
    df = df.drop(columns=[c for c in df.columns if c.startswith("_")], errors="ignore")
    # remove duplicatas pela chave primaria, quando houver
    chave = next(
        (c for (t, c, _) in CONTRATOS[dataset]["expectativas"] if t == "unique"),
        None,
    )
    if chave and chave in df.columns:
        df = df.drop_duplicates(subset=[chave], keep="first")
    # normaliza datas
    for col in _COLS_DATA.get(dataset, []):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def transformar(metrics: RunMetrics | None = None) -> dict:
    t0 = time.time()
    resultado = {"datasets": {}, "quality_gate_ok": True}

    # carrega referencias da Bronze p/ checagem de FK
    refs = {
        nome: storage.ler("bronze", nome)
        for nome in DATASETS_BATCH
        if storage.existe("bronze", nome)
    }

    datasets = [d for d in DATASETS_BATCH + DATASETS_STREAM if storage.existe("bronze", d)]

    total_quarentena = 0
    piores_taxas = []

    for dataset in datasets:
        df = storage.ler("bronze", dataset)
        rel = checks.validar(df, dataset, refs=refs)

        invalidos = df.loc[sorted(rel.indices_invalidos)]
        validos = df.drop(index=list(rel.indices_invalidos))

        if len(invalidos):
            caminho = storage.quarentena(invalidos, dataset, motivo="reprovado_silver")
            log.info("Quarentena %s: %d registros -> %s",
                     dataset, len(invalidos), caminho.name)
            total_quarentena += len(invalidos)

        limpo = _limpar(validos, dataset)
        limpo = privacy.anonimizar(limpo, dataset)
        storage.escrever(limpo, "silver", dataset)
        lineage.registrar(f"bronze/{dataset}", f"silver/{dataset}",
                           "transformar_silver", len(limpo))

        piores_taxas.append(rel.taxa_aprovacao)
        resultado["datasets"][dataset] = {
            "entrada": len(df),
            "validos": len(limpo),
            "quarentena": len(invalidos),
            "taxa_qualidade": round(rel.taxa_aprovacao, 4),
        }
        log.info("Silver/%s: %d validos | %d em quarentena | qualidade %.2f%%",
                 dataset, len(limpo), len(invalidos), rel.taxa_aprovacao * 100)

    # ---- QUALITY GATE (retroalimentacao -> orquestracao) ----
    pior = min(piores_taxas) if piores_taxas else 1.0
    if pior < settings.QUALITY_GATE_MIN_PASS_RATE:
        resultado["quality_gate_ok"] = False
        if metrics:
            metrics.alerta(
                "CRITICAL",
                f"Quality gate REPROVADO: taxa minima {pior:.2%} < "
                f"limite {settings.QUALITY_GATE_MIN_PASS_RATE:.2%}",
                {"pior_taxa": round(pior, 4)},
            )

    if metrics:
        entrada = sum(d["entrada"] for d in resultado["datasets"].values())
        saida = sum(d["validos"] for d in resultado["datasets"].values())
        metrics.registrar_estagio(
            "transformar_silver",
            linhas_entrada=entrada,
            linhas_saida=saida,
            duracao_seg=time.time() - t0,
            taxa_qualidade=round(pior, 4),
            quarentena=total_quarentena,
        )

    return resultado


if __name__ == "__main__":
    transformar()
