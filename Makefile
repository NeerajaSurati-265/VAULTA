# Shortcuts for the common VAULTA tasks. Docker targets need Docker + Compose;
# test/eval run in your local Python environment (activate .venv first).
.PHONY: up down logs test eval

up:  ## build and start the whole stack in the background (UI: http://localhost:8501)
	docker compose up -d --build

down:  ## stop the stack (models and index volumes are kept)
	docker compose down

logs:  ## follow the logs of all services
	docker compose logs -f

test:  ## run the test suite (no Ollama needed)
	pytest

eval:  ## retrieval eval for all modes (semantic/hybrid need a local Ollama)
	python eval/run_eval.py --mode all
