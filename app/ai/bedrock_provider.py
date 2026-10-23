"""AWS Bedrock AI Provider with graceful fallback to rule-based analysis.

Interacts with AWS Bedrock Runtime using boto3, applying strict log redaction
and ensuring fallback to the local engine if AWS credentials are not present.
"""

import json
from typing import List, Optional
from app.ai.provider import BaseAIProvider
from app.ai.rules_provider import RuleBasedAIProvider
from app.core.config import settings
from app.core.logging import logger
from app.models.schemas import Finding, PodDiagnosticInfo, EventInfo
from app.utils.redactor import redactor


class BedrockAIProvider(BaseAIProvider):
    """Integrates with AWS Bedrock Foundation Models (e.g. Claude 3, Titan) for Kubernetes diagnosis."""

    def __init__(self, region_name: Optional[str] = None, model_id: Optional[str] = None):
        self.region_name = region_name or settings.aws_region
        self.model_id = model_id or settings.bedrock_model_id
        self.fallback_provider = RuleBasedAIProvider()
        self._client = None

    def get_name(self) -> str:
        return f"AWS Bedrock ({self.model_id})"

    def _get_client(self):
        """Lazy initialization of boto3 Bedrock client."""
        if self._client is None:
            try:
                import boto3
                # boto3 automatically discovers AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY,
                # ~/.aws/credentials, or IAM Roles. Never hardcoded.
                self._client = boto3.client("bedrock-runtime", region_name=self.region_name)
            except Exception as e:
                logger.warning(f"Could not initialize boto3 bedrock client: {e}")
                self._client = False
        return self._client if self._client is not False else None

    def analyze(
        self,
        findings: List[Finding],
        pods: List[PodDiagnosticInfo],
        events: List[EventInfo],
        namespace: str,
    ) -> str:
        client = self._get_client()
        if not client:
            logger.info("Bedrock client unavailable. Falling back seamlessly to local Rule-Based engine.")
            return self.fallback_provider.analyze(findings, pods, events, namespace)

        # Build redacted payload for Bedrock LLM
        prompt = self._build_prompt(findings, pods, events, namespace)

        try:
            # Handle Anthropic Claude format on Bedrock
            if "anthropic.claude" in self.model_id:
                body = json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 1500,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.2,
                })
            else:
                # Amazon Titan format
                body = json.dumps({
                    "inputText": prompt,
                    "textGenerationConfig": {
                        "maxTokenCount": 1200,
                        "temperature": 0.2,
                    }
                })

            response = client.invoke_model(
                modelId=self.model_id,
                body=body,
                contentType="application/json",
                accept="application/json",
            )
            response_body = json.loads(response["body"].read())

            if "anthropic.claude" in self.model_id:
                content = response_body.get("content", [{}])[0].get("text", "")
            else:
                content = response_body.get("results", [{}])[0].get("outputText", "")

            return redactor.redact_text(content)

        except Exception as e:
            logger.warning(f"AWS Bedrock invocation failed ({e}). Reverting to rule-based analysis.")
            fallback_text = self.fallback_provider.analyze(findings, pods, events, namespace)
            return f"> [!WARNING]\n> AWS Bedrock invocation was unavailable ({str(e)}). Displaying local rule-based diagnostic analysis:\n\n{fallback_text}"

    def _build_prompt(
        self,
        findings: List[Finding],
        pods: List[PodDiagnosticInfo],
        events: List[EventInfo],
        namespace: str,
    ) -> str:
        """Constructs an instruction-guarded, redacted prompt."""
        evidence_summary = []
        for f in findings:
            evidence_summary.append(
                f"- Resource: {f.resource_kind}/{f.resource_name}\n"
                f"  Issue: {f.title} (Severity: {f.severity.value})\n"
                f"  Observed Evidence: {'; '.join(f.evidence)}\n"
                f"  Likely Cause: {f.likely_cause}"
            )

        prompt = (
            "You are an expert Kubernetes reliability engineer. Analyze the following cluster findings for namespace: "
            f"'{namespace}'.\n\n"
            "STRICT GUIDELINES:\n"
            "1. Base your diagnosis strictly on the provided evidence. DO NOT invent logs, pod names, or conditions.\n"
            "2. Distinguish clearly between Confirmed Observations and Hypotheses.\n"
            "3. If evidence is insufficient to be 100% certain, state your uncertainty clearly.\n"
            "4. Provide practical, safe troubleshooting steps and safe kubectl commands.\n"
            "5. Remind the operator that manual verification is required before making destructive changes.\n\n"
            "DIAGNOSTIC EVIDENCE:\n"
            + redactor.redact_text("\n".join(evidence_summary))
            + "\n\nProvide your analysis formatted in clean Markdown."
        )
        return prompt
