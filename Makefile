# Charts In Motion — cross-platform dev workflow (Mac/Linux primary; Windows via Git Bash / WSL)
.PHONY: setup backend frontend dev clean test smoke gate

ifeq ($(OS),Windows_NT)
  PYTHON := .venv/Scripts/python.exe
  PIP := .venv/Scripts/pip.exe
  VENV_PY := python
else
  PYTHON := .venv/bin/python3
  PIP := .venv/bin/pip
  VENV_PY := python3
endif

setup:
	@echo "-> Creating Python virtual environment..."
	$(VENV_PY) -m venv .venv
	@echo "-> Installing Python dependencies..."
	$(PIP) install -r requirements.txt -q
	@echo "-> Installing frontend npm packages..."
	cd frontend && npm install --silent
	@echo "-> Seeding development database..."
	$(PYTHON) scripts/dev_setup.py
	@echo ""
	@echo "Setup complete. Run 'make dev' to start."

backend:
	$(PYTHON) -m uvicorn server.server:app \
		--reload \
		--reload-dir server \
		--host 127.0.0.1 \
		--port 8000 \
		--app-dir .

frontend:
	cd frontend && BROWSER=none npm start

dev:
	@echo "Starting backend on :8000 and frontend on :3000..."
	@$(MAKE) -j2 backend frontend

clean:
	rm -rf .venv frontend/node_modules frontend/build data/nse_data.db
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

test:
	$(PYTHON) -m unittest discover -s server/tests -v

smoke:
	$(PYTHON) scripts/smoke_test.py

gate: test smoke
	@echo "Dev gate passed."
