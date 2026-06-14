"""
Motor de Qualidade de Dados.

Executa as expectativas declaradas nos contratos (config/data_contracts.py)
sobre um DataFrame e devolve um relatorio estruturado. As regras cobrem:
    not_null, unique, in_set, in_range, regex, fk (integridade
    referencial), not_future.

Cada registro reprovado por uma regra "dura" e marcado para quarentena.
O relatorio alimenta o monitoramento (taxa de aprovacao) e os quality gates
(retroalimentacao que pode interromper a promocao para a proxima camada).

Equivale, em escala de prototipo, ao papel do Soda Core / Great Expectations.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from config.data_contracts import CONTRATOS


@dataclass
class ResultadoRegra:
    regra: str
    coluna: str
    aprovados: int
    reprovados: int
    detalhe: str = ""

    @property
    def passou(self) -> bool:
        return self.reprovados == 0


@dataclass
class RelatorioQualidade:
    dataset: str
    total_linhas: int
    resultados: list[ResultadoRegra] = field(default_factory=list)
    indices_invalidos: set = field(default_factory=set)

    @property
    def taxa_aprovacao(self) -> float:
        if self.total_linhas == 0:
            return 1.0
        validos = self.total_linhas - len(self.indices_invalidos)
        return validos / self.total_linhas

    @property
    def passou(self) -> bool:
        return all(r.passou for r in self.resultados)

    def resumo(self) -> dict:
        return {
            "dataset": self.dataset,
            "total_linhas": self.total_linhas,
            "linhas_invalidas": len(self.indices_invalidos),
            "taxa_aprovacao": round(self.taxa_aprovacao, 4),
            "passou": self.passou,
            "ts": datetime.now().isoformat(timespec="seconds"),
            "regras": [
                {
                    "regra": r.regra,
                    "coluna": r.coluna,
                    "reprovados": r.reprovados,
                    "detalhe": r.detalhe,
                }
                for r in self.resultados
            ],
        }


def validar(
    df: pd.DataFrame,
    dataset: str,
    refs: dict[str, pd.DataFrame] | None = None,
) -> RelatorioQualidade:
    """Valida `df` contra o contrato de `dataset`.

    `refs` mapeia nome->DataFrame para checagens de integridade referencial (fk).
    """
    contrato = CONTRATOS[dataset]
    rel = RelatorioQualidade(dataset=dataset, total_linhas=len(df))
    refs = refs or {}

    for tipo, coluna, parametro in contrato["expectativas"]:
        if coluna not in df.columns and tipo not in ("fk",):
            rel.resultados.append(
                ResultadoRegra(tipo, coluna, 0, len(df), "coluna ausente")
            )
            rel.indices_invalidos.update(df.index)
            continue

        mask_invalida = _aplicar_regra(df, tipo, coluna, parametro, refs)
        n_reprovados = int(mask_invalida.sum())
        rel.resultados.append(
            ResultadoRegra(
                regra=tipo,
                coluna=coluna,
                aprovados=len(df) - n_reprovados,
                reprovados=n_reprovados,
                detalhe=str(parametro) if parametro is not None else "",
            )
        )
        if n_reprovados:
            rel.indices_invalidos.update(df.index[mask_invalida].tolist())

    return rel


def _aplicar_regra(df, tipo, coluna, parametro, refs) -> pd.Series:
    """Retorna uma mascara booleana onde True = registro INVALIDO."""
    falso = pd.Series(False, index=df.index)

    if tipo == "not_null":
        return df[coluna].isna()

    if tipo == "unique":
        return df[coluna].duplicated(keep="first") & df[coluna].notna()

    if tipo == "in_set":
        return df[coluna].notna() & ~df[coluna].isin(parametro)

    if tipo == "in_range":
        lo, hi = parametro
        valores = pd.to_numeric(df[coluna], errors="coerce")
        return valores.notna() & ((valores < lo) | (valores > hi))

    if tipo == "regex":
        return df[coluna].notna() & ~df[coluna].astype(str).str.match(parametro)

    if tipo == "not_future":
        datas = pd.to_datetime(df[coluna], errors="coerce")
        return datas.notna() & (datas > pd.Timestamp.now())

    if tipo == "fk":
        dataset_alvo, coluna_alvo = parametro
        ref = refs.get(dataset_alvo)
        if ref is None or coluna_alvo not in ref.columns:
            return falso  # sem referencia disponivel, nao reprova
        validos = set(ref[coluna_alvo].dropna().tolist())
        return df[coluna].notna() & ~df[coluna].isin(validos)

    return falso
