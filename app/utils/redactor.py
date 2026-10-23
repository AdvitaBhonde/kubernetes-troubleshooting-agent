"""Sensitive data redaction and log sanitization utility.

Ensures credentials, tokens, secrets, private keys, and connection strings
are never leaked in diagnostic reports or forwarded to external LLMs.
"""

import re
from typing import Dict, Any, Union, List


class SensitiveDataRedactor:
    """Detects and redacts sensitive information from strings, logs, and structured objects."""

    PATTERNS = [
        # Private keys and certificates
        (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----", re.MULTILINE), "[REDACTED_PRIVATE_KEY]"),
        (re.compile(r"-----BEGIN CERTIFICATE-----[\s\S]*?-----END CERTIFICATE-----", re.MULTILINE), "[REDACTED_CERTIFICATE]"),

        # AWS Access Keys & Secret Keys
        (re.compile(r"\b(AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}\b"), "[REDACTED_AWS_ACCESS_KEY]"),
        (re.compile(r"(?i)(aws_secret_access_key|aws_session_token)\s*[:=]\s*['\"]?([a-zA-Z0-9/+=]{40,})['\"]?"), r"\1=[REDACTED_AWS_SECRET]"),

        # JWT and Bearer tokens
        (re.compile(r"Bearer\s+ey[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}"), "Bearer [REDACTED_JWT_TOKEN]"),
        (re.compile(r"\bey[a-zA-Z0-9_-]{15,}\.[a-zA-Z0-9_-]{15,}\.[a-zA-Z0-9_-]{10,}\b"), "[REDACTED_JWT]"),

        # Generic Passwords, API Keys, Secrets in key-value format (handles db_password, app_secret, etc.)
        (
            re.compile(
                r"(?i)\b([a-zA-Z0-9_-]*(?:password|passwd|pwd|pass|secret|token|api_key|apikey|client_secret|auth_token|access_token|private_key))\b\s*[:=]\s*['\"]?([^'\"\s\r\n;]{3,})['\"]?"
            ),
            r"\1=[REDACTED_SECRET]",
        ),

        # Database URLs with embedded passwords
        (
            re.compile(r"(?i)(postgres|postgresql|mysql|mongodb|redis|amqp|mssql)://([^:]+):([^@]+)@"),
            r"\1://\2:[REDACTED_PASSWORD]@",
        ),

        # Kubernetes ServiceAccount token files / strings
        (re.compile(r"/var/run/secrets/kubernetes.io/serviceaccount/token"), "[K8S_SA_TOKEN_PATH]"),

        # Prompt Injection Protection in untrusted logs
        (
            re.compile(
                r"(?i)(ignore\s+previous\s+instructions|system\s+prompt\s+override|disregard\s+all\s+prior\s+instructions|you\s+are\s+now\s+a\s+DAN)",
                re.MULTILINE,
            ),
            "[SANITIZED_UNTRUSTED_LOG_PROMPT_INJECTION_ATTEMPT]",
        ),
    ]

    @classmethod
    def redact_text(cls, text: str) -> str:
        """Sanitizes raw text string by masking recognized sensitive patterns."""
        if not text or not isinstance(text, str):
            return text
        sanitized = text
        for pattern, replacement in cls.PATTERNS:
            sanitized = pattern.sub(replacement, sanitized)
        return sanitized

    @classmethod
    def sanitize(cls, data: Union[str, Dict[str, Any], List[Any], Any]) -> Any:
        """Recursively traverses dictionaries, lists, and strings to sanitize content."""
        if isinstance(data, str):
            return cls.redact_text(data)
        elif isinstance(data, dict):
            clean_dict = {}
            for k, v in data.items():
                # If key itself hints at a secret or credential, mask value directly
                if any(sec in k.lower() for sec in ["secret", "password", "passwd", "pass", "pwd", "token", "credential", "private_key", "auth"]):
                    clean_dict[k] = "[REDACTED_SENSITIVE_FIELD]"
                else:
                    clean_dict[k] = cls.sanitize(v)
            return clean_dict
        elif isinstance(data, list):
            return [cls.sanitize(item) for item in data]
        return data


redactor = SensitiveDataRedactor()
