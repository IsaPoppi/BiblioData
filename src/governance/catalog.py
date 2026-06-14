"""
Catalogo de Dados / Dicionario de Dados (camada de Governanca).

Gera automaticamente, a partir dos contratos e do perfil real das tabelas:
    - dicionario de dados (colunas, tipos, descricao, flag de PII)
    - perfil de cada camada (linhas, % de nulos, distintos)
    - deteccao simples de DERIVA DE SCHEMA (coluna do contrato ausente, ou
      coluna nova nao prevista) -- uma retroalimentacao de governanca.

Saidas: catalog/data_dictionary.md e catalog/profile.json
"""
from __future__ import annotations

import json
from datetime import datetime

import pandas as pd

from config import settings
from config.data_contracts import CONTRATOS
from src import storage


def perfilar(df: pd.DataFrame) -> dict:
    return {
        "linhas": int(len(df)),
        "colunas": list(df.columns),
        "nulos_pct": {
            c: round(float(df[c].isna().mean()), 4) for c in df.columns
        },
        "distintos": {c: int(df[c].nunique(dropna=True)) for c in df.columns},
    }


def detectar_deriva_schema(dataset: str, df: pd.DataFrame) -> list[str]:
    esperado = set(CONTRATOS[dataset]["colunas"].keys())
    presente = set(c for c in df.columns if not c.startswith("_"))
    avisos = []
    for faltando in esperado - presente:
        avisos.append(f"[{dataset}] coluna esperada ausente: {faltando}")
    for extra in presente - esperado:
        avisos.append(f"[{dataset}] coluna nova nao prevista no contrato: {extra}")
    return avisos


def gerar_catalogo() -> dict:
    """Le as camadas existentes, perfila e materializa o catalogo."""
    profile = {"gerado_em": datetime.now().isoformat(timespec="seconds"), "camadas": {}}
    avisos_deriva: list[str] = []

    for camada in ("bronze", "silver"):
        profile["camadas"][camada] = {}
        for dataset in CONTRATOS:
            if storage.existe(camada, dataset):
                df = storage.ler(camada, dataset)
                profile["camadas"][camada][dataset] = perfilar(df)
                if camada == "bronze":
                    avisos_deriva += detectar_deriva_schema(dataset, df)

    profile["deriva_schema"] = avisos_deriva
    (settings.CATALOG / "profile.json").write_text(
        json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    _escrever_dicionario(profile)
    return profile


def _escrever_dicionario(profile: dict) -> None:
    linhas = [
        "# Dicionario de Dados - BiblioData",
        "",
        f"_Gerado automaticamente em {profile['gerado_em']}._",
        "",
    ]
    for dataset, contrato in CONTRATOS.items():
        linhas.append(f"## {dataset}")
        linhas.append("")
        linhas.append(f"- **Dominio:** {contrato['dominio']}")
        linhas.append(f"- **Tipo:** {contrato['tipo']}")
        linhas.append(f"- **Descricao:** {contrato['descricao']}")
        pii = contrato.get("pii", [])
        linhas.append(f"- **Dados pessoais (LGPD):** {', '.join(pii) if pii else 'nenhum'}")
        linhas.append("")
        linhas.append("| Coluna | Tipo | PII |")
        linhas.append("|---|---|---|")
        for col, tipo in contrato["colunas"].items():
            flag = "sim" if col in pii else "-"
            linhas.append(f"| {col} | {tipo} | {flag} |")
        linhas.append("")

    if profile.get("deriva_schema"):
        linhas.append("## Avisos de deriva de schema")
        linhas.append("")
        for aviso in profile["deriva_schema"]:
            linhas.append(f"- {aviso}")
        linhas.append("")

    (settings.CATALOG / "data_dictionary.md").write_text(
        "\n".join(linhas), encoding="utf-8"
    )
