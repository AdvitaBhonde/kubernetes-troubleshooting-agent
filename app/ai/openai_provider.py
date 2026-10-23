"""OpenAI / Compatible LLM Provider with fallback support."""

import json
from typing import List, Optional
from app.ai.provider import BaseAIProvider
from app.ai.rules_provider import RuleBasedAIProvider
from app.core.config import settings
from app.core.logging import logger
from app.models.schemas import Finding, PodDiagnosticInfo, EventInfo
from app.utils.redactor import redactor


class OpenAIProvider(BaseAIProvider):
    """Generic OpenAI-compatible LLM Provider."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.openai_model
        self.fallback = RuleBasedAIProvider()

    def get_name(self) -> str:
        return f"OpenAI ({self.model})"

    def analyze(
        self,
        findings: List[Finding],
        pods: List[PodDiagnosticInfo],
        events: List[EventInfo],
        namespace: str,
    ) -> str:
        if not self.api_key:
            logger.info("OpenAI API key not configured. Falling back to local Rule-Based engine.")
            return self.fallback.analyze(findings, pods, events, namespace)

        try:
            import requests

            evidence_summary = [
                f"- Resource: {f.resource_kind}/{f.resource_name} | Issue: {f.title} ({f.severity.value}) | Evidence: {'; '.join(f.evidence)}"
                for f in findings
            ]

            prompt = (
                f"You are an expert Kubernetes reliability engineer analyzing namespace '{namespace}'.\n"
                "Rules:\n"
                "- Only use the provided evidence. Do not hallucinate resources.\n"
                "- Clearly separate Confirmed Observations from Probable Hypotheses.\n"
                "- Provide safe, read-only troubleshooting kubectl commands.\n\n"
                "Evidence:\n" + "\n".join(evidence_summary)
            )

            res = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                },
                timeout=15,
            )
            if res.status_code == 200:
                data = res.json()
                text = data["choices"][0]["message"]["content"]
                return redactor.redact_text(text)
            else:
                logger.warning(f"OpenAI API responded with {res.status_code}: {res.text}")
                return self.fallback.analyze(findings, pods, events, namespace)
        except Exception as e:
            logger.warning(f"OpenAI call failed ({e}). Reverting to rule-based.")
            return self.fallback.analyze(findings, pods, events, namespace)
