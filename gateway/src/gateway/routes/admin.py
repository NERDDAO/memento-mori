"""Admin routes — guarded by X-Admin-Api-Key header.

Used by NPC operators (humans running bonfires-ai) to mint long-lived JWTs
for NPC agents. Each NPC that connects to the memento engine via MCP needs
a JWT whose ``sub`` claim is the NPC's KG UUID — the middleware reads the
JWT, stashes the UUID in the ``_current_identity`` ContextVar, and every
tool call routes through the KG capability gate using that identity.

Not callable by players. Not callable without the admin key. Fails closed
when ``ENGINE_ADMIN_KEY`` is unset.
"""

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from gateway.engine_auth import admin_key_valid, sign_jwt


router = APIRouter(prefix="/admin", tags=["admin"])


class IssueNpcJwtRequest(BaseModel):
    npc_id: str = Field(..., min_length=1, max_length=128, description="KG UUID of the NPC entity")
    npc_name: str = Field("", max_length=100, description="Display name, for debugging")
    ttl_days: int = Field(365, ge=1, le=3650, description="Token lifetime in days")


class IssueNpcJwtResponse(BaseModel):
    jwt: str
    npc_id: str
    expires_in_days: int


@router.post("/npc-jwt", response_model=IssueNpcJwtResponse)
async def issue_npc_jwt(
    req: IssueNpcJwtRequest,
    x_admin_api_key: str = Header("", alias="X-Admin-Api-Key"),
) -> IssueNpcJwtResponse:
    """Mint a JWT for an NPC so its bonfires-ai instance can call /mcp.

    The returned token should be stored in bonfires-ai's ``agentenvvars``
    collection as ``{agentId: <npc.agentId>, key: "MEMENTO_JWT", value: <jwt>}``.
    When the NPC's MCP client loads, the ``apiKey`` field of the
    ``memento-engine`` McpTool doc resolves to this per-NPC JWT.
    """
    if not admin_key_valid(x_admin_api_key):
        raise HTTPException(status_code=401, detail="invalid admin api key")

    extra = {"name": req.npc_name} if req.npc_name else None
    token = sign_jwt(
        req.npc_id,
        type="npc",
        ttl_seconds=req.ttl_days * 86400,
        extra_claims=extra,
    )
    return IssueNpcJwtResponse(
        jwt=token,
        npc_id=req.npc_id,
        expires_in_days=req.ttl_days,
    )
