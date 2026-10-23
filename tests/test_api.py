"""Integration tests for FastAPI REST endpoints."""

from starlette.testclient import TestClient


def test_health_endpoint(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data
    assert data["demo_mode"] is True


def test_cluster_status_endpoint(client: TestClient):
    response = client.get("/api/cluster/status")
    assert response.status_code == 200
    data = response.json()
    assert data["connected"] is True
    assert data["demo_mode"] is True
    assert data["node_count"] > 0


def test_namespaces_endpoint(client: TestClient):
    response = client.get("/api/namespaces")
    assert response.status_code == 200
    namespaces = response.json()
    assert isinstance(namespaces, list)
    assert "default" in namespaces


def test_pods_endpoint(client: TestClient):
    response = client.get("/api/pods?namespace=default")
    assert response.status_code == 200
    pods = response.json()
    assert isinstance(pods, list)
    assert len(pods) > 0
    # Verify structure of first pod
    pod = pods[0]
    assert "name" in pod
    assert "phase" in pod
    assert "containers" in pod


def test_events_endpoint(client: TestClient):
    response = client.get("/api/events?namespace=default")
    assert response.status_code == 200
    events = response.json()
    assert isinstance(events, list)
    assert len(events) > 0
    assert any(e["type"] == "Warning" for e in events)


def test_deployments_endpoint(client: TestClient):
    response = client.get("/api/deployments?namespace=default")
    assert response.status_code == 200
    deployments = response.json()
    assert isinstance(deployments, list)
    assert len(deployments) > 0


def test_services_endpoint(client: TestClient):
    response = client.get("/api/services?namespace=default")
    assert response.status_code == 200
    services = response.json()
    assert isinstance(services, list)
    assert len(services) > 0


def test_diagnose_post_endpoint(client: TestClient):
    payload = {
        "namespace": "default",
        "use_ai": True,
        "ai_provider": "rules",
    }
    response = client.post("/api/diagnose", json=payload)
    assert response.status_code == 200
    report = response.json()

    assert "diagnostic_id" in report
    assert report["namespace"] == "default"
    assert report["demo_mode"] is True
    assert len(report["findings"]) > 0
    assert report["summary"]["total_findings"] > 0
    assert report["summary"]["critical_count"] > 0
    assert "Confirmed Observations" in report["ai_analysis_markdown"]

    # Test retrieving by diagnostic_id
    diag_id = report["diagnostic_id"]
    get_res = client.get(f"/api/diagnostics/{diag_id}")
    assert get_res.status_code == 200
    cached_report = get_res.json()
    assert cached_report["diagnostic_id"] == diag_id


def test_get_invalid_diagnostic_id_returns_404(client: TestClient):
    response = client.get("/api/diagnostics/non-existent-uuid-12345")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
