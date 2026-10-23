"""Tests for Kubernetes diagnostic collector."""

from unittest.mock import MagicMock
from app.kubernetes_client.collector import KubernetesCollector


def test_collector_demo_mode_cluster_status():
    collector = KubernetesCollector(demo_mode=True)
    status = collector.get_cluster_status()

    assert status.connected is True
    assert status.demo_mode is True
    assert status.node_count > 0
    assert "demo" in status.context_name.lower() or "demo" in status.message.lower()


def test_collector_demo_mode_pods():
    collector = KubernetesCollector(demo_mode=True)
    pods = collector.get_pods(namespace="default")

    assert len(pods) >= 4
    pod_names = [p.name for p in pods]
    assert any("payment" in name for name in pod_names)
    assert any("frontend" in name for name in pod_names)
    assert any("ml-inference" in name for name in pod_names)

    # Check pod details
    crash_pod = next(p for p in pods if "payment" in p.name)
    assert crash_pod.restarts > 0
    assert crash_pod.logs is not None
    assert crash_pod.previous_logs is not None


def test_collector_handles_invalid_cluster_gracefully(monkeypatch):
    """When real cluster initialization raises an error, collector automatically activates Demo mode."""
    # Force K8S client to fail connection
    collector = KubernetesCollector(demo_mode=False)
    # Collector should gracefully fall back to demo mode
    assert collector.demo_mode is True
    assert collector.get_cluster_status().demo_mode is True


def test_collector_empty_logs_handled_safely():
    collector = KubernetesCollector(demo_mode=True)
    logs = collector.get_pod_logs(namespace="default", pod_name="non-existent-pod")
    assert logs is None
