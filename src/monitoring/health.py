"""
Health Check e Recovery (camada de Monitoramento).

Responde às perguntas operacionais: o pipeline rodou? o banco analítico (Gold)
está acessível? os dados estão atualizados? a qualidade está dentro do limite?

Cada verificação retorna um status (ok | alerta | critico) com um detalhe
legível. O status geral é o pior entre os itens. Se algo estiver fora, um
ALERTA é registrado (logs/alerts.jsonl) e, no caso do banco Gold indisponível,
o recovery() consegue reconstruí-lo a partir da camada Silver.

Uso programático:  health.verificar()  ->  dict
Uso via CLI:       python monitorar.py   (ver arquivo na raiz)
"""
from __future__ import annotations

import json
from datetime import datetime

from config import settings
from config.data_contracts import DATASETS_BATCH, DATASETS_STREAM
from src import storage
from src.monitoring.logger import get_logger
from src.monitoring.metrics import carregar_historico

log = get_logger("monitoramento.health")

_ALERTS_FILE = settings.LOGS / "alerts.jsonl"

# Frescor: dados considerados "desatualizados" após este intervalo (horas)
FRESCOR_MAX_HORAS = float(__import__("os").getenv("FRESCOR_MAX_HORAS", "26"))


def _registrar_alerta(severidade: str, mensagem: str) -> None:
    evento = {
        "run_id": "health-check",
        "ts": datetime.now().isoformat(timespec="seconds"),
        "severidade": severidade,
        "mensagem": mensagem,
        "contexto": {"origem": "health_check"},
    }
    with open(_ALERTS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(evento, ensure_ascii=False) + "\n")


def _conectar_gold():
    if settings.GOLD_ENGINE == "duckdb":
        import duckdb
        return duckdb.connect(str(settings.GOLD_DUCKDB), read_only=True), "duckdb"
    import sqlite3
    return sqlite3.connect(str(settings.GOLD_SQLITE)), "sqlite"


def _pior(statuses: list[str]) -> str:
    ordem = {"ok": 0, "alerta": 1, "critico": 2}
    return max(statuses, key=lambda s: ordem.get(s, 0)) if statuses else "ok"


def verificar() -> dict:
    """Executa todas as verificações de saúde e devolve um relatório."""
    itens = []

    # 1. O pipeline já executou? Qual foi o status e há quanto tempo?
    hist = carregar_historico(limite=1)
    if not hist:
        itens.append({"nome": "Pipeline", "status": "critico",
                      "detalhe": "Nenhuma execução registrada. Rode 'python pipeline.py'."})
        idade_horas = None
    else:
        ultimo = hist[-1]
        ts = datetime.fromisoformat(ultimo["ts"])
        idade_horas = (datetime.now() - ts).total_seconds() / 3600
        if ultimo["status"] == "sucesso":
            itens.append({"nome": "Última execução", "status": "ok",
                          "detalhe": f"Sucesso em {ultimo['ts']} (run {ultimo['run_id']})."})
        else:
            itens.append({"nome": "Última execução", "status": "critico",
                          "detalhe": f"Status '{ultimo['status']}' em {ultimo['ts']}."})
        # Frescor dos dados
        if idade_horas is not None and idade_horas > FRESCOR_MAX_HORAS:
            itens.append({"nome": "Frescor dos dados", "status": "alerta",
                          "detalhe": f"Última carga há {idade_horas:.1f} h (limite {FRESCOR_MAX_HORAS:.0f} h)."})
        else:
            itens.append({"nome": "Frescor dos dados", "status": "ok",
                          "detalhe": f"Atualizado há {idade_horas:.1f} h." if idade_horas is not None else "—"})

    # 2. O banco analítico (Gold) está acessível?
    try:
        conn, engine = _conectar_gold()
        if engine == "duckdb":
            n = conn.execute("SELECT COUNT(*) FROM kpis_gerais").fetchone()[0]
        else:
            cur = conn.execute("SELECT COUNT(*) FROM kpis_gerais")
            n = cur.fetchone()[0]
        conn.close()
        itens.append({"nome": "Banco Gold", "status": "ok",
                      "detalhe": f"Acessível ({engine}); kpis_gerais com {n} métricas."})
    except Exception as exc:
        itens.append({"nome": "Banco Gold", "status": "critico",
                      "detalhe": f"INDISPONÍVEL ({type(exc).__name__}). Recovery: rode 'python monitorar.py --recuperar'."})

    # 3. As camadas Bronze e Silver existem com dados?
    for camada in ("bronze", "silver"):
        faltando = [d for d in DATASETS_BATCH + DATASETS_STREAM if not storage.existe(camada, d)]
        if faltando:
            itens.append({"nome": f"Camada {camada}", "status": "alerta",
                          "detalhe": f"Faltam tabelas: {', '.join(faltando)}."})
        else:
            itens.append({"nome": f"Camada {camada}", "status": "ok",
                          "detalhe": "Todas as tabelas presentes."})

    # 4. Qualidade da última execução vs. limite
    if hist:
        silver = hist[-1].get("estagios", {}).get("transformar_silver", {})
        tq = silver.get("taxa_qualidade")
        if tq is not None:
            if tq < settings.QUALITY_GATE_MIN_PASS_RATE:
                itens.append({"nome": "Qualidade", "status": "critico",
                              "detalhe": f"Taxa {tq:.2%} abaixo do limite {settings.QUALITY_GATE_MIN_PASS_RATE:.0%}."})
            elif tq < 0.99:
                itens.append({"nome": "Qualidade", "status": "alerta",
                              "detalhe": f"Taxa {tq:.2%} (aceitável, mas observar)."})
            else:
                itens.append({"nome": "Qualidade", "status": "ok",
                              "detalhe": f"Taxa {tq:.2%}."})

    status_geral = _pior([i["status"] for i in itens])

    # Registra alerta se houver algo fora do normal
    if status_geral != "ok":
        criticos = [i for i in itens if i["status"] != "ok"]
        _registrar_alerta(
            "CRITICAL" if status_geral == "critico" else "WARN",
            "Health check: " + "; ".join(f"{i['nome']}: {i['detalhe']}" for i in criticos),
        )

    return {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "status_geral": status_geral,
        "itens": itens,
    }


def recuperar() -> bool:
    """Recovery: reconstrói a camada Gold a partir da Silver.

    Usado quando o banco analítico está indisponível ou corrompido. Se a Silver
    também estiver ausente, orienta a reexecução completa do pipeline.
    """
    silver_ok = any(storage.existe("silver", d) for d in DATASETS_BATCH + DATASETS_STREAM)
    if not silver_ok:
        log.error("Recovery impossível: camada Silver ausente. Rode 'python pipeline.py'.")
        return False
    log.info("Recovery: reconstruindo a camada Gold a partir da Silver...")
    from src.transform import transformar_gold
    transformar_gold.transformar()
    log.info("Recovery concluído: banco Gold reconstruído.")
    _registrar_alerta("INFO", "Recovery executado: camada Gold reconstruída a partir da Silver.")
    return True
