from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SettingsForm(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    gost_api_url: str | None = Field(default=None, max_length=500)
    gost_api_username: str | None = Field(default=None, max_length=255)
    gost_api_password: str | None = Field(default=None, max_length=255)
    test_endpoint: str = Field(min_length=8, max_length=500)
    egress_ip_endpoint: str = Field(min_length=8, max_length=500)
    default_timeout_ms: int = Field(ge=500, le=60000)
    polling_interval_sec: int = Field(ge=10, le=86400)
    max_concurrent_checks: int = Field(ge=1, le=100)
    degrade_latency_ms: int = Field(ge=100, le=60000)

    @field_validator("gost_api_url", "gost_api_username", "gost_api_password")
    @classmethod
    def empty_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("gost_api_url", "test_endpoint", "egress_ip_endpoint")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return value
