"""
Painel de Consumo (Serving) -- Streamlit.

Le as tabelas Gold (DuckDB/SQLite) e os logs de monitoramento e apresenta um
painel analitico com identidade visual propria, dividido em duas abas:
    - Visao Geral: KPIs, rankings, distribuicoes e serie temporal
    - Qualidade & Monitoramento: status, taxa de qualidade, quarentena, alertas

Executar:
    streamlit run src/serving/dashboard.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config import settings  # noqa: E402
from src.monitoring.metrics import carregar_historico  # noqa: E402

# ---------------------------------------------------------------------------
# Identidade visual
# ---------------------------------------------------------------------------
TINTA = "#4F46E5"      # indigo (primaria)
TINTA2 = "#0EA5E9"     # azul (secundaria)
AMBAR = "#F59E0B"
VERDE = "#10B981"
VERMELHO = "#EF4444"
ESCALA_GENERO = "tableau10"

st.set_page_config(page_title="BiblioData", page_icon="📚", layout="wide")

st.markdown(
    """
    <style>
    .block-container {padding-top: 2.2rem; padding-bottom: 2rem; max-width: 1300px;}
    h1, h2, h3 {font-family: 'Inter', 'Segoe UI', sans-serif; letter-spacing:-0.01em;}
    .hero {
        background: linear-gradient(120deg, #4F46E5 0%, #0EA5E9 100%);
        border-radius: 18px; padding: 26px 30px; color: #fff; margin-bottom: 22px;
        box-shadow: 0 10px 30px rgba(79,70,229,.25);
    }
    .hero h1 {margin:0; font-size: 2.0rem; color:#fff;}
    .hero p {margin:.35rem 0 0; opacity:.92; font-size:.95rem;}
    .kpi {
        background:#fff; border:1px solid #EEF0F4; border-radius:14px;
        padding:16px 18px; box-shadow:0 2px 10px rgba(16,24,40,.04);
    }
    .kpi .v {font-size:1.7rem; font-weight:700; color:#0F172A; line-height:1.1;}
    .kpi .l {font-size:.78rem; color:#64748B; text-transform:uppercase; letter-spacing:.04em;}
    .kpi .bar {height:4px; border-radius:4px; margin-top:10px;}
    .secao {font-size:1.05rem; font-weight:700; color:#0F172A; margin:6px 0 2px;}
    .badge {display:inline-block; padding:4px 14px; border-radius:999px;
            color:#fff; font-weight:600; font-size:.95rem;}
    [data-testid="stMetricValue"] {font-size:1.6rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    f"""
    <div class="hero">
        <h1>📚 BiblioData — Painel Analítico</h1>
        <p>Ciclo de vida de dados de uma biblioteca digital · engine Gold:
        <b>{settings.GOLD_ENGINE}</b> · armazenamento: <b>{settings.STORAGE_FORMAT}</b></p>
    </div>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Acesso a dados
# ---------------------------------------------------------------------------
def _conectar():
    if settings.GOLD_ENGINE == "duckdb":
        import duckdb

        return duckdb.connect(str(settings.GOLD_DUCKDB), read_only=True), "duckdb"
    import sqlite3

    return sqlite3.connect(str(settings.GOLD_SQLITE)), "sqlite"


def ler(sql: str) -> pd.DataFrame:
    if engine == "duckdb":
        return conn.execute(sql).fetchdf()
    return pd.read_sql_query(sql, conn)


try:
    conn, engine = _conectar()
except Exception as exc:
    st.error(f"Não foi possível abrir a camada Gold. Rode `python pipeline.py` primeiro. ({exc})")
    st.stop()


def grafico_base(c):
    return (c.configure_view(strokeWidth=0)
             .configure_axis(grid=False, labelColor="#475569", titleColor="#334155",
                             labelFontSize=12, titleFontSize=12)
             .configure_legend(labelColor="#475569", titleColor="#334155"))


# ===========================================================================
abas = st.tabs(["📊 Visão Geral", "🔎 Qualidade & Monitoramento"])

# ---------------------------------------------------------------------------
# ABA 1 — VISAO GERAL
# ---------------------------------------------------------------------------
with abas[0]:
    try:
        kpis = ler("SELECT * FROM kpis_gerais")
        rotulos = {
            "total_usuarios": ("Usuários", TINTA),
            "total_livros": ("Livros", TINTA2),
            "total_emprestimos": ("Empréstimos", VERDE),
            "total_avaliacoes": ("Avaliações", AMBAR),
            "total_eventos_acesso": ("Eventos de acesso", "#A855F7"),
        }
        cols = st.columns(len(kpis))
        for col, (_, row) in zip(cols, kpis.iterrows()):
            rot, cor = rotulos.get(row["metrica"], (row["metrica"], TINTA))
            col.markdown(
                f'<div class="kpi"><div class="l">{rot}</div>'
                f'<div class="v">{int(row["valor"]):,}</div>'
                f'<div class="bar" style="background:{cor}"></div></div>'.replace(",", "."),
                unsafe_allow_html=True,
            )
    except Exception:
        st.warning("KPIs ainda não disponíveis.")

    st.write("")
    c1, c2 = st.columns([1.1, 1])

    with c1:
        st.markdown('<div class="secao">Top livros mais emprestados</div>', unsafe_allow_html=True)
        try:
            df = ler("SELECT titulo, genero, total_emprestimos FROM top_livros LIMIT 12")
            ch = alt.Chart(df).mark_bar(cornerRadiusEnd=5).encode(
                x=alt.X("total_emprestimos:Q", title="Empréstimos"),
                y=alt.Y("titulo:N", sort="-x", title=None),
                color=alt.Color("genero:N", scale=alt.Scale(scheme=ESCALA_GENERO),
                                legend=alt.Legend(title="Gênero", orient="bottom")),
                tooltip=["titulo", "genero", "total_emprestimos"],
            ).properties(height=380)
            st.altair_chart(grafico_base(ch), use_container_width=True)
        except Exception:
            st.info("Sem dados.")

    with c2:
        st.markdown('<div class="secao">Empréstimos por gênero</div>', unsafe_allow_html=True)
        try:
            df = ler("SELECT genero, total_emprestimos FROM uso_por_genero")
            ch = alt.Chart(df).mark_bar(cornerRadiusEnd=5).encode(
                x=alt.X("total_emprestimos:Q", title=None),
                y=alt.Y("genero:N", sort="-x", title=None),
                color=alt.Color("total_emprestimos:Q",
                                scale=alt.Scale(scheme="blues"), legend=None),
                tooltip=["genero", "total_emprestimos"],
            ).properties(height=380)
            st.altair_chart(grafico_base(ch), use_container_width=True)
        except Exception:
            st.info("Sem dados.")

    st.write("")
    c3, c4 = st.columns(2)

    with c3:
        st.markdown('<div class="secao">Distribuição das notas</div>', unsafe_allow_html=True)
        try:
            df = ler("SELECT nota, total FROM distribuicao_notas")
            ch = alt.Chart(df).mark_bar(cornerRadius=6, size=42, color=TINTA).encode(
                x=alt.X("nota:O", title="Nota"),
                y=alt.Y("total:Q", title="Avaliações"),
                tooltip=["nota", "total"],
            ).properties(height=300)
            st.altair_chart(grafico_base(ch), use_container_width=True)
        except Exception:
            st.info("Sem dados.")

    with c4:
        st.markdown('<div class="secao">Empréstimos por mês</div>', unsafe_allow_html=True)
        try:
            df = ler("SELECT mes, total_emprestimos FROM emprestimos_por_mes")
            base = alt.Chart(df).encode(
                x=alt.X("mes:N", title=None, axis=alt.Axis(labelAngle=-45)),
                y=alt.Y("total_emprestimos:Q", title="Empréstimos"),
            )
            area = base.mark_area(opacity=0.18, color=TINTA2)
            linha = base.mark_line(color=TINTA, strokeWidth=2.5, point=alt.OverlayMarkDef(color=TINTA))
            st.altair_chart(grafico_base(area + linha), use_container_width=True)
        except Exception:
            st.info("Sem dados.")

    st.markdown('<div class="secao">Livros mais bem avaliados</div>', unsafe_allow_html=True)
    try:
        df = ler("SELECT titulo, genero, nota_media, qtd_avaliacoes FROM avaliacao_por_livro")
        st.dataframe(
            df, use_container_width=True, hide_index=True,
            column_config={
                "titulo": "Título", "genero": "Gênero",
                "nota_media": st.column_config.ProgressColumn(
                    "Nota média", min_value=0, max_value=5, format="%.2f"),
                "qtd_avaliacoes": st.column_config.NumberColumn("Avaliações"),
            },
        )
    except Exception:
        st.info("Sem dados.")

# ---------------------------------------------------------------------------
# ABA 2 — QUALIDADE & MONITORAMENTO
# ---------------------------------------------------------------------------
with abas[1]:
    hist = carregar_historico(limite=20)
    if not hist:
        st.info("Nenhuma execução registrada ainda. Rode `python pipeline.py`.")
    else:
        ultimo = hist[-1]
        cor_status = {"sucesso": VERDE, "falha": VERMELHO,
                      "bloqueado_quality_gate": AMBAR}.get(ultimo["status"], "#64748B")
        silver = ultimo.get("estagios", {}).get("transformar_silver", {})
        tq = silver.get("taxa_qualidade")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("Status da última execução")
            st.markdown(f'<span class="badge" style="background:{cor_status}">'
                        f'{ultimo["status"]}</span>', unsafe_allow_html=True)
        with col2:
            st.metric("Taxa de qualidade (Silver)", f"{tq:.2%}" if tq is not None else "—")
            if tq is not None:
                st.progress(min(int(tq * 100), 100))
        with col3:
            st.metric("Registros em quarentena", silver.get("quarentena", 0))

        st.write("")
        st.markdown('<div class="secao">Taxa de qualidade por execução</div>', unsafe_allow_html=True)
        linhas = []
        for r in hist:
            s = r.get("estagios", {}).get("transformar_silver", {})
            linhas.append({
                "run_id": r["run_id"], "status": r["status"],
                "duracao_seg": r.get("duracao_total_seg"),
                "taxa_qualidade": s.get("taxa_qualidade"),
                "quarentena": s.get("quarentena"),
                "alertas": len(r.get("alertas", [])),
            })
        dfh = pd.DataFrame(linhas)
        serie = dfh.dropna(subset=["taxa_qualidade"])
        if len(serie) > 1:
            ch = alt.Chart(serie).mark_line(color=TINTA, strokeWidth=2.5,
                                            point=alt.OverlayMarkDef(color=TINTA)).encode(
                x=alt.X("run_id:N", title=None, axis=alt.Axis(labelAngle=-45)),
                y=alt.Y("taxa_qualidade:Q", title="Taxa", scale=alt.Scale(domain=[0.9, 1.0])),
                tooltip=["run_id", "taxa_qualidade"],
            ).properties(height=240)
            st.altair_chart(grafico_base(ch), use_container_width=True)

        st.markdown('<div class="secao">Histórico de execuções</div>', unsafe_allow_html=True)
        def _cor_status(v):
            m = {"sucesso": f"color:{VERDE};font-weight:600",
                 "falha": f"color:{VERMELHO};font-weight:600",
                 "bloqueado_quality_gate": f"color:{AMBAR};font-weight:600"}
            return m.get(v, "")
        st.dataframe(dfh.style.map(_cor_status, subset=["status"]),
                     use_container_width=True, hide_index=True)

        alertas = [a for r in hist for a in r.get("alertas", [])]
        if alertas:
            st.markdown('<div class="secao">Alertas recentes</div>', unsafe_allow_html=True)
            dfa = pd.DataFrame(alertas)[["ts", "severidade", "mensagem"]]
            def _cor_sev(v):
                m = {"CRITICAL": "background-color:#FEE2E2;color:#991B1B;font-weight:600",
                     "WARN": "background-color:#FEF3C7;color:#92400E",
                     "INFO": "background-color:#DBEAFE;color:#1E40AF"}
                return m.get(v, "")
            st.dataframe(dfa.style.map(_cor_sev, subset=["severidade"]),
                         use_container_width=True, hide_index=True)
