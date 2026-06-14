# Dicionario de Dados - BiblioData

_Gerado automaticamente em 2026-06-14T13:32:07._

## usuarios

- **Dominio:** Usuarios
- **Tipo:** Cadastral
- **Descricao:** Cadastro de leitores da biblioteca digital.
- **Dados pessoais (LGPD):** nome, email

| Coluna | Tipo | PII |
|---|---|---|
| id_usuario | int | - |
| nome | string | sim |
| email | string | sim |
| cidade | string | - |
| data_cadastro | date | - |

## livros

- **Dominio:** Acervo
- **Tipo:** Mestre
- **Descricao:** Catalogo do acervo (dado mestre / referencia).
- **Dados pessoais (LGPD):** nenhum

| Coluna | Tipo | PII |
|---|---|---|
| id_livro | int | - |
| titulo | string | - |
| autor | string | - |
| isbn | string | - |
| genero | string | - |
| editora | string | - |
| ano | int | - |

## emprestimos

- **Dominio:** Emprestimos
- **Tipo:** Transacional
- **Descricao:** Historico transacional de emprestimos virtuais.
- **Dados pessoais (LGPD):** nenhum

| Coluna | Tipo | PII |
|---|---|---|
| id_emprestimo | int | - |
| id_usuario | int | - |
| id_livro | int | - |
| data_emprestimo | date | - |
| data_devolucao | date | - |

## avaliacoes

- **Dominio:** Emprestimos
- **Tipo:** Transacional
- **Descricao:** Notas e comentarios deixados apos a leitura.
- **Dados pessoais (LGPD):** nenhum

| Coluna | Tipo | PII |
|---|---|---|
| id_avaliacao | int | - |
| id_usuario | int | - |
| id_livro | int | - |
| nota | int | - |
| comentario | string | - |
| data_avaliacao | date | - |

## acessos

- **Dominio:** Analise
- **Tipo:** Evento (streaming)
- **Descricao:** Eventos de streaming: buscas, cliques e visualizacoes.
- **Dados pessoais (LGPD):** nenhum

| Coluna | Tipo | PII |
|---|---|---|
| id_evento | string | - |
| id_usuario | int | - |
| tipo_evento | string | - |
| id_livro | int | - |
| timestamp_evento | timestamp | - |
