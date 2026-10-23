"""Application configuration settings for Kubernetes Troubleshooting Agent."""

import os
from typing import List, Optional
from pydantic import BaseModel, Field


class Settings(BaseModel):
    app_name: str = "AI-Powered Kubernetes Troubleshooting Agent"
    app_version: str = "1.0.0"
    debug: bool = Field(default_factory=lambda: os.getenv("DEBUG", "false").lower() in ("true", "1", "yes"))
    
    # Cluster configuration
    kubeconfig_path: Optional[str] = Field(default_factory=lambda: os.getenv("KUBECONFIG"))
    in_cluster: bool = Field(default_factory=lambda: os.getenv("KUBERNETES_SERVICE_HOST") is not None)
    demo_mode: bool = Field(default_factory=lambda: os.getenv("DEMO_MODE", "false").lower() in ("true", "1", "yes"))
    default_namespace: str = Field(default_factory=lambda: os.getenv("DEFAULT_NAMESPACE", "default"))
    
    # Limits for collection safety
    max_log_lines: int = Field(default_factory=lambda: int(os.getenv("MAX_LOG_LINES", "150")))
    max_events: int = Field(default_factory=lambda: int(os.getenv("MAX_EVENTS", "50")))
    
    # AI / LLM Provider configuration
    # Options: 'rules' (default offline), 'bedrock', 'openai'
    ai_provider: str = Field(default_factory=lambda: os.getenv("AI_PROVIDER", "rules").lower())
    
    # AWS Bedrock settings (optional)
    aws_region: str = Field(default_factory=lambda: os.getenv("AWS_REGION", "us-east-1"))
    bedrock_model_id: str = Field(
        default_factory=lambda: os.getenv(
            "BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0"
        )
    )
    
    # OpenAI settings (optional)
    openai_api_key: Optional[str] = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    openai_model: str = Field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    
    # CORS
    cors_origins: List[str] = ["*"]


settings = Settings()
