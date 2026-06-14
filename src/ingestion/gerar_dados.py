"""
Geracao de dados sinteticos (Ingestao - origem batch).

Em producao usa Faker (pt_BR) com seed fixo (reprodutibilidade). Sem Faker
instalado, cai para um gerador interno equivalente baseado na biblioteca
padrao -- assim o pipeline roda em qualquer ambiente.

REALISMO: cada livro recebe dois atributos latentes deterministicos:
    - qualidade  -> nota media esperada (uns livros sao melhores que outros)
    - popularidade -> peso de sorteio (uns livros sao muito mais lidos)
Emprestimos e avaliacoes seguem esses atributos. Isso faz os rankings terem
SIGNIFICADO (sem isso, com sorteio uniforme, "top avaliados" vira empate de
ruido). Os generos tambem tem pesos diferentes, deixando a distribuicao
realista em vez de plana.

PROPOSITAL: injeta uma pequena fracao de registros "sujos" (e-mails invalidos,
notas fora da faixa, FKs orfas) para EXERCITAR a camada de qualidade e a
quarentena -- ou seja, para nao testarmos apenas o caminho feliz.

Saida: arquivos CSV em data/raw/
"""
from __future__ import annotations

import csv
import random
from datetime import date, timedelta

from config import settings
from config.data_contracts import DATASETS_BATCH
from src.monitoring.logger import get_logger

log = get_logger("ingestao.gerar_dados")

try:
    from faker import Faker

    _fake = Faker("pt_BR")
    Faker.seed(settings.SEED)
    _USANDO_FAKER = True
except Exception:  # pragma: no cover - fallback
    _fake = None
    _USANDO_FAKER = False

random.seed(settings.SEED)

GENEROS = [
    "Romance", "Ficcao Cientifica", "Fantasia", "Tecnico",
    "Biografia", "Historia", "Infantil", "Poesia",
]
# Pesos de atribuicao de genero -> deixa a distribuicao realista (nao plana)
GENERO_PESOS = {
    "Romance": 1.6, "Fantasia": 1.4, "Infantil": 1.3, "Historia": 1.1,
    "Ficcao Cientifica": 1.0, "Biografia": 0.8, "Tecnico": 0.7, "Poesia": 0.5,
}

_NOMES = ["Ana", "Bruno", "Carla", "Diego", "Elena", "Felipe", "Gabriela",
          "Hugo", "Isadora", "Joao", "Karina", "Lucas", "Maria", "Nelson"]
_SOBRENOMES = ["Silva", "Souza", "Oliveira", "Costa", "Pereira", "Almeida",
               "Lima", "Gomes", "Ribeiro", "Carvalho"]
_CIDADES = ["Brasilia", "Sao Paulo", "Rio de Janeiro", "Belo Horizonte",
            "Curitiba", "Salvador", "Recife", "Porto Alegre"]
_PALAVRAS = ["dados", "leitura", "historia", "mundo", "tempo", "luz", "sombra",
             "cidade", "mar", "fogo", "vento", "memoria", "sonho", "silencio"]


def _nome() -> str:
    return _fake.name() if _USANDO_FAKER else f"{random.choice(_NOMES)} {random.choice(_SOBRENOMES)}"


def _email(i: int) -> str:
    return _fake.email() if _USANDO_FAKER else f"user{i}{random.randint(1,99)}@exemplo.com"


def _cidade() -> str:
    return _fake.city() if _USANDO_FAKER else random.choice(_CIDADES)


def _titulo() -> str:
    base = " ".join(random.choice(_PALAVRAS) for _ in range(random.randint(2, 4)))
    return base.capitalize()


def _data(dias_atras_max: int) -> date:
    return date.today() - timedelta(days=random.randint(0, dias_atras_max))


def atributos_livros(n: int) -> tuple[dict, list]:
    """Gera, por livro, a qualidade latente (nota media) e a popularidade.

    popularidade segue uma lei de potencia (Pareto): a maioria dos livros e
    pouco lida e poucos sao muito populares -- como num acervo real.
    """
    qualidade = {}
    popularidade = []
    for i in range(1, n + 1):
        # qualidade latente entre ~2.2 e ~4.8 (cada livro e diferente)
        qualidade[i] = round(random.uniform(2.2, 4.8), 2)
        # popularidade com cauda longa
        popularidade.append(min(random.paretovariate(1.3), 30.0))
    return qualidade, popularidade


