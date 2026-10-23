"""FastAPI router defining all REST endpoints for Kubernetes troubleshooting."""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status

from app.core.config import settings
from app.models.schemas import (
    ClusterStatus,
    PodDiagnosticInfo,
    EventInfo,
    DeploymentInfo,
    ServiceInfo,
    DiagnosticReport,
    DiagnoseRequest,
)
from app.services.agent_service import AgentService

api_router = APIRouter()


@api_router.get("/health", tags=["Health"], summary="System Health Check")
def health_check():
    """Returns application health status, version, and cluster mode."""
    cluster_status = AgentService.get_cluster_status()
    return {
        "status": "healthy",
        "app_name": settings.app_name,
        "version": settings.app_version,
        "demo_mode": cluster_status.demo_mode,
        "cluster_connected": cluster_status.connected,
    }


@api_router.get(
    "/api/cluster/status",
    response_model=ClusterStatus,
    tags=["Cluster"],
    summary="Get Kubernetes Cluster Connectivity Status",
)
def get_cluster_status():
    """Returns cluster connection details, context name, node count, and demo mode indicator."""
    return AgentService.get_cluster_status()


@api_router.get(
    "/api/namespaces",
    response_model=List[str],
    tags=["Cluster"],
    summary="List Accessible Namespaces",
)
def get_namespaces():
    """Lists available namespaces in the cluster or demo environment."""
    return AgentService.get_namespaces()


@api_router.get(
    "/api/pods",
    response_model=List[PodDiagnosticInfo],
    tags=["Diagnostics Data"],
    summary="List Pods in Namespace",
)
def get_pods(namespace: str = Query("default", description="Namespace to inspect")):
    """Retrieves pods, container states, restart counts, and diagnostic logs."""
    return AgentService.get_pods(namespace=namespace)


@api_router.get(
    "/api/events",
    response_model=List[EventInfo],
    tags=["Diagnostics Data"],
    summary="List Recent Kubernetes Events",
)
def get_events(namespace: str = Query("default", description="Namespace to inspect")):
    """Retrieves recent warning and normal cluster events."""
    return AgentService.get_events(namespace=namespace)


@api_router.get(
    "/api/deployments",
    response_model=List[DeploymentInfo],
    tags=["Diagnostics Data"],
    summary="List Deployments in Namespace",
)
def get_deployments(namespace: str = Query("default", description="Namespace to inspect")):
    """Retrieves deployment replica specifications and rollout conditions."""
    return AgentService.get_deployments(namespace=namespace)


@api_router.get(
    "/api/services",
    response_model=List[ServiceInfo],
    tags=["Diagnostics Data"],
    summary="List Services and Endpoints",
)
def get_services(namespace: str = Query("default", description="Namespace to inspect")):
    """Retrieves services, port configurations, selectors, and backing endpoint IP status."""
    return AgentService.get_services(namespace=namespace)


@api_router.post(
    "/api/diagnose",
    response_model=DiagnosticReport,
    status_code=status.HTTP_200_OK,
    tags=["Root Cause Analysis"],
    summary="Run AI & Rule-Based Kubernetes Diagnosis",
)
def run_diagnostics(payload: DiagnoseRequest):
    """Executes automated data collection, evaluates diagnostic rules, and generates AI root cause analysis."""
    try:
        report = AgentService.run_diagnostics(payload)
        return report
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Diagnostic evaluation failed: {str(e)}",
        )


@api_router.get(
    "/api/diagnostics/{diagnostic_id}",
    response_model=DiagnosticReport,
    tags=["Root Cause Analysis"],
    summary="Get Diagnostic Report by ID",
)
def get_diagnostic_report(diagnostic_id: str):
    """Retrieves a previously generated diagnostic report by its unique ID."""
    report = AgentService.get_diagnostic_report(diagnostic_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Diagnostic report '{diagnostic_id}' was not found.",
        )
    return report
