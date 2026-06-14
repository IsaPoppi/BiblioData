"""
Privacidade e conformidade LGPD (camada de Governanca).

Aplica pseudonimizacao/mascaramento das colunas marcadas como PII nos
contratos. A regra: dados pessoais (nome, e-mail) NUNCA chegam em claro a
Silver/Gold. Mantemos um pseudonimo estavel (hash com sal) para permitir
analises sem expor o titular dos dados -- principio da minimizacao da LGPD.

A Bronze guarda o dado original (auditavel, acesso restrito); a Silver em
diante so trabalha com a versao anonimizada.
"""
from __future__ import annotations

import hashlib
import os

import pandas as pd

from config.data_contracts import CONTRATOS

# Em producao o sal viria de um cofre (.env / secrets manager), nao do codigo.
_SALT = os.getenv("PII_SALT", "bibliodata-lgpd-salt")


def _pseudonimo(valor) -> str:
    if pd.isna(valor):
        return valor
    digest = hashlib.sha256((_SALT + str(valor)).encode("utf-8")).hexdigest()
    return digest[:16]


def _mascarar_email(valor) -> str:
    if pd.isna(valor) or "@" not in str(valor):
        return valor
    usuario, dominio = str(valor).split("@", 1)
    visivel = usuario[:2]
    return f"{visivel}{'*' * max(len(usuario) - 2, 1)}@{dominio}"


def anonimizar(df: pd.DataFrame, dataset: str) -> pd.DataFrame:
    """Aplica as politicas de PII do contrato do dataset."""
    contrato = CONTRATOS.get(dataset, {})
    pii = contrato.get("pii", [])
    if not pii:
        return df

    df = df.copy()
    for coluna in pii:
        if coluna not in df.columns:
            continue
        if coluna == "email":
            df[coluna] = df[coluna].map(_mascarar_email)
        elif coluna == "nome":
            # substitui o nome por um pseudonimo estavel
            df[coluna + "_pseudo"] = df[coluna].map(_pseudonimo)
            df = df.drop(columns=[coluna])
        else:
            df[coluna] = df[coluna].map(_pseudonimo)
    return df


def colunas_pii(dataset: str) -> list[str]:
    return CONTRATOS.get(dataset, {}).get("pii", [])
