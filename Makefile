.PHONY: help install test lint run run-demo docker-build docker-run k8s-apply clean

PYTHON ?= python

help:
	@echo "Available commands:"
	@echo "  make install       Install dependencies from requirements.txt"
	@echo "  make test          Run pytest automated test suite"
	@echo "  make run           Run application on port 8000"
	@echo "  make run-demo      Launch demo simulation in browser"
	@echo "  make docker-build  Build Docker image"
	@echo "  make docker-run    Run Docker container on port 8000"
	@echo "  make k8s-apply     Apply Kubernetes deployment manifests"
	@echo "  make clean         Remove Python build and cache artifacts"

install:
	$(PYTHON) -m pip install -r requirements.txt

test:
	$(PYTHON) -m pytest -v --tb=short

run:
	$(PYTHON) -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

run-demo:
	$(PYTHON) scripts/run_demo.py

docker-build:
	docker build -t kubernetes-troubleshooting-agent:latest .

docker-run:
	docker run -p 8000:8000 -e DEMO_MODE=true kubernetes-troubleshooting-agent:latest

k8s-apply:
	kubectl apply -k k8s/

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache
