# ClauseLens — one process, no Docker (D7). Node is build-time only; Python
# boots the demo. `make demo` is the single command used on stage.

SHELL := /bin/bash
VENV := backend/.venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
HOST ?= 127.0.0.1
PORT ?= 8000

.DEFAULT_GOAL := help
.PHONY: help backend build-frontend demo test clean

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

backend: ## Create venv and install backend deps
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r backend/requirements.txt

build-frontend: ## Install deps and build the React app into frontend/dist
	cd frontend && npm install && npm run build

demo: build-frontend ## Build frontend, then launch the single FastAPI process
	@echo "Serving ClauseLens at http://$(HOST):$(PORT)"
	cd backend && ../$(VENV)/bin/uvicorn app.main:app --host $(HOST) --port $(PORT)

test: ## Run backend smoke tests (AWS integration test auto-skips without creds)
	cd backend && ../$(VENV)/bin/pytest -q

clean: ## Remove venv, node_modules, and build output
	rm -rf $(VENV) frontend/node_modules frontend/dist
