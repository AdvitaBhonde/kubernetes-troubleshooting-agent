"""Kubernetes diagnostic data collector.

Executes read-only operations across Pods, Events, Deployments, Services,
Endpoints, and Logs. Supports Kubeconfig, in-cluster ServiceAccount, and
seamless fallback to high-fidelity demo mode.
"""

import json
import os
from pathlib import Path
from typing import List, Optional, Dict, Any

from app.core.config import settings
from app.core.logging import logger
from app.models.schemas import (
    ClusterStatus,
    PodDiagnosticInfo,
    ContainerInfo,
    ContainerStateInfo,
    EventInfo,
    DeploymentInfo,
    ServiceInfo,
)
from app.utils.redactor import redactor

try:
    from kubernetes import client, config
    from kubernetes.client.rest import ApiException
    K8S_AVAILABLE = True
except ImportError:
    K8S_AVAILABLE = False
    ApiException = Exception


class KubernetesCollector:
    """Read-only diagnostic collector for Kubernetes clusters."""

    def __init__(self, demo_mode: Optional[bool] = None):
        self.demo_mode = settings.demo_mode if demo_mode is None else demo_mode
        self.connected = False
        self.context_name = None
        self.server_version = None
        self.node_count = 0
        self.core_v1: Optional[Any] = None
        self.apps_v1: Optional[Any] = None
        self.version_api: Optional[Any] = None
        self._demo_data: Optional[Dict[str, Any]] = None

        if not self.demo_mode:
            self._init_client()

    def _init_client(self):
        """Attempts to initialize Kubernetes client via in-cluster or kubeconfig."""
        if not K8S_AVAILABLE:
            logger.warning("Kubernetes Python client not installed. Falling back to Demo Mode.")
            self.demo_mode = True
            return

        # 1. Try In-Cluster Config if running inside Kubernetes
        if settings.in_cluster:
            try:
                config.load_in_cluster_config()
                self._setup_apis("in-cluster")
                return
            except Exception as e:
                logger.warning(f"In-cluster config failed: {e}")

        # 2. Try local Kubeconfig
        try:
            kubeconfig_file = settings.kubeconfig_path or os.path.expanduser("~/.kube/config")
            if os.path.exists(kubeconfig_file):
                config.load_kube_config(config_file=kubeconfig_file)
                contexts, active_context = config.list_kube_config_contexts(config_file=kubeconfig_file)
                ctx_name = active_context.get("name", "local-kubeconfig") if active_context else "local-kubeconfig"
                self._setup_apis(ctx_name)
                return
            else:
                logger.info(f"No kubeconfig found at {kubeconfig_file}.")
        except Exception as e:
            logger.warning(f"Failed to load local kubeconfig: {e}")

        # Fallback to demo mode if no real cluster reachable
        logger.info("No active cluster connection detected. Activating Demo Mode with realistic Kubernetes diagnostics.")
        self.demo_mode = True

    def _setup_apis(self, context_name: str):
        """Creates API clients and tests connectivity with version check."""
        try:
            self.core_v1 = client.CoreV1Api()
            self.apps_v1 = client.AppsV1Api()
            self.version_api = client.VersionApi()

            # Test connection
            version_info = self.version_api.get_code()
            self.server_version = f"{version_info.major}.{version_info.minor}"
            self.context_name = context_name
            self.connected = True

            # Get node count
            try:
                nodes = self.core_v1.list_node(limit=50)
                self.node_count = len(nodes.items)
            except Exception:
                self.node_count = 1

            logger.info(f"Successfully connected to Kubernetes cluster: {context_name} (v{self.server_version})")
        except Exception as e:
            logger.warning(f"Cluster connectivity test failed ({e}). Reverting to Demo Mode.")
            self.connected = False
            self.demo_mode = True

    def _load_demo_data(self) -> Dict[str, Any]:
        """Loads realistic cluster fixtures for offline demo mode."""
        if self._demo_data is None:
            # Look for demo_cluster.json in project root or relative path
            search_paths = [
                Path(__file__).parent.parent.parent / "sample_data" / "demo_cluster.json",
                Path("sample_data/demo_cluster.json"),
                Path("/app/sample_data/demo_cluster.json"),
            ]
            for p in search_paths:
                if p.exists():
                    try:
                        with open(p, "r", encoding="utf-8") as f:
                            self._demo_data = json.load(f)
                            break
                    except Exception as e:
                        logger.error(f"Error loading demo data from {p}: {e}")
            if not self._demo_data:
                self._demo_data = {"namespaces": ["default"], "pods": [], "deployments": [], "services": [], "events": []}
        return self._demo_data

    def get_cluster_status(self) -> ClusterStatus:
        """Returns cluster connection details or demo mode state."""
        if self.demo_mode or not self.connected:
            demo_info = self._load_demo_data().get("cluster_info", {})
            return ClusterStatus(
                connected=True,
                demo_mode=True,
                context_name=demo_info.get("context_name", "simulated-demo-cluster"),
                server_version=demo_info.get("server_version", "v1.30.2-demo"),
                node_count=demo_info.get("node_count", 3),
                message="Running in Demo Mode with realistic Kubernetes failure scenarios.",
            )

        return ClusterStatus(
            connected=True,
            demo_mode=False,
            context_name=self.context_name,
            server_version=self.server_version,
            node_count=self.node_count,
            message="Connected to live Kubernetes cluster.",
        )

    def get_namespaces(self) -> List[str]:
        """Lists namespaces accessible in the cluster."""
        if self.demo_mode or not self.connected:
            return self._load_demo_data().get("namespaces", ["default", "production", "staging", "kube-system"])

        try:
            ns_list = self.core_v1.list_namespace(timeout_seconds=5)
            return [ns.metadata.name for ns in ns_list.items]
        except Exception as e:
            logger.warning(f"Failed to list namespaces (permission or timeout): {e}")
            return [settings.default_namespace]

    def get_pods(self, namespace: str = "default") -> List[PodDiagnosticInfo]:
        """Gathers pods, container states, restart counts, conditions, and recent logs."""
        if self.demo_mode or not self.connected:
            raw_pods = self._load_demo_data().get("pods", [])
            # Filter by namespace if requested
            filtered = [p for p in raw_pods if p.get("namespace") == namespace or namespace == "all"]
            results = []
            for p in (filtered or raw_pods):
                containers = []
                for c in p.get("containers", []):
                    curr = ContainerStateInfo(**c["current_state"])
                    last = ContainerStateInfo(**c["last_state"]) if c.get("last_state") else None
                    containers.append(
                        ContainerInfo(
                            name=c["name"],
                            image=c["image"],
                            ready=c.get("ready", False),
                            restart_count=c.get("restart_count", 0),
                            current_state=curr,
                            last_state=last,
                            ports=c.get("ports", []),
                            cpu_request=c.get("cpu_request"),
                            memory_request=c.get("memory_request"),
                            cpu_limit=c.get("cpu_limit"),
                            memory_limit=c.get("memory_limit"),
                        )
                    )
                results.append(
                    PodDiagnosticInfo(
                        name=p["name"],
                        namespace=p["namespace"],
                        phase=p["phase"],
                        pod_ip=p.get("pod_ip"),
                        node_name=p.get("node_name"),
                        restarts=p.get("restarts", 0),
                        containers=containers,
                        events=p.get("events", []),
                        logs=redactor.redact_text(p.get("logs") or ""),
                        previous_logs=redactor.redact_text(p.get("previous_logs") or ""),
                        conditions=p.get("conditions", {}),
                        created_at=p.get("created_at"),
                    )
                )
            return results

        results = []
        try:
            pod_list = (
                self.core_v1.list_pod_for_all_namespaces(limit=100)
                if namespace == "all"
                else self.core_v1.list_namespaced_pod(namespace=namespace, limit=100)
            )

            for pod in pod_list.items:
                containers: List[ContainerInfo] = []
                total_restarts = 0

                # Map container specs
                spec_containers = {c.name: c for c in pod.spec.containers}

                # Statuses
                c_statuses = pod.status.container_statuses or []
                for cs in c_statuses:
                    total_restarts += cs.restart_count

                    curr_state = ContainerStateInfo(state="waiting", reason="Unknown")
                    if cs.state.running:
                        curr_state = ContainerStateInfo(state="running")
                    elif cs.state.waiting:
                        curr_state = ContainerStateInfo(
                            state="waiting",
                            reason=cs.state.waiting.reason,
                            message=cs.state.waiting.message,
                        )
                    elif cs.state.terminated:
                        curr_state = ContainerStateInfo(
                            state="terminated",
                            reason=cs.state.terminated.reason,
                            exit_code=cs.state.terminated.exit_code,
                            message=cs.state.terminated.message,
                        )

                    last_state = None
                    if cs.last_state:
                        if cs.last_state.terminated:
                            last_state = ContainerStateInfo(
                                state="terminated",
                                reason=cs.last_state.terminated.reason,
                                exit_code=cs.last_state.terminated.exit_code,
                                message=cs.last_state.terminated.message,
                            )
                        elif cs.last_state.waiting:
                            last_state = ContainerStateInfo(
                                state="waiting",
                                reason=cs.last_state.waiting.reason,
                                message=cs.last_state.waiting.message,
                            )

                    spec_c = spec_containers.get(cs.name)
                    ports = [p.container_port for p in spec_c.ports] if spec_c and spec_c.ports else []
                    resources = spec_c.resources if spec_c else None
                    reqs = resources.requests if resources and resources.requests else {}
                    lims = resources.limits if resources and resources.limits else {}

                    containers.append(
                        ContainerInfo(
                            name=cs.name,
                            image=cs.image,
                            ready=cs.ready,
                            restart_count=cs.restart_count,
                            current_state=curr_state,
                            last_state=last_state,
                            ports=ports,
                            cpu_request=reqs.get("cpu"),
                            memory_request=reqs.get("memory"),
                            cpu_limit=lims.get("cpu"),
                            memory_limit=lims.get("memory"),
                        )
                    )

                # Pod conditions
                conditions = {}
                if pod.status.conditions:
                    for cond in pod.status.conditions:
                        conditions[cond.type] = cond.status == "True"

                # Fetch logs for the first container if pod is unhealthy or restarting
                pod_logs = None
                prev_logs = None
                if containers and (not pod.status.phase == "Running" or total_restarts > 0):
                    first_c = containers[0].name
                    pod_logs = self.get_pod_logs(pod.metadata.namespace, pod.metadata.name, first_c, previous=False)
                    if total_restarts > 0:
                        prev_logs = self.get_pod_logs(pod.metadata.namespace, pod.metadata.name, first_c, previous=True)

                results.append(
                    PodDiagnosticInfo(
                        name=pod.metadata.name,
                        namespace=pod.metadata.namespace,
                        phase=pod.status.phase or "Unknown",
                        pod_ip=pod.status.pod_ip,
                        node_name=pod.spec.node_name,
                        restarts=total_restarts,
                        containers=containers,
                        conditions=conditions,
                        created_at=pod.metadata.creation_timestamp.isoformat() if pod.metadata.creation_timestamp else None,
                        logs=pod_logs,
                        previous_logs=prev_logs,
                    )
                )
        except Exception as e:
            logger.error(f"Error fetching pods in namespace '{namespace}': {e}")

        return results

    def get_pod_logs(
        self,
        namespace: str,
        pod_name: str,
        container_name: Optional[str] = None,
        previous: bool = False,
        tail_lines: int = 100,
    ) -> Optional[str]:
        """Safely retrieves logs with line caps and sensitive data redaction."""
        if self.demo_mode or not self.connected:
            raw_pods = self._load_demo_data().get("pods", [])
            for p in raw_pods:
                if p["name"] == pod_name:
                    content = p.get("previous_logs") if previous else p.get("logs")
                    return redactor.redact_text(content) if content else None
            return None

        try:
            logs = self.core_v1.read_namespaced_pod_log(
                name=pod_name,
                namespace=namespace,
                container=container_name,
                previous=previous,
                tail_lines=min(tail_lines, settings.max_log_lines),
                timestamps=True,
            )
            return redactor.redact_text(logs)
        except Exception as e:
            logger.debug(f"Could not read logs for {pod_name} (prev={previous}): {e}")
            return None

    def get_events(self, namespace: str = "default") -> List[EventInfo]:
        """Fetches Kubernetes warning and normal events."""
        if self.demo_mode or not self.connected:
            raw_events = self._load_demo_data().get("events", [])
            filtered = [e for e in raw_events if e.get("namespace") == namespace or namespace == "all"]
            return [EventInfo(**e) for e in (filtered or raw_events)]

        results = []
        try:
            event_list = (
                self.core_v1.list_event_for_all_namespaces(limit=settings.max_events)
                if namespace == "all"
                else self.core_v1.list_namespaced_event(namespace=namespace, limit=settings.max_events)
            )
            for ev in event_list.items:
                results.append(
                    EventInfo(
                        type=ev.type or "Normal",
                        reason=ev.reason or "Unknown",
                        message=redactor.redact_text(ev.message or ""),
                        resource_kind=ev.involved_object.kind or "Pod",
                        resource_name=ev.involved_object.name or "Unknown",
                        namespace=ev.metadata.namespace or namespace,
                        count=ev.count or 1,
                        last_seen=ev.last_timestamp.isoformat() if ev.last_timestamp else None,
                    )
                )
        except Exception as e:
            logger.error(f"Error fetching events for namespace '{namespace}': {e}")

        return results

    def get_deployments(self, namespace: str = "default") -> List[DeploymentInfo]:
        """Inspects Deployments, replica counts, and availability status."""
        if self.demo_mode or not self.connected:
            raw_deps = self._load_demo_data().get("deployments", [])
            filtered = [d for d in raw_deps if d.get("namespace") == namespace or namespace == "all"]
            return [DeploymentInfo(**d) for d in (filtered or raw_deps)]

        results = []
        try:
            dep_list = (
                self.apps_v1.list_deployment_for_all_namespaces(limit=50)
                if namespace == "all"
                else self.apps_v1.list_namespaced_deployment(namespace=namespace, limit=50)
            )
            for dep in dep_list.items:
                conds = []
                if dep.status.conditions:
                    for c in dep.status.conditions:
                        if c.status == "False" or c.type == "ReplicaFailure":
                            conds.append(f"{c.type}: {c.message}")

                results.append(
                    DeploymentInfo(
                        name=dep.metadata.name,
                        namespace=dep.metadata.namespace,
                        desired_replicas=dep.spec.replicas or 0,
                        ready_replicas=dep.status.ready_replicas or 0,
                        available_replicas=dep.status.available_replicas or 0,
                        updated_replicas=dep.status.updated_replicas or 0,
                        selector=dep.spec.selector.match_labels or {},
                        conditions=conds,
                    )
                )
        except Exception as e:
            logger.error(f"Error fetching deployments: {e}")

        return results

    def get_services(self, namespace: str = "default") -> List[ServiceInfo]:
        """Inspects Services, selector matching, and backing Endpoints."""
        if self.demo_mode or not self.connected:
            raw_svcs = self._load_demo_data().get("services", [])
            filtered = [s for s in raw_svcs if s.get("namespace") == namespace or namespace == "all"]
            return [ServiceInfo(**s) for s in (filtered or raw_svcs)]

        results = []
        try:
            svc_list = (
                self.core_v1.list_service_for_all_namespaces(limit=50)
                if namespace == "all"
                else self.core_v1.list_namespaced_service(namespace=namespace, limit=50)
            )

            for svc in svc_list.items:
                endpoints: List[str] = []
                has_endpoints = False
                ports = []
                if svc.spec.ports:
                    for p in svc.spec.ports:
                        ports.append({"port": p.port, "target_port": str(p.target_port), "protocol": p.protocol})

                # Check endpoints if service has a selector
                if svc.spec.selector:
                    try:
                        ep = self.core_v1.read_namespaced_endpoints(name=svc.metadata.name, namespace=svc.metadata.namespace)
                        if ep.subsets:
                            for sub in ep.subsets:
                                if sub.addresses:
                                    for addr in sub.addresses:
                                        endpoints.append(addr.ip)
                        has_endpoints = len(endpoints) > 0
                    except Exception:
                        has_endpoints = False
                else:
                    has_endpoints = True  # ExternalName or headless without selector

                results.append(
                    ServiceInfo(
                        name=svc.metadata.name,
                        namespace=svc.metadata.namespace,
                        service_type=svc.spec.type or "ClusterIP",
                        cluster_ip=svc.spec.cluster_ip,
                        ports=ports,
                        selector=svc.spec.selector or {},
                        endpoints=endpoints,
                        has_endpoints=has_endpoints,
                    )
                )
        except Exception as e:
            logger.error(f"Error fetching services: {e}")

        return results
