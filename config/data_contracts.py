"""
Contratos de dados (Data Contracts).

Fonte unica de verdade sobre CADA dataset: schema esperado, tipos, colunas que
contem dados pessoais (LGPD) e as expectativas de qualidade. Tudo o que e
governanca, qualidade e privacidade no projeto deriva daqui.

Esse arquivo e a "espinha dorsal" da camada de governanca: o catalogo de dados,
as mascaras de PII e as regras de qualidade sao geradas a partir dele.
"""
from __future__ import annotations

# Cada expectativa e uma tupla (tipo_regra, coluna, parametro_opcional)
#   not_null        -> coluna nao pode ter nulos
#   unique          -> coluna deve ser unica (chave)
#   in_set          -> valor deve estar no conjunto informado
#   in_range        -> valor numerico entre (min, max)
#   regex           -> string casa com o padrao
#   fk              -> integridade referencial: (dataset_alvo, coluna_alvo)
#   not_future      -> data nao pode ser no futuro

EMAIL_REGEX = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

CONTRATOS = {
    "usuarios": {
        "descricao": "Cadastro de leitores da biblioteca digital.",
        "dominio": "Usuarios",
        "tipo": "Cadastral",
        "colunas": {
            "id_usuario": "int",
            "nome": "string",
            "email": "string",
            "cidade": "string",
            "data_cadastro": "date",
        },
        "pii": ["nome", "email"],  # LGPD: pseudonimizar na Silver
        "expectativas": [
            ("not_null", "id_usuario", None),
            ("unique", "id_usuario", None),
            ("not_null", "email", None),
            ("regex", "email", EMAIL_REGEX),
            ("not_future", "data_cadastro", None),
        ],
    },
    "livros": {
        "descricao": "Catalogo do acervo (dado mestre / referencia).",
        "dominio": "Acervo",
        "tipo": "Mestre",
        "colunas": {
            "id_livro": "int",
            "titulo": "string",
            "autor": "string",
            "isbn": "string",
            "genero": "string",
            "editora": "string",
            "ano": "int",
        },
        "pii": [],
        "expectativas": [
            ("not_null", "id_livro", None),
            ("unique", "id_livro", None),
            ("not_null", "titulo", None),
            ("in_range", "ano", (1450, 2026)),
            ("in_set", "genero", [
                "Romance", "Ficcao Cientifica", "Fantasia", "Tecnico",
                "Biografia", "Historia", "Infantil", "Poesia",
            ]),
        ],
    },
    "emprestimos": {
        "descricao": "Historico transacional de emprestimos virtuais.",
        "dominio": "Emprestimos",
        "tipo": "Transacional",
        "colunas": {
            "id_emprestimo": "int",
            "id_usuario": "int",
            "id_livro": "int",
            "data_emprestimo": "date",
            "data_devolucao": "date",
        },
        "pii": [],
        "expectativas": [
            ("not_null", "id_emprestimo", None),
            ("unique", "id_emprestimo", None),
            ("fk", "id_usuario", ("usuarios", "id_usuario")),
            ("fk", "id_livro", ("livros", "id_livro")),
            ("not_future", "data_emprestimo", None),
        ],
    },
    "avaliacoes": {
        "descricao": "Notas e comentarios deixados apos a leitura.",
        "dominio": "Emprestimos",
        "tipo": "Transacional",
        "colunas": {
            "id_avaliacao": "int",
            "id_usuario": "int",
            "id_livro": "int",
            "nota": "int",
            "comentario": "string",
            "data_avaliacao": "date",
        },
        "pii": [],
        "expectativas": [
            ("not_null", "id_avaliacao", None),
            ("unique", "id_avaliacao", None),
            ("in_range", "nota", (1, 5)),
            ("fk", "id_usuario", ("usuarios", "id_usuario")),
            ("fk", "id_livro", ("livros", "id_livro")),
        ],
    },
    "acessos": {
        "descricao": "Eventos de streaming: buscas, cliques e visualizacoes.",
        "dominio": "Analise",
        "tipo": "Evento (streaming)",
        "colunas": {
            "id_evento": "string",
            "id_usuario": "int",
            "tipo_evento": "string",
            "id_livro": "int",
            "timestamp_evento": "timestamp",
        },
        "pii": [],
        "expectativas": [
            ("not_null", "id_evento", None),
            ("in_set", "tipo_evento", ["busca", "clique", "visualizacao"]),
        ],
    },
}

# Datasets que entram pelo caminho batch (CSV) x streaming
DATASETS_BATCH = ["usuarios", "livros", "emprestimos", "avaliacoes"]
DATASETS_STREAM = ["acessos"]
