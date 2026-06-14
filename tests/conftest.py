"""
conftest.py na raiz do projeto: permite ao pytest achar `src` e `config`
e define volumes pequenos + modo fallback para os testes.
"""
import os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("N_USUARIOS", "300")
os.environ.setdefault("N_LIVROS", "200")
os.environ.setdefault("N_EMPRESTIMOS", "600")
os.environ.setdefault("N_AVALIACOES", "300")
os.environ.setdefault("N_EVENTOS_STREAM", "100")
os.environ.setdefault("STREAM_BACKEND", "file")
os.environ.setdefault("BIBLIODATA_SEED", "42")