def gerar_usuarios(n: int) -> list[dict]:
    linhas = []
    for i in range(1, n + 1):
        email = _email(i)
        if random.random() < 0.01:  # 1% de e-mails invalidos
            email = email.replace("@", "_at_")
        linhas.append({
            "id_usuario": i,
            "nome": _nome(),
            "email": email,
            "cidade": _cidade(),
            "data_cadastro": _data(1095),
        })
    return linhas


def gerar_livros(n: int) -> list[dict]:
    generos = list(GENERO_PESOS.keys())
    pesos = list(GENERO_PESOS.values())
    linhas = []
    for i in range(1, n + 1):
        linhas.append({
            "id_livro": i,
            "titulo": _titulo(),
            "autor": _nome(),
            "isbn": f"978-{random.randint(10**9, 10**10 - 1)}",
            "genero": random.choices(generos, weights=pesos, k=1)[0],
            "editora": f"Editora {random.choice(_SOBRENOMES)}",
            "ano": random.randint(1950, 2026),
        })
    return linhas


def gerar_emprestimos(n, n_usuarios, n_livros, popularidade) -> list[dict]:
    # sorteia livros ponderando pela popularidade -> ranking com significado
    livros = random.choices(range(1, n_livros + 1), weights=popularidade, k=n)
    linhas = []
    for i in range(1, n + 1):
        uid = random.randint(1, n_usuarios)
        if random.random() < 0.01:  # 1% de FK orfa
            uid = n_usuarios + random.randint(1, 500)
        d_emp = _data(365)
        devolvido = random.random() < 0.8
        linhas.append({
            "id_emprestimo": i,
            "id_usuario": uid,
            "id_livro": livros[i - 1],
            "data_emprestimo": d_emp,
            "data_devolucao": (d_emp + timedelta(days=random.randint(1, 30)))
            if devolvido else None,
        })
    return linhas


def gerar_avaliacoes(n, n_usuarios, n_livros, popularidade, qualidade) -> list[dict]:
    # quem avalia tende a ser quem leu -> mesma ponderacao por popularidade
    livros = random.choices(range(1, n_livros + 1), weights=popularidade, k=n)
    linhas = []
    for i in range(1, n + 1):
        id_livro = livros[i - 1]
        # nota em torno da qualidade latente do livro (com ruido), 1..5
        nota = round(random.gauss(qualidade[id_livro], 0.7))
        nota = max(1, min(5, nota))
        if random.random() < 0.005:  # ~0.5% de notas fora da faixa
            nota = random.choice([0, 6, 7])
        linhas.append({
            "id_avaliacao": i,
            "id_usuario": random.randint(1, n_usuarios),
            "id_livro": id_livro,
            "nota": nota,
            "comentario": _titulo(),
            "data_avaliacao": _data(365),
        })
    return linhas


def _salvar_csv(linhas: list[dict], nome: str) -> None:
    caminho = settings.RAW / f"{nome}.csv"
    if not linhas:
        return
    with open(caminho, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0].keys()))
        w.writeheader()
        w.writerows(linhas)
    log.info("Gerado %s: %d registros -> %s", nome, len(linhas), caminho.name)


def main() -> dict[str, int]:
    motor = "Faker" if _USANDO_FAKER else "fallback (stdlib)"
    log.info("Gerando dados sinteticos com %s (seed=%d)", motor, settings.SEED)

    qualidade, popularidade = atributos_livros(settings.N_LIVROS)
    dados = {
        "usuarios": gerar_usuarios(settings.N_USUARIOS),
        "livros": gerar_livros(settings.N_LIVROS),
        "emprestimos": gerar_emprestimos(
            settings.N_EMPRESTIMOS, settings.N_USUARIOS, settings.N_LIVROS, popularidade
        ),
        "avaliacoes": gerar_avaliacoes(
            settings.N_AVALIACOES, settings.N_USUARIOS, settings.N_LIVROS,
            popularidade, qualidade
        ),
    }
    contagem = {}
    for nome in DATASETS_BATCH:
        _salvar_csv(dados[nome], nome)
        contagem[nome] = len(dados[nome])
    return contagem


if __name__ == "__main__":
    main()
