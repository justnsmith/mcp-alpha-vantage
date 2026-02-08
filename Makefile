help:
	@echo "Available commands:"
	@echo "  make install      - Install production dependencies"
	@echo "  make install-dev  - Install development dependencies"
	@echo "  make test         - Run tests"
	@echo "  make lint         - Run linters"
	@echo "  make format       - Format code"
	@echo "  make clean        - Clean up generated files"
	@echo "  make run          - Run server in stdio mode"
	@echo "  make run-http     - Run server in HTTP mode"

install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements.txt

test:
	pytest -v

lint:
	ruff check src/ tests/
	black --check src/ tests/

format:
	black src/ tests/
	ruff check --fix src/ tests/

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

run:
	cd src && python server.py

run-http:
	cd src && uvicorn server:app --host 0.0.0.0 --port 8000 --reload
