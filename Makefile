.PHONY: up down down-volumes down-snap-fix logs ps experiment analyze analyze-docker final clean clean-raw-experiment

PYTHON ?= python3
ANALYSIS_IMAGE ?= python:3.12-slim
SCENARIO_DURATION ?= 20s
WORKLOAD ?= tens
RESULTS_DIR ?= results
RUN_LABEL ?= $(WORKLOAD)
RUN_DIR := $(RESULTS_DIR)/runs/$(RUN_LABEL)
K6_METRICS := $(RUN_DIR)/raw/k6_metrics.json
K6_METRICS_CONTAINER := /results/runs/$(RUN_LABEL)/raw/k6_metrics.json

up:
	docker compose up -d --build

down:
	docker compose down

down-volumes:
	docker compose down -v --remove-orphans

down-snap-fix:
	sudo snap restart docker
	@echo "Aguardando Docker voltar..."
	@until docker info >/dev/null 2>&1; do sleep 2; done
	docker compose down -v --remove-orphans

logs:
	docker compose logs -f --tail=100

ps:
	docker compose ps

experiment:
	mkdir -p $(RUN_DIR)/raw
	WORKLOAD=$(WORKLOAD) SCENARIO_DURATION=$(SCENARIO_DURATION) docker compose --profile experiments run --rm --no-deps --entrypoint k6 k6 run --out json=$(K6_METRICS_CONTAINER) /scripts/soap_rest.js

analyze:
	$(PYTHON) experiments/analyze_results.py --input $(K6_METRICS) --outdir $(RUN_DIR)

analyze-docker:
	docker run --rm -v "$$(pwd):/app" -w /app $(ANALYSIS_IMAGE) sh -c "pip install -r experiments/requirements.txt && python experiments/analyze_results.py --input $(K6_METRICS) --outdir $(RUN_DIR)"

final: experiment analyze-docker
	docker run --rm --network host -v "$$(pwd):/app" -w /app $(ANALYSIS_IMAGE) sh -c "pip install requests==2.32.3 && python scripts/collect_evidence.py --output $(RUN_DIR)/evidence_runtime.json"
	@echo "Resultados finais em $(RUN_DIR)/tables, $(RUN_DIR)/figures, $(RUN_DIR)/raw e $(RUN_DIR)/evidence_runtime.json"

clean-raw-experiment:
	rm -f $(RUN_DIR)/raw/k6_metrics.json $(RUN_DIR)/raw/experiment_latency.csv

clean:
	rm -rf $(RESULTS_DIR)/runs results/raw/*.csv results/raw/*.json results/tables/*.csv results/figures/*.png results/evidence_runtime.json
