"""Environment-driven configuration for the FastMCP server. Secrets arrive as env vars injected from
AWS Secrets Manager / AgentCore Identity at deploy time; nothing sensitive is stored in code or images."""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TRC_MCP_", env_file=".env", extra="ignore")

    # ── backend selection ───────────────────────────────────────────────
    backend: Literal["stub", "http"] = "stub"  # ASSUMPTION: real APIs not yet wired -> default to stub
    onprem_base_url: str = "https://trc-api.onprem.guidewell.example"  # PLACEHOLDER
    connect_timeout_s: float = 3.0
    read_timeout_s: float = 5.0  # per attempt; worst case 3 attempts + backoff stays under the agent's 20 s tool timeout
    write_timeout_s: float = 10.0  # per attempt for POST (processing time on-prem)
    max_retries: int = 2
    retry_backoff_s: float = 0.25
    breaker_failure_threshold: int = 5
    breaker_reset_s: float = 30.0
    ca_bundle: str | None = None  # path to the GuideWell private CA bundle
    # Optional per-operation overrides, e.g. {"GET_MEMBER": "GET /api/v2/trc/members/{memberId}"}
    endpoint_overrides_json: str = "{}"

    # ── on-prem auth (ASSUMPTION: OAuth2 client-credentials against Entra ID / GuideWell STS) ──
    token_url: str | None = None
    client_id: str | None = None
    client_secret: str | None = Field(None, repr=False)
    scope: str = "api://trc-onprem/.default"

    # ── inbound identity ────────────────────────────────────────────────
    require_auth: bool = True
    trust_upstream_jwt: bool = True  # AgentCore Gateway/Runtime authorizer already validated the JWT
    user_header: str = "x-gw-user-id"  # fallback when Gateway forwards identity as a header
    write_tools_enabled: bool = False  # feature flag: expose transactional tools

    # ── limits ──────────────────────────────────────────────────────────
    max_page_size: int = 50
    max_bulk_resend: int = 25
    max_validation_batch: int = 200

    log_level: str = "INFO"
    stub_as_of: str = "2026-08-05"  # deterministic 'today' for stub data

    @field_validator("endpoint_overrides_json")
    @classmethod
    def _json(cls, v: str) -> str:
        json.loads(v)
        return v

    @property
    def endpoint_overrides(self) -> dict[str, str]:
        return json.loads(self.endpoint_overrides_json)


@lru_cache
def get_settings() -> Settings:
    return Settings()
