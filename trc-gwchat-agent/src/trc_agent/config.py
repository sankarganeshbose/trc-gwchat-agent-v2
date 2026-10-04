"""Agent runtime configuration (env-driven; secrets injected by AgentCore Identity / Secrets Manager)."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TRC_AGENT_", env_file=".env", extra="ignore")

    # ── AgentCore Gateway (MCP) ─────────────────────────────────────────
    gateway_url: str = "https://<gateway-id>.gateway.bedrock-agentcore.<region>.amazonaws.com/mcp"  # PLACEHOLDER
    # propagate : forward the caller's inbound JWT (Entra ID) so the Gateway authorizes the END USER (recommended)
    # client_credentials : agent authenticates as itself (workload identity) — fallback / local
    # none : local dev against an unauthenticated FastMCP
    gateway_auth: Literal["propagate", "client_credentials", "none"] = "propagate"
    token_url: str | None = None
    client_id: str | None = None
    client_secret: str | None = Field(None, repr=False)
    scope: str | None = None
    gateway_connect_timeout_s: float = 10.0
    gateway_read_timeout_s: float = 30.0

    # ── model ───────────────────────────────────────────────────────────
    model_id: str = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"  # ASSUMPTION: align with GWChat model policy
    region: str = "us-east-1"
    temperature: float = 0.0
    max_tokens: int = 4096
    guardrail_id: str | None = None  # optional Bedrock Guardrail (PII / prompt-attack filters)
    guardrail_version: str = "DRAFT"

    # ── execution policy ────────────────────────────────────────────────
    turn_timeout_s: float = 90.0
    tool_timeout_s: float = 20.0
    write_tool_timeout_s: float = 30.0
    tool_retries: int = 1  # agent-level retries sit ON TOP of the MCP server's own bounded retries; keep small
    retry_backoff_s: float = 0.4
    max_tool_calls_per_turn: int = 24
    max_parallel_calls: int = 6
    write_actions_enabled: bool = False  # mirrors the MCP feature flag; both must be on
    ticket_ttl_s: int = 600
    ticket_secret: str = Field("dev-only-change-me", repr=False)  # HMAC key from Secrets Manager in AWS

    log_level: str = "INFO"


@lru_cache
def get_settings() -> AgentSettings:
    return AgentSettings()
