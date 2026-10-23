"""Diagnostic Engine orchestrator.

Coordinates read-only data collection, deterministic rule evaluations,
and AI-assisted root cause analysis.
"""

import uuid
from datetime import datetime, timezone
from typing import Dict, Optional, List

from app.core.logging import logger
from app.kubernetes_client.collector import KubernetesCollector
from app.diagnostics.rules import DiagnosticRulesEngine
from app.ai.factory import get_ai_provider
from app.models.schemas import (
    DiagnosticReport,
    DiagnosticSummary,
    DiagnosticSeverity,
    Finding,
    PodDiagnosticInfo,
)


class DiagnosticEngine:
    """Orchestrates diagnostic data collection and reasoning."""

    def __init__(self, collector: Optional[KubernetesCollector] = None):
        self.collector = collector or KubernetesCollector()
        self._history: Dict[str, DiagnosticReport] = {}

    def diagnose(
        self,
        namespace: str = "default",
        use_ai: bool = True,
        ai_provider_name: Optional[str] = None,
        pod_name: Optional[str] = None,
    ) -> DiagnosticReport:
        """Executes a full diagnostic run across the target namespace."""
        diagnostic_id = f"diag-{uuid.uuid4().hex[:10]}"
        now_iso = datetime.now(timezone.utc).isoformat()

        cluster_status = self.collector.get_cluster_status()

        # 1. Collect resources
        pods = self.collector.get_pods(namespace=namespace)
        if pod_name:
            pods = [p for p in pods if p.name == pod_name]

        events = self.collector.get_events(namespace=namespace)
        deployments = self.collector.get_deployments(namespace=namespace)
        services = self.collector.get_services(namespace=namespace)

        # 2. Run deterministic rule evaluation
        findings = DiagnosticRulesEngine.evaluate_all(
            pods=pods,
            events=events,
            deployments=deployments,
            services=services,
            namespace=namespace,
        )

        # 3. Calculate summary metrics
        total_pods = len(pods)
        healthy_pods = sum(
            1 for p in pods if p.phase == "Running" and p.conditions.get("Ready", False) and p.restarts == 0
        )
        unhealthy_pods = total_pods - healthy_pods

        critical_count = sum(1 for f in findings if f.severity == DiagnosticSeverity.CRITICAL)
        high_count = sum(1 for f in findings if f.severity == DiagnosticSeverity.HIGH)
        medium_count = sum(1 for f in findings if f.severity == DiagnosticSeverity.MEDIUM)
        low_count = sum(1 for f in findings if f.severity == DiagnosticSeverity.LOW)

        summary = DiagnosticSummary(
            total_pods=total_pods,
            healthy_pods=healthy_pods,
            unhealthy_pods=unhealthy_pods,
            total_deployments=len(deployments),
            total_services=len(services),
            total_warning_events=sum(1 for e in events if e.type == "Warning"),
            total_findings=len(findings),
            critical_count=critical_count,
            high_count=high_count,
            medium_count=medium_count,
            low_count=low_count,
        )

        # 4. Run AI reasoning if requested
        provider = get_ai_provider(ai_provider_name)
        ai_analysis_md = None
        ai_summary = None

        if use_ai:
            try:
                ai_analysis_md = provider.analyze(
                    findings=findings,
                    pods=pods,
                    events=events,
                    namespace=namespace,
                )
                ai_summary = f"Analysis generated via {provider.get_name()} across {len(findings)} findings."
            except Exception as e:
                logger.error(f"AI Provider analysis failed: {e}")
                ai_analysis_md = f"AI analysis unavailable: {str(e)}"
                ai_summary = "AI analysis failed; falling back to deterministic findings."

        report = DiagnosticReport(
            diagnostic_id=diagnostic_id,
            timestamp=now_iso,
            namespace=namespace,
            cluster_connected=cluster_status.connected,
            demo_mode=cluster_status.demo_mode,
            ai_provider=provider.get_name(),
            summary=summary,
            findings=findings,
            ai_summary=ai_summary,
            ai_analysis_markdown=ai_analysis_md,
            raw_evidence_count=len(events) + len(pods),
        )

        # Store in historical cache
        self._history[diagnostic_id] = report
        return report

    def get_report(self, diagnostic_id: str) -> Optional[DiagnosticReport]:
        """Retrieves a previously generated diagnostic report."""
        return self._history.get(diagnostic_id)
