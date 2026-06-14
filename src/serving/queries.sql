-- Consultas analiticas de Consumo (Serving) sobre a camada Gold.
-- Executar no DuckDB: duckdb data/gold/bibliodata.duckdb < src/serving/queries.sql
-- (ou abrir o .sqlite no fallback)

-- 1. Visao geral
SELECT * FROM kpis_gerais;

-- 2. Top 10 livros mais emprestados
SELECT titulo, genero, total_emprestimos
FROM top_livros
ORDER BY total_emprestimos DESC
LIMIT 10;

-- 3. Distribuicao de emprestimos por genero
SELECT genero, total_emprestimos
FROM uso_por_genero
ORDER BY total_emprestimos DESC;

-- 4. Livros mais bem avaliados (com pelo menos 2 avaliacoes)
SELECT titulo, nota_media, qtd_avaliacoes
FROM avaliacao_por_livro
ORDER BY nota_media DESC, qtd_avaliacoes DESC
LIMIT 10;

-- 5. Comportamento de acesso (streaming)
SELECT tipo_evento, total
FROM eventos_por_tipo
ORDER BY total DESC;
