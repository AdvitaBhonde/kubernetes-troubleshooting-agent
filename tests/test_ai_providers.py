"""Tests for AI reasoning providers and graceful fallback behavior."""

from unittest.mock import MagicMock
from app.ai.rules_provider import RuleBasedAIProvider
from app.ai.bedrock_provider import BedrockAIProvider
from app.ai.openai_provider import OpenAIProvider
from app.ai.factory import get_ai_provider
from app.models.schemas import Finding, DiagnosticSeverity, PodDiagnosticInfo


def test_rule_based_provider_analysis():
    provider = RuleBasedAIProvider()
    assert "Rule-Based" in provider.get_name()

    finding = Finding(
        id="f1",
        title="Container CrashLoopBackOff",
        severity=DiagnosticSeverity.CRITICAL,
        resource_kind="Pod",
        resource_name="order-service-xyz",
        namespace="default",
        evidence=["Exit code 1", "Database connection refused"],
        likely_cause="PostgreSQL database unreachable",
        confidence="High (Confirmed)",
        recommended_steps=["Check postgres service"],
        kubectl_commands=["kubectl logs order-service-xyz -n default --previous"],
        safe_remediation="Verify DB pod is up before restarting",
    )

    markdown = provider.analyze([finding], [], [], "default")
    assert "Confirmed Observations" in markdown
    assert "Root Cause Analysis & AI Hypotheses" in markdown
    assert "order-service-xyz" in markdown
    assert "kubectl logs order-service-xyz" in markdown


def test_bedrock_provider_graceful_fallback_without_credentials(monkeypatch):
    """When Bedrock client raises an error or is unavailable, fallback to rule-based analysis."""
    provider = BedrockAIProvider(region_name="us-east-1")

    # Mock client to simulate boto3 client failure
    mock_client = MagicMock()
    mock_client.invoke_model.side_effect = Exception("AWS Access Denied / No Credentials Found")
    provider._client = mock_client

    finding = Finding(
        id="f2",
        title="OOMKilled Container",
        severity=DiagnosticSeverity.CRITICAL,
        resource_kind="Pod",
        resource_name="worker-pod",
        namespace="default",
        evidence=["Exit code 137"],
        likely_cause="Exceeded 256Mi memory limit",
        confidence="High (Confirmed)",
        safe_remediation="Increase memory limit",
    )

    result = provider.analyze([finding], [], [], "default")
    # Verify fallback was invoked cleanly without throwing unhandled exception
    assert "AWS Bedrock invocation was unavailable" in result
    assert "Confirmed Observations" in result
    assert "worker-pod" in result


def test_openai_provider_fallback_without_api_key():
    provider = OpenAIProvider(api_key=None)
    finding = Finding(
        id="f3",
        title="Pending Pod",
        severity=DiagnosticSeverity.MEDIUM,
        resource_kind="Pod",
        resource_name="pending-pod",
        namespace="default",
        evidence=["0/3 nodes available"],
        likely_cause="Insufficient CPU",
        confidence="High (Confirmed)",
        safe_remediation="Scale nodes",
    )

    result = provider.analyze([finding], [], [], "default")
    assert "Confirmed Observations" in result
    assert "pending-pod" in result


def test_ai_provider_factory():
    assert isinstance(get_ai_provider("rules"), RuleBasedAIProvider)
    assert isinstance(get_ai_provider("bedrock"), BedrockAIProvider)
    assert isinstance(get_ai_provider("openai"), OpenAIProvider)
    assert isinstance(get_ai_provider("unknown"), RuleBasedAIProvider)
