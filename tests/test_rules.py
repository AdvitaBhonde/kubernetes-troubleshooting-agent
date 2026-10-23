"""Unit tests for deterministic Kubernetes diagnostic rules."""

from app.diagnostics.rules import DiagnosticRulesEngine
from app.models.schemas import (
    PodDiagnosticInfo,
    ContainerInfo,
    ContainerStateInfo,
    EventInfo,
    DeploymentInfo,
    ServiceInfo,
    DiagnosticSeverity,
)


def test_crashloop_backoff_detection():
    container = ContainerInfo(
        name="web",
        image="nginx:alpine",
        ready=False,
        restart_count=8,
        current_state=ContainerStateInfo(state="waiting", reason="CrashLoopBackOff"),
        last_state=ContainerStateInfo(state="terminated", reason="Error", exit_code=1),
    )
    pod = PodDiagnosticInfo(
        name="web-crash-pod",
        namespace="default",
        phase="Running",
        restarts=8,
        containers=[container],
        logs="FATAL: Configuration file missing",
    )

    finding = DiagnosticRulesEngine._check_crashloop(pod, [])
    assert finding is not None
    assert finding.severity == DiagnosticSeverity.CRITICAL
    assert "CrashLoopBackOff" in finding.title
    assert finding.resource_name == "web-crash-pod"
    assert "kubectl logs" in finding.recommended_steps[0]
    assert any("exit code: 1" in e for e in finding.evidence)


def test_image_pull_backoff_detection():
    container = ContainerInfo(
        name="frontend",
        image="registry.invalid/repo/app:v999",
        ready=False,
        restart_count=0,
        current_state=ContainerStateInfo(state="waiting", reason="ImagePullBackOff"),
    )
    event = EventInfo(
        type="Warning",
        reason="Failed",
        message="Failed to pull image 'registry.invalid/repo/app:v999': not found",
        resource_kind="Pod",
        resource_name="frontend-pull-fail",
        namespace="default",
    )
    pod = PodDiagnosticInfo(
        name="frontend-pull-fail",
        namespace="default",
        phase="Pending",
        containers=[container],
    )

    finding = DiagnosticRulesEngine._check_image_pull(pod, [event])
    assert finding is not None
    assert finding.severity == DiagnosticSeverity.HIGH
    assert "Image Pull Failure" in finding.title
    assert "does not exist in the specified container registry" in finding.likely_cause


def test_oom_killed_detection():
    container = ContainerInfo(
        name="worker",
        image="worker:latest",
        ready=False,
        restart_count=4,
        current_state=ContainerStateInfo(state="waiting", reason="CrashLoopBackOff"),
        last_state=ContainerStateInfo(state="terminated", reason="OOMKilled", exit_code=137),
        memory_limit="256Mi",
    )
    pod = PodDiagnosticInfo(
        name="worker-oom-pod",
        namespace="default",
        phase="Running",
        restarts=4,
        containers=[container],
    )

    finding = DiagnosticRulesEngine._check_oom_killed(pod, [])
    assert finding is not None
    assert finding.severity == DiagnosticSeverity.CRITICAL
    assert "OOMKilled" in finding.title
    assert "256Mi" in finding.likely_cause or "cgroup" in finding.likely_cause
    assert any("exit code 137" in e for e in finding.evidence)


def test_failed_scheduling_detection():
    pod = PodDiagnosticInfo(
        name="spark-heavy-pod",
        namespace="default",
        phase="Pending",
        node_name=None,
    )
    event = EventInfo(
        type="Warning",
        reason="FailedScheduling",
        message="0/5 nodes are available: 5 Insufficient memory.",
        resource_kind="Pod",
        resource_name="spark-heavy-pod",
        namespace="default",
    )

    finding = DiagnosticRulesEngine._check_scheduling_and_pending(pod, [event])
    assert finding is not None
    assert finding.severity == DiagnosticSeverity.HIGH
    assert "Pending / Failed Scheduling" in finding.title
    assert "Insufficient memory" in finding.evidence[2] or "scheduler cannot place" in finding.likely_cause


def test_probe_failure_detection():
    pod = PodDiagnosticInfo(
        name="api-gateway",
        namespace="default",
        phase="Running",
    )
    event = EventInfo(
        type="Warning",
        reason="Unhealthy",
        message="Liveness probe failed: HTTP probe failed with statuscode: 500",
        resource_kind="Pod",
        resource_name="api-gateway",
        namespace="default",
    )

    finding = DiagnosticRulesEngine._check_probe_failures(pod, [event])
    assert finding is not None
    assert finding.severity == DiagnosticSeverity.HIGH
    assert "Liveness Probe Failure" in finding.title
    assert "health check endpoint" in finding.likely_cause


def test_deployment_replicas_unavailable():
    dep = DeploymentInfo(
        name="order-service",
        namespace="default",
        desired_replicas=3,
        ready_replicas=0,
        available_replicas=0,
        updated_replicas=3,
        selector={"app": "order"},
        conditions=["ReplicaFailure: Pod admission denied"],
    )

    findings = DiagnosticRulesEngine.evaluate_deployment(dep, [])
    assert len(findings) == 1
    assert findings[0].severity == DiagnosticSeverity.CRITICAL
    assert "Deployment Replicas Unavailable" in findings[0].title
    assert findings[0].resource_name == "order-service"


def test_service_with_no_endpoints():
    svc = ServiceInfo(
        name="auth-service",
        namespace="default",
        service_type="ClusterIP",
        cluster_ip="10.96.20.10",
        selector={"app": "auth"},
        endpoints=[],
        has_endpoints=False,
    )

    findings = DiagnosticRulesEngine.evaluate_service(svc, [])
    assert len(findings) == 1
    assert findings[0].severity == DiagnosticSeverity.HIGH
    assert "Service Has No Active Endpoints" in findings[0].title
    assert "auth-service" in findings[0].resource_name


def test_dns_and_network_failure():
    event = EventInfo(
        type="Warning",
        reason="DNSFailure",
        message="CoreDNS degraded: dial tcp 10.96.0.10:53: i/o timeout",
        resource_kind="Node",
        resource_name="worker-node-1",
        namespace="kube-system",
    )

    findings = DiagnosticRulesEngine.evaluate_network_and_dns([event], "kube-system")
    assert len(findings) == 1
    assert "Potential Networking / DNS Failure" in findings[0].title
    assert "CoreDNS" in findings[0].likely_cause or "network policy" in findings[0].likely_cause
