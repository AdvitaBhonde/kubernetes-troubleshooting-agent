"""Service layer providing agent functionality to API routes."""

from typing import List, Optional
from app.kubernetes_client.collector import KubernetesCollector
from app.diagnostics.engine import DiagnosticEngine
from app.models.schemas import (
    ClusterStatus,
    PodDiagnosticInfo,
    EventInfo,
    DeploymentInfo,
    ServiceInfo,
    DiagnosticReport,
    DiagnoseRequest,
)

# Shared singleton instances
collector = KubernetesCollector()
engine = DiagnosticEngine(collector=collector)


class AgentService:
    """Service facade connecting API endpoints to collector and diagnostic engine."""

    @staticmethod
    def get_cluster_status() -> ClusterStatus:
        return collector.get_cluster_status()

    @staticmethod
    def get_namespaces() -> List[str]:
        return collector.get_namespaces()

    @staticmethod
    def get_pods(namespace: str = "default") -> List[PodDiagnosticInfo]:
        return collector.get_pods(namespace=namespace)

    @staticmethod
    def get_events(namespace: str = "default") -> List[EventInfo]:
        return collector.get_events(namespace=namespace)

    @staticmethod
    def get_deployments(namespace: str = "default") -> List[DeploymentInfo]:
        return collector.get_deployments(namespace=namespace)

    @staticmethod
    def get_services(namespace: str = "default") -> List[ServiceInfo]:
        return collector.get_services(namespace=namespace)

    @staticmethod
    def run_diagnostics(request: DiagnoseRequest) -> DiagnosticReport:
        return engine.diagnose(
            namespace=request.namespace or "default",
            use_ai=request.use_ai,
            ai_provider_name=request.ai_provider,
            pod_name=request.pod_name,
        )

    @staticmethod
    def get_diagnostic_report(diagnostic_id: str) -> Optional[DiagnosticReport]:
        return engine.get_report(diagnostic_id)
