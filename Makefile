# ClauseLens — one process, no Docker (D7). Node is build-time only; Python
# boots the demo. `make demo` is the single command used on stage.
#
# Run order from a clean checkout:   make backend  →  make demo
# (make backend creates the venv + installs deps; make demo builds the
#  frontend and launches uvicorn from that venv.)
#
# Cross-platform venv layout: POSIX venvs put executables in .venv/bin, Windows
# venvs (incl. Git Bash) put them in .venv/Scripts. We always invoke the venv's
# python as `$(PY) -m <tool>` so the demo can never pick up a system interpreter
# that lacks the installed packages.

SHELL := /bin/bash
VENV := backend/.venv
HOST ?= 127.0.0.1
PORT ?= 8000

ifeq ($(OS),Windows_NT)
  VENV_BIN := $(VENV)/Scripts
  PYTHON_BOOT ?= python
else
  VENV_BIN := $(VENV)/bin
  PYTHON_BOOT ?= python3
endif
PY := $(VENV_BIN)/python

.DEFAULT_GOAL := help
.PHONY: help backend build-frontend demo test clean

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

backend: ## Create venv and install backend deps
	$(PYTHON_BOOT) -m venv $(VENV)
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r backend/requirements.txt

build-frontend: ## Install deps (deterministic, from lockfile) and build into frontend/dist
	cd frontend && npm ci && npm run build

demo: build-frontend ## Build frontend, then launch the single FastAPI process
	@$(PY) -c "import uvicorn" 2>/dev/null || { \
		echo "Backend venv not ready (no uvicorn). Run 'make backend' first."; exit 1; }
	@echo "Serving ClauseLens at http://$(HOST):$(PORT)"
	$(PY) -m uvicorn app.main:app --app-dir backend --host $(HOST) --port $(PORT)

test: ## Run backend smoke tests (AWS integration test auto-skips without creds)
	$(PY) -m pytest backend -q

clean: ## Remove venv, node_modules, and build output
	rm -rf $(VENV) frontend/node_modules frontend/dist
