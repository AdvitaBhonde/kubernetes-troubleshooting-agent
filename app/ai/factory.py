"""AI Provider factory for dynamic selection of reasoning engines."""

from typing import Optional
from app.ai.provider import BaseAIProvider
from app.ai.rules_provider import RuleBasedAIProvider
from app.ai.bedrock_provider import BedrockAIProvider
from app.ai.openai_provider import OpenAIProvider
from app.core.config import settings


def get_ai_provider(provider_name: Optional[str] = None) -> BaseAIProvider:
    """Returns an AI provider instance based on request or global settings."""
    choice = (provider_name or settings.ai_provider or "rules").lower().strip()

    if choice == "bedrock":
        return BedrockAIProvider()
    elif choice == "openai":
        return OpenAIProvider()
    else:
        return RuleBasedAIProvider()
