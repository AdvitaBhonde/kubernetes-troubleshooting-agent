"""Pytest configuration and shared test fixtures."""

import os
import pytest
from starlette.testclient import TestClient

from app.main import app
from app.kubernetes_client.collector import KubernetesCollector
from app.diagnostics.engine import DiagnosticEngine


@pytest.fixture(scope="session", autouse=True)
def configure_test_environment():
    """Sets test environment variables."""
    os.environ["DEMO_MODE"] = "true"
    os.environ["AI_PROVIDER"] = "rules"


@pytest.fixture
def client():
    """FastAPI test client fixture."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def demo_collector():
    """Kubernetes collector in demo mode."""
    return KubernetesCollector(demo_mode=True)


@pytest.fixture
def test_engine(demo_collector):
    """Diagnostic engine with demo collector."""
    return DiagnosticEngine(collector=demo_collector)
