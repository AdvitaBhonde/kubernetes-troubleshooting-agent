"""Base AI Provider interface for Kubernetes diagnostic analysis."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

from app.models.schemas import Finding, PodDiagnosticInfo, EventInfo


class BaseAIProvider(ABC):
    """Abstract base class for all AI/LLM diagnostic reasoning providers."""

    @abstractmethod
    def get_name(self) -> str:
        """Returns the provider identification string."""
        pass

    @abstractmethod
    def analyze(
        self,
        findings: List[Finding],
        pods: List[PodDiagnosticInfo],
        events: List[EventInfo],
        namespace: str,
    ) -> str:
        """Generates comprehensive markdown troubleshooting analysis.

        Must clearly separate confirmed observations from AI hypotheses.
        """
        pass
