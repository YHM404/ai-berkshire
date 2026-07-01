SHELL := /bin/bash
.DEFAULT_GOAL := dev

.PHONY: dev install build api frontend clean

dev:
	@set -euo pipefail; \
	pids=(); \
	cleanup() { \
		echo; \
		echo "Stopping AI Berkshire dev servers..."; \
		trap - INT TERM EXIT; \
		for pid in "$${pids[@]}"; do \
			kill "$$pid" 2>/dev/null || true; \
		done; \
		wait "$${pids[@]}" 2>/dev/null || true; \
	}; \
	trap 'cleanup; exit 0' INT TERM; \
	trap cleanup EXIT; \
	echo "Starting FastAPI backend on http://localhost:8000"; \
	uv run uvicorn server.app:app --host 0.0.0.0 --port 8000 & \
	pids+=("$$!"); \
	echo "Starting React frontend on http://localhost:5173"; \
	(cd frontend && npm run dev) & \
	pids+=("$$!"); \
	echo; \
	echo "Open: http://localhost:5173"; \
	echo "Press Ctrl+C to stop both servers."; \
	wait "$${pids[@]}"

install:
	uv sync
	cd frontend && npm install

build:
	python -m py_compile server/app.py agent/chat_agent.py agent/runner.py web/db.py
	uv run python scripts/verify_final_report_only.py
	uv run python scripts/verify_research_report_tool.py
	cd frontend && npm run test:markdown
	cd frontend && npm run build

api:
	uv run uvicorn server.app:app --host 0.0.0.0 --port 8000

frontend:
	cd frontend && npm run dev

clean:
	rm -rf frontend/dist
