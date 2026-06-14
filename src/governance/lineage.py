"""
Linhagem de dados (Data Lineage) -- camada de Governanca.

Registra como cada tabela foi produzida: de onde veio, qual processo a gerou
e quantas linhas resultaram. Isso responde "de onde veio esse numero?" e e
parte essencial de auditabilidade e governanca.

A linhagem e persistida em catalog/lineage.json e tambem renderizada como
diagrama Mermaid para o README/painel.
"""
from __future__ import annotations

import json
from datetime import datetime

from config import settings

_LINEAGE_FILE = settings.CATALOG / "lineage.json"


def registrar(origem: str, destino: str, processo: str, linhas: int) -> None:
    arestas = _carregar()
    arestas.append(
        {
            "origem": origem,
            "destino": destino,
            "processo": processo,
            "linhas": int(linhas),
            "ts": datetime.now().isoformat(timespec="seconds"),
        }
    )
    _LINEAGE_FILE.write_text(
        json.dumps(arestas, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _carregar() -> list[dict]:
    if not _LINEAGE_FILE.exists():
        return []
    try:
        return json.loads(_LINEAGE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def para_mermaid() -> str:
    """Gera um grafo de linhagem (ultima aresta por par origem->destino)."""
    arestas = _carregar()
    vistos: dict[tuple, dict] = {}
    for a in arestas:
        vistos[(a["origem"], a["destino"])] = a  # mantem a mais recente

    linhas = ["flowchart LR"]
    for (origem, destino), a in vistos.items():
        oid = _id(origem)
        did = _id(destino)
        linhas.append(f'    {oid}["{origem}"] -->|{a["processo"]} ({a["linhas"]})| {did}["{destino}"]')
    return "\n".join(linhas)


def _id(nome: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in nome)
