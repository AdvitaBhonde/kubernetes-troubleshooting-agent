/**
 * Client-side script for AI-Powered Kubernetes Troubleshooting Dashboard.
 * Interacts with FastAPI backend to inspect clusters, pods, logs, and root cause reports.
 */

document.addEventListener("DOMContentLoaded", () => {
    // State
    let currentNamespace = "default";
    let currentFindings = [];
    let cachedPods = [];
    let selectedSeverityFilter = "all";

    // DOM Elements
    const clusterStatusPill = document.getElementById("cluster-status-pill");
    const clusterStatusText = document.getElementById("cluster-status-text");
    const demoModeBadge = document.getElementById("demo-mode-badge");
    const namespaceSelect = document.getElementById("namespace-select");
    const aiProviderSelect = document.getElementById("ai-provider-select");
    const btnRunDiagnostics = document.getElementById("btn-run-diagnostics");
    const btnRefreshData = document.getElementById("btn-refresh-data");

    // Metrics
    const metricTotalPods = document.getElementById("metric-total-pods");
    const metricPodBreakdown = document.getElementById("metric-pod-breakdown");
    const metricCriticalIssues = document.getElementById("metric-critical-issues");
    const metricWarningEvents = document.getElementById("metric-warning-events");
    const metricDeployments = document.getElementById("metric-deployments");
    const metricDeploymentsSub = document.getElementById("metric-deployments-sub");

    // Tabs & Containers
    const tabButtons = document.querySelectorAll(".tab-btn");
    const tabContents = document.querySelectorAll(".tab-content");
    const findingsContainer = document.getElementById("findings-container");
    const findingsCountText = document.getElementById("findings-count-text");
    const aiMarkdownContent = document.getElementById("ai-markdown-content");
    const aiProviderBadge = document.getElementById("ai-provider-badge");
    const podsTableBody = document.getElementById("pods-table-body");
    const deploymentsContainer = document.getElementById("deployments-container");
    const servicesContainer = document.getElementById("services-container");
    const eventsTableBody = document.getElementById("events-table-body");

    // Modal
    const logModal = document.getElementById("log-modal");
    const modalTitle = document.getElementById("modal-title");
    const modalLogViewer = document.getElementById("modal-log-viewer");
    const modalCloseBtn = document.getElementById("modal-close-btn");
    const btnCopyLog = document.getElementById("btn-copy-log");

    // Severity Filters
    const filterChips = document.querySelectorAll(".filter-chip");

    // --- TAB SWITCHING ---
    tabButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            tabButtons.forEach(b => b.classList.remove("active"));
            tabContents.forEach(c => c.classList.remove("active"));
            btn.classList.add("active");
            const target = document.getElementById(btn.dataset.tab);
            if (target) target.classList.add("active");
        });
    });

    // --- SEVERITY FILTERING ---
    filterChips.forEach(chip => {
        chip.addEventListener("click", () => {
            filterChips.forEach(c => c.classList.remove("active"));
            chip.classList.add("active");
            selectedSeverityFilter = chip.dataset.severity;
            renderFindings();
        });
    });

    // --- MODAL HANDLING ---
    modalCloseBtn.addEventListener("click", () => logModal.classList.add("hidden"));
    window.addEventListener("click", (e) => {
        if (e.target === logModal) logModal.classList.add("hidden");
    });
    btnCopyLog.addEventListener("click", () => {
        navigator.clipboard.writeText(modalLogViewer.textContent);
        btnCopyLog.textContent = "Copied!";
        setTimeout(() => (btnCopyLog.textContent = "Copy Logs"), 1500);
    });

    // --- FETCH CLUSTER STATUS & NAMESPACES ---
    async function loadClusterStatus() {
        try {
            const res = await fetch("/api/cluster/status");
            const status = await res.json();
            const dot = clusterStatusPill.querySelector(".status-dot");

            if (status.connected) {
                dot.classList.add("connected");
                clusterStatusText.textContent = `${status.context_name} (${status.server_version})`;
            } else {
                dot.classList.remove("connected");
                clusterStatusText.textContent = "Disconnected";
            }

            if (status.demo_mode) {
                demoModeBadge.classList.remove("hidden");
            } else {
                demoModeBadge.classList.add("hidden");
            }
        } catch (err) {
            console.error("Cluster status error:", err);
            clusterStatusText.textContent = "API Unreachable";
        }
    }

    async function loadNamespaces() {
        try {
            const res = await fetch("/api/namespaces");
            const namespaces = await res.json();
            namespaceSelect.innerHTML = "";
            namespaces.forEach(ns => {
                const opt = document.createElement("option");
                opt.value = ns;
                opt.textContent = ns;
                if (ns === currentNamespace) opt.selected = true;
                namespaceSelect.appendChild(opt);
            });
        } catch (err) {
            console.error("Namespaces load error:", err);
        }
    }

    // --- LOAD CLUSTER RESOURCES (Pods, Deployments, Services, Events) ---
    async function refreshClusterData() {
        currentNamespace = namespaceSelect.value;
        await Promise.all([
            loadPods(),
            loadDeploymentsAndServices(),
            loadEvents(),
        ]);
    }

    async function loadPods() {
        try {
            podsTableBody.innerHTML = `<tr><td colspan="7" class="text-center">Loading pods in ${currentNamespace}...</td></tr>`;
            const res = await fetch(`/api/pods?namespace=${currentNamespace}`);
            cachedPods = await res.json();

            let healthy = 0;
            let failing = 0;

            if (cachedPods.length === 0) {
                podsTableBody.innerHTML = `<tr><td colspan="7" class="text-center">No pods found in namespace ${currentNamespace}.</td></tr>`;
            } else {
                podsTableBody.innerHTML = "";
                cachedPods.forEach(pod => {
                    const isHealthy = pod.phase === "Running" && pod.restarts === 0 && pod.conditions.Ready;
                    if (isHealthy) healthy++; else failing++;

                    const primaryC = pod.containers[0] || {};
                    const stateObj = primaryC.current_state || {};
                    const lastStateObj = primaryC.last_state;

                    let stateText = stateObj.reason || stateObj.state;
                    if (lastStateObj && lastStateObj.reason) {
                        stateText += ` (prev: ${lastStateObj.reason})`;
                    }

                    const tr = document.createElement("tr");
                    tr.innerHTML = `
                        <td><strong>${pod.name}</strong></td>
                        <td><span class="badge ${pod.phase === 'Running' ? 'badge-Low' : 'badge-Critical'}">${pod.phase}</span></td>
                        <td>${pod.restarts > 0 ? `<strong style="color: var(--critical)">${pod.restarts}</strong>` : '0'}</td>
                        <td>${pod.node_name || 'None'}</td>
                        <td>${pod.containers.map(c => c.name).join(', ')}</td>
                        <td><code>${stateText}</code></td>
                        <td>
                            ${(pod.logs || pod.previous_logs) ? 
                                `<button class="btn btn-sm btn-secondary inspect-log-btn" data-pod="${pod.name}">Inspect Logs</button>` 
                                : '<span class="text-muted">No logs</span>'}
                        </td>
                    `;
                    podsTableBody.appendChild(tr);
                });

                document.querySelectorAll(".inspect-log-btn").forEach(b => {
                    b.addEventListener("click", () => openLogInspector(b.dataset.pod));
                });
            }

            metricTotalPods.textContent = cachedPods.length;
            metricPodBreakdown.textContent = `${healthy} healthy / ${failing} failing`;
        } catch (err) {
            console.error("Error loading pods:", err);
            podsTableBody.innerHTML = `<tr><td colspan="7" class="text-center" style="color:var(--critical)">Failed to load pods.</td></tr>`;
        }
    }

    async function loadDeploymentsAndServices() {
        try {
            const [depRes, svcRes] = await Promise.all([
                fetch(`/api/deployments?namespace=${currentNamespace}`),
                fetch(`/api/services?namespace=${currentNamespace}`)
            ]);
            const deployments = await depRes.json();
            const services = await svcRes.json();

            // Metric
            metricDeployments.textContent = `${deployments.length} / ${services.length}`;
            metricDeploymentsSub.textContent = `${deployments.length} deployments / ${services.length} services`;

            // Render Deployments
            if (deployments.length === 0) {
                deploymentsContainer.innerHTML = `<p class="empty-state">No deployments in ${currentNamespace}.</p>`;
            } else {
                deploymentsContainer.innerHTML = deployments.map(dep => `
                    <div class="workload-item">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <strong>${dep.name}</strong>
                            <span class="badge ${dep.available_replicas < dep.desired_replicas ? 'badge-Critical' : 'badge-Low'}">
                                ${dep.available_replicas}/${dep.desired_replicas} Ready
                            </span>
                        </div>
                        <div style="font-size:12px; color:var(--text-secondary); margin-top:6px;">
                            Selector: <code>${JSON.stringify(dep.selector)}</code>
                        </div>
                        ${dep.conditions.length > 0 ? `<div style="font-size:11px; color:var(--critical); margin-top:4px;">${dep.conditions[0]}</div>` : ''}
                    </div>
                `).join('');
            }

            // Render Services
            if (services.length === 0) {
                servicesContainer.innerHTML = `<p class="empty-state">No services in ${currentNamespace}.</p>`;
            } else {
                servicesContainer.innerHTML = services.map(svc => `
                    <div class="workload-item">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <strong>${svc.name}</strong>
                            <span class="badge ${svc.has_endpoints ? 'badge-Low' : 'badge-Critical'}">
                                ${svc.has_endpoints ? `${svc.endpoints.length} Endpoints` : 'No Endpoints'}
                            </span>
                        </div>
                        <div style="font-size:12px; color:var(--text-secondary); margin-top:6px;">
                            ClusterIP: <code>${svc.cluster_ip || 'None'}</code> | Selector: <code>${JSON.stringify(svc.selector)}</code>
                        </div>
                    </div>
                `).join('');
            }
        } catch (err) {
            console.error("Error loading workloads:", err);
        }
    }

    async function loadEvents() {
        try {
            const res = await fetch(`/api/events?namespace=${currentNamespace}`);
            const events = await res.json();
            const warningCount = events.filter(e => e.type === "Warning").length;

            metricWarningEvents.textContent = warningCount;
            metricWarningEvents.parentElement.querySelector(".metric-sub").textContent = `${events.length} total events`;

            if (events.length === 0) {
                eventsTableBody.innerHTML = `<tr><td colspan="5" class="text-center">No recent events recorded.</td></tr>`;
            } else {
                eventsTableBody.innerHTML = events.map(e => `
                    <tr>
                        <td><span class="badge ${e.type === 'Warning' ? 'badge-Critical' : 'badge-Low'}">${e.type}</span></td>
                        <td><strong>${e.reason}</strong></td>
                        <td><code>${e.resource_kind}/${e.resource_name}</code></td>
                        <td>${e.count}</td>
                        <td>${escapeHtml(e.message)}</td>
                    </tr>
                `).join('');
            }
        } catch (err) {
            console.error("Error loading events:", err);
        }
    }

    // --- RUN DIAGNOSTIC ANALYSIS ---
    async function runDiagnostics() {
        btnRunDiagnostics.disabled = true;
        btnRunDiagnostics.innerHTML = "Diagnosing Cluster...";

        currentNamespace = namespaceSelect.value;
        const aiProvider = aiProviderSelect.value;

        try {
            const res = await fetch("/api/diagnose", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    namespace: currentNamespace,
                    use_ai: true,
                    ai_provider: aiProvider
                })
            });

            if (!res.ok) {
                throw new Error(`Diagnostics API error: ${res.statusText}`);
            }

            const report = await res.json();
            currentFindings = report.findings || [];

            // Update Metrics
            metricCriticalIssues.textContent = report.summary.critical_count;

            // Render Findings
            renderFindings();

            // Render AI Markdown
            aiProviderBadge.textContent = `Provider: ${report.ai_provider}`;
            aiMarkdownContent.innerHTML = renderMarkdown(report.ai_analysis_markdown || "No AI narrative generated.");

            // Also refresh other tabs
            await refreshClusterData();

        } catch (err) {
            console.error("Diagnostics failure:", err);
            alert(`Diagnostic execution failed: ${err.message}`);
        } finally {
            btnRunDiagnostics.disabled = false;
            btnRunDiagnostics.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"></path></svg>
                Run Diagnostic Analysis
            `;
        }
    }

    function renderFindings() {
        const filtered = selectedSeverityFilter === "all"
            ? currentFindings
            : currentFindings.filter(f => f.severity.toLowerCase() === selectedSeverityFilter.toLowerCase());

        findingsCountText.textContent = `${filtered.length} of ${currentFindings.length} Issues Displayed`;

        if (filtered.length === 0) {
            findingsContainer.innerHTML = `
                <div class="empty-state">
                    <p>No issues matching filter <strong>${selectedSeverityFilter}</strong>.</p>
                </div>
            `;
            return;
        }

        findingsContainer.innerHTML = filtered.map(f => `
            <div class="finding-card ${f.severity}">
                <div class="finding-header">
                    <div class="finding-title-group">
                        <span class="finding-title">${escapeHtml(f.title)}</span>
                        <span class="finding-resource">${f.resource_kind}/${f.resource_name} (ns: ${f.namespace})</span>
                    </div>
                    <span class="badge badge-${f.severity}">${f.severity}</span>
                </div>

                <div>
                    <div class="finding-section-title">Verified Observations:</div>
                    <div class="evidence-box">
                        ${f.evidence.map(e => `<div>&bull; ${escapeHtml(e)}</div>`).join('')}
                    </div>
                </div>

                <div>
                    <div class="finding-section-title">Probable Root Cause:</div>
                    <div style="font-size: 13px; color: var(--text-primary);">
                        ${escapeHtml(f.likely_cause)} 
                        <span style="font-size:11px; color:var(--text-muted); margin-left:6px;">[Confidence: ${f.confidence}]</span>
                    </div>
                </div>

                <div>
                    <div class="finding-section-title">Safe Remediation:</div>
                    <div class="remediation-box">
                        ${escapeHtml(f.safe_remediation)}
                    </div>
                </div>

                ${f.kubectl_commands.length > 0 ? `
                    <div>
                        <div class="finding-section-title">Recommended Inspection Commands:</div>
                        <div class="cmd-container">
                            ${f.kubectl_commands.map(cmd => `
                                <div class="cmd-item">
                                    <span>${escapeHtml(cmd)}</span>
                                    <button class="copy-btn" onclick="copyCommand('${escapeHtml(cmd)}')">Copy</button>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                ` : ''}
            </div>
        `).join('');
    }

    // Modal log viewer
    function openLogInspector(podName) {
        const pod = cachedPods.find(p => p.name === podName);
        if (!pod) return;

        modalTitle.textContent = `Pod Logs: ${pod.name}`;
        const logContent = pod.logs || pod.previous_logs || "No logs available for container.";
        modalLogViewer.textContent = logContent;
        logModal.classList.remove("hidden");
    }

    // Helpers
    function escapeHtml(str) {
        if (!str) return "";
        return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    }

    window.copyCommand = function(text) {
        navigator.clipboard.writeText(text);
    };

    function renderMarkdown(md) {
        if (!md) return "";
        // Basic Markdown Parser for headers, code blocks, lists, alerts
        let html = md
            .replace(/### (.*?)\n/g, '<h3>$1</h3>')
            .replace(/#### (.*?)\n/g, '<h4>$1</h4>')
            .replace(/##### (.*?)\n/g, '<h5>$1</h5>')
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/`([^`]+)`/g, '<code>$1</code>')
            .replace(/```bash([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
            .replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
            .replace(/> \[!NOTE\]\s*(.*?)\n/g, '<blockquote><strong>Note:</strong> $1</blockquote>')
            .replace(/> \[!IMPORTANT\]\s*(.*?)\n/g, '<blockquote style="border-left-color: var(--warning);"><strong>Important:</strong> $1</blockquote>')
            .replace(/> \[!WARNING\]\s*(.*?)\n/g, '<blockquote style="border-left-color: var(--critical);"><strong>Warning:</strong> $1</blockquote>')
            .replace(/- (.*?)\n/g, '<li>$1</li>');
        return html;
    }

    // Event Listeners
    btnRunDiagnostics.addEventListener("click", runDiagnostics);
    btnRefreshData.addEventListener("click", refreshClusterData);
    namespaceSelect.addEventListener("change", refreshClusterData);

    // Initial load
    loadClusterStatus();
    loadNamespaces().then(async () => {
        await refreshClusterData();
        // Automatically run initial diagnosis on startup
        await runDiagnostics();

        // Check URL parameter for specific tab selection
        const urlParams = new URLSearchParams(window.location.search);
        const requestedTab = urlParams.get("tab");
        if (requestedTab) {
            const targetBtn = document.querySelector(`.tab-btn[data-tab="${requestedTab}"]`);
            if (targetBtn) {
                targetBtn.click();
            }
        }
    });
});
