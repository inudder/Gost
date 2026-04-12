from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class NodeForm(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=255)
    protocol: str = Field(default="socks5", min_length=1, max_length=50)
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    username: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, max_length=255)
    notes: str | None = None
    tags: str | None = None
    enabled: bool = True
    test_url_override: str | None = Field(default=None, max_length=500)
    timeout_override_ms: int | None = Field(default=None, ge=500, le=60000)

    @field_validator("protocol")
    @classmethod
    def normalize_protocol(cls, value: str) -> str:
        return value.lower()

    @field_validator("username", "password", "notes", "tags", "test_url_override")
    @classmethod
    def empty_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("test_url_override")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return value
