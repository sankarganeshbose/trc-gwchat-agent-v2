"""AgentCore Runtime entrypoint (HTTP protocol; POST /invocations, GET /ping on port 8080 are provided by BedrockAgentCoreApp).

Runtime config assumptions: inbound auth = CUSTOM_JWT (Entra ID); `Authorization` is in the request-header allow-list so it can be propagated to the Gateway.
"""
from __future__ import annotations

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from pydantic import ValidationError

from .agent import TrcAgentService
from .config import get_settings
from .logging import configure_logging
from .models.schemas import GWChatRequest, GWChatResponse, ResponseStatus
from .orchestration.gateway import StrandsGatewayConnector

settings = get_settings()
configure_logging(settings.log_level)
app = BedrockAgentCoreApp()
service = TrcAgentService(settings, StrandsGatewayConnector(settings))


@app.entrypoint
async def invoke(payload: dict, context) -> dict:
    headers = {k.lower(): v for k, v in (getattr(context, "request_headers", None) or {}).items()}
    # In production, user_id MUST come from the validated JWT claim, not from the payload (payload value is overwritten when a token is present).
    try:
        req = GWChatRequest.model_validate({**payload, "session_id": payload.get("session_id") or getattr(context, "session_id", None) or ""})
    except ValidationError as exc:
        return GWChatResponse(request_id="invalid", session_id="invalid", intent="INVALID_REQUEST", status=ResponseStatus.ERROR,
                              message="The request was not valid: " + "; ".join(sorted({str(e["loc"][-1]) for e in exc.errors()})),
                              warnings=["INVALID_REQUEST"]).model_dump(mode="json")
    resp = await service.handle(req, inbound_authorization=headers.get("authorization"))
    return resp.model_dump(mode="json")


if __name__ == "__main__":
    app.run()
