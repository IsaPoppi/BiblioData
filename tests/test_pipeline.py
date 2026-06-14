"""Teste de integracao: roda o pipeline ponta a ponta."""

import pandas as pd


def test_pipeline_ponta_a_ponta():
    import pipeline
    from config import settings

    resultado = pipeline.rodar(gerar=True)
    assert resultado["status"] == "sucesso"

    # a camada Gold foi criada e tem KPIs
    con = None

    try:
        if settings.GOLD_ENGINE == "duckdb":
            import duckdb

            con = duckdb.connect(str(settings.GOLD_DUCKDB))
            kpis = con.execute("SELECT * FROM kpis_gerais").fetchdf()

        else:
            import sqlite3

            con = sqlite3.connect(str(settings.GOLD_SQLITE))
            kpis = pd.read_sql_query("SELECT * FROM kpis_gerais", con)

    finally:
        if con is not None:
            con.close()

    assert len(kpis) == 5
    assert kpis["valor"].sum() > 0

    # dados sujos injetados foram parar na quarentena
    arquivos_quarentena = list(settings.QUARANTINE.glob("*"))
    assert len(arquivos_quarentena) > 0


def test_quality_gate_bloqueia_gold():
    """Com limite alto de qualidade, a Silver deve reprovar o quality gate."""
    from config import settings
    from src.transform import transformar_silver

    original = settings.QUALITY_GATE_MIN_PASS_RATE

    try:
        settings.QUALITY_GATE_MIN_PASS_RATE = 0.999
        res = transformar_silver.transformar()
        assert res["quality_gate_ok"] is False

    finally:
        settings.QUALITY_GATE_MIN_PASS_RATE = original