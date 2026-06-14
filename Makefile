.PHONY: install run dash gold-query clean infra-up infra-down test-gate

install:
	pip install -r requirements.txt

run:            ## executa o pipeline completo
	python pipeline.py

run-small:      ## execucao rapida com volumes reduzidos
	N_USUARIOS=800 N_LIVROS=400 N_EMPRESTIMOS=1500 N_AVALIACOES=300 N_EVENTOS_STREAM=200 python pipeline.py

dash:           ## abre o painel de consumo
	streamlit run src/serving/dashboard.py

test-gate:      ## demonstra o quality gate bloqueando a Gold
	QUALITY_GATE_MIN_PASS_RATE=0.999 python pipeline.py --no-gen

infra-up:       ## sobe Kafka (Redpanda) + Metabase
	docker compose up -d

infra-down:
	docker compose down

clean:          ## limpa dados gerados, logs e catalogo
	rm -rf data/raw/* data/bronze/* data/silver/* data/gold/* data/quarantine/* data/stream_queue/* logs/*.log logs/*.jsonl catalog/*.json catalog/*.md
