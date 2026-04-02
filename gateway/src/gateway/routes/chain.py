# gateway/src/gateway/routes/chain.py
"""Chain routes — proxy reads from MUD indexer."""

from fastapi import APIRouter, Path, HTTPException
from gateway.chain_client import fetch_chain_record, ALLOWED_TABLES

router = APIRouter()


@router.get("/chain/{table}/{entity_id}")
async def get_chain_record(
    table: str = Path(...),
    entity_id: str = Path(...),
):
    """Fetch onchain record from MUD indexer for a given table and entity ID."""
    if table not in ALLOWED_TABLES:
        raise HTTPException(status_code=400, detail=f"Unknown table: {table}. Allowed: {', '.join(sorted(ALLOWED_TABLES))}")

    data = await fetch_chain_record(table, entity_id)
    if data is None:
        raise HTTPException(status_code=404, detail="No onchain record found")

    return {"table": table, "id": entity_id, "data": data}
