"""
Coleta de metricas e saude do pipeline (camada de Monitoramento).

Registra, por execucao e por estagio:
    - linhas de entrada / saida (detecta perda de dados)
    - duracao
    - taxa de aprovacao de qualidade
    - registros enviados para quarentena
    - alertas disparados

As metricas sao anexadas em logs/pipeline_metrics.jsonl (uma linha por run)
e servem de base para o painel de Consumo e para as RETROALIMENTACOES
(deteccao de deriva de volume, quality gates, alertas).
"""
from __future__ import annotations

import json
import time
from datetime import datetime

from config import settings

_METRICS_FILE = settings.LOGS / "pipeline_metrics.jsonl"
_ALERTS_FILE = settings.LOGS / "alerts.jsonl"


class RunMetrics:
    """Acumula metricas de uma execucao do pipeline."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.inicio = time.time()
        self.config = settings.resumo()
        self.estagios: dict[str, dict] = {}
        self.alertas: list[dict] = []
        self.status = "em_execucao"

    # ----- registro por estagio -------------------------------------------
    def registrar_estagio(
        self,
        estagio: str,
        linhas_entrada: int = 0,
        linhas_saida: int = 0,
        duracao_seg: float = 0.0,
        taxa_qualidade: float | None = None,
        quarentena: int = 0,
        extra: dict | None = None,
    ) -> None:
        self.estagios[estagio] = {
            "linhas_entrada": int(linhas_entrada),
            "linhas_saida": int(linhas_saida),
            "duracao_seg": round(duracao_seg, 3),
            "taxa_qualidade": taxa_qualidade,
            "quarentena": int(quarentena),
            **(extra or {}),
        }

    # ----- alertas (retroalimentacao para o operador) ---------------------
    def alerta(self, severidade: str, mensagem: str, contexto: dict | None = None) -> None:
        evento = {
            "run_id": self.run_id,
            "ts": datetime.now().isoformat(timespec="seconds"),
            "severidade": severidade,  # INFO | WARN | CRITICAL
            "mensagem": mensagem,
            "contexto": contexto or {},
        }
        self.alertas.append(evento)
        with open(_ALERTS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(evento, ensure_ascii=False) + "\n")

    # ----- deriva de volume (retroalimentacao historica) ------------------
    def checar_deriva_volume(self, estagio: str, linhas: int) -> None:
        """Compara o volume atual com a ultima execucao bem-sucedida."""
        anterior = _ultimo_volume(estagio)
        if anterior is None or anterior == 0:
            return
        variacao = abs(linhas - anterior) / anterior
        if variacao > settings.VOLUME_DRIFT_TOLERANCE:
            self.alerta(
                "WARN",
                f"Deriva de volume em '{estagio}': {anterior} -> {linhas} "
                f"({variacao:.0%} de variacao)",
                {"estagio": estagio, "anterior": anterior, "atual": linhas},
            )

    # ----- finalizacao -----------------------------------------------------
    def finalizar(self, status: str = "sucesso") -> dict:
        self.status = status
        registro = {
            "run_id": self.run_id,
            "ts": datetime.now().isoformat(timespec="seconds"),
            "status": status,
            "duracao_total_seg": round(time.time() - self.inicio, 3),
            "config": self.config,
            "estagios": self.estagios,
            "alertas": self.alertas,
        }
        with open(_METRICS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")
        return registro


def _ultimo_volume(estagio: str) -> int | None:
    """Le o ultimo volume de saida registrado para um estagio."""
    if not _METRICS_FILE.exists():
        return None
    ultimo = None
    with open(_METRICS_FILE, encoding="utf-8") as f:
        for linha in f:
            try:
                reg = json.loads(linha)
            except json.JSONDecodeError:
                continue
            if reg.get("status") == "sucesso" and estagio in reg.get("estagios", {}):
                ultimo = reg["estagios"][estagio]["linhas_saida"]
    return ultimo


def carregar_historico(limite: int = 50) -> list[dict]:
    """Carrega as ultimas execucoes (para o painel de monitoramento)."""
    if not _METRICS_FILE.exists():
        return []
    linhas = _METRICS_FILE.read_text(encoding="utf-8").strip().splitlines()
    registros = []
    for linha in linhas[-limite:]:
        try:
            registros.append(json.loads(linha))
        except json.JSONDecodeError:
            continue
    return registros
