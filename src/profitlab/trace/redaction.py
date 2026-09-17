"""Redact before persistence; reuse the same policy at presentation boundaries."""
import re
from collections.abc import Mapping
from urllib.parse import quote

from pydantic import BaseModel, SecretStr


class Redactor:
    def __init__(self, secrets=()):
        self.secrets = sorted({variant for secret in secrets if secret
                               for variant in (secret, quote(secret, safe=''))},
                              key=len, reverse=True)

    def text(self, value: str) -> str:
        for secret in self.secrets:
            value = value.replace(secret, '[REDACTED]')
        value = re.sub(r'(?i)(https?://)[^\s/@]+:[^\s/@]+@', r'\1[REDACTED]@', value)
        value = re.sub(r'(?i)(bearer\s+)[^\s,;"\']+', r'\1[REDACTED]', value)
        value = re.sub(r'(?i)((?:api[_-]?key|token|password|secret)=)[^&\s]+',
                       r'\1[REDACTED]', value)
        return value

    def __call__(self, value):
        if isinstance(value, SecretStr):
            return '[REDACTED]'
        if isinstance(value, BaseModel):
            value = value.model_dump(mode='json')
        if isinstance(value, Mapping):
            return {self.text(str(key)): '[REDACTED]' if re.search(
                r'(?i)authorization|api[_-]?key|cookie|password|secret|access[_-]?token',
                str(key)) else self(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [self(item) for item in value]
        if isinstance(value, str):
            return self.text(value)
        return value
