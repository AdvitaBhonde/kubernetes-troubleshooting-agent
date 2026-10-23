"""Pydantic data models and schemas for API requests, diagnostics, and resources."""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class DiagnosticSeverity(str, Enum):
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class ClusterStatus(BaseModel):
    connected: bool
    demo_mode: bool
    context_name: Optional[str] = None
    server_version: Optional[str] = None
    node_count: int = 0
    message: str = "Cluster status checked"


class ContainerStateInfo(BaseModel):
    state: str  # "running", "waiting", "terminated"
    reason: Optional[str] = None
    message: Optional[str] = None
    exit_code: Optional[int] = None


class ContainerInfo(BaseModel):
    name: str
    image: str
    ready: bool
    restart_count: int = 0
    current_state: ContainerStateInfo
    last_state: Optional[ContainerStateInfo] = None
    ports: List[int] = []
    cpu_request: Optional[str] = None
    memory_request: Optional[str] = None
    cpu_limit: Optional[str] = None
    memory_limit: Optional[str] = None


class PodDiagnosticInfo(BaseModel):
    name: str
    namespace: str
    phase: str
    node_name: Optional[str] = None
    pod_ip: Optional[str] = None
    restarts: int = 0
    containers: List[ContainerInfo] = []
    events: List[str] = []
    logs: Optional[str] = None
    previous_logs: Optional[str] = None
    conditions: Dict[str, bool] = {}
    created_at: Optional[str] = None


class EventInfo(BaseModel):
    type: str  # "Normal" or "Warning"
    reason: str
    message: str
    resource_kind: str
    resource_name: str
    namespace: str
    count: int = 1
    last_seen: Optional[str] = None


class DeploymentInfo(BaseModel):
    name: str
    namespace: str
    desired_replicas: int
    ready_replicas: int
    available_replicas: int
    updated_replicas: int
    selector: Dict[str, str] = {}
    conditions: List[str] = []


class ServiceInfo(BaseModel):
    name: str
    namespace: str
    service_type: str
    cluster_ip: Optional[str] = None
    ports: List[Dict[str, Any]] = []
    selector: Dict[str, str] = {}
    endpoints: List[str] = []
    has_endpoints: bool = True


class Finding(BaseModel):
    id: str
    title: str
    severity: DiagnosticSeverity
    resource_kind: str
    resource_name: str
    namespace: str
    evidence: List[str] = []
    likely_cause: str
    confidence: str = "High (Confirmed)"  # e.g. "High (Confirmed)", "Medium (Probable)", "Low (Hypothesis)"
    recommended_steps: List[str] = []
    kubectl_commands: List[str] = []
    safe_remediation: str
    manual_verification_required: bool = True
    is_ai_hypothesis: bool = False


class DiagnosticSummary(BaseModel):
    total_pods: int = 0
    healthy_pods: int = 0
    unhealthy_pods: int = 0
    total_deployments: int = 0
    total_services: int = 0
    total_warning_events: int = 0
    total_findings: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0


class DiagnosticReport(BaseModel):
    diagnostic_id: str
    timestamp: str
    namespace: str
    cluster_connected: bool
    demo_mode: bool
    ai_provider: str
    summary: DiagnosticSummary
    findings: List[Finding]
    ai_summary: Optional[str] = None
    ai_analysis_markdown: Optional[str] = None
    raw_evidence_count: int = 0


class DiagnoseRequest(BaseModel):
    namespace: Optional[str] = "default"
    use_ai: bool = True
    ai_provider: Optional[str] = None
    pod_name: Optional[str] = None
