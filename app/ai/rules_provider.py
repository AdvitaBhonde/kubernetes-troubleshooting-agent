"""Local, offline, deterministic Rule-Based AI Provider.

Produces high-fidelity root cause analyses without external cloud dependencies
or API tokens, rigorously separating confirmed facts from hypotheses.
"""

from typing import List
from app.ai.provider import BaseAIProvider
from app.models.schemas import Finding, PodDiagnosticInfo, EventInfo, DiagnosticSeverity


class RuleBasedAIProvider(BaseAIProvider):
    """Local offline provider that transforms diagnostic observations into an actionable report."""

    def get_name(self) -> str:
        return "Local Rule-Based Engine (Zero-Cost / Offline Mode)"

    def analyze(
        self,
        findings: List[Finding],
        pods: List[PodDiagnosticInfo],
        events: List[EventInfo],
        namespace: str,
    ) -> str:
        if not findings:
            return (
                "### Diagnostic Summary\n\n"
                f"No critical or warning anomalies were detected in namespace **{namespace}**.\n\n"
                "- All analyzed pods are currently running and passing health checks.\n"
                "- Deployments have satisfied their desired replica criteria.\n"
                "- Services have valid, active backing endpoints."
            )

        critical_count = sum(1 for f in findings if f.severity == DiagnosticSeverity.CRITICAL)
        high_count = sum(1 for f in findings if f.severity == DiagnosticSeverity.HIGH)
        medium_count = sum(1 for f in findings if f.severity == DiagnosticSeverity.MEDIUM)

        lines = [
            "### AI Diagnostic Summary & Root Cause Evaluation",
            "",
            f"**Target Namespace:** `{namespace}` | **Provider:** Local Rule-Based Engine",
            f"**Severity Breakdown:** {critical_count} Critical, {high_count} High, {medium_count} Medium",
            "",
            "---",
            "#### 1. Confirmed Observations (Direct Diagnostic Facts)",
            "",
        ]

        for idx, f in enumerate(findings, 1):
            lines.append(f"**[{idx}] {f.title}** (`{f.severity.value}`)")
            lines.append(f"- **Target Resource:** `{f.resource_kind}/{f.resource_name}` in namespace `{f.namespace}`")
            lines.append(f"- **Confirmed Fact:** {f.evidence[0]}")
            if len(f.evidence) > 1:
                lines.append(f"- **Supporting Evidence:** {f.evidence[1]}")
            lines.append("")

        lines.extend([
            "---",
            "#### 2. Root Cause Analysis & AI Hypotheses",
            "> [!NOTE]",
            "> Observations listed above are verified facts from cluster metrics and logs. Hypotheses below represent probable root causes requiring manual verification before destructive actions.",
            "",
        ])

        for idx, f in enumerate(findings, 1):
            lines.append(f"##### Finding #{idx}: {f.title}")
            lines.append(f"- **Likely Cause:** {f.likely_cause}")
            lines.append(f"- **Confidence:** `{f.confidence}`")
            lines.append(f"- **Safe Remediation:** {f.safe_remediation}")
            lines.append("")

        lines.extend([
            "---",
            "#### 3. Recommended Remediation Runbook",
            "Execute the following read-only commands first to inspect active cluster states before making changes:",
            "",
            "```bash",
        ])

        # Aggregate unique kubectl commands
        all_cmds = []
        for f in findings:
            for cmd in f.kubectl_commands:
                if cmd not in all_cmds:
                    all_cmds.append(cmd)

        for cmd in all_cmds[:6]:
            lines.append(cmd)

        lines.extend([
            "```",
            "",
            "> [!IMPORTANT]",
            "> All remediation steps must be reviewed by an authorized cluster operator. The troubleshooting agent performs only read-only operations.",
        ])

        return "\n".join(lines)
