"""Testes do motor de qualidade de dados."""
import pandas as pd

from src.quality import checks


def test_detecta_email_invalido_e_duplicata():
    df = pd.DataFrame([
        {"id_usuario": 1, "nome": "A", "email": "a@x.com", "cidade": "BSB", "data_cadastro": "2024-01-01"},
        {"id_usuario": 1, "nome": "B", "email": "b@x.com", "cidade": "SP", "data_cadastro": "2024-01-02"},   # id duplicado
        {"id_usuario": 3, "nome": "C", "email": "email_invalido", "cidade": "RJ", "data_cadastro": "2024-01-03"},  # email ruim
    ])
    rel = checks.validar(df, "usuarios")

    regras = {r.regra + ":" + r.coluna: r.reprovados for r in rel.resultados}
    assert regras["unique:id_usuario"] == 1
    assert regras["regex:email"] == 1
    assert not rel.passou


def test_nota_fora_da_faixa_e_reprovada():
    refs = {
        "usuarios": pd.DataFrame({"id_usuario": [1]}),
        "livros": pd.DataFrame({"id_livro": [1]}),
    }
    df = pd.DataFrame([
        {"id_avaliacao": 1, "id_usuario": 1, "id_livro": 1, "nota": 5, "comentario": "ok", "data_avaliacao": "2024-01-01"},
        {"id_avaliacao": 2, "id_usuario": 1, "id_livro": 1, "nota": 7, "comentario": "x", "data_avaliacao": "2024-01-01"},
    ])
    rel = checks.validar(df, "avaliacoes", refs=refs)
    regras = {r.regra + ":" + r.coluna: r.reprovados for r in rel.resultados}
    assert regras["in_range:nota"] == 1


def test_fk_orfa_e_detectada():
    refs = {
        "usuarios": pd.DataFrame({"id_usuario": [1, 2]}),
        "livros": pd.DataFrame({"id_livro": [1]}),
    }
    df = pd.DataFrame([
        {"id_emprestimo": 1, "id_usuario": 1, "id_livro": 1, "data_emprestimo": "2024-01-01", "data_devolucao": None},
        {"id_emprestimo": 2, "id_usuario": 999, "id_livro": 1, "data_emprestimo": "2024-01-01", "data_devolucao": None},  # usuario inexistente
    ])
    rel = checks.validar(df, "emprestimos", refs=refs)
    regras = {r.regra + ":" + r.coluna: r.reprovados for r in rel.resultados}
    assert regras["fk:id_usuario"] == 1


def test_taxa_aprovacao():
    df = pd.DataFrame([
        {"id_usuario": 1, "nome": "A", "email": "a@x.com", "cidade": "BSB", "data_cadastro": "2024-01-01"},
        {"id_usuario": 2, "nome": "B", "email": "ruim", "cidade": "SP", "data_cadastro": "2024-01-02"},
    ])
    rel = checks.validar(df, "usuarios")
    assert rel.taxa_aprovacao == 0.5  # 1 de 2 invalido
