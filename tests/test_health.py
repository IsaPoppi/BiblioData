"""Testes do health check e recovery (camada de Monitoramento)."""
from src.monitoring import health


def test_health_ok_apos_pipeline():
    import pipeline
    pipeline.rodar(gerar=True)
    rel = health.verificar()
    assert rel["status_geral"] in ("ok", "alerta")  # saudável após execução
    nomes = [i["nome"] for i in rel["itens"]]
    assert "Banco Gold" in nomes


def test_health_detecta_banco_fora_e_recupera():
    from config import settings
    import pipeline
    pipeline.rodar(gerar=True)
    # simula o banco Gold caindo
    alvo = settings.GOLD_SQLITE if settings.GOLD_ENGINE == "sqlite" else settings.GOLD_DUCKDB
    if alvo.exists():
        alvo.unlink()
    rel = health.verificar()
    assert rel["status_geral"] == "critico"
    # recovery reconstrói a Gold
    assert health.recuperar() is True
    assert health.verificar()["status_geral"] in ("ok", "alerta")
