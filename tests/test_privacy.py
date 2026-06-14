"""Testes da camada de privacidade (LGPD)."""
import pandas as pd

from src.governance import privacy


def test_email_mascarado_e_nome_pseudonimizado():
    df = pd.DataFrame([
        {"id_usuario": 1, "nome": "Ana Silva", "email": "ana.silva@exemplo.com"},
        {"id_usuario": 2, "nome": "Bruno Costa", "email": "bruno@teste.com"},
    ])
    out = privacy.anonimizar(df, "usuarios")

    # nome original some; entra um pseudonimo
    assert "nome" not in out.columns
    assert "nome_pseudo" in out.columns
    # e-mail fica mascarado (nao revela o usuario completo)
    assert all("*" in e for e in out["email"])
    assert "ana.silva" not in out["email"].iloc[0]


def test_pseudonimo_e_deterministico():
    df = pd.DataFrame([{"id_usuario": 1, "nome": "Ana Silva", "email": "a@b.com"}])
    p1 = privacy.anonimizar(df, "usuarios")["nome_pseudo"].iloc[0]
    p2 = privacy.anonimizar(df, "usuarios")["nome_pseudo"].iloc[0]
    assert p1 == p2  # mesmo nome -> mesmo pseudonimo (permite analise sem expor)


def test_dataset_sem_pii_nao_muda():
    df = pd.DataFrame([{"id_livro": 1, "titulo": "X", "genero": "Poesia"}])
    out = privacy.anonimizar(df, "livros")
    assert list(out.columns) == list(df.columns)
