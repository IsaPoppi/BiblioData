"""
Transformacao Gold (Silver -> Gold).

Carrega as tabelas Silver em um banco analitico e materializa tabelas
agregadas prontas para consumo. Em producao usa DuckDB; sem DuckDB, usa
SQLite (biblioteca padrao). O SQL de agregacao e compativel com os dois
(a unica diferenca -- a funcao de mes -- e resolvida por engine).

Tabelas Gold produzidas:
    - top_livros           ranking de livros mais emprestados
    - uso_por_genero       emprestimos por genero literario
    - avaliacao_por_livro  nota media por livro (com volume relevante)
    - distribuicao_notas   quantas avaliacoes de cada nota (1..5)
    - emprestimos_por_mes  serie temporal de emprestimos
    - eventos_por_tipo     eventos de acesso por tipo (streaming)
    - kpis_gerais          numeros de cabecalho do painel
"""
from __future__ import annotations

import time

import pandas as pd

from config import settings
from src import storage
from src.governance import lineage
from src.monitoring.logger import get_logger
from src.monitoring.metrics import RunMetrics

log = get_logger("transform.gold")


def _consultas(engine: str) -> dict[str, str]:
    # funcao de mes difere entre engines
    if engine == "duckdb":
        mes_expr = "strftime(data_emprestimo, '%Y-%m')"
    else:  # sqlite
        mes_expr = "strftime('%Y-%m', data_emprestimo)"

    return {
        "top_livros": """
            SELECT l.id_livro, l.titulo, l.genero,
                   COUNT(e.id_emprestimo) AS total_emprestimos
            FROM emprestimos e
            JOIN livros l ON l.id_livro = e.id_livro
            GROUP BY l.id_livro, l.titulo, l.genero
            ORDER BY total_emprestimos DESC
            LIMIT 20
        """,
        "uso_por_genero": """
            SELECT l.genero, COUNT(e.id_emprestimo) AS total_emprestimos
            FROM emprestimos e
            JOIN livros l ON l.id_livro = e.id_livro
            GROUP BY l.genero
            ORDER BY total_emprestimos DESC
        """,
        "avaliacao_por_livro": """
            SELECT l.id_livro, l.titulo, l.genero,
                   ROUND(AVG(a.nota), 2) AS nota_media,
                   COUNT(a.id_avaliacao) AS qtd_avaliacoes
            FROM avaliacoes a
            JOIN livros l ON l.id_livro = a.id_livro
            GROUP BY l.id_livro, l.titulo, l.genero
            HAVING COUNT(a.id_avaliacao) >= 5
            ORDER BY nota_media DESC, qtd_avaliacoes DESC
            LIMIT 20
        """,
        "distribuicao_notas": """
            SELECT nota, COUNT(*) AS total
            FROM avaliacoes
            WHERE nota BETWEEN 1 AND 5
            GROUP BY nota
            ORDER BY nota
        """,
        "emprestimos_por_mes": f"""
            SELECT {mes_expr} AS mes, COUNT(*) AS total_emprestimos
            FROM emprestimos
            WHERE data_emprestimo IS NOT NULL
            GROUP BY mes
            ORDER BY mes
        """,
        "eventos_por_tipo": """
            SELECT tipo_evento, COUNT(*) AS total
            FROM acessos
            GROUP BY tipo_evento
            ORDER BY total DESC
        """,
    }


def _conectar():
    if settings.GOLD_ENGINE == "duckdb":
        import duckdb

        return duckdb.connect(str(settings.GOLD_DUCKDB)), "duckdb"
    import sqlite3

    return sqlite3.connect(str(settings.GOLD_SQLITE)), "sqlite"


def _carregar_tabela(conn, engine, nome, df):
    if engine == "duckdb":
        temp_name = f"_df_{nome}"
        conn.register(temp_name, df)
        try:
            conn.execute(f"CREATE OR REPLACE TABLE {nome} AS SELECT * FROM {temp_name}")
        finally:
            conn.unregister(temp_name)
    else:
        df.to_sql(nome, conn, if_exists="replace", index=False)


def _query_df(conn, engine, sql) -> pd.DataFrame:
    if engine == "duckdb":
        return conn.execute(sql).fetchdf()
    return pd.read_sql_query(sql, conn)


def _materializar(conn, engine, nome, df):
    if engine == "duckdb":
        temp_name = f"_g_{nome}"
        conn.register(temp_name, df)
        try:
            conn.execute(f"CREATE OR REPLACE TABLE {nome} AS SELECT * FROM {temp_name}")
        finally:
            conn.unregister(temp_name)
    else:
        df.to_sql(nome, conn, if_exists="replace", index=False)


def transformar(metrics: RunMetrics | None = None) -> dict:
    t0 = time.time()
    conn = None
    engine = None
    produzidas = {}
    carregadas = []

    try:
        conn, engine = _conectar()
        log.info("Camada Gold usando engine: %s", engine)

        tabelas = ["usuarios", "livros", "emprestimos", "avaliacoes", "acessos"]

        for nome in tabelas:
            if storage.existe("silver", nome):
                _carregar_tabela(conn, engine, nome, storage.ler("silver", nome))
                carregadas.append(nome)

        for nome_tabela, sql in _consultas(engine).items():
            try:
                df = _query_df(conn, engine, sql)
            except Exception as exc:
                log.warning("Pulando gold/%s: %s", nome_tabela, exc)
                continue

            _materializar(conn, engine, nome_tabela, df)
            produzidas[nome_tabela] = len(df)

            lineage.registrar(
                "silver/*",
                f"gold/{nome_tabela}",
                "transformar_gold",
                len(df),
            )

            log.info("Gold/%s: %d linhas", nome_tabela, len(df))

        kpis = _kpis(conn, engine)
        _materializar(conn, engine, "kpis_gerais", kpis)

        if engine == "sqlite":
            conn.commit()

        if metrics:
            metrics.registrar_estagio(
                "transformar_gold",
                linhas_entrada=0,
                linhas_saida=sum(produzidas.values()),
                duracao_seg=time.time() - t0,
                extra={
                    "tabelas_gold": list(produzidas.keys()),
                    "engine": engine,
                },
            )

        return {
            "engine": engine,
            "tabelas": produzidas,
            "silver_carregadas": carregadas,
        }

    except Exception:
        if conn is not None and engine == "sqlite":
            try:
                conn.rollback()
            except Exception:
                pass
        raise

    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception as exc:
                log.warning("Falha ao fechar conexao Gold: %s", exc)


def _kpis(conn, engine) -> pd.DataFrame:
    def conta(tabela):
        try:
            return int(_query_df(conn, engine, f"SELECT COUNT(*) AS c FROM {tabela}").iloc[0]["c"])
        except Exception:
            return 0

    return pd.DataFrame([
        {"metrica": "total_usuarios", "valor": conta("usuarios")},
        {"metrica": "total_livros", "valor": conta("livros")},
        {"metrica": "total_emprestimos", "valor": conta("emprestimos")},
        {"metrica": "total_avaliacoes", "valor": conta("avaliacoes")},
        {"metrica": "total_eventos_acesso", "valor": conta("acessos")},
    ])


if __name__ == "__main__":
    transformar()
