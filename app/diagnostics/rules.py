"""Deterministic diagnostic rules engine for Kubernetes resources.

Evaluates observed facts against 10 distinct failure patterns, producing
structured findings with verified evidence, severity ratings, and actionable
troubleshooting commands.
"""

import re
from typing import List, Dict, Any, Optional

from app.models.schemas import (
    PodDiagnosticInfo,
    EventInfo,
    DeploymentInfo,
    ServiceInfo,
    Finding,
    DiagnosticSeverity,
)


class DiagnosticRulesEngine:
    """Evaluates cluster diagnostic artifacts using deterministic rules."""

    @classmethod
    def evaluate_all(
        cls,
        pods: List[PodDiagnosticInfo],
        events: List[EventInfo],
        deployments: List[DeploymentInfo],
        services: List[ServiceInfo],
        namespace: str,
    ) -> List[Finding]:
        """Runs the complete rule suite across all inspected resources."""
        findings: List[Finding] = []

        # 1. Evaluate Pods
        for pod in pods:
            findings.extend(cls.evaluate_pod(pod, events))

        # 2. Evaluate Deployments
        for dep in deployments:
            findings.extend(cls.evaluate_deployment(dep, events))

        # 3. Evaluate Services & Endpoints
        for svc in services:
            findings.extend(cls.evaluate_service(svc, pods))

        # 4. Evaluate Cluster-wide Network/DNS Events
        findings.extend(cls.evaluate_network_and_dns(events, namespace))

        # Deduplicate findings by (resource_kind, resource_name, title)
        unique_findings = []
        seen = set()
        for f in findings:
            key = (f.resource_kind, f.resource_name, f.title)
            if key not in seen:
                seen.add(key)
                unique_findings.append(f)

        return unique_findings

    @classmethod
    def evaluate_pod(cls, pod: PodDiagnosticInfo, events: List[EventInfo]) -> List[Finding]:
        """Runs rule checks for a specific Pod."""
        findings: List[Finding] = []
        pod_events = [e for e in events if e.resource_name == pod.name or e.resource_name.startswith(pod.name)]

        # Check 1: CrashLoopBackOff & High Restarts
        crash_finding = cls._check_crashloop(pod, pod_events)
        if crash_finding:
            findings.append(crash_finding)

        # Check 2: ImagePullBackOff & ErrImagePull
        image_finding = cls._check_image_pull(pod, pod_events)
        if image_finding:
            findings.append(image_finding)

        # Check 3: OOMKilled
        oom_finding = cls._check_oom_killed(pod, pod_events)
        if oom_finding:
            findings.append(oom_finding)

        # Check 4: Failed Scheduling & Pending Pods
        sched_finding = cls._check_scheduling_and_pending(pod, pod_events)
        if sched_finding:
            findings.append(sched_finding)

        # Check 5: Probe Failures (Liveness / Readiness)
        probe_finding = cls._check_probe_failures(pod, pod_events)
        if probe_finding:
            findings.append(probe_finding)

        return findings

    @classmethod
    def _check_crashloop(cls, pod: PodDiagnosticInfo, events: List[EventInfo]) -> Optional[Finding]:
        """Rule 1: Detects CrashLoopBackOff or repeatedly failing containers."""
        for c in pod.containers:
            is_waiting_crashloop = (
                c.current_state.state == "waiting" and c.current_state.reason == "CrashLoopBackOff"
            )
            has_high_restarts = c.restart_count > 2
            is_terminated_error = (
                c.last_state
                and c.last_state.state == "terminated"
                and c.last_state.exit_code is not None
                and c.last_state.exit_code != 0
                and c.last_state.exit_code != 137  # Handled by OOM rule
            )

            if is_waiting_crashloop or (has_high_restarts and is_terminated_error):
                evidence = [
                    f"Container '{c.name}' in Pod '{pod.name}' is in CrashLoopBackOff.",
                    f"Restart count: {c.restart_count}.",
                ]
                if c.last_state and c.last_state.exit_code is not None:
                    evidence.append(f"Last termination exit code: {c.last_state.exit_code} ({c.last_state.reason or 'Error'}).")

                # Extract relevant log lines if available
                log_snippet = None
                if pod.logs:
                    error_lines = [
                        line.strip()
                        for line in pod.logs.splitlines()
                        if any(k in line.lower() for k in ["fatal", "error", "exception", "panic", "refused", "timeout"])
                    ]
                    if error_lines:
                        log_snippet = "; ".join(error_lines[-2:])
                        evidence.append(f"Log error excerpt: {log_snippet}")

                likely_cause = (
                    f"Application process in container '{c.name}' starts and then immediately crashes or exits with code {c.last_state.exit_code if c.last_state else 1}. "
                    + (f"Observed error: '{log_snippet}'" if log_snippet else "Usually caused by unhandled exceptions, missing configuration, or unreachable external dependencies.")
                )

                return Finding(
                    id=f"crashloop-{pod.namespace}-{pod.name}-{c.name}",
                    title=f"Container in CrashLoopBackOff ({c.name})",
                    severity=DiagnosticSeverity.CRITICAL,
                    resource_kind="Pod",
                    resource_name=pod.name,
                    namespace=pod.namespace,
                    evidence=evidence,
                    likely_cause=likely_cause,
                    confidence="High (Confirmed)",
                    recommended_steps=[
                        f"Check previous container logs using: kubectl logs {pod.name} -c {c.name} -n {pod.namespace} --previous",
                        "Inspect environment variables and ConfigMaps mounted into the container.",
                        "Verify that all dependent services (databases, caches, upstream APIs) are reachable.",
                        "Check if application requires specific entrypoint arguments or file permissions.",
                    ],
                    kubectl_commands=[
                        f"kubectl describe pod {pod.name} -n {pod.namespace}",
                        f"kubectl logs {pod.name} -c {c.name} -n {pod.namespace} --previous --tail=100",
                        f"kubectl get pod {pod.name} -n {pod.namespace} -o jsonpath='{{.status.containerStatuses}}'",
                    ],
                    safe_remediation="Inspect previous logs and application error traces before restarting. Do not delete the pod until logs have been examined.",
                    manual_verification_required=True,
                    is_ai_hypothesis=False,
                )
        return None

    @classmethod
    def _check_image_pull(cls, pod: PodDiagnosticInfo, events: List[EventInfo]) -> Optional[Finding]:
        """Rules 2 & 3: Detects ImagePullBackOff and ErrImagePull."""
        for c in pod.containers:
            reason = c.current_state.reason or ""
            is_pull_error = reason in ["ImagePullBackOff", "ErrImagePull"]

            pull_event = next(
                (e for e in events if "image" in e.message.lower() and any(k in e.message.lower() for k in ["failed", "not found", "errimagepull", "back-off"])),
                None,
            )

            if is_pull_error or pull_event:
                evidence = [
                    f"Container '{c.name}' image: '{c.image}'.",
                    f"Current container state: waiting ({reason or 'ErrImagePull'}).",
                ]
                if pull_event:
                    evidence.append(f"Kubernetes Event: {pull_event.message}")

                # Determine specific cause
                msg_lower = (pull_event.message if pull_event else "").lower()
                if "not found" in msg_lower or "notfound" in msg_lower:
                    likely_cause = f"The image tag '{c.image}' does not exist in the specified container registry or the repository name is misspelled."
                elif "unauthorized" in msg_lower or "authentication" in msg_lower or "denied" in msg_lower:
                    likely_cause = "Authentication failure connecting to container registry. imagePullSecrets may be missing or expired."
                else:
                    likely_cause = f"Kubernetes worker node failed to pull container image '{c.image}' from the container registry."

                return Finding(
                    id=f"imagepull-{pod.namespace}-{pod.name}-{c.name}",
                    title=f"Container Image Pull Failure ({c.name})",
                    severity=DiagnosticSeverity.HIGH,
                    resource_kind="Pod",
                    resource_name=pod.name,
                    namespace=pod.namespace,
                    evidence=evidence,
                    likely_cause=likely_cause,
                    confidence="High (Confirmed)",
                    recommended_steps=[
                        f"Verify that image '{c.image}' exists by running 'docker pull {c.image}' locally.",
                        "Check if the image tag is valid, correctly spelled, and published.",
                        "If using a private registry, verify that the imagePullSecret is attached to the pod or service account.",
                        "Verify network connectivity from worker nodes to the container registry.",
                    ],
                    kubectl_commands=[
                        f"kubectl describe pod {pod.name} -n {pod.namespace}",
                        f"kubectl get secret -n {pod.namespace}",
                        f"kubectl get pod {pod.name} -n {pod.namespace} -o jsonpath='{{.spec.imagePullSecrets}}'",
                    ],
                    safe_remediation="Correct the image name or tag in the deployment manifest, or create/update the required imagePullSecret.",
                    manual_verification_required=True,
                    is_ai_hypothesis=False,
                )
        return None

    @classmethod
    def _check_oom_killed(cls, pod: PodDiagnosticInfo, events: List[EventInfo]) -> Optional[Finding]:
        """Rule 4: Detects Out-Of-Memory termination (ExitCode 137 / OOMKilled)."""
        for c in pod.containers:
            was_oom = False
            exit_code = None
            if c.last_state and c.last_state.state == "terminated":
                if c.last_state.reason == "OOMKilled" or c.last_state.exit_code == 137:
                    was_oom = True
                    exit_code = c.last_state.exit_code

            oom_event = next(
                (e for e in events if "oomkilled" in e.message.lower() or "oom" in e.reason.lower()),
                None,
            )

            if was_oom or oom_event:
                evidence = [
                    f"Container '{c.name}' terminated with exit code 137 (OOMKilled).",
                    f"Configured Memory Limit: {c.memory_limit or 'Not specified (unbounded)'}.",
                    f"Configured Memory Request: {c.memory_request or 'Not specified'}.",
                    f"Total restarts: {c.restart_count}.",
                ]
                if oom_event:
                    evidence.append(f"Event: {oom_event.message}")

                return Finding(
                    id=f"oom-{pod.namespace}-{pod.name}-{c.name}",
                    title=f"Container OOMKilled - Out Of Memory ({c.name})",
                    severity=DiagnosticSeverity.CRITICAL,
                    resource_kind="Pod",
                    resource_name=pod.name,
                    namespace=pod.namespace,
                    evidence=evidence,
                    likely_cause=(
                        f"Container '{c.name}' exceeded its configured memory limit of {c.memory_limit or 'host cgroup limit'}, "
                        "triggering the Linux kernel cgroup OOM killer to terminate the process."
                    ),
                    confidence="High (Confirmed)",
                    recommended_steps=[
                        f"Examine pod memory consumption trends and peak requirements.",
                        f"Increase the memory limit in resources.limits.memory (e.g. from {c.memory_limit or 'current'} to 1.5x - 2x).",
                        "Profile the application for memory leaks, unclosed database connections, or large in-memory buffers.",
                        "Set JVM / runtime max heap limits (e.g. -Xmx) below the container's cgroup memory limit.",
                    ],
                    kubectl_commands=[
                        f"kubectl describe pod {pod.name} -n {pod.namespace}",
                        f"kubectl top pod {pod.name} -n {pod.namespace} --containers",
                        f"kubectl logs {pod.name} -c {c.name} -n {pod.namespace} --previous --tail=50",
                    ],
                    safe_remediation="Adjust resource limits in the deployment specification. Ensure node capacity can satisfy the new request.",
                    manual_verification_required=True,
                    is_ai_hypothesis=False,
                )
        return None

    @classmethod
    def _check_scheduling_and_pending(cls, pod: PodDiagnosticInfo, events: List[EventInfo]) -> Optional[Finding]:
        """Rules 5 & 6: Detects Pending pods and FailedScheduling due to resource exhaustion."""
        if pod.phase != "Pending":
            return None

        sched_event = next(
            (e for e in events if e.reason == "FailedScheduling" or "insufficient" in e.message.lower() or "no nodes are available" in e.message.lower()),
            None,
        )

        evidence = [
            f"Pod '{pod.name}' is stuck in 'Pending' phase.",
            f"Node Assignment: {pod.node_name or 'Unassigned'}.",
        ]

        if sched_event:
            evidence.append(f"Scheduling Event: {sched_event.message}")
            msg = sched_event.message.lower()
            if "insufficient memory" in msg or "insufficient cpu" in msg:
                likely_cause = "Kubernetes scheduler cannot place the pod because available cluster nodes lack sufficient unallocated CPU or Memory requests."
                severity = DiagnosticSeverity.HIGH
            elif "taint" in msg or "match pod toleration" in msg:
                likely_cause = "Node taints prevent pod scheduling; pod specification is missing required tolerations."
                severity = DiagnosticSeverity.MEDIUM
            else:
                likely_cause = f"Pod scheduling failed: {sched_event.message}"
                severity = DiagnosticSeverity.HIGH
        else:
            likely_cause = "Pod is pending. It may be waiting for image pulling, init containers, or persistent volume claims."
            severity = DiagnosticSeverity.MEDIUM

        return Finding(
            id=f"pending-{pod.namespace}-{pod.name}",
            title=f"Pod Pending / Failed Scheduling ({pod.name})",
            severity=severity,
            resource_kind="Pod",
            resource_name=pod.name,
            namespace=pod.namespace,
            evidence=evidence,
            likely_cause=likely_cause,
            confidence="High (Confirmed)",
            recommended_steps=[
                "Check cluster node allocatable resources and current capacity: kubectl describe nodes",
                "Review the pod's CPU and memory requests to verify they are not excessively large.",
                "Verify if cluster autoscaler is running or if additional worker nodes should be provisioned.",
                "Check for persistent volume claims (PVCs) that may be unbound.",
            ],
            kubectl_commands=[
                f"kubectl describe pod {pod.name} -n {pod.namespace}",
                "kubectl describe nodes | grep -A 8 'Allocated resources:'",
                "kubectl get events -n " + pod.namespace + " --field-selector reason=FailedScheduling",
            ],
            safe_remediation="Decrease the pod's CPU/memory requests if over-provisioned, or scale the node group capacity.",
            manual_verification_required=True,
            is_ai_hypothesis=False,
        )

    @classmethod
    def _check_probe_failures(cls, pod: PodDiagnosticInfo, events: List[EventInfo]) -> Optional[Finding]:
        """Rule 7: Detects Readiness or Liveness probe failures."""
        probe_events = [
            e for e in events
            if e.reason == "Unhealthy" or "probe failed" in e.message.lower()
        ]

        if not probe_events:
            return None

        evidence = [f"Pod '{pod.name}' encountered probe failure events:"]
        for pe in probe_events[:3]:
            evidence.append(f"{pe.reason}: {pe.message} (count: {pe.count})")

        is_liveness = any("liveness" in pe.message.lower() for pe in probe_events)
        is_readiness = any("readiness" in pe.message.lower() for pe in probe_events)

        if is_liveness:
            title = f"Liveness Probe Failure ({pod.name})"
            severity = DiagnosticSeverity.HIGH
            likely_cause = "The application failed its liveness health check endpoint. Kubernetes restarts the container when liveness probes fail."
        else:
            title = f"Readiness Probe Failure ({pod.name})"
            severity = DiagnosticSeverity.MEDIUM
            likely_cause = "The application is failing its readiness probe, causing Kubernetes to remove it from service endpoints so it does not receive user traffic."

        return Finding(
            id=f"probe-{pod.namespace}-{pod.name}",
            title=title,
            severity=severity,
            resource_kind="Pod",
            resource_name=pod.name,
            namespace=pod.namespace,
            evidence=evidence,
            likely_cause=likely_cause,
            confidence="High (Confirmed)",
            recommended_steps=[
                "Verify health check path, port, and response format in the container's probe configuration.",
                "Check if initialDelaySeconds or timeoutSeconds is too short for slow startup times.",
                "Test the health check endpoint directly from within the cluster.",
                "Inspect application logs during probe failure timestamps.",
            ],
            kubectl_commands=[
                f"kubectl describe pod {pod.name} -n {pod.namespace}",
                f"kubectl logs {pod.name} -n {pod.namespace} --tail=100",
            ],
            safe_remediation="Adjust initialDelaySeconds or failureThreshold if the application takes longer to warm up.",
            manual_verification_required=True,
            is_ai_hypothesis=False,
        )

    @classmethod
    def evaluate_deployment(cls, dep: DeploymentInfo, events: List[EventInfo]) -> List[Finding]:
        """Rule 8: Detects Deployment replicas unavailable."""
        findings: List[Finding] = []

        if dep.desired_replicas > 0 and dep.available_replicas < dep.desired_replicas:
            dep_events = [
                e for e in events if e.resource_name == dep.name or dep.name in e.resource_name
            ]
            evidence = [
                f"Deployment '{dep.name}' desired replicas: {dep.desired_replicas}.",
                f"Available replicas: {dep.available_replicas}.",
                f"Ready replicas: {dep.ready_replicas}.",
                f"Updated replicas: {dep.updated_replicas}.",
            ]
            if dep.conditions:
                evidence.extend([f"Condition: {c}" for c in dep.conditions])
            if dep_events:
                evidence.extend([f"Event: {e.message}" for e in dep_events[:2]])

            severity = (
                DiagnosticSeverity.CRITICAL
                if dep.available_replicas == 0
                else DiagnosticSeverity.HIGH
            )

            findings.append(
                Finding(
                    id=f"dep-{dep.namespace}-{dep.name}-unavailable",
                    title=f"Deployment Replicas Unavailable ({dep.name})",
                    severity=severity,
                    resource_kind="Deployment",
                    resource_name=dep.name,
                    namespace=dep.namespace,
                    evidence=evidence,
                    likely_cause=(
                        f"Deployment '{dep.name}' has {dep.desired_replicas - dep.available_replicas} pods failing to become ready. "
                        "Underlying pods may be experiencing CrashLoopBackOff, ImagePullBackOff, admission webhook rejections, or resource constraints."
                    ),
                    confidence="High (Confirmed)",
                    recommended_steps=[
                        f"Check rollout status: kubectl rollout status deployment/{dep.name} -n {dep.namespace}",
                        f"List pods managed by this deployment: kubectl get pods -l {','.join([f'{k}={v}' for k,v in dep.selector.items()])} -n {dep.namespace}",
                        "Inspect ReplicaSets for creation failures or quota limits.",
                    ],
                    kubectl_commands=[
                        f"kubectl describe deployment {dep.name} -n {dep.namespace}",
                        f"kubectl get replicaset -l {','.join([f'{k}={v}' for k,v in dep.selector.items()])} -n {dep.namespace}",
                        f"kubectl rollout status deployment/{dep.name} -n {dep.namespace}",
                    ],
                    safe_remediation="Resolve the underlying pod or admission errors before attempting a deployment rollout or rollback.",
                    manual_verification_required=True,
                    is_ai_hypothesis=False,
                )
            )

        return findings

    @classmethod
    def evaluate_service(cls, svc: ServiceInfo, pods: List[PodDiagnosticInfo]) -> List[Finding]:
        """Rule 9: Detects Services with no matching endpoints."""
        findings: List[Finding] = []

        # Only evaluate services that use selectors (ClusterIP, NodePort, LoadBalancer)
        if svc.selector and not svc.has_endpoints:
            # Check if any pods match the selector labels
            matching_pods = []
            for pod in pods:
                # Basic check: do pod name or namespace indicate relation
                # In demo/client data, we verify if pods exist for selector
                pass

            selector_str = ", ".join([f"{k}={v}" for k, v in svc.selector.items()])
            evidence = [
                f"Service '{svc.name}' defines selector: {svc.selector}.",
                f"Backing endpoints list is completely empty.",
                f"Service Type: {svc.service_type}, ClusterIP: {svc.cluster_ip or 'None'}.",
            ]

            findings.append(
                Finding(
                    id=f"svc-{svc.namespace}-{svc.name}-no-endpoints",
                    title=f"Service Has No Active Endpoints ({svc.name})",
                    severity=DiagnosticSeverity.HIGH,
                    resource_kind="Service",
                    resource_name=svc.name,
                    namespace=svc.namespace,
                    evidence=evidence,
                    likely_cause=(
                        f"No ready pods match the Service selector ({selector_str}). "
                        "Any internal or external traffic routed to this service will result in connection refused or HTTP 502/503."
                    ),
                    confidence="High (Confirmed)",
                    recommended_steps=[
                        f"Verify that pods have labels matching the service selector: kubectl get pods --show-labels -n {svc.namespace}",
                        f"Check if pods exist but are failing readiness checks (unready pods are excluded from service endpoints).",
                        f"Compare pod template labels in deployment spec with service selector: kubectl get svc {svc.name} -o yaml -n {svc.namespace}",
                    ],
                    kubectl_commands=[
                        f"kubectl get endpoints {svc.name} -n {svc.namespace}",
                        f"kubectl get pods -l {selector_str.replace(', ', ',')} -n {svc.namespace} --show-labels",
                        f"kubectl describe service {svc.name} -n {svc.namespace}",
                    ],
                    safe_remediation="Correct label selectors in the Service manifest or fix pod readiness so endpoints populate automatically.",
                    manual_verification_required=True,
                    is_ai_hypothesis=False,
                )
            )

        return findings

    @classmethod
    def evaluate_network_and_dns(cls, events: List[EventInfo], namespace: str) -> List[Finding]:
        """Rule 10: Detects DNS or Networking anomalies across warning events."""
        findings: List[Finding] = []

        net_events = [
            e for e in events
            if any(term in e.message.lower() for term in [
                "dns", "lookup", "coredns", "dial tcp", "connection timed out", "i/o timeout", "temporary failure in name resolution"
            ])
        ]

        for ne in net_events:
            findings.append(
                Finding(
                    id=f"net-{ne.namespace}-{ne.resource_name}-{ne.reason}",
                    title=f"Potential Networking / DNS Failure ({ne.resource_name})",
                    severity=DiagnosticSeverity.MEDIUM,
                    resource_kind=ne.resource_kind,
                    resource_name=ne.resource_name,
                    namespace=ne.namespace,
                    evidence=[
                        f"Event Type: {ne.type}, Reason: {ne.reason}.",
                        f"Observed Message: {ne.message}",
                        f"Count: {ne.count}.",
                    ],
                    likely_cause=(
                        "Inter-pod communication or DNS resolution degraded. "
                        "Possible CoreDNS pod failure, network policy blocking egress, or flannel/calico CNI routing issue."
                    ),
                    confidence="Medium (Probable)",
                    recommended_steps=[
                        "Check status of CoreDNS pods in kube-system: kubectl get pods -n kube-system -l k8s-app=kube-dns",
                        "Verify NetworkPolicies in the namespace allowing DNS traffic on UDP/TCP port 53.",
                        "Inspect node CNI plugin status and kube-proxy logs.",
                    ],
                    kubectl_commands=[
                        "kubectl get pods -n kube-system -l k8s-app=kube-dns",
                        "kubectl logs -n kube-system -l k8s-app=kube-dns --tail=50",
                        f"kubectl get networkpolicies -n {ne.namespace}",
                    ],
                    safe_remediation="Check DNS configuration and network policies before restarting networking daemons.",
                    manual_verification_required=True,
                    is_ai_hypothesis=False,
                )
            )

        return findings
